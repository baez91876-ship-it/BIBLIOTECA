"""Modelo ORM de los socios y su historial de préstamos."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base

if TYPE_CHECKING:
    from .prestamo import Prestamo


class Socio(Base):
    """Socio de la biblioteca, conservado si tiene historial."""

    __tablename__ = "socios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    telefono: Mapped[str | None] = mapped_column(String(15))
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    fecha_alta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    prestamos: Mapped[list["Prestamo"]] = relationship(back_populates="socio")
