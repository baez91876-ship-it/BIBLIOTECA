"""Endpoints HTTP para socios y consultas de su historial de préstamos."""

from fastapi import APIRouter, Response, status

from ..controllers import members
from ..core.dependencies import PaginationDep, SessionDep
from ..models import Prestamo, Socio
from ..schemas.prestamo import EstadoPrestamo, PrestamoRead
from ..schemas.socio import SocioCreate, SocioPatch, SocioRead

router = APIRouter(prefix="/socios", tags=["socios"])


@router.get("", response_model=list[SocioRead])
def listar_socios(
    db: SessionDep, pagination: PaginationDep, activo: bool | None = None
) -> list[Socio]:
    """Lista socios paginados y permite filtrar por estado."""
    return members.list_members(db, pagination, activo)


@router.get("/{socio_id}", response_model=SocioRead)
def obtener_socio(socio_id: int, db: SessionDep) -> Socio:
    """Devuelve el socio identificado por su ID."""
    return members.get_member(socio_id, db)


@router.get("/{socio_id}/prestamos", response_model=list[PrestamoRead])
def listar_prestamos_socio(
    socio_id: int,
    db: SessionDep,
    pagination: PaginationDep,
    estado: EstadoPrestamo | None = None,
) -> list[Prestamo]:
    """Devuelve préstamos del socio, opcionalmente filtrados por estado."""
    return members.list_member_loans(socio_id, db, pagination, estado)


@router.post("", response_model=SocioRead, status_code=status.HTTP_201_CREATED)
def crear_socio(data: SocioCreate, db: SessionDep) -> Socio:
    """Registra un socio y devuelve el recurso creado."""
    return members.create_member(data, db)


@router.patch("/{socio_id}", response_model=SocioRead)
def actualizar_socio(socio_id: int, data: SocioPatch, db: SessionDep) -> Socio:
    """Modifica los campos enviados del socio."""
    return members.patch_member(socio_id, data, db)


@router.delete("/{socio_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_socio(socio_id: int, db: SessionDep) -> Response:
    """Elimina al socio o lo desactiva si conserva historial."""
    members.delete_member(socio_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
