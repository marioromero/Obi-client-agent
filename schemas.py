from pydantic import BaseModel
from typing import Optional, List, TypeVar, Generic
from datetime import datetime

T = TypeVar('T')

# --- Esquemas de Reportes (Instrumentos) ---
class ReportBase(BaseModel):
    name: str
    user_identifier: str
    sql_query: str
    type: str = 'table'
    scope: str = 'personal'
    question: Optional[str] = None
    scope_target: Optional[List[str]] = None
    conversation_id: Optional[str] = None # Vital para el chat
    dashboard_id: Optional[int] = None    # Vital para anidarlo

class ReportCreate(ReportBase):
    pass

class Report(ReportBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Esquemas de Dashboards (NUEVO) ---
class DashboardBase(BaseModel):
    title: str
    description: Optional[str] = None
    user_identifier: str
    layout_config: Optional[str] = None
    context_definition: Optional[str] = None # JSON stringified

class DashboardCreate(DashboardBase):
    pass

class Dashboard(DashboardBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime]
    # Opcional: incluir los reportes anidados en la respuesta
    reports: List[Report] = []

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
    cloud_refs_json: Optional[str] = None

class SchemaDraftResponse(SchemaDraftBase):
    id: int
    last_scanned_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

# --- Envoltura Estándar ---
class StandardResponse(BaseModel, Generic[T]):
    status: bool
    message: str
# --- Esquemas de Traducción (Chat) ---
class TranslateRequest(BaseModel):
    question: str
    dashboard_id: Optional[int] = None
    # Si no hay dashboard, se pueden enviar IDs manuales (legacy)
    schema_table_ids: Optional[List[int]] = []

class TranslateResponse(BaseModel):
    sql: str
    explanation: Optional[str] = None
    data: Optional[T] = None