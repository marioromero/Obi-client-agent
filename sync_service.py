import json
import requests
from sqlalchemy import create_engine, inspect
from config import settings

def get_database_schema():
    """
    Conecta a la BD del cliente y extrae la metadata.
    Devuelve una lista de objetos listos para enviar a la API.
    """
    print(f"🔌 Conectando a {settings.DB_CLIENT_DIALECT} en {settings.DB_CLIENT_HOST}...")

    try:
        engine = create_engine(settings.get_client_db_url())
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
    except Exception as e:
        print(f"❌ Error crítico al conectar a la BD local: {e}")
        return []

    print(f"📋 Tablas encontradas: {len(table_names)}")

    schema_data = []
    # Eliminado el prefijo DB, usamos el nombre directo de la tabla

    for table_name in table_names:
        # Usamos el nombre simple que viene de la inspección

        columns = inspector.get_columns(table_name)
        col_metadata = []

        # Definición SQL con el nombre simple
        definition_lines = [f"CREATE TABLE {table_name} ("]

        for col in columns:
            # Metadata para el "mapper"
            col_info = {
                "col": col['name'],
                "type": str(col['type']),
                "is_default": False
            }
            col_metadata.append(col_info)

            # Línea de definición SQL
            def_line = f"  {col['name']} {col['type']}"
            if col.get('primary_key'):
                def_line += " PRIMARY KEY"
            definition_lines.append(def_line)

        definition_lines.append(");")
        definition_str = "\n".join(definition_lines)

        # Objeto final listo para tu API SchemaTableController
        table_obj = {
            "table_name": table_name, # <-- AHORA ES SOLO EL NOMBRE DE LA TABLA
            "column_metadata": col_metadata,
            "definition": definition_str
        }

        schema_data.append(table_obj)

    return schema_data

def upload_schema_to_api(schema_tables):
    """
    Sube la estructura extraída a tu API de Laravel.
    """
    if not schema_tables:
        print("⚠️ No hay tablas para subir.")
        return

    api_url = settings.API_SERVICE_URL.rstrip('/')
    headers = {
        "Authorization": f"Bearer {settings.API_SERVICE_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"\n🚀 Iniciando sincronización con API remota: {api_url}")

    # PASO 1: Crear o Actualizar el "Schema" (La carpeta contenedora)
    # Usamos el nombre de la BD como nombre del esquema
    schema_payload = {
        "name": f"BD Cliente: {settings.DB_CLIENT_DBNAME}",
        "dialect": settings.DB_CLIENT_DIALECT,
        "database_name_prefix": settings.DB_CLIENT_DBNAME
    }

    print("   -> Creando/Verificando Esquema contenedor...")
    try:
        # Intentamos crear el esquema.
        resp = requests.post(f"{api_url}/api/schemas", json=schema_payload, headers=headers)

        if resp.status_code not in [200, 201]:
            print(f"❌ Error al crear esquema: {resp.status_code} - {resp.text}")
            return

        schema_remote = resp.json()['data']
        schema_id = schema_remote['id']
        print(f"   ✅ Esquema ID {schema_id} listo.")

    except Exception as e:
        print(f"❌ Error de conexión con API Remota: {e}")
        return

    # PASO 2: Subir cada tabla
    print(f"   -> Subiendo {len(schema_tables)} tablas...")

    for table in schema_tables:
        payload = {
            "schema_id": schema_id,
            "table_name": table['table_name'],
            "definition": table['definition'],
            "column_metadata": table['column_metadata']
        }

        try:
            r_table = requests.post(f"{api_url}/api/schema-tables", json=payload, headers=headers)
            if r_table.status_code in [200, 201]:
                print(f"      ✅ Tabla '{table['table_name']}' sincronizada.")
            else:
                print(f"      ⚠️ Error en tabla '{table['table_name']}': {r_table.text}")
        except Exception as e:
             print(f"      ❌ Error de red subiendo tabla: {e}")

    print("\n✨ Sincronización finalizada.")

if __name__ == "__main__":
    # --- EJECUCIÓN COMPLETA ---
    extracted_data = get_database_schema()

    if extracted_data:
        # Preguntar al usuario antes de subir
        print(f"\nSe han extraído {len(extracted_data)} tablas.")
        confirm = input("¿Quieres subirlas a tu API ahora? (s/n): ")

        if confirm.lower() == 's':
            upload_schema_to_api(extracted_data)
        else:
            print("Operación cancelada. Solo se mostró la extracción.")
            # Imprimir ejemplo para verificar formato
            print("\nEjemplo de formato generado:")
            print(json.dumps(extracted_data[0], indent=2))