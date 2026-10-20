from datetime import date

from pydantic import BaseModel


class LibroMasPrestado(BaseModel):
    libro_id: int
    titulo: str
    autor: str
    total_prestamos: int


class CategoriaReporte(BaseModel):
    categoria_id: int
    nombre: str
    total_libros: int


class PrestamoVencido(BaseModel):
    prestamo_id: int
    titulo: str
    socio: str
    email: str
    fecha_limite: date
    dias_retraso: int


class SocioMultas(BaseModel):
    socio_id: int
    nombre: str
    email: str
    total_multas: float
    prestamos_con_multa: int


class AutorReporte(BaseModel):
    autor_id: int
    nombre: str
    total_libros: int
    total_ejemplares: int
    total_prestamos: int


class ResumenReporte(BaseModel):
    total_libros: int
    total_ejemplares: int
    prestamos_activos: int
    socios_activos: int
    prestamos_vencidos: int
    multas_totales: float
