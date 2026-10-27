"""Dependencias compartidas para paginación y acceso a la base de datos."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from .database import get_db


@dataclass(frozen=True)
class Pagination:
    """Límites de paginación validados para una consulta."""

    skip: int
    limit: int


def get_pagination(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> Pagination:
    """Construye los parámetros de paginación aceptados por la API."""
    return Pagination(skip=skip, limit=limit)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]
SessionDep = Annotated[Session, Depends(get_db)]
