import re
import json
import requests
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, attributes
from sqlalchemy import create_engine, text, or_, delete
from typing import List

import models
import schemas
from database import get_db
from config import settings
from sync_service import scan_specific_connection, push_schema_to_cloud

# --- SEGURIDAD ---
FORBIDDEN_KEYWORDS = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE', 'ALTER', 'GRANT', 'REVOKE', 'CREATE', 'EXEC']
FORBIDDEN_PATTERNS = [r";", r"--", r"\/\*"]

app = FastAPI(title="Agente de Cliente OBI Multi-BD", version="2.3.0")

# --- CONFIGURACIÓN CORS ---
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- UTILIDADES ---
def validate_sql_safety(sql: str):
    """
    Valida que el SQL sea seguro para ejecutar.
    """
    sql_normalized = sql.strip().upper()
    if not sql_normalized.startswith("SELECT") and not sql_normalized.startswith("WITH"):
        # Permitimos WITH para CTEs comunes en analítica
        raise HTTPException(403, "Solo SELECT o CTEs permitidos.")

    for k in FORBIDDEN_KEYWORDS:
        pattern = rf'\b{k}\b'
        if re.search(pattern, sql_normalized):
            raise HTTPException(403, f"Prohibido: {k}")

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, sql):
            raise HTTPException(403, f"Patrón SQL no permitido detectado.")

    return True

def get_any_valid_connection_url():
    connections = settings.get_connections_config()
    if not connections: raise Exception("Sin conexiones.")
    first_key = next(iter(connections))
    return settings.get_db_url_from_config(connections[first_key])

# --- ENDPOINTS BASE ---

@app.get("/")
async def root():
    return {"status": True, "message": "OBI Agent Online (Dashboard Ready)", "data": None}

@app.get("/api/v1/connections", response_model=schemas.StandardResponse)
async def list_connections():
    conns = settings.get_connections_config()
    data = [{"key": k, "dbname": v.get("dbname"), "type": v.get("type")} for k, v in conns.items()]
    return {
        "status": True,
        "message": "Conexiones recuperadas.",
        "data": data
    }

# --- EJECUCIÓN ---
@app.post("/api/v1/execute", response_model=schemas.StandardResponse)
async def execute_query(query: schemas.QueryExecuteRequest):
    validate_sql_safety(query.sql)
    client_engine = None
    try:
        # NOTA: Aquí idealmente deberíamos seleccionar la conexión específica
        # basada en el contexto del dashboard, pero por ahora usamos la default válida.
        url = get_any_valid_connection_url()
        client_engine = create_engine(url)
        with client_engine.connect() as connection:
            result = connection.execute(text(query.sql))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]

            data = schemas.QueryExecuteResponse(columns=columns, rows=rows, row_count=len(rows))

            return {
                "status": True,
                "message": "Consulta ejecutada.",
                "data": data
            }
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    finally:
        if client_engine: client_engine.dispose()

# --- GESTIÓN DE ESQUEMAS ---

@app.post("/api/v1/schema/scan", response_model=schemas.StandardResponse)
async def scan_schema(req: schemas.ScanRequest, db: AsyncSession = Depends(get_db)):
    try:
        structure = scan_specific_connection(req.connection_key)
        structure_json = json.dumps(structure)
    except Exception as e:
        raise HTTPException(400, detail=str(e))

    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == req.connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()

    if not draft:
        draft = models.SchemaDraft(connection_key=req.connection_key, structure_json=structure_json, is_synced=False)
        db.add(draft)
    else:
        draft.structure_json = structure_json
        draft.is_synced = False

    await db.commit()
    await db.refresh(draft)

    return { "status": True, "message": "Escaneo completado.", "data": schemas.SchemaDraftResponse.model_validate(draft) }

@app.get("/api/v1/schema/draft", response_model=schemas.StandardResponse)
async def get_draft(connection_key: str = Query(...), db: AsyncSession = Depends(get_db)):
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()
    if not draft: raise HTTPException(404, detail=f"No hay borrador para '{connection_key}'.")
    return { "status": True, "message": "Borrador recuperado.", "data": schemas.SchemaDraftResponse.model_validate(draft) }

@app.put("/api/v1/schema/draft", response_model=schemas.StandardResponse)
async def update_draft(draft_data: schemas.SchemaDraftUpdate, connection_key: str = Query(...), db: AsyncSession = Depends(get_db)):
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()
    if not draft: raise HTTPException(404, detail="No hay borrador.")

    draft.structure_json = draft_data.structure_json
    draft.is_synced = False
    await db.commit()
    await db.refresh(draft)
    return { "status": True, "message": "Borrador actualizado.", "data": schemas.SchemaDraftResponse.model_validate(draft) }

@app.post("/api/v1/schema/publish", response_model=schemas.StandardResponse)
async def publish_schema(req: schemas.ScanRequest, db: AsyncSession = Depends(get_db)):
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == req.connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()
    if not draft: raise HTTPException(404, detail="Sin borrador.")

    try:
        cloud_refs = push_schema_to_cloud(draft.structure_json, req.connection_key)
        draft.cloud_refs_json = json.dumps(cloud_refs)
        draft.is_synced = True
        await db.commit()

        return {
            "status": True,
            "message": "Sincronización completa.",
            "data": { "connection_key": req.connection_key, "synced": True, "tables_mapped": len(cloud_refs) }
        }
    except Exception as e:
        raise HTTPException(500, detail=f"Error al publicar: {str(e)}")


