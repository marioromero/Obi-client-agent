import re
import json
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import create_engine, text, or_

# Importamos las piezas del proyecto
import models
import schemas
from database import get_db
from config import settings
# Importamos los servicios de sincronización
# NOTA: Asegúrate que tu sync_service.py tenga estas funciones
from sync_service import scan_specific_connection, push_schema_to_cloud

# --- LISTAS DE SEGURIDAD ---
FORBIDDEN_KEYWORDS = [
    'DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE', 'ALTER', 'GRANT',
    'REVOKE', 'CREATE', 'EXEC', 'SHUTDOWN', 'MERGE', 'CALL'
]
FORBIDDEN_PATTERNS = [r";", r"--", r"\/\*"]

# 1. Creamos la aplicación FastAPI
app = FastAPI(title="Agente de Cliente OBI Multi-BD", version="2.1.0")


# --- FUNCIÓN DE SEGURIDAD ---
def validate_sql_safety(sql: str):
    """
    Valida que la consulta SQL sea segura (Confianza Cero).
    Solo permite consultas SELECT.
    """
    sql_normalized = sql.strip().upper()

    if not sql_normalized.startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operación no permitida. Solo se aceptan consultas SELECT."
        )

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operación no permitida. Palabra clave '{keyword}' detectada."
            )

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operación no permitida. Patrón '{pattern}' detectado."
            )

    return True

def get_any_valid_connection_url():
    """
    Obtiene una URL de conexión válida para ejecutar consultas cruzadas.
    """
    connections = settings.get_connections_config()
    if not connections:
        raise Exception("No se encontraron conexiones en connections.json")

    # Usamos la primera conexión disponible como punto de entrada
    first_key = next(iter(connections))
    return settings.get_db_url_from_config(connections[first_key])


# --- ENDPOINTS DE UTILIDAD ---

@app.get("/")
async def root():
    return {"status": "OBI Agent Online", "mode": "Professional RBAC Multi-BD"}

@app.get("/api/v1/connections")
async def list_connections():
    """
    Devuelve la lista de microservicios disponibles en connections.json.
    """
    conns = settings.get_connections_config()
    return [
        {"key": k, "dbname": v.get("dbname"), "type": v.get("type")}
        for k, v in conns.items()
    ]


# --- (FLUJO 2) ENDPOINT DE EJECUCIÓN SQL ---

@app.post("/api/v1/execute", response_model=schemas.QueryExecuteResponse)
async def execute_query(query: schemas.QueryExecuteRequest):
    """
    Ejecuta una consulta SQL de SOLO LECTURA.
    """
    validate_sql_safety(query.sql)

    client_engine = None
    try:
        url = get_any_valid_connection_url()
        client_engine = create_engine(url)

        with client_engine.connect() as connection:
            result = connection.execute(text(query.sql))

            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]
            row_count = len(rows)

            return schemas.QueryExecuteResponse(
                columns=columns,
                rows=rows,
                row_count=row_count
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error SQL: {str(e)}"
        )
    finally:
        if client_engine:
            client_engine.dispose()


# --- (FLUJO 1 - STAGING SEGMENTADO) GESTIÓN DE ESQUEMAS ---

@app.post("/api/v1/schema/scan", response_model=schemas.SchemaDraftResponse)
async def scan_schema(req: schemas.ScanRequest, db: AsyncSession = Depends(get_db)):
    """
    Escanea SOLO la conexión solicitada y guarda su borrador independiente.
    """
    try:
        # Usamos la función específica para Multi-BD
        structure = scan_specific_connection(req.connection_key)
        structure_json = json.dumps(structure)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == req.connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()

    if not draft:
        draft = models.SchemaDraft(
            connection_key=req.connection_key,
            structure_json=structure_json,
            is_synced=False
        )
        db.add(draft)
    else:
        draft.structure_json = structure_json
        draft.is_synced = False

    await db.commit()
    await db.refresh(draft)
    return draft

