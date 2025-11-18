from pydantic_settings import BaseSettings, SettingsConfigDict
import urllib.parse  # <-- ¡Importante para codificar la contraseña!

class Settings(BaseSettings):
    # Carga las variables desde el archivo .env
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # --- Variables para API de IA (Flujo 1) ---
    API_SERVICE_URL: str
    API_SERVICE_TOKEN: str

    # --- Variables para BD Cliente (Flujo 2) ---
    DB_CLIENT_DIALECT: str
    DB_CLIENT_HOST: str
    DB_CLIENT_PORT: int
    DB_CLIENT_USER: str
    DB_CLIENT_PASSWORD: str
    DB_CLIENT_DBNAME: str  # <-- Corregido (coincide con tu .env)

    # Específico de SQL Server
    DB_CLIENT_ODBC_DRIVER: str = "ODBC Driver 17 for SQL Server"

    def get_client_db_url(self) -> str:
        """
        Construye la URL de conexión de SQLAlchemy para la BD del cliente
        basado en el dialecto.
        """

        # ¡CRÍTICO! Codificamos la contraseña (para el '$' en 'obi$2025')
        safe_password = urllib.parse.quote_plus(self.DB_CLIENT_PASSWORD)

        dialect_driver = ""

        if self.DB_CLIENT_DIALECT == "mariadb":
            dialect_driver = "mariadb+mariadbconnector"
        elif self.DB_CLIENT_DIALECT == "mysql":
            dialect_driver = "mysql+mysqlconnector"
        elif self.DB_CLIENT_DIALECT == "postgresql":
            dialect_driver = "postgresql+psycopg2"
        elif self.DB_CLIENT_DIALECT == "oracle":
            # Para Oracle, DBNAME es usualmente el "Service Name" o SID
            dialect_driver = "oracle+oracledb"
        elif self.DB_CLIENT_DIALECT == "sqlserver":
            # pyodbc necesita el nombre del driver codificado para la URL
            driver_safe = urllib.parse.quote_plus(self.DB_CLIENT_ODBC_DRIVER)

            return (
                f"mssql+pyodbc://"
                f"{self.DB_CLIENT_USER}:{safe_password}@"
                f"{self.DB_CLIENT_HOST}:{self.DB_CLIENT_PORT}"
                f"/{self.DB_CLIENT_DBNAME}?driver={driver_safe}"
            )
        else:
            raise ValueError(f"Dialecto de BD no soportado: {self.DB_CLIENT_DIALECT}")

        # URL estándar para MariaDB, MySQL, Postgres, Oracle
        return (
            f"{dialect_driver}://"
            f"{self.DB_CLIENT_USER}:{safe_password}@"
            f"{self.DB_CLIENT_HOST}:{self.DB_CLIENT_PORT}"
            f"/{self.DB_CLIENT_DBNAME}"
        )


# Creamos una instancia única que será usada por toda la app
settings = Settings()