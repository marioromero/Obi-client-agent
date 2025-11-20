import re

def humanize_column_name(col_name: str) -> str:
    """
    Convierte nombres de columna técnicos a formato legible.
    Actúa como 'Sugerencia Inicial' para el Humano.
    """

    # 1. Diccionario de reemplazos comunes
    replacements = {
        r'(?<!\w)id$': 'Identificador',
        r'(?<!\w)pk$': 'Llave Primaria',
        r'_(id)$': ' de Identificador',
        r'^id_': 'Identificador de ',
        r'created_at$': 'Fecha de Creación',
        r'updated_at$': 'Fecha de Actualización',
        r'softdeleted$': 'Estado de Eliminación (Lógica)',
        r'dni$': 'DNI',
        r'rut$': 'RUT',
        r'tel$': 'Teléfono',
        r'state$': 'Estado',
        r'status$': 'Estado',
        r'name$': 'Nombre',
        r'desc$': 'Descripción',
    }

    name = col_name.strip().lower()

    # 2. Aplicar reemplazos
    for pattern, replacement in replacements.items():
        name = re.sub(pattern, replacement, name)

    # 3. Formato Título (guiones a espacios)
    name = name.replace('_', ' ').title()

    return name.strip()