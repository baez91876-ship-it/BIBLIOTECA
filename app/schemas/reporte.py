"""Esquemas de respuesta para los reportes agregados."""

from datetime import date

from pydantic import BaseModel


class LibroMasPrestado(BaseModel):
    """Fila del ranking de libros más prestados."""

    libro_id: int
    titulo: str
    autor: str
    total_prestamos: int


class CategoriaReporte(BaseModel):
    """Cantidad de libros asociada a una categoría."""

    categoria_id: int
    nombre: str
    total_libros: int


class PrestamoVencido(BaseModel):
    """Préstamo abierto vencido con sus días de retraso."""

    prestamo_id: int
    titulo: str
    socio: str
    email: str
    fecha_limite: date
    dias_retraso: int


class SocioMultas(BaseModel):
    """Totales de multas e incidencias de un socio."""

    socio_id: int
    nombre: str
    email: str
    total_multas: float
    prestamos_con_multa: int


class AutorReporte(BaseModel):
    """Totales de libros, ejemplares y préstamos de un autor."""

    autor_id: int
    nombre: str
    total_libros: int
    total_ejemplares: int
    total_prestamos: int


class ResumenReporte(BaseModel):
    """Indicadores generales de actividad de la biblioteca."""

    total_libros: int
    total_ejemplares: int
    prestamos_activos: int
    socios_activos: int
    prestamos_vencidos: int
    multas_totales: float
