from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# --- Esquema Base ---
# Campos que comparte nuestro modelo
class ReportBase(BaseModel):
    name: str
    user_identifier: str
    sql_query: str
    type: str = 'table'
    scope: str = 'personal'
    question: Optional[str] = None
    scope_target: Optional[str] = None

# --- Esquema para CREAR ---
# Qué datos necesitamos para CREAR un reporte
# (Hereda de ReportBase)
class ReportCreate(ReportBase):
    pass # Por ahora, es igual que el Base

# --- Esquema para LEER ---
# Qué datos vamos a DEVOLVER cuando alguien pida un reporte
# (Hereda de ReportBase y añade los campos que genera la BD)
class Report(ReportBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True # Permite a Pydantic leer el modelo de SQLAlchemy

# --- Esquema para EJECUTAR una Consulta ---
class QueryExecuteRequest(BaseModel):
    sql: str

# --- Esquema para DEVOLVER los resultados de la consulta ---
class QueryExecuteResponse(BaseModel):
    columns: List[str]
    rows: List[list]
    row_count: int