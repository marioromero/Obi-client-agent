from pydantic import BaseModel, computed_field
import json
from typing import Optional, List, Any, Dict
from datetime import datetime

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

    @computed_field
    def layout(self) -> Optional[List[Any]]:
        if self.layout_config:
            try:
                return json.loads(self.layout_config)
            except: return None
        return None

    @computed_field
    def context(self) -> Optional[List[Any]]:
        if self.context_definition:
            try:
                return json.loads(self.context_definition)
            except: return None
        return None

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

    @computed_field
    def structure(self) -> Optional[List[Any]]:
        if self.structure_json:
            try:
                return json.loads(self.structure_json)
            except: return None
        return None

    @computed_field
    def cloud_refs(self) -> Optional[Dict[str, int]]:
        if self.cloud_refs_json:
            try:
                return json.loads(self.cloud_refs_json)
            except: return None
        return None

    class Config:
        from_attributes = True

# --- Envoltura Estándar ---
class StandardResponse(BaseModel):
    status: bool
    message: str
    data: Any = None
# --- Esquemas de Traducción (Chat) ---
class TranslateRequest(BaseModel):
    question: str
    dashboard_id: Optional[int] = None
    # Si no hay dashboard, se pueden enviar IDs manuales (legacy)
    schema_table_ids: Optional[List[int]] = []

class TranslateResponse(BaseModel):
    sql: str
    explanation: Optional[str] = None