import sqlalchemy
from sqlalchemy import Column, Integer, String, Text, DateTime, func
# Esta es la línea actualizada para la Base de SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# 1. Definimos una 'Base' de la que heredarán todos nuestros modelos
class Base(DeclarativeBase):
    pass

# 2. Definimos nuestro primer modelo: Report
class Report(Base):
    __tablename__ = 'reports'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    user_identifier = Column(String(255), nullable=False, index=True)
    type = Column(String(50), nullable=False, default='table') # 'table' o 'graph'
    scope = Column(String(50), nullable=False, default='personal') # 'personal', 'role', 'global'
    scope_target = Column(String(255), nullable=True) # ej. "Admins" si el scope es 'role'

    question = Column(Text, nullable=True)
    sql_query = Column(Text, nullable=False) # El SQL a ejecutar

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Corregimos 'onupdate' para que funcione con SQLAlchemy moderno
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<Report(id={self.id}, name='{self.name}')>"