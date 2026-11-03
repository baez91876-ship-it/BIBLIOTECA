"""Endpoints HTTP para consultar y gestionar préstamos y devoluciones."""

from fastapi import APIRouter, Query, Request, Response, status

from ..controllers import loans
from ..core.dependencies import ApiUserDep, PaginationDep, SessionDep
from ..core.exceptions import NoEncontrado, Prohibido
from ..models import Prestamo
from ..schemas.pagination import Pagina, crear_pagina
from ..schemas.prestamo import (
    DevolucionCreate,
    EstadoPrestamo,
    PrestamoCreate,
    PrestamoPatch,
    PrestamoRead,
)

router = APIRouter(prefix="/prestamos", tags=["prestamos"])


@router.get("", response_model=list[PrestamoRead] | Pagina[PrestamoRead])
def listar_prestamos(
    request: Request,
    db: SessionDep,
    pagination: PaginationDep,
    user: ApiUserDep,
    estado: EstadoPrestamo | None = None,
    socio_id: int | None = Query(default=None, gt=0),
    libro_id: int | None = Query(default=None, gt=0),
) -> list[Prestamo] | Pagina[PrestamoRead]:
    """Lista préstamos aplicando filtros opcionales."""
    owner_id = user.socio_id if user is not None and user.rol == "socio" else None
    if owner_id is not None:
        socio_id = owner_id
    elif user is not None and user.rol == "socio":
        if request.url.path.startswith("/api/v1/"):
            return crear_pagina([], 0, pagination.skip, pagination.limit)
        return []
    if request.url.path.startswith("/api/v1/"):
        items, total = loans.list_loans(
            db,
            pagination,
            estado,
            socio_id,
            libro_id,
            owner_id,
            include_total=True,
        )
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return loans.list_loans(db, pagination, estado, socio_id, libro_id, owner_id)


@router.get("/{prestamo_id}", response_model=PrestamoRead)
def obtener_prestamo(prestamo_id: int, db: SessionDep, user: ApiUserDep) -> Prestamo:
    """Devuelve el préstamo identificado por su ID."""
    owner_id = user.socio_id if user is not None and user.rol == "socio" else None
    if user is not None and user.rol == "socio" and owner_id is None:
        raise NoEncontrado("Préstamo no encontrado")
    return loans.get_loan(prestamo_id, db, owner_id)


@router.post("", response_model=PrestamoRead, status_code=status.HTTP_201_CREATED)
def crear_prestamo(data: PrestamoCreate, db: SessionDep, user: ApiUserDep) -> Prestamo:
    """Abre un préstamo si el socio y el libro cumplen las reglas de negocio."""
    if (
        user is not None
        and user.rol == "socio"
        and (user.socio_id is None or data.socio_id != user.socio_id)
    ):
        raise Prohibido("Solo puedes solicitar préstamos para tu propia cuenta")
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
