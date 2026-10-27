"""Esquemas de validación y serialización de préstamos."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .libro import LibroRead
from .socio import SocioRead


class EstadoPrestamo(str, Enum):
    """Estados posibles de un préstamo según sus fechas."""

    activo = "activo"
    vencido = "vencido"
    devuelto = "devuelto"


class PrestamoCreate(BaseModel):
    """Datos de entrada para abrir un préstamo."""

    libro_id: int = Field(gt=0)
    socio_id: int = Field(gt=0)
    fecha_prestamo: date | None = None
    dias: int = Field(default=14, ge=1, le=30)


class DevolucionCreate(BaseModel):
    """Fecha efectiva de devolución; hoy se usa si no se especifica."""

    fecha_devolucion: date = Field(default_factory=date.today)


class PrestamoPatch(BaseModel):
    """Único dato editable de un préstamo todavía abierto."""

    fecha_limite: date


class PrestamoRead(BaseModel):
    """Préstamo de respuesta con el libro, el socio y el estado."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    libro_id: int
    socio_id: int
    fecha_prestamo: date
    fecha_limite: date
    fecha_devolucion: date | None
    multa: float
    estado: EstadoPrestamo
    libro: LibroRead
    socio: SocioRead
