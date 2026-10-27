"""Motor PostgreSQL y configuración común de los modelos ORM."""

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


def _parse_database_url(value: str) -> URL:
    """Valida PostgreSQL LIBRERIA y selecciona el controlador psycopg 3."""
    database_url = make_url(value)
    if database_url.drivername == "postgresql":
        database_url = database_url.set(drivername="postgresql+psycopg")
    if database_url.drivername != "postgresql+psycopg":
        raise ValueError("La aplicación solo puede conectarse a PostgreSQL.")
    if database_url.database is None or database_url.database.casefold() != "libreria":
        raise ValueError("La aplicación solo puede conectarse a la base libreria.")
    return database_url


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

engine = create_engine(
    _parse_database_url(get_settings().database_url), pool_pre_ping=True
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Clase base para registrar los modelos ORM de la aplicación."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db():
    """Proporciona una sesión por solicitud y la cierra al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
