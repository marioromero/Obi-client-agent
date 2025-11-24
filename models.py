import sqlalchemy
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, func
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Report(Base):
    __tablename__ = 'reports'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    user_identifier = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=False, default='table')

    # scope: 'personal', 'global', 'role'
    scope = Column(String(50), nullable=False, default='personal')

    # CAMBIO: Almacena la lista de roles como texto JSON
    scope_target = Column(Text, nullable=True)

    question = Column(Text, nullable=True)
    sql_query = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

class SchemaDraft(Base):
    __tablename__ = 'schema_drafts'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    connection_key = Column(String(100), nullable=False, unique=True, index=True)
    structure_json = Column(Text, nullable=False)
    cloud_refs_json = Column(Text, nullable=True)
    is_synced = Column(Boolean, default=False)
    last_scanned_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<SchemaDraft(key={self.connection_key}, synced={self.is_synced})>"