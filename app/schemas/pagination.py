"""Formato genérico y autocontenido para resultados paginados."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Pagina(BaseModel, Generic[T]):
    """Elementos de una página, total filtrado y parámetros aplicados."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int = Field(ge=0)
    skip: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


def crear_pagina(
    items: list[T], total: int, skip: int, limit: int
) -> Pagina[T]:
    """Construye la respuesta genérica de una consulta paginada."""
    return Pagina(items=items, total=total, skip=skip, limit=limit)
