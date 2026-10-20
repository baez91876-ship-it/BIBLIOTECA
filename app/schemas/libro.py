from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .autor import AutorRead
from .categoria import CategoriaRead


def _validar_categoria_ids(value: list[int]) -> list[int]:
    if not 1 <= len(value) <= 5:
        raise ValueError("Debe seleccionar entre 1 y 5 categorías")
    if len(value) != len(set(value)):
        raise ValueError("No se permiten categorías repetidas")
    return value


class LibroCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    titulo: str = Field(min_length=1, max_length=150)
    isbn: str = Field(pattern=r"^\d{13}$")
    anio_publicacion: int = Field(ge=1450, le=date.today().year)
    ejemplares: int = Field(ge=1, le=50)
    autor_id: int = Field(gt=0)
    categoria_ids: list[int] = Field(min_length=1, max_length=5)

    @field_validator("titulo")
    @classmethod
    def formatear_titulo(cls, value: str) -> str:
        return " ".join(value.split()).title()

    @field_validator("categoria_ids")
    @classmethod
    def validar_categoria_ids(cls, value: list[int]) -> list[int]:
        return _validar_categoria_ids(value)


class LibroPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    titulo: str | None = Field(default=None, min_length=1, max_length=150)
    isbn: str | None = Field(default=None, pattern=r"^\d{13}$")
    anio_publicacion: int | None = Field(
        default=None, ge=1450, le=date.today().year
    )
    ejemplares: int | None = Field(default=None, ge=1, le=50)
    autor_id: int | None = Field(default=None, gt=0)
    categoria_ids: list[int] | None = Field(default=None, min_length=1, max_length=5)

    @field_validator("titulo")
    @classmethod
    def formatear_titulo(cls, value: str | None) -> str | None:
        return " ".join(value.split()).title() if value else value

    @field_validator("categoria_ids")
    @classmethod
    def validar_categoria_ids(
        cls, value: list[int] | None
    ) -> list[int] | None:
        return _validar_categoria_ids(value) if value is not None else None

    @model_validator(mode="after")
    def validar_valores_no_nulos(self):
        if any(
            getattr(self, field) is None
            for field in self.model_fields_set
        ):
            raise ValueError("Los campos enviados no pueden ser nulos")
        return self


class LibroRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    isbn: str
    anio_publicacion: int
    ejemplares: int
    disponibles: int
    autor: AutorRead
    categorias: list[CategoriaRead]


class LibroAutorRead(LibroRead):
    pass
