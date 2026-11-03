"""Modelo ORM de categorías y asociación con los libros."""

from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base

if TYPE_CHECKING:
    from .libro import Libro


libro_categoria = Table(
    # La clave compuesta impide asociar dos veces el mismo libro y categoría.
    "libro_categoria",
    Base.metadata,
    Column("libro_id", ForeignKey("libros.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "categoria_id",
        ForeignKey("categorias.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Categoria(Base):
    """Categoría temática asignable a varios libros."""

    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(200))

    libros: Mapped[list["Libro"]] = relationship(
        secondary=libro_categoria, back_populates="categorias"
    )