# --- GESTIÓN DE DASHBOARDS (NUEVO) ---

@app.get("/api/v1/dashboards/", response_model=schemas.StandardResponse)
async def list_dashboards(
    current_user: str = Query(..., description="Email o ID del usuario"),
    db: AsyncSession = Depends(get_db)
):
    # Usar selectinload para cargar ansiosamente la relación reports y evitar MissingGreenlet
    query = select(models.Dashboard).options(
        selectinload(models.Dashboard.reports)
    ).where(models.Dashboard.user_identifier == current_user).order_by(models.Dashboard.created_at.desc())
    result = await db.execute(query)
    dashboards = result.scalars().all()
    # Convertir a Pydantic explícitamente para evitar error de serialización con Any
    data = [schemas.Dashboard.model_validate(d) for d in dashboards]
    return { "status": True, "message": "Dashboards recuperados.", "data": data }

@app.post("/api/v1/dashboards/", response_model=schemas.StandardResponse)
async def create_dashboard(
    dash_data: schemas.DashboardCreate,
    db: AsyncSession = Depends(get_db)
):
    new_dash = models.Dashboard(**dash_data.model_dump())
    db.add(new_dash)
    await db.commit()
    await db.refresh(new_dash)
    # Usar set_committed_value para evitar lazy loading y MissingGreenlet al serializar
    attributes.set_committed_value(new_dash, 'reports', [])
    return { "status": True, "message": "Dashboard creado.", "data": schemas.Dashboard.model_validate(new_dash) }

