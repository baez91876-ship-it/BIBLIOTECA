"""Modelo ORM de los libros y sus relaciones de catálogo y préstamos."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from .categoria import libro_categoria

if TYPE_CHECKING:
    from .autor import Autor
    from .categoria import Categoria
    from .prestamo import Prestamo


class Libro(Base):
    """Libro catalogado con autor, categorías, ejemplares y préstamos."""

    __tablename__ = "libros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(150), nullable=False)
    isbn: Mapped[str] = mapped_column(String(13), nullable=False, unique=True)
    anio_publicacion: Mapped[int] = mapped_column(Integer, nullable=False)
    ejemplares: Mapped[int] = mapped_column(Integer, nullable=False)
    autor_id: Mapped[int] = mapped_column(
        ForeignKey("autores.id", ondelete="RESTRICT"), nullable=False
    )

    autor: Mapped["Autor"] = relationship(back_populates="libros")
    categorias: Mapped[list["Categoria"]] = relationship(
        secondary=libro_categoria, back_populates="libros"
    )
    prestamos: Mapped[list["Prestamo"]] = relationship(back_populates="libro")

    @property
    def disponibles(self) -> int:
        """Calcula los ejemplares disponibles descontando préstamos abiertos."""
        return self.ejemplares - sum(
            prestamo.fecha_devolucion is None for prestamo in self.prestamos
        )
