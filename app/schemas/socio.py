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
    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str = Field(min_length=2, max_length=100)
    email: EmailStr = Field(max_length=150)
    telefono: str | None = Field(default=None, min_length=7, max_length=15)
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def formatear_nombre(cls, value: str) -> str:
        return " ".join(value.split()).title()

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: EmailStr) -> str:
        return str(value).lower()

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9 +]{7,15}", value):
            raise ValueError("El teléfono solo admite dígitos, espacios y +")
        return value


class SocioPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=150)
    telefono: str | None = Field(default=None, min_length=7, max_length=15)
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def formatear_nombre(cls, value: str | None) -> str | None:
        return " ".join(value.split()).title() if value else value

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, value: EmailStr | None) -> str | None:
        return str(value).lower() if value else value

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9 +]{7,15}", value):
            raise ValueError("El teléfono solo admite dígitos, espacios y +")
        return value

    @model_validator(mode="after")
    def validar_campos_requeridos(self):
        if any(
            getattr(self, field) is None
            for field in ("nombre", "email", "activo")
            if field in self.model_fields_set
        ):
            raise ValueError("Nombre, email y estado activo no pueden ser nulos")
        return self


class SocioRead(SocioCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_alta: datetime
