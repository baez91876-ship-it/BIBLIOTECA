"""Endpoints HTTP para socios y consultas de su historial de préstamos."""

from fastapi import APIRouter, Request, Response, status

from ..controllers import members
from ..core.dependencies import ApiUserDep, PaginationDep, SessionDep
from ..core.exceptions import NoEncontrado, ReglaNegocio
from ..models import Prestamo, Socio
from ..schemas.prestamo import EstadoPrestamo, PrestamoRead
from ..schemas.pagination import Pagina, crear_pagina
from ..schemas.socio import SocioCreate, SocioPatch, SocioRead

router = APIRouter(prefix="/socios", tags=["socios"])


@router.get("", response_model=list[SocioRead] | Pagina[SocioRead])
def listar_socios(
    request: Request,
    db: SessionDep,
    pagination: PaginationDep,
    user: ApiUserDep,
    activo: bool | None = None,
) -> list[Socio] | Pagina[SocioRead]:
    """Lista socios paginados y permite filtrar por estado."""
    owner_id = user.socio_id if user is not None and user.rol == "socio" else None
    if user is not None and user.rol == "socio":
        if owner_id is None:
            return []
        activo = None
    if request.url.path.startswith("/api/v1/"):
        items, total = members.list_members(
            db, pagination, activo, owner_id, include_total=True
        )
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return members.list_members(db, pagination, activo, owner_id)


@router.get("/{socio_id}", response_model=SocioRead)
def obtener_socio(socio_id: int, db: SessionDep, user: ApiUserDep) -> Socio:
    """Devuelve el socio identificado por su ID."""
    owner_id = user.socio_id if user is not None and user.rol == "socio" else None
    if user is not None and user.rol == "socio" and owner_id is None:
        raise NoEncontrado("Socio no encontrado")
    return members.get_member(socio_id, db, owner_id)


@router.get(
    "/{socio_id}/prestamos",
    response_model=list[PrestamoRead] | Pagina[PrestamoRead],
)
def listar_prestamos_socio(
    socio_id: int,
    request: Request,
    db: SessionDep,
    pagination: PaginationDep,
    user: ApiUserDep,
    estado: EstadoPrestamo | None = None,
) -> list[Prestamo] | Pagina[PrestamoRead]:
    """Devuelve préstamos del socio, opcionalmente filtrados por estado."""
    owner_id = user.socio_id if user is not None and user.rol == "socio" else None
    if user is not None and user.rol == "socio" and owner_id is None:
        raise NoEncontrado("Socio no encontrado")
    if request.url.path.startswith("/api/v1/"):
        items, total = members.list_member_loans(
            socio_id,
            db,
            pagination,
            estado,
            owner_id,
            include_total=True,
        )
        return crear_pagina(items, total, pagination.skip, pagination.limit)
    return members.list_member_loans(socio_id, db, pagination, estado, owner_id)


@router.post("", response_model=SocioRead, status_code=status.HTTP_201_CREATED)
def crear_socio(data: SocioCreate, db: SessionDep) -> Socio:
    """Registra un socio y devuelve el recurso creado."""
    return members.create_member(data, db)


@router.patch("/{socio_id}", response_model=SocioRead)
def actualizar_socio(
    socio_id: int,
    data: SocioPatch,
    db: SessionDep,
    user: ApiUserDep,
) -> Socio:
    """Modifica los campos enviados del socio."""
    if user is not None and user.rol == "socio":
        if user.socio_id != socio_id:
            raise NoEncontrado("Socio no encontrado")
        if "activo" in data.model_fields_set:
            raise ReglaNegocio("El socio no puede modificar su estado activo")
    return members.patch_member(socio_id, data, db)


@router.delete("/{socio_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_socio(socio_id: int, db: SessionDep) -> Response:
    """Elimina al socio o lo desactiva si conserva historial."""
    members.delete_member(socio_id, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
