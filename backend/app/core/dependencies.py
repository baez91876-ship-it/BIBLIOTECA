"""Dependencias compartidas para paginación y acceso a la base de datos."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..models import Usuario
from .database import get_db
from .exceptions import CuentaBloqueada, NoAutenticado, Prohibido
from .roles import Rol
from .security import decode_token


@dataclass(frozen=True)
class Pagination:
    """Límites de paginación validados para una consulta."""

    skip: int
    limit: int


def get_pagination(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> Pagination:
    """Construye los parámetros de paginación aceptados por la API."""
    return Pagination(skip=skip, limit=limit)


PaginationDep = Annotated[Pagination, Depends(get_pagination)]
SessionDep = Annotated[Session, Depends(get_db)]

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: SessionDep,
) -> Usuario:
    """Valida un access token y carga el usuario actual desde la base."""
    if token is None:
        raise NoAutenticado("Se requiere autenticación")
    claims = decode_token(token, "access")
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NoAutenticado("Credenciales no válidas") from exc
    user = db.get(Usuario, user_id)
    if user is None or not user.activo or user.rol != claims.get("rol"):
        raise NoAutenticado("Credenciales no válidas")
    if user.socio is not None and not user.socio.activo:
        raise CuentaBloqueada("La cuenta de socio está inactiva")
    return user


CurrentUserDep = Annotated[Usuario, Depends(get_current_user)]


def get_api_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: SessionDep,
) -> Usuario | None:
    """Devuelve el usuario de una ruta versionada y omite la API legacy local."""
    if request.url.path.startswith("/api/v1/"):
        return get_current_user(token, db)
    return None


ApiUserDep = Annotated[Usuario | None, Depends(get_api_user)]


def requiere_rol(*roles: Rol | str) -> Callable:
    """Restringe una ruta a los roles declarados explícitamente."""
    allowed = {role.value if isinstance(role, Rol) else role for role in roles}

    def check_role(user: CurrentUserDep) -> Usuario:
        if user.rol not in allowed:
            raise Prohibido("No tienes permiso para esta operación")
        return user

    return check_role


def require_api_access(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: SessionDep,
) -> Usuario | None:
    """Aplica permisos mínimos y deja público únicamente el catálogo."""
    staff = {Rol.bibliotecario.value, Rol.administrador.value}
    path = request.url.path.removeprefix("/api/v1")
    public_catalog = request.method == "GET" and path.startswith(
        ("/libros", "/autores", "/categorias")
    )
    user = get_current_user(token, db) if token is not None else None
    if user is None and not public_catalog:
        raise NoAutenticado("Se requiere autenticación")
    if path.startswith("/reportes") and user is not None and user.rol not in staff:
        raise Prohibido(
            "Solo bibliotecarios y administradores pueden consultar reportes"
        )
    if request.method in {"POST", "PATCH", "DELETE"}:
        member_loan = path == "/prestamos" and request.method == "POST"
        own_member_patch = (
            request.method == "PATCH"
            and re.fullmatch(r"/socios/\d+", path) is not None
            and user is not None
            and user.rol == Rol.socio.value
        )
        if user is None or (
            user.rol not in staff
            and not (member_loan and user.rol == Rol.socio.value)
            and not own_member_patch
        ):
            raise Prohibido(
                "Solo bibliotecarios y administradores pueden modificar este recurso"
            )
    return user
