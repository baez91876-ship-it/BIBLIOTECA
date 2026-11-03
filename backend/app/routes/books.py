"""Endpoints HTTP para consultar y administrar el catálogo de libros."""

from fastapi import APIRouter, Depends, Query, Request, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ..controllers import books
from ..core.covers import MAX_COVER_BYTES
from ..core.dependencies import PaginationDep, SessionDep, requiere_rol
from ..core.exceptions import ReglaNegocio
from ..core.roles import Rol
from ..models import Libro
from ..schemas.libro import LibroCreate, LibroPatch, LibroRead
from ..schemas.pagination import Pagina, crear_pagina

router = APIRouter(prefix="/libros", tags=["libros"])


@router.get("", response_model=list[LibroRead] | Pagina[LibroRead])
def listar_libros(
    request: Request,
    db: SessionDep,
    pagination: PaginationDep,
    buscar: str | None = None,
    autor: str | None = None,
    categoria_id: int | None = Query(default=None, gt=0),
    desde: int | None = Query(default=None, ge=1450),
    hasta: int | None = Query(default=None, ge=1450),
    orden: books.OrdenLibro = books.OrdenLibro.titulo,
) -> list[Libro] | Pagina[LibroRead]:
    """Lista libros con filtros combinables y orden configurable."""
    if request.url.path.startswith("/api/v1/"):
        items, total = books.list_books(
            db, pagination, buscar, autor, categoria_id, desde, hasta, orden,
            include_total=True,
        )
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return books.list_books(
        db, pagination, buscar, autor, categoria_id, desde, hasta, orden
    )


@router.get("/{libro_id}", response_model=LibroRead)
def obtener_libro(libro_id: int, db: SessionDep) -> Libro:
    """Devuelve el libro identificado por su ID."""
    return books.get_book(libro_id, db)


@router.post("", response_model=LibroRead, status_code=status.HTTP_201_CREATED)
def crear_libro(data: LibroCreate, db: SessionDep) -> Libro:
    """Registra un libro y devuelve el recurso creado."""
    return books.create_book(data, db)


@router.patch("/{libro_id}", response_model=LibroRead)
def actualizar_libro(libro_id: int, data: LibroPatch, db: SessionDep) -> Libro:
    """Modifica los campos enviados del libro."""
    return books.patch_book(libro_id, data, db)


@router.post(
    "/{libro_id}/portada", response_model=LibroRead,
    dependencies=[Depends(requiere_rol(Rol.bibliotecario, Rol.administrador))],
)
async def subir_portada(libro_id: int, archivo: UploadFile, db: SessionDep) -> Libro:
    """Sube una imagen limitada y validada, solo para personal autenticado."""
    try:
        data = await archivo.read(MAX_COVER_BYTES + 1)
    finally:
        await archivo.close()
    if len(data) > MAX_COVER_BYTES:
        raise ReglaNegocio("La portada no puede superar 5 MiB.")
    return await run_in_threadpool(books.set_book_cover, libro_id, data, db)


@router.delete("/{libro_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_libro(libro_id: int, db: SessionDep) -> Response:
    """Elimina un libro si no tiene préstamos asociados."""
    books.delete_book(libro_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
