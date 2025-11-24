from pydantic import BaseModel
from typing import Optional, List, TypeVar, Generic
from datetime import datetime

# --- Variable Genérica para la Envoltura ---
T = TypeVar('T')

# --- Esquemas de Reportes ---
class ReportBase(BaseModel):
    name: str
    user_identifier: str
    sql_query: str
    type: str = 'table'
    scope: str = 'personal'
    question: Optional[str] = None
    scope_target: Optional[List[str]] = None

class ReportCreate(ReportBase):
    pass

class Report(ReportBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Esquemas de Ejecución ---
class QueryExecuteRequest(BaseModel):
    sql: str

class QueryExecuteResponse(BaseModel):
    columns: List[str]
    rows: List[list]
    row_count: int

# --- Esquemas de Staging/Drafts ---
class ScanRequest(BaseModel):
    connection_key: str

class SchemaDraftBase(BaseModel):
    connection_key: str
    structure_json: str
    is_synced: bool
    cloud_refs_json: Optional[str] = None

class SchemaDraftUpdate(BaseModel):
    structure_json: str

class SchemaDraftResponse(SchemaDraftBase):
    id: int
    last_scanned_at: datetime
    updated_at: Optional[datetime]
    cloud_refs_json: Optional[str] = None

    class Config:
        from_attributes = True

# --- (NUEVO) ENVOLTURA DE RESPUESTA ESTÁNDAR ---
class StandardResponse(BaseModel, Generic[T]):
    status: bool
    message: str
    data: Optional[T] = None