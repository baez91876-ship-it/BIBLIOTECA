"""Modelo ORM de los préstamos y su estado derivado."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class Prestamo(Base):
    """Préstamo de un libro a un socio, con fechas e importe de multa."""

    __tablename__ = "prestamos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    libro_id: Mapped[int] = mapped_column(
        ForeignKey("libros.id", ondelete="RESTRICT"), nullable=False
    )
    socio_id: Mapped[int] = mapped_column(
        ForeignKey("socios.id", ondelete="RESTRICT"), nullable=False
    )
    fecha_prestamo: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    fecha_limite: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_devolucion: Mapped[date | None] = mapped_column(Date)
    multa: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0"), server_default="0"
    )

    libro: Mapped["Libro"] = relationship(back_populates="prestamos")
    socio: Mapped["Socio"] = relationship(back_populates="prestamos")

    @property
    def estado(self) -> str:
        """Deriva el estado a partir de la devolución y la fecha límite."""
        if self.fecha_devolucion is not None:
            return "devuelto"
        if self.fecha_limite < date.today():
            return "vencido"
        return "activo"
