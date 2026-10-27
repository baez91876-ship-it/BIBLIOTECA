"""Endpoints HTTP de autores y libros asociados."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from ..controllers import authors
from ..core.dependencies import Pagination, SessionDep, get_pagination
from ..models import Autor, Libro
from ..schemas.autor import AutorCreate, AutorPatch, AutorRead
from ..schemas.libro import LibroRead

router = APIRouter(prefix="/autores", tags=["autores"])
PaginationQuery = Annotated[Pagination, Depends(get_pagination)]


@router.get("", response_model=list[AutorRead])
def listar_autores(
    db: SessionDep,
    pagination: PaginationQuery,
    nacionalidad: str | None = None,
) -> list[Autor]:
    """Devuelve autores paginados, con filtro opcional por nacionalidad."""
    return authors.list_authors(db, pagination, nacionalidad)


@router.get("/{autor_id}", response_model=AutorRead)
def obtener_autor(autor_id: int, db: SessionDep) -> Autor:
    """Devuelve el autor identificado por su ID."""
    return authors.get_author(autor_id, db)


@router.get("/{autor_id}/libros", response_model=list[LibroRead])
def listar_libros_autor(
    autor_id: int, db: SessionDep, pagination: PaginationQuery
) -> list[Libro]:
    """Devuelve la página de libros asociada al autor."""
    return authors.list_author_books(autor_id, db, pagination)


@router.post("", response_model=AutorRead, status_code=status.HTTP_201_CREATED)
def crear_autor(data: AutorCreate, db: SessionDep) -> Autor:
    """Registra un autor y devuelve el recurso creado."""
    return authors.create_author(data, db)


@router.patch("/{autor_id}", response_model=AutorRead)
def actualizar_autor(autor_id: int, data: AutorPatch, db: SessionDep) -> Autor:
    """Modifica los campos enviados del autor."""
    return authors.patch_author(autor_id, data, db)


@router.delete("/{autor_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_autor(autor_id: int, db: SessionDep) -> Response:
    """Elimina un autor sin libros asociados."""
    authors.delete_author(autor_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
