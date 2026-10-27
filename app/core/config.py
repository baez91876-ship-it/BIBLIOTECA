"""Configuración validada de la aplicación y sus controles de seguridad."""

from functools import lru_cache
from typing import Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Valores de entorno validados al iniciar la aplicación."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        enable_decoding=False,
    )

    database_url: str
    jwt_secret_key: SecretStr = Field(
        default="local-development-secret-do-not-use-in-production",
        min_length=32,
    )
    access_token_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_days: int = Field(default=7, ge=1, le=90)
    cors_origins: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "CORS_ORIGINS"),
    )
    app_env: str = "development"
    login_rate_limit: str = "5/minute"
    registration_rate_limit: str = "5/minute"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        """Acepta una lista o una variable separada por comas."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Limita la aplicación a PostgreSQL y normaliza la base del taller."""
        from sqlalchemy.engine import make_url

        parsed = make_url(value)
        if parsed.drivername == "postgresql":
            parsed = parsed.set(drivername="postgresql+psycopg")
        if parsed.drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL debe usar PostgreSQL con psycopg.")
        if parsed.database is None or parsed.database.casefold() != "libreria":
            raise ValueError("DATABASE_URL debe apuntar a la base libreria.")
        return parsed.render_as_string(hide_password=False)

    @model_validator(mode="after")
    def require_production_secret(self) -> Self:
        """Impide desplegar la clave de ejemplo en producción."""
        if (
            self.app_env.casefold() == "production"
            and self.jwt_secret_key.get_secret_value()
            in {
                "local-development-secret-do-not-use-in-production",
                "replace_with_a_random_secret_at_least_32_characters",
            }
        ):
            raise ValueError("JWT_SECRET_KEY debe ser una clave aleatoria en producción.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración única ya validada."""
    return Settings()
