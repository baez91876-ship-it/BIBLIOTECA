"""Hash Argon2 y emisión/verificación de tokens JWT."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError

from .config import get_settings
from .exceptions import NoAutenticado

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Genera un hash Argon2 con parámetros recomendados."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verifica una contraseña sin propagar errores de hashes corruptos."""
    try:
        return password_hasher.verify(password, password_hash)
    except (PwdlibError, ValueError, TypeError):
        return False


def create_token(
    subject: int,
    role: str,
    token_type: str,
    expires_delta: timedelta,
    jti: str | None = None,
) -> tuple[str, str, datetime]:
    """Firma un JWT e incluye su identificador revocable."""
    now = datetime.now(UTC)
    token_id = jti or str(uuid4())
    expires_at = now + expires_delta
    claims = {
        "sub": str(subject),
        "rol": role,
        "tipo": token_type,
        "jti": token_id,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(
        claims,
        get_settings().jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return token, token_id, expires_at


def decode_token(token: str, expected_type: str) -> dict:
    """Valida firma, algoritmo, expiración y propósito del JWT."""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat", "jti", "tipo"]},
        )
    except jwt.InvalidTokenError as exc:
        raise NoAutenticado("Credenciales no válidas") from exc
    if claims.get("tipo") != expected_type:
        raise NoAutenticado("Credenciales no válidas")
    return claims
