"""Configuración de PostgreSQL y sesiones de SQLAlchemy."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL no está configurada. Define la conexión PostgreSQL "
        "a la base de datos LIBRERIA en el archivo .env."
    )


def _parse_database_url(value: str) -> URL:
    """Valida PostgreSQL LIBRERIA y usa el controlador psycopg instalado."""
    database_url = make_url(value)
    if database_url.drivername == "postgresql":
        database_url = database_url.set(drivername="postgresql+psycopg")
    if database_url.drivername != "postgresql+psycopg":
        raise RuntimeError("La aplicación solo puede conectarse a PostgreSQL.")
    if database_url.database is None or database_url.database.casefold() != "libreria":
        raise RuntimeError(
            "La aplicación solo puede conectarse a la base de datos LIBRERIA."
        )
    return database_url


database_url = _parse_database_url(DATABASE_URL)

engine = create_engine(database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Clase base para registrar los modelos ORM de la aplicación."""


def get_db():
    """Proporciona una sesión por solicitud y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
