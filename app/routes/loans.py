from fastapi import APIRouter, Query, status

from ..controllers import loans
from ..core.dependencies import PaginationDep, SessionDep
from ..models import Prestamo
from ..schemas.prestamo import (
    DevolucionCreate,
    EstadoPrestamo,
    PrestamoCreate,
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
    return loans.list_loans(db, pagination, estado, socio_id, libro_id)


@router.get("/{prestamo_id}", response_model=PrestamoRead)
def obtener_prestamo(prestamo_id: int, db: SessionDep) -> Prestamo:
    return loans.get_loan(prestamo_id, db)


@router.post("", response_model=PrestamoRead, status_code=status.HTTP_201_CREATED)
def crear_prestamo(data: PrestamoCreate, db: SessionDep) -> Prestamo:
    return loans.create_loan(data, db)


@router.post("/{prestamo_id}/devolucion", response_model=PrestamoRead)
def devolver_prestamo(
    prestamo_id: int, data: DevolucionCreate, db: SessionDep
) -> Prestamo:
    return loans.return_loan(prestamo_id, data, db)
