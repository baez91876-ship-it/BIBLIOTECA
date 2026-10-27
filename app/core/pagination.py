"""Ejecución común de consultas SQL paginadas."""

from typing import TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from .dependencies import Pagination

T = TypeVar("T")


def execute_page(
    db: Session,
    query: Select[tuple[T]],
    pagination: Pagination,
) -> tuple[list[T], int]:
    """Ejecuta una consulta de items y su total sin aplicar límites al total."""
    count_query = select(func.count()).select_from(
        query.order_by(None).offset(None).limit(None).subquery()
    )
    total = db.scalar(count_query) or 0
    items = (
        db.scalars(
            query.offset(pagination.skip).limit(pagination.limit)
        )
        .unique()
        .all()
    )
    return items, total
