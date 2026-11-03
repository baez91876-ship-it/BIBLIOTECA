"""Esquemas de validación y serialización de autores."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AutorCreate(BaseModel):
    """Datos necesarios para registrar un autor."""

    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str = Field(min_length=2, max_length=100)
    nacionalidad: str | None = Field(default=None, max_length=60)
    anio_nacimiento: int | None = Field(default=None, ge=1000, le=date.today().year)

    @field_validator("nombre")
    @classmethod
    def formatear_nombre(cls, value: str | None) -> str | None:
        """Normaliza espacios y capitalización del nombre."""
        return " ".join(value.split()).title() if value is not None else None

    @field_validator("nacionalidad")
    @classmethod
    def limpiar_nacionalidad(cls, value: str | None) -> str | None:
        """Reduce espacios repetidos en la nacionalidad."""
        return " ".join(value.split()) if value else value


class AutorPatch(AutorCreate):
    """Campos opcionales permitidos al modificar un autor."""

    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    nacionalidad: str | None = Field(default=None, max_length=60)
    anio_nacimiento: int | None = Field(default=None, ge=1000, le=date.today().year)

    @field_validator("nombre")
    @classmethod
    def validar_nombre_patch(cls, value: str | None) -> str | None:
        """Exige un nombre no nulo cuando se envía en la actualización."""
        if value is None:
            raise ValueError("El nombre no puede ser nulo")
        return " ".join(value.split()).title()

    @model_validator(mode="after")
    def validar_campos_requeridos(self):
        """Evita que PATCH borre el nombre mediante un valor nulo."""
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser nulo")
        return self


class AutorRead(AutorCreate):
    """Representación pública de un autor, incluido su identificador."""

    model_config = ConfigDict(from_attributes=True)

    id: int