@app.get("/api/v1/schema/draft", response_model=schemas.SchemaDraftResponse)
async def get_draft(connection_key: str = Query(...), db: AsyncSession = Depends(get_db)):
    """
    Obtiene el borrador de una conexión específica.
    """
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail=f"No hay borrador para '{connection_key}'.")
    return draft

@app.put("/api/v1/schema/draft", response_model=schemas.SchemaDraftResponse)
async def update_draft(
    draft_data: schemas.SchemaDraftUpdate,
    connection_key: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Guarda la edición humana para una conexión específica.
    """
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="No hay borrador para editar.")

    draft.structure_json = draft_data.structure_json
    await db.commit()
    await db.refresh(draft)
    return draft

@app.post("/api/v1/schema/publish")
async def publish_schema(req: schemas.ScanRequest, db: AsyncSession = Depends(get_db)):
    """
    Publica el borrador de la conexión indicada a la nube.
    """
    query = select(models.SchemaDraft).where(models.SchemaDraft.connection_key == req.connection_key)
    result = await db.execute(query)
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(status_code=404, detail="Sin borrador.")

    try:
        # Pasamos la connection_key para que el servicio nombre bien el esquema
        push_schema_to_cloud(draft.structure_json, req.connection_key)

        draft.is_synced = True
        await db.commit()

        return {"message": "Sincronización exitosa", "status": "published", "key": req.connection_key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al publicar: {str(e)}")


# --- (FLUJO 3) GESTIÓN DE REPORTES (Multi-Rol Profesional) ---

@app.post("/api/v1/reports/", response_model=schemas.Report)
async def create_report(
    report_data: schemas.ReportCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Guarda un reporte. Serializa la lista de roles a JSON string.
    """
    data = report_data.model_dump()

    # Serializar la lista de roles a JSON string (Ej: '["Admin", "Ventas"]')
    if data.get('scope_target'):
        data['scope_target'] = json.dumps(data['scope_target'])
    else:
        data['scope_target'] = None

    db_report = models.Report(**data)
    db.add(db_report)
    await db.commit()
    await db.refresh(db_report)

    # Deserializar para devolver respuesta correcta a Pydantic
    if db_report.scope_target:
        db_report.scope_target = json.loads(db_report.scope_target)

    return db_report

@app.get("/api/v1/reports/", response_model=List[schemas.Report])
async def list_reports(
    current_user: str = Query(..., description="Email o ID del usuario actual"),
    current_role: str = Query(None, description="Rol del usuario actual"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    Lista reportes aplicando lógica de permisos (Scope) con soporte de Lista de Roles.
    """

    # 1. Traemos TODOS los reportes potenciales
    base_filters = [
        models.Report.scope == 'global',
        (models.Report.scope == 'personal') & (models.Report.user_identifier == current_user),
        models.Report.scope == 'role' # Traemos todos los de rol y filtramos abajo
    ]

    query = select(models.Report).where(or_(*base_filters)).offset(skip).limit(limit).order_by(models.Report.created_at.desc())
    result = await db.execute(query)
    all_candidates = result.scalars().all()

    final_reports = []

    for r in all_candidates:
        # A. Si es Global o Personal (y pasó el filtro SQL), entra directo
        if r.scope in ['global', 'personal']:
            r.scope_target = None # Asegurar formato null para Pydantic
            final_reports.append(r)
            continue

        # B. Si es por Rol, verificamos la lista JSON
        if r.scope == 'role':
            try:
                # Parseamos el string JSON: '["Admin", "User"]' -> List
                target_roles = json.loads(r.scope_target) if r.scope_target else []

                # Si no es lista válida, se ignora por seguridad
                if not isinstance(target_roles, list):
                    continue

                # LÓGICA CLAVE: ¿El rol del usuario está en la lista del reporte?
                if current_role and current_role in target_roles:
                    # Asignamos la lista real al objeto antes de devolverlo
                    r.scope_target = target_roles
                    final_reports.append(r)

            except json.JSONDecodeError:
                # Si hay error en el JSON, ignoramos el reporte
                continue

    return final_reports