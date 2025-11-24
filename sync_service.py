import json
import requests
from sqlalchemy import create_engine, inspect
from config import settings
from mapper_service import humanize_column_name

def scan_specific_connection(connection_key: str):
    """
    Escanea UNA sola base de datos definida en connections.json, identificada por su key.
    """
    # 1. Obtener la configuración específica
    connections = settings.get_connections_config()
    db_config = connections.get(connection_key)

    if not db_config:
        raise Exception(f"La conexión '{connection_key}' no existe en connections.json")

    db_name = db_config.get('dbname')
    print(f"🔌 Escaneando conexión: {connection_key} ({db_name})...")

    try:
        # Crear motor específico para esta conexión
        url = settings.get_db_url_from_config(db_config)
        engine = create_engine(url)
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
    except Exception as e:
        raise Exception(f"Error conectando a {connection_key}: {e}")

    schema_data = []

    for table_name in table_names:
        try:
            columns = inspector.get_columns(table_name)
        except Exception as e:
            print(f"⚠️ Error en tabla {table_name}: {e}")
            continue

        # Prefijo del nombre de BD (Crucial para multi-tenant)
        full_table_name = f"{db_name}.{table_name}"

        col_metadata = []

        # Definición SQL base
        definition_lines = [f"CREATE TABLE {full_table_name} ("]

        for col in columns:
            sql_def = f"`{col['name']}` {col['type']}"
            if col.get('nullable') is False: sql_def += " NOT NULL"
            if col.get('primary_key'): sql_def += " PRIMARY KEY"

            is_default_flag = True if col.get('primary_key') else False

            col_info = {
                "col": col['name'],
                "sql_def": sql_def,
                "desc": humanize_column_name(col['name']),
                "is_default": is_default_flag,
                "instructions": None
            }
            col_metadata.append(col_info)
            definition_lines.append(f"  {sql_def}")

        definition_lines.append(");")

        table_obj = {
            "table_name": full_table_name,
            "definition": "\n".join(definition_lines),
            "column_metadata": col_metadata,
        }
        schema_data.append(table_obj)

    print(f"✅ Escaneo de '{connection_key}' completado. {len(schema_data)} tablas.")
    return schema_data

def push_schema_to_cloud(schema_data_json, connection_key):
    """
    Sube un borrador a la nube y RETORNA el mapa de IDs.
    Returns:
        dict: { "nombre_tabla": id_cloud_int, ... }
    """
    if isinstance(schema_data_json, str):
        schema_tables = json.loads(schema_data_json)
    else:
        schema_tables = schema_data_json

    # Obtener config
    connections = settings.get_connections_config()
    db_config = connections.get(connection_key, {})
    db_name = db_config.get('dbname', connection_key)
    db_dialect = db_config.get('type', 'mariadb')

    api_url = settings.API_SERVICE_URL.rstrip('/')

    # IMPORTANTE: Asegúrate de que API_SERVICE_TOKEN sea válido en tu .env o config
    headers = {
        "Authorization": f"Bearer {settings.API_SERVICE_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"🚀 Subiendo esquema '{connection_key}' a la nube...")

    # 1. Crear/Obtener Schema Padre
    schema_payload = {
        "name": f"Microservicio: {connection_key}",
        "dialect": db_dialect,
        "database_name_prefix": db_name
    }

    try:
        resp = requests.post(f"{api_url}/api/schemas", json=schema_payload, headers=headers)
        if resp.status_code not in [200, 201]:
            raise Exception(f"Error creando Schema: {resp.text}")

        # Asumimos que Laravel devuelve { data: { id: 1, ... } }
        schema_id = resp.json()['data']['id']
    except Exception as e:
        raise Exception(f"Fallo de red al crear esquema: {str(e)}")

    # 2. Subir Tablas y CAPTURAR IDs
    errors = []
    cloud_refs = {} # Aquí guardaremos el mapa: "nombre_tabla" -> id

    for table in schema_tables:
        payload = {
            "schema_id": schema_id,
            "table_name": table['table_name'],
            "definition": table['definition'],
            "column_metadata": table['column_metadata']
        }
        try:
            r = requests.post(f"{api_url}/api/schema-tables", json=payload, headers=headers)

            if r.status_code in [200, 201]:
                # ÉXITO: Capturamos el ID que nos dio Laravel
                response_data = r.json()
                cloud_id = response_data['data']['id']
                cloud_refs[table['table_name']] = cloud_id
            else:
                errors.append(f"{table['table_name']}: {r.text}")

        except Exception as e:
            errors.append(f"{table['table_name']}: {str(e)}")

    if errors:
        raise Exception(f"Errores en subida parcial: {'; '.join(errors)}")

    print(f"✨ Esquema '{connection_key}' sincronizado. {len(cloud_refs)} tablas mapeadas.")

    # 3. Retornamos el diccionario para guardarlo en local
    return cloud_refs