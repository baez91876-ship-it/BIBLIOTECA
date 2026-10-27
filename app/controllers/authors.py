"""Consultas y reglas de negocio para autores y sus libros."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.dependencies import Pagination
from ..core.exceptions import Conflicto, NoEncontrado
from ..core.pagination import execute_page
from ..models import Autor, Libro
from ..schemas.autor import AutorCreate, AutorPatch


def list_authors(
    db: Session,
    pagination: Pagination,
    nacionalidad: str | None = None,
    include_total: bool = False,
) -> list[Autor] | tuple[list[Autor], int]:
    """Lista autores en orden estable y filtra opcionalmente por nacionalidad."""
    query = select(Autor).order_by(Autor.nombre, Autor.id)
    if nacionalidad:
        query = query.where(Autor.nacionalidad.ilike(f"%{nacionalidad.strip()}%"))
    if include_total:
        return execute_page(db, query, pagination)
    return db.scalars(query.offset(pagination.skip).limit(pagination.limit)).all()


def get_author(author_id: int, db: Session) -> Autor:
    """Obtiene un autor o informa que no existe."""
    author = db.get(Autor, author_id)
    if author is None:
        raise NoEncontrado("Autor no encontrado")
    return author


def list_author_books(
    author_id: int,
    db: Session,
    pagination: Pagination,
    include_total: bool = False,
) -> list[Libro] | tuple[list[Libro], int]:
    """Lista los libros de un autor después de validar que exista."""
    get_author(author_id, db)
    query = (
        select(Libro)
        .where(Libro.autor_id == author_id)
        .options(
            selectinload(Libro.autor),
            selectinload(Libro.categorias),
            selectinload(Libro.prestamos),
        )
        .order_by(Libro.titulo, Libro.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    if include_total:
        return execute_page(db, query, pagination)
    return db.scalars(query).all()


def create_author(data: AutorCreate, db: Session) -> Autor:
    """Crea un autor y traduce conflictos de unicidad a un error de dominio."""
    if db.scalar(select(Autor.id).where(Autor.nombre == data.nombre)):
        raise Conflicto("El autor ya existe")
    author = Autor(**data.model_dump())
    db.add(author)
    _commit(db, "El autor ya existe")
    db.refresh(author)
    return author


def patch_author(author_id: int, data: AutorPatch, db: Session) -> Autor:
    """Actualiza solo los campos enviados y protege la unicidad del nombre."""
    author = get_author(author_id, db)
    changes = data.model_dump(exclude_unset=True)
    if "nombre" in changes and changes["nombre"] is not None:
        duplicate = db.scalar(
            select(Autor.id).where(
                Autor.nombre == changes["nombre"], Autor.id != author_id
            )
        )
        if duplicate:
            raise Conflicto("El autor ya existe")
    for field, value in changes.items():
        setattr(author, field, value)
    _commit(db, "El autor ya existe")
    db.refresh(author)
    return author


def delete_author(author_id: int, db: Session) -> None:
    """Elimina un autor únicamente si no tiene libros asociados."""
    author = get_author(author_id, db)
    if author.libros:
        raise Conflicto("No se puede eliminar un autor que tiene libros")
    db.delete(author)
    db.commit()


def _commit(db: Session, duplicate_message: str) -> None:
    """Revierte la transacción y traduce restricciones de unicidad."""
    from sqlalchemy.exc import IntegrityError

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto(duplicate_message) from exc
