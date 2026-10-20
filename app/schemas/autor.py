from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AutorCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str = Field(min_length=2, max_length=100)
    nacionalidad: str | None = Field(default=None, max_length=60)
    anio_nacimiento: int | None = Field(
        default=None, ge=1000, le=date.today().year
    )

    @field_validator("nombre")
    @classmethod
    def formatear_nombre(cls, value: str | None) -> str | None:
        return " ".join(value.split()).title() if value is not None else None

    @field_validator("nacionalidad")
    @classmethod
    def limpiar_nacionalidad(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value


class AutorPatch(AutorCreate):
    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    nacionalidad: str | None = Field(default=None, max_length=60)
    anio_nacimiento: int | None = Field(
        default=None, ge=1000, le=date.today().year
    )

    @field_validator("nombre")
    @classmethod
    def validar_nombre_patch(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("El nombre no puede ser nulo")
        return " ".join(value.split()).title()

    @model_validator(mode="after")
    def validar_campos_requeridos(self):
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser nulo")
        return self


class AutorRead(AutorCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
