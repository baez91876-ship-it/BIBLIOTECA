"""Endpoints HTTP para administrar categorías."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from ..controllers import categories
from ..core.dependencies import Pagination, SessionDep, get_pagination
from ..models import Categoria
from ..schemas.categoria import CategoriaCreate, CategoriaPatch, CategoriaRead
from ..schemas.pagination import Pagina, crear_pagina

router = APIRouter(prefix="/categorias", tags=["categorias"])
PaginationQuery = Annotated[Pagination, Depends(get_pagination)]


@router.get("", response_model=list[CategoriaRead] | Pagina[CategoriaRead])
def listar_categorias(
    request: Request,
    db: SessionDep,
    pagination: PaginationQuery,
) -> list[Categoria] | Pagina[CategoriaRead]:
    """Devuelve la página solicitada de categorías."""
    if request.url.path.startswith("/api/v1/"):
        items, total = categories.list_categories(db, pagination, include_total=True)
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return categories.list_categories(db, pagination)


@router.get("/{categoria_id}", response_model=CategoriaRead)
def obtener_categoria(categoria_id: int, db: SessionDep) -> Categoria:
    """Devuelve la categoría identificada por su ID."""
    return categories.get_category(categoria_id, db)


@router.post("", response_model=CategoriaRead, status_code=status.HTTP_201_CREATED)
def crear_categoria(data: CategoriaCreate, db: SessionDep) -> Categoria:
    """Registra una categoría y devuelve el recurso creado."""
    return categories.create_category(data, db)


@router.patch("/{categoria_id}", response_model=CategoriaRead)
def actualizar_categoria(
    categoria_id: int, data: CategoriaPatch, db: SessionDep
) -> Categoria:
    """Modifica los campos enviados de la categoría."""
    return categories.patch_category(categoria_id, data, db)


@router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_categoria(categoria_id: int, db: SessionDep) -> Response:
    """Elimina la categoría sin eliminar sus libros asociados."""
    categories.delete_category(categoria_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
