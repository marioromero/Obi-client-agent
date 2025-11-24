import re
import json
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import create_engine, text, or_
from typing import List

import models
import schemas
from database import get_db
from config import settings
from sync_service import scan_specific_connection, push_schema_to_cloud

# --- SEGURIDAD ---
FORBIDDEN_KEYWORDS = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE', 'ALTER', 'GRANT', 'REVOKE', 'CREATE', 'EXEC']
FORBIDDEN_PATTERNS = [r";", r"--", r"\/\*"]

app = FastAPI(title="Agente de Cliente OBI Multi-BD", version="2.2.0")

# --- CONFIGURACIÓN CORS BLINDADA PARA DESARROLLO ---
# Permitimos ["*"] para que acepte peticiones desde localhost:5173, 5174, etc.
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # Acepta cualquier origen
    allow_credentials=True,
    allow_methods=["*"],   # Acepta GET, POST, PUT, DELETE, OPTIONS
    allow_headers=["*"],   # Acepta cualquier header
)

# --- UTILIDADES ---
def validate_sql_safety(sql: str):
    sql_normalized = sql.strip().upper()
    if not sql_normalized.startswith("SELECT"): raise HTTPException(403, "Solo SELECT.")
    for k in FORBIDDEN_KEYWORDS:
        if k in sql_normalized: raise HTTPException(403, f"Prohibido: {k}")
    return True

def get_any_valid_connection_url():
    connections = settings.get_connections_config()
    if not connections: raise Exception("Sin conexiones.")
    first_key = next(iter(connections))
    return settings.get_db_url_from_config(connections[first_key])

# --- ENDPOINTS ---

@app.get("/")
async def root():
    return {"status": True, "message": "OBI Agent Online (Standard Response)", "data": None}

@app.get("/api/v1/connections", response_model=schemas.StandardResponse[List[dict]])
async def list_connections():
    """
    Lista las conexiones disponibles.
    """
    conns = settings.get_connections_config()
    data = [{"key": k, "dbname": v.get("dbname"), "type": v.get("type")} for k, v in conns.items()]

    return {
        "status": True,
        "message": "Conexiones recuperadas exitosamente.",
        "data": data
    }

# --- EJECUCIÓN ---
@app.post("/api/v1/execute", response_model=schemas.StandardResponse[schemas.QueryExecuteResponse])
async def execute_query(query: schemas.QueryExecuteRequest):
    validate_sql_safety(query.sql)
    client_engine = None
    try:
        url = get_any_valid_connection_url()
        client_engine = create_engine(url)
        with client_engine.connect() as connection:
            result = connection.execute(text(query.sql))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]

            data = schemas.QueryExecuteResponse(columns=columns, rows=rows, row_count=len(rows))

            return {
                "status": True,
                "message": "Consulta SQL ejecutada exitosamente.",
                "data": data
            }
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    finally:
        if client_engine: client_engine.dispose()

# --- GESTIÓN DE ESQUEMAS ---

@app.post("/api/v1/schema/scan", response_model=schemas.StandardResponse[schemas.SchemaDraftResponse])
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

    return {
        "status": True,
        "message": f"Escaneo de '{req.connection_key}' completado exitosamente.",
        "data": draft
    }

@app.get("/api/v1/schema/draft", response_model=schemas.StandardResponse[schemas.SchemaDraftResponse])
async def get_draft(connection_key: str = Query(...), db: AsyncSession = Depends(get_db)):
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()

    if not draft: raise HTTPException(404, detail=f"No hay borrador para '{connection_key}'.")

    return {
        "status": True,
        "message": "Borrador recuperado exitosamente.",
        "data": draft
    }

@app.put("/api/v1/schema/draft", response_model=schemas.StandardResponse[schemas.SchemaDraftResponse])
async def update_draft(draft_data: schemas.SchemaDraftUpdate, connection_key: str = Query(...), db: AsyncSession = Depends(get_db)):
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()
    if not draft: raise HTTPException(404, detail="No hay borrador para editar.")

    draft.structure_json = draft_data.structure_json
    await db.commit()
    await db.refresh(draft)

    return {
        "status": True,
        "message": "Borrador actualizado localmente.",
        "data": draft
    }

@app.post("/api/v1/schema/publish", response_model=schemas.StandardResponse[dict])
async def publish_schema(req: schemas.ScanRequest, db: AsyncSession = Depends(get_db)):
    # 1. Buscar el borrador
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == req.connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(404, detail="Sin borrador para publicar.")

    try:
        # 2. Llamar al servicio y CAPTURAR el retorno (el mapa de IDs)
        # cloud_refs será un dict: {"tabla": 15, ...}
        cloud_refs = push_schema_to_cloud(draft.structure_json, req.connection_key)

        # 3. Guardar los IDs en la base de datos local
        draft.cloud_refs_json = json.dumps(cloud_refs) # Guardamos como texto JSON
        draft.is_synced = True

        await db.commit()

        return {
            "status": True,
            "message": "Sincronización completa. IDs de nube vinculados.",
            "data": {
                "connection_key": req.connection_key,
                "synced": True,
                "tables_mapped": len(cloud_refs) # Dato útil para debug
            }
        }
    except Exception as e:
        raise HTTPException(500, detail=f"Error al publicar: {str(e)}")


# --- GESTIÓN DE REPORTES ---

@app.post("/api/v1/reports/", response_model=schemas.StandardResponse[schemas.Report])
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

    return {
        "status": True,
        "message": "Reporte guardado exitosamente.",
        "data": db_report
    }

@app.get("/api/v1/reports/", response_model=schemas.StandardResponse[List[schemas.Report]])
async def list_reports(
    current_user: str = Query(..., description="Email o ID del usuario"),
    current_role: str = Query(None, description="Rol del usuario"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    base_filters = [
        models.Report.scope == 'global',
        (models.Report.scope == 'personal') & (models.Report.user_identifier == current_user),
        models.Report.scope == 'role'
    ]
    query = select(models.Report).where(or_(*base_filters)).offset(skip).limit(limit).order_by(models.Report.created_at.desc())
    result = await db.execute(query)
    all_candidates = result.scalars().all()

    final_reports = []
    for r in all_candidates:
        if r.scope in ['global', 'personal']:
            r.scope_target = None
            final_reports.append(r)
            continue
        if r.scope == 'role':
            try:
                target_roles = json.loads(r.scope_target) if r.scope_target else []
                if not isinstance(target_roles, list): continue
                if current_role and current_role in target_roles:
                    r.scope_target = target_roles
                    final_reports.append(r)
            except json.JSONDecodeError: continue

    return {
        "status": True,
        "message": "Lista de reportes recuperada exitosamente.",
        "data": final_reports
    }