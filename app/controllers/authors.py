from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.dependencies import Pagination
from ..core.exceptions import Conflicto, NoEncontrado
from ..models import Autor, Libro
from ..schemas.autor import AutorCreate, AutorPatch


def list_authors(
    db: Session, pagination: Pagination, nacionalidad: str | None = None
) -> list[Autor]:
    query = select(Autor).order_by(Autor.nombre, Autor.id)
    if nacionalidad:
        query = query.where(Autor.nacionalidad.ilike(f"%{nacionalidad.strip()}%"))
    return db.scalars(query.offset(pagination.skip).limit(pagination.limit)).all()


def get_author(author_id: int, db: Session) -> Autor:
    author = db.get(Autor, author_id)
    if author is None:
        raise NoEncontrado("Autor no encontrado")
    return author


def list_author_books(author_id: int, db: Session, pagination: Pagination):
    get_author(author_id, db)
    return db.scalars(
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
    ).all()


def create_author(data: AutorCreate, db: Session) -> Autor:
    if db.scalar(select(Autor.id).where(Autor.nombre == data.nombre)):
        raise Conflicto("El autor ya existe")
    author = Autor(**data.model_dump())
    db.add(author)
    _commit(db, "El autor ya existe")
    db.refresh(author)
    return author


def patch_author(author_id: int, data: AutorPatch, db: Session) -> Autor:
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
    author = get_author(author_id, db)
    if author.libros:
        raise Conflicto("No se puede eliminar un autor que tiene libros")
    db.delete(author)
    db.commit()


def _commit(db: Session, duplicate_message: str) -> None:
    from sqlalchemy.exc import IntegrityError

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto(duplicate_message) from exc
