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
    "CategoriaCreate",
    "CategoriaPatch",
    "CategoriaRead",
    "LibroCreate",
    "LibroPatch",
    "LibroRead",
    "SocioCreate",
    "SocioPatch",
    "SocioRead",
    "PrestamoCreate",
    "PrestamoPatch",
    "PrestamoRead",
    "DevolucionCreate",
    "EstadoPrestamo",
    "LibroMasPrestado",
    "CategoriaReporte",
    "PrestamoVencido",
    "SocioMultas",
    "AutorReporte",
    "ResumenReporte",
]
"""Esquemas Pydantic para validar solicitudes y respuestas de la API."""
