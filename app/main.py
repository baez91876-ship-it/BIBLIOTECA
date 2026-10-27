"""Punto de entrada FastAPI, configuración de rutas y recursos web."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from . import models  # noqa: F401  # Register models in SQLAlchemy metadata.
from .core.config import get_settings
from .core.database import engine
from .core.dependencies import require_api_access
from .core.exceptions import ErrorAplicacion
from .routes import authors, books, categories, loans, members, reports
from .routes.auth import limiter as auth_limiter
from .routes.auth import router as auth_router

logger = logging.getLogger("uvicorn.error")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "docs"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Deja la gestión del esquema a las migraciones versionadas de Alembic."""
    logger.info("API iniciada; el esquema debe estar actualizado con alembic upgrade head.")
    yield


app = FastAPI(
    title="API de biblioteca",
    description="API para gestionar el catálogo de una biblioteca.",
    version="2.0.0",
    lifespan=lifespan,
)
settings = get_settings()
app.state.limiter = auth_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
cors_origins = settings.cors_origins
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )


@app.middleware("http")
async def request_id_and_access_log(request: Request, call_next):
    """Asigna un identificador a cada petición y registra su resultado."""
    request_id = str(uuid4())
    request.state.request_id = request_id
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Error procesando request_id=%s", request_id)
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s %s %.3fms request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - started_at) * 1000,
        request_id,
    )
    return response


app.include_router(auth_router)
api_v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_access)])
for resource_router in (
    authors.router,
    books.router,
    categories.router,
    members.router,
    loans.router,
    reports.router,
):
    api_v1.include_router(resource_router)
app.include_router(api_v1)

# The unauthenticated Taller 1 paths stay available only for local compatibility.
if settings.app_env.casefold() != "production":
    app.include_router(books.router)
    app.include_router(authors.router)
    app.include_router(categories.router)
    app.include_router(members.router)
    app.include_router(loans.router)
    app.include_router(reports.router)

app.mount("/static", StaticFiles(directory=FRONTEND_ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
def interfaz():
    """Entrega la interfaz web de la biblioteca."""
    return FileResponse(FRONTEND_ROOT / "index.html")


@app.get("/api-config.js", include_in_schema=False)
def configuracion_api():
    """Usa el mismo origen para la interfaz servida por esta API."""
    return Response(
        "window.BIBLIOTECA_API_URL = '';",
        media_type="application/javascript",
    )


@app.get("/catalogo.json", include_in_schema=False)
def catalogo_estatico():
    """Entrega la copia estática del catálogo para GitHub Pages."""
    return FileResponse(
        FRONTEND_ROOT / "catalogo.json",
        media_type="application/json",
    )


@app.get("/health", include_in_schema=False)
def health():
    """Comprueba que la base conectada sea la base esperada."""
    with engine.connect() as connection:
        database_name = connection.scalar(text("SELECT current_database()"))
        if database_name is None or database_name.casefold() != "libreria":
            raise RuntimeError("La aplicación no está conectada a LIBRERIA.")
    return {"status": "ok", "database": database_name}


@app.get("/api/v1/health", tags=["salud"])
def versioned_health():
    """Comprueba que PostgreSQL responde a una consulta simple."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        database_name = connection.scalar(text("SELECT current_database()"))
    if database_name is None or database_name.casefold() != "libreria":
        raise RuntimeError("La aplicación no está conectada a la base libreria.")
    return {"status": "ok", "database": database_name}


@app.exception_handler(ErrorAplicacion)
async def application_error_handler(_, exc: ErrorAplicacion):
    """Convierte excepciones de dominio en respuestas JSON con su estado HTTP."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Registra el detalle en servidor y devuelve un error genérico al cliente."""
    logger.error(
        "Error no controlado request_id=%s",
        getattr(request.state, "request_id", "unknown"),
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
        headers={
            "X-Request-ID": getattr(request.state, "request_id", "unknown")
        },
    )
