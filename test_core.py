"""Pruebas de configuración, conexiones y tokens de seguridad."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.core import database, security
from app.core.config import Settings
from app.core.exceptions import NoAutenticado


def build_settings(**overrides):
    values = {
        "database_url": "postgresql://user:password@localhost/libreria",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_settings_normalize_database_driver_and_cors_origins():
    settings = build_settings(
        cors_origins=" https://one.example, ,https://two.example "
    )

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.cors_origins == [
        "https://one.example",
        "https://two.example",
    ]


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///libreria.db",
        "postgresql://user:password@localhost/another_database",
    ],
)
def test_settings_reject_non_postgresql_or_wrong_database(database_url):
    with pytest.raises(ValidationError):
        build_settings(database_url=database_url)


def test_settings_requires_random_secret_only_in_production():
    with pytest.raises(ValidationError, match="clave aleatoria"):
        build_settings(app_env="production")

    assert (
        build_settings(
            app_env="production",
            jwt_secret_key="a-random-production-secret-with-more-than-32-chars",
        ).app_env
        == "production"
    )


def test_database_dependency_closes_session(monkeypatch):
    class Session:
        closed = False

        def close(self):
            self.closed = True

    session = Session()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    dependency = database.get_db()

    assert next(dependency) is session
    dependency.close()
    assert session.closed


def test_database_url_rejects_non_postgresql_driver():
    with pytest.raises(ValueError, match="PostgreSQL"):
        database._parse_database_url("sqlite:///libreria.db")
    with pytest.raises(ValueError, match="PostgreSQL"):
        database._parse_database_url(
            "postgresql+psycopg2://user:password@localhost/libreria"
        )


def test_database_url_rejects_wrong_database_name():
    with pytest.raises(ValueError, match="base libreria"):
        database._parse_database_url("postgresql://localhost/another_database")
    with pytest.raises(ValueError, match="base libreria"):
        database._parse_database_url("postgresql://localhost")


def test_access_token_round_trip_and_wrong_token_type():
    token, token_id, _ = security.create_token(
        42,
        "administrador",
        "access",
        timedelta(minutes=5),
        jti="test-token-id",
    )

    claims = security.decode_token(token, "access")
    assert token_id == "test-token-id"
    assert claims["sub"] == "42"
    assert claims["rol"] == "administrador"
    with pytest.raises(NoAutenticado):
        security.decode_token(token, "refresh")


@pytest.mark.parametrize("token", ["not-a-jwt", ""])
def test_invalid_access_token_is_rejected(token):
    with pytest.raises(NoAutenticado):
        security.decode_token(token, "access")
