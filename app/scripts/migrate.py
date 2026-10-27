"""Aplica las migraciones y registra con seguridad bases del Taller 1."""

import importlib
import importlib.util
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

package_name = "app" if importlib.util.find_spec("app") else "APP"
database = importlib.import_module(f"{package_name}.core.database")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG = Config(str(PROJECT_ROOT / "alembic.ini"))
ALEMBIC_CONFIG.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
LEGACY_COLUMNS = {
    "autores": {"id", "nombre", "nacionalidad", "anio_nacimiento"},
    "categorias": {"id", "nombre", "descripcion"},
    "libros": {"id", "titulo", "isbn", "anio_publicacion", "ejemplares", "autor_id"},
    "libro_categoria": {"libro_id", "categoria_id"},
    "socios": {"id", "nombre", "email", "telefono", "activo", "fecha_alta"},
    "prestamos": {
        "id",
        "libro_id",
        "socio_id",
        "fecha_prestamo",
        "fecha_limite",
        "fecha_devolucion",
        "multa",
    },
}


def stamp_legacy_schema() -> None:
    """Marca solo un esquema Taller 1 completo, sin modificar sus datos."""
    with database.engine.connect() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "alembic_version" in tables or not tables:
            return
        missing_tables = set(LEGACY_COLUMNS) - tables
        if missing_tables:
            raise RuntimeError(
                "La base no está vacía ni coincide con Taller 1; "
                "no se marcará un baseline automáticamente. "
                f"Faltan tablas: {', '.join(sorted(missing_tables))}."
            )
        for table_name, required_columns in LEGACY_COLUMNS.items():
            columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            missing_columns = required_columns - columns
            if missing_columns:
                raise RuntimeError(
                    f"El esquema Taller 1 de '{table_name}' está incompleto; "
                    f"faltan columnas: {', '.join(sorted(missing_columns))}."
                )
        has_paid_fines = "multa_pagada" in {
            column["name"] for column in inspector.get_columns("prestamos")
        }
    command.stamp(
        ALEMBIC_CONFIG,
        "0002_multa_pagada" if has_paid_fines else "0001_estado_inicial",
    )


def main() -> None:
    """Actualiza el esquema de base de datos a la revisión más reciente."""
    stamp_legacy_schema()
    command.upgrade(ALEMBIC_CONFIG, "head")


if __name__ == "__main__":
    main()
