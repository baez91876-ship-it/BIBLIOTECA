"""Esquemas de registro y gestión de sesiones."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegistroCreate(BaseModel):
    """Datos necesarios para crear una cuenta de socio."""

    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: Annotated[str, Field(min_length=2, max_length=100)]
    email: EmailStr
    password: Annotated[str, Field(min_length=12, max_length=128)]

    @field_validator("password")
    @classmethod
    def secure_password(cls, value: str) -> str:
        """Exige al menos una letra y un dígito además de la longitud mínima."""
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("La contraseña debe incluir letras y números")
        return value


class TokenRequest(BaseModel):
    """Refresh token en claro recibido solo para rotación o cierre."""

    refresh_token: Annotated[str, Field(min_length=1)]


class TokenResponse(BaseModel):
    """Tokens de acceso y renovación emitidos al autenticar."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserRead(BaseModel):
    """Identidad pública autenticada sin datos de credenciales."""

    id: int
    email: EmailStr
    nombre: str
    rol: str
    socio_id: int | None
    activo: bool

    model_config = ConfigDict(from_attributes=True)
