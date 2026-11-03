"""Registro de socios, autenticación, renovación y cierre de sesión."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..controllers import auth
from ..core.config import get_settings
from ..core.dependencies import CurrentUserDep, SessionDep, requiere_rol
from ..core.roles import Rol
from ..models import Usuario
from ..schemas.auth import RegistroCreate, TokenRequest, TokenResponse, UserRead

router = APIRouter(prefix="/api/v1/auth", tags=["autenticacion"])
limiter = Limiter(key_func=get_remote_address)
settings = get_settings()


@router.post(
    "/registro",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.registration_rate_limit)
def register(
    request: Request,
    data: RegistroCreate,
    db: SessionDep,
) -> UserRead:
    """Registra atómicamente un socio y su cuenta de acceso."""
    return auth.register(data, db)


@router.post(
    "/bibliotecarios",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def create_librarian(
    data: RegistroCreate,
    db: SessionDep,
    _: Annotated[Usuario, Depends(requiere_rol(Rol.administrador))],
) -> UserRead:
    """Permite que un administrador cree cuentas de bibliotecario."""
    return auth.create_librarian(data, db)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.login_rate_limit)
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: SessionDep,
) -> TokenResponse:
    """Autentica con email y contraseña y devuelve access y refresh tokens."""
    return auth.login(form.username, form.password, db)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: TokenRequest, db: SessionDep) -> TokenResponse:
    """Rota el refresh token y revoca la familia si se reutiliza."""
    return auth.rotate_refresh_token(data.refresh_token, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: TokenRequest, db: SessionDep) -> None:
    """Revoca el refresh token de la sesión actual."""
    auth.revoke_refresh_token(data.refresh_token, db)


@router.get("/me", response_model=UserRead)
def me(user: CurrentUserDep) -> UserRead:
    """Devuelve el perfil de la cuenta autenticada."""
    return user
