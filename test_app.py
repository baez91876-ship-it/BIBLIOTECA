"""Pruebas de los endpoints de salud y del manejo global de errores."""

import asyncio
import importlib

import pytest
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import main
from app.core import config
from app.core.exceptions import Conflicto


class DatabaseConnection:
    def __init__(self, database_name):
        self.database_name = database_name

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, _):
        return None

    def scalar(self, _):
        return self.database_name


class DatabaseEngine:
    def __init__(self, database_name):
        self.database_name = database_name

    def connect(self):
        return DatabaseConnection(self.database_name)


def build_request():
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/test",
            "raw_path": b"/test",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 12345),
        }
    )


@pytest.mark.parametrize("health_endpoint", [main.health, main.versioned_health])
def test_health_endpoints_require_the_expected_database(monkeypatch, health_endpoint):
    monkeypatch.setattr(main, "engine", DatabaseEngine("libreria"))
    assert health_endpoint() == {"status": "ok", "database": "libreria"}

    monkeypatch.setattr(main, "engine", DatabaseEngine("other"))
    with pytest.raises(RuntimeError, match="conectada"):
        health_endpoint()


def test_application_error_handler_returns_domain_status_and_message():
    response = asyncio.run(main.application_error_handler(None, Conflicto("Ya existe")))

    assert response.status_code == 409
    assert response.body == b'{"detail":"Ya existe"}'


def test_unhandled_error_handler_hides_details_and_preserves_request_id():
    request = build_request()
    request.state.request_id = "request-test-id"

    response = asyncio.run(
        main.unhandled_error_handler(request, RuntimeError("sensitive detail"))
    )

    assert response.status_code == 500
    assert response.body == b'{"detail":"Error interno del servidor"}'
    assert response.headers["x-request-id"] == "request-test-id"


def test_access_middleware_logs_and_reraises_processing_errors():
    async def failing_handler(_):
        raise RuntimeError("handler failed")

    with pytest.raises(RuntimeError, match="handler failed"):
        asyncio.run(main.request_id_and_access_log(build_request(), failing_handler))


def test_access_middleware_adds_request_id_to_successful_response():
    async def successful_handler(_):
        return Response("ok")

    response = asyncio.run(
        main.request_id_and_access_log(build_request(), successful_handler)
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_lifespan_can_start_and_stop_application():
    async def run_lifespan():
        async with main.lifespan(main.app):
            return "running"

    assert asyncio.run(run_lifespan()) == "running"


def test_unhandled_error_uses_fallback_request_id_when_missing():
    response = asyncio.run(
        main.unhandled_error_handler(build_request(), RuntimeError("internal"))
    )

    assert response.headers["x-request-id"] == "unknown"


def test_production_configuration_enables_cors_and_omits_legacy_routes(monkeypatch):
    def settings_factory():
        return config.Settings(
            _env_file=None,
            database_url="postgresql://localhost/libreria",
            jwt_secret_key="a-random-production-secret-with-more-than-32-chars",
            cors_origins=["https://library.example"],
            app_env="production",
        )

    monkeypatch.setattr(config, "get_settings", settings_factory)
    try:
        importlib.reload(main)

        assert any(
            middleware.cls is CORSMiddleware for middleware in main.app.user_middleware
        )
        paths = main.app.openapi()["paths"]
        assert "/autores" not in paths
        assert "/api/v1/autores" in paths
    finally:
        monkeypatch.undo()
        importlib.reload(main)
