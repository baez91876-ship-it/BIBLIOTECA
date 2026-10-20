from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CategoriaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nombre: str = Field(min_length=3, max_length=50)
    descripcion: str | None = Field(default=None, max_length=200)

    @field_validator("nombre")
    @classmethod
    def normalizar_nombre(cls, value: str | None) -> str | None:
        return " ".join(value.split()).lower() if value is not None else None


class CategoriaPatch(CategoriaCreate):
    nombre: str | None = Field(default=None, min_length=3, max_length=50)
    descripcion: str | None = Field(default=None, max_length=200)

    @field_validator("nombre")
    @classmethod
    def validar_nombre_patch(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("El nombre no puede ser nulo")
        return " ".join(value.split()).lower()

    @model_validator(mode="after")
    def validar_campos_requeridos(self):
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede ser nulo")
        return self


class CategoriaRead(CategoriaCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
