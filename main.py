import re  # <-- NUEVO: Para la validación de seguridad
from fastapi import FastAPI, Depends, HTTPException, status # <-- 'status' es nuevo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import create_engine, text  # <-- NUEVO: Para ejecutar SQL síncrono
from typing import List

# Importamos las piezas que creamos
import models
import schemas
from database import get_db, engine
from config import settings  # <-- NUEVO: Para leer el .env

# --- (NUEVAS LISTAS DE SEGURIDAD) ---
# (Puedes añadir más si lo necesitas)
FORBIDDEN_KEYWORDS = [
    'DROP', 'DELETE', 'UPDATE', 'INSERT', 'TRUNCATE', 'ALTER', 'GRANT',
    'REVOKE', 'CREATE', 'EXEC', 'SHUTDOWN', 'MERGE', 'CALL'
]
FORBIDDEN_PATTERNS = [r";", r"--", r"\/\*"] # Evitar fin de sentencias y comentarios

# 1. Creamos la aplicación FastAPI
app = FastAPI(title="Agente de Cliente OBI", version="0.1.0")


# --- (NUEVA FUNCIÓN DE SEGURIDAD) ---
def validate_sql_safety(sql: str):
    """
    Valida que la consulta SQL sea segura (Confianza Cero).
    Solo permite consultas SELECT.
    """
    sql_normalized = sql.strip().upper()

    # 1. Regla: Debe empezar con SELECT
    if not sql_normalized.startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operación no permitida. Solo se aceptan consultas SELECT."
        )

    # 2. Regla: No debe contener palabras clave peligrosas
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operación no permitida. Palabra clave '{keyword}' detectada."
            )

    # 3. Regla: No debe contener patrones de inyección (comentarios, multi-statement)
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operación no permitida. Patrón '{pattern}' detectado."
            )

    return True


# --- Endpoint de prueba (Existente) ---
@app.get("/")
async def root():
    return {"message": "Hola, soy el Agente OBI. Estoy vivo."}


# --- (NUEVO ENDPOINT DE EJECUCIÓN) ---
@app.post("/api/v1/execute", response_model=schemas.QueryExecuteResponse)
async def execute_query(query: schemas.QueryExecuteRequest):
    """
    (Flujo 2) Ejecuta una consulta SQL de SOLO LECTURA
    contra la base de datos del cliente.
    """
    # 1. Validar la seguridad del SQL (Confianza Cero)
    validate_sql_safety(query.sql)

    client_engine = None
    try:
        # 2. Crear un motor de BD del cliente (síncrono)
        #    Lee la configuración del .env a través de settings
        client_engine = create_engine(settings.get_client_db_url())

        # 3. Conectarse y ejecutar la consulta
        with client_engine.connect() as connection:

            # Usamos text() para asegurar que SQLAlchemy trate el string de forma segura
            result = connection.execute(text(query.sql))

            # 4. Procesar los resultados
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]
            row_count = len(rows)

            # 5. Devolver la respuesta en el formato correcto
            return schemas.QueryExecuteResponse(
                columns=columns,
                rows=rows,
                row_count=row_count
            )

    except Exception as e:
        # Capturar errores (ej. "Conexión rechazada", "Tabla no encontrada")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al ejecutar la consulta: {str(e)}"
        )
    finally:
        # Asegurarse de cerrar el motor si se creó
        if client_engine:
            client_engine.dispose()


# --- Endpoint para CREAR un Reporte (Existente) ---
@app.post("/api/v1/reports/", response_model=schemas.Report)
async def create_report(
    report_data: schemas.ReportCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    (Flujo 3) Crea y guarda un nuevo reporte en la base de datos local (SQLite).
    """
    db_report = models.Report(**report_data.model_dump())

    db.add(db_report)
    await db.commit()
    await db.refresh(db_report)

    return db_report

# --- Endpoint para LISTAR todos los Reportes (Existente) ---
@app.get("/api/v1/reports/", response_model=List[schemas.Report])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """
    (Flujo 3) Obtiene una lista de todos los reportes guardados localmente (SQLite).
    """
    query = select(models.Report).offset(skip).limit(limit)
    result = await db.execute(query)
    reports = result.scalars().all()
    return reports