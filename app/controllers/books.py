"""Consultas, filtros y reglas de negocio para libros del catálogo."""

from enum import Enum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..core.dependencies import Pagination
from ..core.exceptions import Conflicto, NoEncontrado, ReglaNegocio
from ..models import Autor, Categoria, Libro, Prestamo
from ..schemas.libro import LibroCreate, LibroPatch


class OrdenLibro(str, Enum):
    """Criterios admitidos para ordenar el catálogo."""

    titulo = "titulo"
    anio = "anio"
    anio_desc = "-anio"


def _libro_con_relaciones():
    """Carga las relaciones necesarias para serializar un libro sin consultas extra."""
    return (
        selectinload(Libro.autor),
        selectinload(Libro.categorias),
        selectinload(Libro.prestamos),
    )


def list_books(
    db: Session,
    pagination: Pagination,
    buscar: str | None = None,
    autor: str | None = None,
    categoria_id: int | None = None,
    desde: int | None = None,
    hasta: int | None = None,
    orden: OrdenLibro = OrdenLibro.titulo,
) -> list[Libro]:
    """Combina filtros del catálogo y devuelve una página ordenada."""
    if desde is not None and hasta is not None and desde > hasta:
        raise ReglaNegocio("'desde' no puede ser mayor que 'hasta'")
    query = select(Libro).options(*_libro_con_relaciones())
    if buscar:
        query = query.where(Libro.titulo.ilike(f"%{buscar.strip()}%"))
    if autor:
        query = query.join(Libro.autor).where(Autor.nombre.ilike(f"%{autor.strip()}%"))
    if categoria_id is not None:
        query = query.join(Libro.categorias).where(Categoria.id == categoria_id)
    if desde is not None:
        query = query.where(Libro.anio_publicacion >= desde)
    if hasta is not None:
        query = query.where(Libro.anio_publicacion <= hasta)
    query = query.distinct()
    if orden == OrdenLibro.anio:
        query = query.order_by(Libro.anio_publicacion, Libro.id)
    elif orden == OrdenLibro.anio_desc:
        query = query.order_by(Libro.anio_publicacion.desc(), Libro.id)
    else:
        query = query.order_by(Libro.titulo, Libro.id)
    return (
        db.scalars(query.offset(pagination.skip).limit(pagination.limit)).unique().all()
    )


def get_book(book_id: int, db: Session) -> Libro:
    """Obtiene un libro con sus relaciones o informa que no existe."""
    book = db.scalar(
        select(Libro).where(Libro.id == book_id).options(*_libro_con_relaciones())
    )
    if book is None:
        raise NoEncontrado("Libro no encontrado")
    return book


def create_book(data: LibroCreate, db: Session) -> Libro:
    """Crea un libro tras comprobar el autor, categorías e ISBN."""
    _validate_author_and_categories(db, data.autor_id, data.categoria_ids)
    if db.scalar(select(Libro.id).where(Libro.isbn == data.isbn)):
        raise Conflicto("El ISBN ya está registrado")
    changes = data.model_dump()
    category_ids = changes.pop("categoria_ids")
    book = Libro(**changes)
    book.categorias = list(
        db.scalars(select(Categoria).where(Categoria.id.in_(category_ids))).all()
    )
    db.add(book)
    _commit(db, "El ISBN ya está registrado")
    return get_book(book.id, db)


def patch_book(book_id: int, data: LibroPatch, db: Session) -> Libro:
    """Actualiza campos enviados y conserva ejemplares suficientes para préstamos."""
    book = get_book(book_id, db)
    changes = data.model_dump(exclude_unset=True)
    author_id = changes.get("autor_id", book.autor_id)
    category_ids = changes.pop("categoria_ids", None)
    _validate_author_and_categories(db, author_id, category_ids or [])
    isbn = changes.get("isbn")
    if isbn and db.scalar(
        select(Libro.id).where(Libro.isbn == isbn, Libro.id != book_id)
    ):
        raise Conflicto("El ISBN ya está registrado")
    if "autor_id" in changes:
        book.autor_id = changes.pop("autor_id")
    for field, value in changes.items():
        if value is not None:
            setattr(book, field, value)
    if category_ids is not None:
        book.categorias = list(
            db.scalars(select(Categoria).where(Categoria.id.in_(category_ids))).all()
        )
    active_loans = _active_loan_count(db, book.id)
    if book.ejemplares < active_loans:
        raise ReglaNegocio(
            "Los ejemplares no pueden ser menores que los préstamos sin devolver"
        )
    _commit(db, "El ISBN ya está registrado")
    return get_book(book.id, db)


def delete_book(book_id: int, db: Session) -> None:
    """Impide borrar libros con préstamos abiertos o historial asociado."""
    book = get_book(book_id, db)
    if _active_loan_count(db, book_id):
        raise Conflicto("No se puede eliminar un libro con préstamos sin devolver")
    if db.scalar(select(Prestamo.id).where(Prestamo.libro_id == book_id)):
        raise Conflicto("No se puede eliminar un libro con historial de préstamos")
    db.delete(book)
    db.commit()


def _active_loan_count(db: Session, book_id: int) -> int:
    """Cuenta préstamos todavía no devueltos para un libro."""
    return (
        db.query(Prestamo)
        .filter(Prestamo.libro_id == book_id, Prestamo.fecha_devolucion.is_(None))
        .count()
    )


def _validate_author_and_categories(
    db: Session, author_id: int, category_ids: list[int]
) -> None:
    """Valida que existan el autor y todas las categorías, sin duplicados."""
    if db.get(Autor, author_id) is None:
        raise NoEncontrado("Autor no encontrado")
    if len(category_ids) != len(set(category_ids)):
        raise ReglaNegocio("No se permiten categorías repetidas")
    found_ids = set(
        db.scalars(select(Categoria.id).where(Categoria.id.in_(category_ids))).all()
    )
    missing_ids = set(category_ids) - found_ids
    if missing_ids:
        raise NoEncontrado(
            "Categorías no encontradas: " + ", ".join(map(str, sorted(missing_ids)))
        )


def _commit(db: Session, duplicate_message: str) -> None:
    """Revierte la transacción y traduce restricciones de unicidad."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto(duplicate_message) from exc
