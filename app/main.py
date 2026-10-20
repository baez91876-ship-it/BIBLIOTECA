import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from . import models
from .core.database import Base, engine
from .core.exceptions import ErrorAplicacion
from .routes import authors, books, categories, loans, members, reports

logger = logging.getLogger("uvicorn.error")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        database_name = connection.scalar(text("SELECT current_database()"))
        table_names = sorted(inspect(connection).get_table_names())
        expected_columns = {
            "autores": {"id", "nombre", "nacionalidad", "anio_nacimiento"},
            "categorias": {"id", "nombre", "descripcion"},
            "libros": {
                "id",
                "titulo",
                "isbn",
                "anio_publicacion",
                "ejemplares",
                "autor_id",
            },
            "libro_categoria": {"libro_id", "categoria_id"},
            "socios": {
                "id",
                "nombre",
                "email",
                "telefono",
                "activo",
                "fecha_alta",
            },
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
        missing_tables = set(expected_columns) - set(table_names)
        if missing_tables:
            raise RuntimeError(
                "No se crearon todas las tablas esperadas: "
                + ", ".join(sorted(missing_tables))
            )
        for table_name, expected in expected_columns.items():
            actual = {
                column["name"]
                for column in inspect(connection).get_columns(table_name)
            }
            missing_columns = expected - actual
            if missing_columns:
                raise RuntimeError(
                    f"El esquema existente de '{table_name}' es incompatible; "
                    f"faltan columnas: {', '.join(sorted(missing_columns))}. "
                    "Migra la base de datos o configura una base nueva."
                )
        logger.info(
            "Conexión exitosa a la base de datos '%s' (%s). "
            "Tablas disponibles: %s",
            database_name,
            engine.dialect.name,
            ", ".join(table_names),
        )
    yield


app = FastAPI(
    title="API de biblioteca",
    description="API para gestionar el catálogo de una biblioteca.",
    version="1.0.0",
    lifespan=lifespan,
)
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
app.mount(
    "/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static"
)
app.include_router(books.router)
app.include_router(authors.router)
app.include_router(categories.router)
app.include_router(members.router)
app.include_router(loans.router)
app.include_router(reports.router)


@app.get("/", include_in_schema=False)
def interfaz():
    return FileResponse(PROJECT_ROOT / "index.html")


@app.get("/api-config.js", include_in_schema=False)
def configuracion_api():
    return FileResponse(
        PROJECT_ROOT / "api-config.js",
        media_type="application/javascript",
    )


@app.get("/health", include_in_schema=False)
def health():
    with engine.connect() as connection:
        database_name = connection.scalar(text("SELECT current_database()"))
        if database_name != "LIBRERIA":
            raise RuntimeError("La aplicación no está conectada a LIBRERIA.")
    return {"status": "ok", "database": database_name}


@app.exception_handler(ErrorAplicacion)
async def application_error_handler(_, exc: ErrorAplicacion):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
