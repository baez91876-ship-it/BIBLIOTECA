"""Endpoints HTTP de los informes y métricas de la biblioteca."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from ..controllers import reports
from ..core.dependencies import PaginationDep, SessionDep
from ..core.exceptions import ReglaNegocio
from ..schemas.reporte import (
    AutorReporte,
    CategoriaReporte,
    LibroMasPrestado,
    PrestamoVencido,
    ResumenReporte,
    SocioMultas,
)
from ..schemas.pagination import Pagina, crear_pagina

router = APIRouter(prefix="/reportes", tags=["reportes"])
LimiteReporte = Annotated[int, Query(ge=1, le=100)]
LimiteReporteAnterior = Annotated[
    int | None, Query(ge=1, le=100, alias="limite", deprecated=True)
]


@router.get(
    "/libros-mas-prestados",
    response_model=list[LibroMasPrestado] | Pagina[LibroMasPrestado],
)
def libros_mas_prestados(
    request: Request,
    db: SessionDep,
    limit: LimiteReporte = 5,
    skip: Annotated[int, Query(ge=0)] = 0,
    limite_anterior: LimiteReporteAnterior = None,
) -> list[dict] | Pagina[LibroMasPrestado]:
    """Devuelve los libros más prestados con límite y desplazamiento."""
    if limite_anterior is not None:
        if limit != 5 and limit != limite_anterior:
            raise ReglaNegocio("No combines los parámetros 'limit' y 'limite'")
        limit = limite_anterior
    if request.url.path.startswith("/api/v1/"):
        items, total = reports.most_borrowed_books(
            db, skip, limit, include_total=True
        )
        return crear_pagina(items, total, skip, limit)
    return reports.most_borrowed_books(db, skip, limit)


@router.get(
    "/categorias",
    response_model=list[CategoriaReporte] | Pagina[CategoriaReporte],
)
def reporte_categorias(
    request: Request,
    db: SessionDep,
    pagination: PaginationDep,
) -> list[dict] | Pagina[CategoriaReporte]:
    """Devuelve el total de libros registrado por categoría."""
    if request.url.path.startswith("/api/v1/"):
        items, total = reports.books_by_category(
            db, pagination, include_total=True
        )
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return reports.books_by_category(db, pagination)


@router.get(
    "/prestamos-vencidos",
    response_model=list[PrestamoVencido] | Pagina[PrestamoVencido],
)
def reporte_prestamos_vencidos(
    request: Request,
    db: SessionDep,
    pagination: PaginationDep,
) -> list[dict] | Pagina[PrestamoVencido]:
    """Devuelve los préstamos vencidos y sus días de retraso."""
    if request.url.path.startswith("/api/v1/"):
        items, total = reports.overdue_loans(
            db, pagination, include_total=True
        )
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return reports.overdue_loans(db, pagination)


@router.get(
    "/socios-con-multas",
    response_model=list[SocioMultas] | Pagina[SocioMultas],
)
def reporte_socios_con_multas(
    request: Request,
    db: SessionDep,
    pagination: PaginationDep,
) -> list[dict] | Pagina[SocioMultas]:
    """Devuelve socios con multas acumuladas."""
    if request.url.path.startswith("/api/v1/"):
        items, total = reports.members_with_fines(
            db, pagination, include_total=True
        )
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return reports.members_with_fines(db, pagination)


@router.get(
    "/autores",
    response_model=list[AutorReporte] | Pagina[AutorReporte],
)
def reporte_autores(
    request: Request,
    db: SessionDep,
    pagination: PaginationDep,
) -> list[dict] | Pagina[AutorReporte]:
    """Devuelve totales de libros, ejemplares y préstamos por autor."""
    if request.url.path.startswith("/api/v1/"):
        items, total = reports.authors_summary(
            db, pagination, include_total=True
        )
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return reports.authors_summary(db, pagination)


@router.get("/resumen", response_model=ResumenReporte)
def reporte_resumen(db: SessionDep) -> dict:
    """Devuelve los indicadores globales de actividad."""
    return reports.library_summary(db)
