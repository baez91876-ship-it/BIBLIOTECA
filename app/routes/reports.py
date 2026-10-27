"""Endpoints HTTP de los informes y métricas de la biblioteca."""

from typing import Annotated

from fastapi import APIRouter, Query

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

router = APIRouter(prefix="/reportes", tags=["reportes"])
LimiteReporte = Annotated[int, Query(ge=1, le=100)]
LimiteReporteAnterior = Annotated[
    int | None, Query(ge=1, le=100, alias="limite", deprecated=True)
]


@router.get("/libros-mas-prestados", response_model=list[LibroMasPrestado])
def libros_mas_prestados(
    db: SessionDep,
    limit: LimiteReporte = 5,
    skip: Annotated[int, Query(ge=0)] = 0,
    limite_anterior: LimiteReporteAnterior = None,
) -> list[dict]:
    """Devuelve los libros más prestados con límite y desplazamiento."""
    if limite_anterior is not None:
        if limit != 5 and limit != limite_anterior:
            raise ReglaNegocio("No combines los parámetros 'limit' y 'limite'")
        limit = limite_anterior
    return reports.most_borrowed_books(db, skip, limit)


@router.get("/categorias", response_model=list[CategoriaReporte])
def reporte_categorias(db: SessionDep, pagination: PaginationDep) -> list[dict]:
    """Devuelve el total de libros registrado por categoría."""
    return reports.books_by_category(db, pagination)


@router.get("/prestamos-vencidos", response_model=list[PrestamoVencido])
def reporte_prestamos_vencidos(db: SessionDep, pagination: PaginationDep) -> list[dict]:
    """Devuelve los préstamos vencidos y sus días de retraso."""
    return reports.overdue_loans(db, pagination)


@router.get("/socios-con-multas", response_model=list[SocioMultas])
def reporte_socios_con_multas(db: SessionDep, pagination: PaginationDep) -> list[dict]:
    """Devuelve socios con multas acumuladas."""
    return reports.members_with_fines(db, pagination)


@router.get("/autores", response_model=list[AutorReporte])
def reporte_autores(db: SessionDep, pagination: PaginationDep) -> list[dict]:
    """Devuelve totales de libros, ejemplares y préstamos por autor."""
    return reports.authors_summary(db, pagination)


@router.get("/resumen", response_model=ResumenReporte)
def reporte_resumen(db: SessionDep) -> dict:
    """Devuelve los indicadores globales de actividad."""
    return reports.library_summary(db)
