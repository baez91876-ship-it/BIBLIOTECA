"""Casos de uso transaccionales de registro, login y ciclo de tokens."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.exceptions import (
    CuentaBloqueada,
    Conflicto,
    NoAutenticado,
)
from ..core.security import create_token, decode_token, hash_password, verify_password
from ..models import RefreshToken, Socio, Usuario
from ..schemas.auth import RegistroCreate, TokenResponse

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def register(data: RegistroCreate, db: Session) -> Usuario:
    """Crea socio y usuario en una sola transacción."""
    email = str(data.email).casefold()
    existing = db.scalar(
        select(Usuario.id).where(func.lower(Usuario.email) == email)
    ) or db.scalar(select(Socio.id).where(func.lower(Socio.email) == email))
    if existing is not None:
        raise Conflicto("El correo electrónico ya está registrado")
    member = Socio(nombre=data.nombre, email=email)
    user = Usuario(
        email=email,
        nombre=data.nombre,
        password_hash=hash_password(data.password),
        rol="socio",
        socio=member,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto("El correo electrónico ya está registrado") from exc
    return user


def create_librarian(data: RegistroCreate, db: Session) -> Usuario:
    """Crea una cuenta bibliotecaria sin asociarla a un socio."""
    email = str(data.email).casefold()
    existing = db.scalar(
        select(Usuario.id).where(func.lower(Usuario.email) == email)
    ) or db.scalar(select(Socio.id).where(func.lower(Socio.email) == email))
    if existing is not None:
        raise Conflicto("El correo electrónico ya está registrado")
    user = Usuario(
        email=email,
        nombre=data.nombre,
        password_hash=hash_password(data.password),
        rol="bibliotecario",
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto("El correo electrónico ya está registrado") from exc
    return user


def login(email: str, password: str, db: Session) -> TokenResponse:
    """Valida las credenciales y bloquea la cuenta tras cinco fallos."""
    normalized_email = email.casefold()
    user = db.scalar(
        select(Usuario)
        .where(func.lower(Usuario.email) == normalized_email)
        .with_for_update()
    )
    if user is None:
        raise NoAutenticado("Correo o contraseña incorrectos")
    now = datetime.now(UTC)
    blocked_until = user.bloqueado_hasta
    if blocked_until is not None:
        if blocked_until.tzinfo is None:
            blocked_until = blocked_until.replace(tzinfo=UTC)
        if blocked_until > now:
            raise CuentaBloqueada("Cuenta bloqueada temporalmente")
    if not user.activo or (user.socio is not None and not user.socio.activo):
        raise NoAutenticado("La cuenta está inactiva")
    if not verify_password(password, user.password_hash):
        user.intentos_fallidos += 1
        if user.intentos_fallidos >= MAX_LOGIN_ATTEMPTS:
            user.bloqueado_hasta = now + LOCKOUT_DURATION
        db.commit()
        if user.intentos_fallidos >= MAX_LOGIN_ATTEMPTS:
            raise CuentaBloqueada("Cuenta bloqueada temporalmente")
        raise NoAutenticado("Correo o contraseña incorrectos")
    user.intentos_fallidos = 0
    user.bloqueado_hasta = None
    tokens = _issue_tokens(user, db)
    db.commit()
    return tokens.response


def rotate_refresh_token(token: str, db: Session) -> TokenResponse:
    """Rota refresh tokens y revoca todas las sesiones ante reuso detectado."""
    claims = decode_token(token, "refresh")
    token_id = claims["jti"]
    stored = db.get(RefreshToken, token_id)
    if stored is None:
        raise NoAutenticado("Refresh token revocado o desconocido")
    now = datetime.now(UTC)
    if stored.revocado_en is not None or stored.reemplazado_por is not None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.usuario_id == stored.usuario_id)
            .values(revocado_en=now)
        )
        db.commit()
        raise NoAutenticado("Se detectó reutilización del refresh token")
    expiry = stored.expira_en
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if expiry <= now:
        raise NoAutenticado("Refresh token expirado")
    user = db.get(Usuario, stored.usuario_id)
    if user is None or not user.activo:
        raise NoAutenticado("La cuenta está inactiva")
    replacement = _issue_tokens(user, db)
    stored.revocado_en = now
    stored.reemplazado_por = replacement.refresh_token_jti
    db.commit()
    return replacement.response


def revoke_refresh_token(token: str, db: Session) -> None:
    """Revoca la sesión identificada por un refresh token válido."""
    claims = decode_token(token, "refresh")
    stored = db.get(RefreshToken, claims["jti"])
    if stored is not None and stored.revocado_en is None:
        stored.revocado_en = datetime.now(UTC)
        db.commit()


class IssuedTokens:
    """Contenedor interno de respuesta y JTI para vincular la rotación."""

    def __init__(self, response: TokenResponse, refresh_token_jti: str):
        self.response = response
        self.refresh_token_jti = refresh_token_jti


def _issue_tokens(user: Usuario, db: Session) -> IssuedTokens:
    """Emite access y refresh con duraciones independientes."""
    settings = get_settings()
    access_expiry = timedelta(minutes=settings.access_token_minutes)
    refresh_expiry = timedelta(days=settings.refresh_token_days)
    access_token, _, _ = create_token(user.id, user.rol, "access", access_expiry)
    refresh_token, refresh_jti, expires_at = create_token(
        user.id, user.rol, "refresh", refresh_expiry
    )
    db.add(
        RefreshToken(
            jti=refresh_jti,
            usuario_id=user.id,
            expira_en=expires_at,
        )
    )
    return IssuedTokens(
        TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(access_expiry.total_seconds()),
        ),
        refresh_jti,
    )
