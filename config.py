import json
import os
import logging
import urllib.parse
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Carga las variables desde el archivo .env (API URL y Token)
    # "extra='ignore'" permite que existan variables extra en el .env sin dar error
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Variables para API de IA (Estas SÍ vienen del .env) ---
    API_SERVICE_URL: str
    API_SERVICE_TOKEN: str

    # --- Variable opcional para SQL Server ---
    DB_CLIENT_ODBC_DRIVER: str = "ODBC Driver 17 for SQL Server"

    def get_connections_config(self) -> dict:
        """
        Lee el archivo connections.json de la raíz y devuelve el diccionario.
        Usa ruta absoluta basada en el directorio del script para robustez.
        """
        # Ruta absoluta basada en el directorio donde está este archivo (config.py)
        file_path = os.path.join(os.path.dirname(__file__), "connections.json")

        logging.info(f"Intentando leer connections.json desde ruta absoluta: {file_path}")

        if not os.path.exists(file_path):
            logging.warning(f"No se encontró el archivo connections.json en: {file_path}")
            return {}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logging.info(f"Conexiones cargadas exitosamente: {len(data)} conexiones encontradas.")
            return data
        except Exception as e:
            logging.error(f"Error leyendo connections.json: {e}")
            return {}

    def get_db_url_from_config(self, db_config: dict) -> str:
        """
        Construye la URL de conexión de SQLAlchemy para una base de datos específica
        basada en un objeto de configuración del JSON.
        """
        dialect = db_config.get("type", "mariadb").lower()
        user = db_config.get("user")
        password = db_config.get("password")
        host = db_config.get("host")
        port = db_config.get("port", 3306)
        dbname = db_config.get("dbname")

        # Codificar contraseña (CRÍTICO para caracteres como '$' en 'obi$2025')
        safe_password = urllib.parse.quote_plus(password) if password else ""

        dialect_driver = ""

        if dialect == "mariadb":
            dialect_driver = "mariadb+mariadbconnector"
        elif dialect == "mysql":
            dialect_driver = "mysql+mysqlconnector"
        elif dialect == "postgresql":
            dialect_driver = "postgresql+psycopg2"
        elif dialect == "oracle":
            dialect_driver = "oracle+oracledb"
        elif dialect == "sqlserver":
            driver_safe = urllib.parse.quote_plus(self.DB_CLIENT_ODBC_DRIVER)
            return (
                f"mssql+pyodbc://"
                f"{user}:{safe_password}@"
                f"{host}:{port}"
                f"/{dbname}?driver={driver_safe}"
            )
        else:
            # Fallback genérico
            dialect_driver = dialect

        return (
            f"{dialect_driver}://"
            f"{user}:{safe_password}@"
            f"{host}:{port}"
            f"/{dbname}"
        )

# Instancia global
settings = Settings()