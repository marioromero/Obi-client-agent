import sqlalchemy
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, func, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class Dashboard(Base):
    __tablename__ = 'dashboards'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    user_identifier = Column(String(255), nullable=False, index=True)

    # Configuración visual (JSON) para el grid del frontend (posiciones x, y, w, h)
    layout_config = Column(Text, nullable=True)

    # Contexto Granular (JSON) para optimización de tokens en IA
    # Estructura: [{"table_id": 1, "include_columns": ["col1", "col2"]}, ...]
    context_definition = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relación: Un Dashboard tiene muchos Reportes (Instrumentos)
    reports = relationship("Report", back_populates="dashboard", cascade="all, delete-orphan")

class Report(Base):
    __tablename__ = 'reports'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Vinculación al Dashboard (NUEVO)
    dashboard_id = Column(Integer, ForeignKey('dashboards.id'), nullable=True)
    dashboard = relationship("Dashboard", back_populates="reports")

    name = Column(String(255), nullable=False) # Título del instrumento
    user_identifier = Column(String(255), nullable=False, index=True)

    type = Column(String(50), nullable=False, default='table') # 'table', 'bar', 'line', etc.

    # Scope RBAC (Mantenemos esto por si quieres compartir dashboards completos)
    scope = Column(String(50), nullable=False, default='personal')
    scope_target = Column(Text, nullable=True)

    # --- CEREBRO DEL CHAT ---
    question = Column(Text, nullable=True) # La última pregunta hecha
    sql_query = Column(Text, nullable=False) # El SQL resultante

    # CRUCIAL: Para que el chat tenga memoria por instrumento
    conversation_id = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class SchemaDraft(Base):
    __tablename__ = 'schema_drafts'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    connection_key = Column(String(100), nullable=False, unique=True, index=True)
    structure_json = Column(Text, nullable=False)

    # Mapa de IDs nube para traducción
    cloud_refs_json = Column(Text, nullable=True)

    is_synced = Column(Boolean, default=False)
    last_scanned_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<SchemaDraft(key={self.connection_key}, synced={self.is_synced})>"