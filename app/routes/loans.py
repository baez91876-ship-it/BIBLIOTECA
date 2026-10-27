"""Endpoints HTTP para consultar y gestionar préstamos y devoluciones."""

from fastapi import APIRouter, Query, Response, status

from ..controllers import loans
from ..core.dependencies import PaginationDep, SessionDep
from ..models import Prestamo
from ..schemas.prestamo import (
    DevolucionCreate,
    EstadoPrestamo,
    PrestamoCreate,
    PrestamoPatch,
    PrestamoRead,
)

router = APIRouter(prefix="/prestamos", tags=["prestamos"])


@router.get("", response_model=list[PrestamoRead])
def listar_prestamos(
    db: SessionDep,
    pagination: PaginationDep,
    estado: EstadoPrestamo | None = None,
    socio_id: int | None = Query(default=None, gt=0),
    libro_id: int | None = Query(default=None, gt=0),
) -> list[Prestamo]:
    """Lista préstamos aplicando filtros opcionales."""
    return loans.list_loans(db, pagination, estado, socio_id, libro_id)


@router.get("/{prestamo_id}", response_model=PrestamoRead)
def obtener_prestamo(prestamo_id: int, db: SessionDep) -> Prestamo:
    """Devuelve el préstamo identificado por su ID."""
    return loans.get_loan(prestamo_id, db)


@router.post("", response_model=PrestamoRead, status_code=status.HTTP_201_CREATED)
def crear_prestamo(data: PrestamoCreate, db: SessionDep) -> Prestamo:
    """Abre un préstamo si el socio y el libro cumplen las reglas de negocio."""
    return loans.create_loan(data, db)


@router.post("/{prestamo_id}/devolucion", response_model=PrestamoRead)
def devolver_prestamo(
    prestamo_id: int, data: DevolucionCreate, db: SessionDep
) -> Prestamo:
    """Registra la devolución y la multa que corresponda."""
    return loans.return_loan(prestamo_id, data, db)


@router.patch("/{prestamo_id}", response_model=PrestamoRead)
def actualizar_prestamo(
    prestamo_id: int, data: PrestamoPatch, db: SessionDep
) -> Prestamo:
    """Actualiza la fecha límite de un préstamo todavía abierto."""
    return loans.patch_loan(prestamo_id, data, db)


@router.delete("/{prestamo_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_prestamo(prestamo_id: int, db: SessionDep) -> Response:
    """Elimina un préstamo abierto, no su historial ya devuelto."""
    loans.delete_loan(prestamo_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
