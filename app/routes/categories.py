"""Endpoints HTTP para administrar categorías."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from ..controllers import categories
from ..core.dependencies import Pagination, SessionDep, get_pagination
from ..models import Categoria
from ..schemas.categoria import CategoriaCreate, CategoriaPatch, CategoriaRead

router = APIRouter(prefix="/categorias", tags=["categorias"])
PaginationQuery = Annotated[Pagination, Depends(get_pagination)]


@router.get("", response_model=list[CategoriaRead])
def listar_categorias(db: SessionDep, pagination: PaginationQuery) -> list[Categoria]:
    """Devuelve la página solicitada de categorías."""
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
