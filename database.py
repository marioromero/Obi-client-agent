from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import Base # Importamos la Base de nuestros modelos

# 1. Esta es la URL de conexión ASÍNCRONA para SQLAlchemy
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./agent_storage.db"

# 2. Creamos el "motor" (engine) asíncrono
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} # Requerido para SQLite
)

# 3. Creamos una "fábrica" de sesiones asíncronas
#    Esto nos permitirá crear sesiones de BD en nuestros endpoints
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession
)

# 4. Función de ayuda para obtener una sesión de BD en un endpoint
#    FastAPI usará esto para "inyectar" una sesión de BD en nuestras
#    funciones de API.
async def get_db():
    async with SessionLocal() as session:
        yield session