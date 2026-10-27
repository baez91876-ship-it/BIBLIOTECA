"""Configuración de PostgreSQL y sesiones de SQLAlchemy."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL no está configurada. Define la conexión PostgreSQL "
        "a la base de datos LIBRERIA en el archivo .env."
    )

database_url = make_url(DATABASE_URL)
if not database_url.drivername.startswith("postgresql"):
    raise RuntimeError("La aplicación solo puede conectarse a PostgreSQL.")
if database_url.database != "LIBRERIA":
    raise RuntimeError(
        "La aplicación solo puede conectarse a la base de datos LIBRERIA."
    )

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Clase base para registrar los modelos ORM de la aplicación."""

    pass


def get_db():
    """Proporciona una sesión por solicitud y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
