"""Esquemas de validación y serialización de socios."""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class SocioCreate(BaseModel):
    """Datos necesarios para registrar un socio."""

    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str = Field(min_length=2, max_length=100)
    email: EmailStr = Field(max_length=150)
    telefono: str | None = Field(default=None, min_length=7, max_length=15)
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def formatear_nombre(cls, value: str) -> str:
        """Normaliza espacios y capitalización del nombre."""
        return " ".join(value.split()).title()

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: EmailStr) -> str:
        """Guarda el correo en minúsculas para comparaciones consistentes."""
        return str(value).lower()

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, value: str | None) -> str | None:
        """Admite solo dígitos, espacios y el signo más en el teléfono."""
        if value is not None and not re.fullmatch(r"[0-9 +]{7,15}", value):
            raise ValueError("El teléfono solo admite dígitos, espacios y +")
        return value


class SocioPatch(BaseModel):
    """Campos opcionales permitidos al modificar un socio."""

    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=150)
    telefono: str | None = Field(default=None, min_length=7, max_length=15)
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def formatear_nombre(cls, value: str | None) -> str | None:
        """Normaliza el nombre solo cuando se proporciona."""
        return " ".join(value.split()).title() if value else value

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: EmailStr | None) -> str | None:
        """Normaliza el correo solo cuando se proporciona."""
        return str(value).lower() if value else value

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, value: str | None) -> str | None:
        """Rechaza teléfonos con caracteres distintos de los permitidos."""
        if value is not None and not re.fullmatch(r"[0-9 +]{7,15}", value):
            raise ValueError("El teléfono solo admite dígitos, espacios y +")
        return value

    @model_validator(mode="after")
    def validar_campos_requeridos(self):
        """Evita borrar con nulos los campos requeridos de un socio."""
        if any(
            getattr(self, field) is None
            for field in ("nombre", "email", "activo")
            if field in self.model_fields_set
        ):
            raise ValueError("Nombre, email y estado activo no pueden ser nulos")
        return self


class SocioRead(SocioCreate):
    """Representación pública de un socio, con alta e identificador."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_alta: datetime
