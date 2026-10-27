"""Esquemas Pydantic para validar solicitudes y respuestas de la API."""

from .autor import AutorCreate, AutorPatch, AutorRead
from .categoria import CategoriaCreate, CategoriaPatch, CategoriaRead
from .libro import LibroCreate, LibroPatch, LibroRead
from .prestamo import (
    DevolucionCreate,
    EstadoPrestamo,
    PrestamoCreate,
    PrestamoPatch,
    PrestamoRead,
)
from .reporte import (
    AutorReporte,
    CategoriaReporte,
    LibroMasPrestado,
    PrestamoVencido,
    ResumenReporte,
    SocioMultas,
)
from .socio import SocioCreate, SocioPatch, SocioRead

__all__ = [
    "AutorCreate",
    "AutorPatch",
    "AutorRead",
    "AutorReporte",
    "CategoriaCreate",
    "CategoriaPatch",
    "CategoriaRead",
    "CategoriaReporte",
    "DevolucionCreate",
    "EstadoPrestamo",
    "LibroCreate",
    "LibroMasPrestado",
    "LibroPatch",
    "LibroRead",
    "PrestamoCreate",
    "PrestamoPatch",
    "PrestamoRead",
    "PrestamoVencido",
    "ResumenReporte",
    "SocioCreate",
    "SocioMultas",
    "SocioPatch",
    "SocioRead",
]
