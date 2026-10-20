from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from ..controllers import books
from ..core.dependencies import PaginationDep, SessionDep
from ..models import Libro
from ..schemas.libro import LibroCreate, LibroPatch, LibroRead

router = APIRouter(prefix="/libros", tags=["libros"])


@router.get("", response_model=list[LibroRead])
def listar_libros(
    db: SessionDep,
    pagination: PaginationDep,
    buscar: str | None = None,
    autor: str | None = None,
    categoria_id: int | None = Query(default=None, gt=0),
    desde: int | None = Query(default=None, ge=1450),
    hasta: int | None = Query(default=None, ge=1450),
    orden: books.OrdenLibro = books.OrdenLibro.titulo,
) -> list[Libro]:
    return books.list_books(
        db, pagination, buscar, autor, categoria_id, desde, hasta, orden
    )


@router.get("/{libro_id}", response_model=LibroRead)
def obtener_libro(libro_id: int, db: SessionDep) -> Libro:
    return books.get_book(libro_id, db)


@router.post("", response_model=LibroRead, status_code=status.HTTP_201_CREATED)
def crear_libro(data: LibroCreate, db: SessionDep) -> Libro:
    return books.create_book(data, db)


@router.patch("/{libro_id}", response_model=LibroRead)
def actualizar_libro(libro_id: int, data: LibroPatch, db: SessionDep) -> Libro:
    return books.patch_book(libro_id, data, db)


@router.delete("/{libro_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_libro(libro_id: int, db: SessionDep) -> Response:
    books.delete_book(libro_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
