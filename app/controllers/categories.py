"""Consultas y reglas de negocio para categorías."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.dependencies import Pagination
from ..core.exceptions import Conflicto, NoEncontrado
from ..models import Categoria
from ..schemas.categoria import CategoriaCreate, CategoriaPatch


def list_categories(db: Session, pagination: Pagination) -> list[Categoria]:
    """Lista categorías con orden estable y paginación."""
    return db.scalars(
        select(Categoria)
        .order_by(Categoria.nombre, Categoria.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    ).all()


def get_category(category_id: int, db: Session) -> Categoria:
    """Obtiene una categoría o informa que no existe."""
    category = db.get(Categoria, category_id)
    if category is None:
        raise NoEncontrado("Categoría no encontrada")
    return category


def create_category(data: CategoriaCreate, db: Session) -> Categoria:
    """Crea una categoría y evita nombres repetidos."""
    if db.scalar(select(Categoria.id).where(Categoria.nombre == data.nombre)):
        raise Conflicto("La categoría ya existe")
    category = Categoria(**data.model_dump())
    db.add(category)
    _commit(db)
    db.refresh(category)
    return category


def patch_category(category_id: int, data: CategoriaPatch, db: Session) -> Categoria:
    """Actualiza los campos enviados y conserva la unicidad del nombre."""
    category = get_category(category_id, db)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("nombre") is not None:
        duplicate = db.scalar(
            select(Categoria.id).where(
                Categoria.nombre == changes["nombre"], Categoria.id != category_id
            )
        )
        if duplicate:
            raise Conflicto("La categoría ya existe")
    for field, value in changes.items():
        setattr(category, field, value)
    _commit(db)
    db.refresh(category)
    return category


def delete_category(category_id: int, db: Session) -> None:
    """Elimina la categoría y desasocia sus libros sin borrarlos."""
    category = get_category(category_id, db)
    category.libros.clear()
    db.delete(category)
    db.commit()


def _commit(db: Session) -> None:
    """Revierte la transacción y traduce nombres duplicados a conflicto."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto("La categoría ya existe") from exc
