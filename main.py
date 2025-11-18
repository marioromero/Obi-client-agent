from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

# Importamos las piezas que creamos
import models
import schemas
from database import get_db, engine

# 1. Creamos la aplicación FastAPI
app = FastAPI(title="Agente de Cliente OBI", version="0.1.0")


# --- Endpoint de prueba ---
@app.get("/")
async def root():
    return {"message": "Hola, soy el Agente OBI. Estoy vivo."}


# --- Endpoint para CREAR un Reporte ---
@app.post("/api/v1/reports/", response_model=schemas.Report)
async def create_report(
    report_data: schemas.ReportCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Crea y guarda un nuevo reporte en la base de datos local.
    """
    # Convertimos los datos del schema (Pydantic) a un modelo (SQLAlchemy)
    db_report = models.Report(**report_data.model_dump())

    # Añadimos y guardamos en la BD
    db.add(db_report)
    await db.commit()
    await db.refresh(db_report)

    return db_report

# --- Endpoint para LISTAR todos los Reportes ---
@app.get("/api/v1/reports/", response_model=List[schemas.Report])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """
    Obtiene una lista de todos los reportes guardados.
    """
    # Creamos la consulta para seleccionar reportes
    query = select(models.Report).offset(skip).limit(limit)

    # Ejecutamos la consulta
    result = await db.execute(query)

    # Obtenemos los resultados y los retornamos
    reports = result.scalars().all()
    return reports