@app.put("/api/v1/dashboards/{dashboard_id}", response_model=schemas.StandardResponse)
async def update_dashboard(
    dashboard_id: int,
    dash_data: schemas.DashboardCreate,
    current_user: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    query = select(models.Dashboard).where(models.Dashboard.id == dashboard_id, models.Dashboard.user_identifier == current_user)
    result = await db.execute(query)
    dash = result.scalar_one_or_none()
    if not dash: raise HTTPException(404, "Dashboard no encontrado.")

    dash.title = dash_data.title
    dash.description = dash_data.description
    dash.layout_config = dash_data.layout_config
    dash.context_definition = dash_data.context_definition

    await db.commit()
    await db.refresh(dash)
    # Evitar error de lazy loading en respuesta
    attributes.set_committed_value(dash, 'reports', [])
    
    return { "status": True, "message": "Dashboard actualizado.", "data": schemas.Dashboard.model_validate(dash) }

@app.delete("/api/v1/dashboards/{dashboard_id}", response_model=schemas.StandardResponse)
async def delete_dashboard(
    dashboard_id: int,
    current_user: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    query = select(models.Dashboard).where(models.Dashboard.id == dashboard_id, models.Dashboard.user_identifier == current_user)
    result = await db.execute(query)
    dash = result.scalar_one_or_none()
    if not dash: raise HTTPException(404, "Dashboard no encontrado.")

    await db.delete(dash)
    await db.commit()
    return { "status": True, "message": "Dashboard eliminado.", "data": {"id": dashboard_id} }


# --- GESTIÓN DE REPORTES (INSTRUMENTOS) ---

@app.post("/api/v1/reports/", response_model=schemas.StandardResponse)
async def create_report(
    report_data: schemas.ReportCreate,
    db: AsyncSession = Depends(get_db)
):
    data = report_data.model_dump()
    if data.get('scope_target'):
        data['scope_target'] = json.dumps(data['scope_target'])
    else:
        data['scope_target'] = None

    db_report = models.Report(**data)
    db.add(db_report)
    await db.commit()
    await db.refresh(db_report)

    if db_report.scope_target:
        db_report.scope_target = json.loads(db_report.scope_target)

    return { "status": True, "message": "Instrumento creado.", "data": db_report }

@app.get("/api/v1/reports/", response_model=schemas.StandardResponse)
async def list_reports(
    current_user: str = Query(..., description="Usuario"),
    dashboard_id: int = Query(None, description="ID del Dashboard contenedor"),
    current_role: str = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    conditions = []
    if dashboard_id:
        # Si estamos dentro de un dashboard, mostrar sus items
        conditions.append(models.Report.dashboard_id == dashboard_id)
    else:
        # Si no, mostrar items sueltos (Librería) + RBAC
        base_filters = [
            models.Report.scope == 'global',
            (models.Report.scope == 'personal') & (models.Report.user_identifier == current_user),
            models.Report.scope == 'role'
        ]
        conditions.append(or_(*base_filters))
        conditions.append(models.Report.dashboard_id == None) # Solo huérfanos

    query = select(models.Report).where(*conditions).offset(skip).limit(limit).order_by(models.Report.created_at.desc())
    result = await db.execute(query)
    all_candidates = result.scalars().all()

    final_reports = []
    for r in all_candidates:
        if r.scope == 'role' and r.scope_target:
             try:
                target_roles = json.loads(r.scope_target)
                r.scope_target = target_roles
                if current_role and current_role not in target_roles and r.user_identifier != current_user:
                    continue
             except: pass
        final_reports.append(r)

    return { "status": True, "message": "Instrumentos recuperados.", "data": final_reports }

# --- NUEVO: ACTUALIZAR REPORTE (CHAT CONTINUO) ---
@app.put("/api/v1/reports/{report_id}", response_model=schemas.StandardResponse)
async def update_report(
    report_id: int,
    report_update: schemas.ReportCreate, # Reutilizamos el schema o crea uno Update específico si prefieres parciales
    current_user: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    # Verificar propiedad
    query = select(models.Report).where(models.Report.id == report_id)
    result = await db.execute(query)
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(404, "Instrumento no encontrado.")

    # Validación simple de propiedad (o si es global/colaborativo, ajusta aquí)
    if report.user_identifier != current_user and report.scope == 'personal':
         raise HTTPException(403, "No tienes permiso para editar este reporte.")

    # Actualizamos campos clave para el Chat
    report.sql_query = report_update.sql_query
    report.question = report_update.question
    report.conversation_id = report_update.conversation_id # ¡La memoria del chat!

    # Opcionales
    report.name = report_update.name
    report.type = report_update.type

    await db.commit()
    await db.refresh(report)

    return { "status": True, "message": "Instrumento actualizado.", "data": report }

@app.delete("/api/v1/reports/{report_id}", response_model=schemas.StandardResponse)
async def delete_report(
    report_id: int,
    current_user: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    query = select(models.Report).where(models.Report.id == report_id, models.Report.user_identifier == current_user)
    result = await db.execute(query)
    report = result.scalar_one_or_none()
    if not report: raise HTTPException(404, "Instrumento no encontrado.")

    await db.delete(report)
    await db.commit()
    return { "status": True, "message": "Instrumento eliminado.", "data": {"id": report_id} }

# --- CHAT / TRADUCCIÓN (NUEVO) ---

@app.post("/api/v1/chat/translate", response_model=schemas.StandardResponse)
async def translate_question(
    req: schemas.TranslateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Proxy inteligente que prepara el contexto granular y consulta a la API de IA (Laravel).
    """
    
    # 1. Preparar el payload base
    payload = {
        "question": req.question,
        "schema_table_ids": [],
        "schema_config": []
    }

    # 2. Resolver contexto desde Dashboard (Prioridad)
    if req.dashboard_id:
        query = select(models.Dashboard).where(models.Dashboard.id == req.dashboard_id)
        result = await db.execute(query)
        dash = result.scalar_one_or_none()
        
        if dash and dash.context_definition:
            try:
                context_list = json.loads(dash.context_definition)
                # context_list estructura esperada: [{"table_id": 1, "include_columns": [...]}, ...]
                
                for item in context_list:
                    t_id = item.get('table_id')
                    cols = item.get('include_columns', [])
                    
                    if t_id:
                        payload["schema_table_ids"].append(t_id)
                        
                        # Lógica de optimización solicitada:
                        # Si cols está vacío -> use_full_schema: false (solo defaults)
                        # Si cols tiene datos -> use_full_schema: false (solo esas columnas)
                        # En ambos casos enviamos la lista explícita (vacía o llena)
                        
                        config_entry = {
                            "table_id": t_id,
                            "use_full_schema": False, # Siempre false para forzar granularidad
                            "include_columns": cols
                        }
                        payload["schema_config"].append(config_entry)
                        
            except Exception as e:
                print(f"Error parseando contexto de dashboard: {e}")
                # Fallback: si falla el parseo, no enviamos config granular, solo IDs si se pudieron rescatar
                pass
    
    # 3. Fallback a IDs manuales si no hay dashboard o contexto (Legacy)
    if not payload["schema_table_ids"] and req.schema_table_ids:
        payload["schema_table_ids"] = req.schema_table_ids
        # No generamos schema_config aquí, asumimos comportamiento default del backend IA
    
    # 4. Validar antes de enviar
    if not payload["schema_table_ids"]:
         raise HTTPException(400, "No se seleccionaron tablas para el contexto (ni Dashboard ni manual).")

    # 5. Enviar a API Laravel
    api_url = settings.API_SERVICE_URL.rstrip('/')
    headers = {
        "Authorization": f"Bearer {settings.API_SERVICE_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        print(f"🤖 Enviando a IA: {json.dumps(payload)}")
        resp = requests.post(f"{api_url}/api/translate", json=payload, headers=headers)
        
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Error IA: {resp.text}")
            
        ai_data = resp.json()
        # Asumimos que la IA devuelve { data: { sql: "...", explanation: "..." } }
        
        return {
            "status": True,
            "message": "Traducción exitosa.",
            "data": {
                "sql": ai_data.get('data', {}).get('sql', '-- No SQL generated'),
                "explanation": ai_data.get('data', {}).get('explanation')
            }
        }

    except Exception as e:
        raise HTTPException(500, f"Fallo de comunicación con IA: {str(e)}")