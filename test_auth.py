"""Pruebas de seguridad para registro, sesiones y autorización de la API V2."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.controllers.auth as auth_controller
import app.routes.auth as auth_router
from app import main, models
from app.core import database, security


@pytest.fixture
def api():
    """Proporciona una aplicación cliente y una base SQLite aislada."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        with test_session() as db:
            yield db

    main.app.dependency_overrides[database.get_db] = override_db
    auth_router.limiter.reset()
    with TestClient(main.app) as client:
        yield client, test_session
    main.app.dependency_overrides.clear()
    auth_router.limiter.reset()
    engine.dispose()


def register(client: TestClient, email: str = "reader@example.com"):
    return client.post(
        "/api/v1/auth/registro",
        json={
            "nombre": "Lector De Prueba",
            "email": email,
            "password": "BibliotecaSegura123",
        },
    )


def login(client: TestClient, email: str = "reader@example.com"):
    return client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "BibliotecaSegura123"},
    )


def test_hash_usa_argon2_y_verifica_contrasenas():
    password_hash = security.hash_password("BibliotecaSegura123")

    assert password_hash.startswith("$argon2id$")
    assert security.verify_password("BibliotecaSegura123", password_hash)
    assert not security.verify_password("incorrecta", password_hash)
    assert not security.verify_password("anything", "hash-invalido")


def test_registro_crea_usuario_y_socio_en_una_transaccion(api):
    client, session_factory = api
    response = register(client)

    assert response.status_code == 201
    assert response.json()["rol"] == "socio"
    assert response.json()["socio_id"] is not None
    with session_factory() as db:
        assert db.scalar(select(func.count(models.Usuario.id))) == 1
        assert db.scalar(select(func.count(models.Socio.id))) == 1


def test_registro_rechaza_contrasena_debil(api):
    client, _ = api

    response = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre": "Lector",
            "email": "weak@example.com",
            "password": "sin-numeros-en-esta-clave",
        },
    )

    assert response.status_code == 422


def test_registro_rechaza_email_duplicado(api):
    client, _ = api
    assert register(client).status_code == 201

    assert register(client).status_code == 409


def test_login_emite_access_y_refresh_y_auth_me(api):
    client, _ = api
    assert register(client).status_code == 201

    response = login(client)
    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 900
    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["email"] == "reader@example.com"


def test_cinco_intentos_fallidos_bloquean_por_quince_minutos(api):
    client, session_factory = api
    assert register(client).status_code == 201

    with session_factory() as db:
        for attempt in range(4):
            with pytest.raises(auth_controller.NoAutenticado):
                auth_controller.login("reader@example.com", "wrong", db)
        with pytest.raises(auth_controller.CuentaBloqueada):
            auth_controller.login("reader@example.com", "wrong", db)
        user = db.scalar(select(models.Usuario))
        assert user.intentos_fallidos == 5
        assert user.bloqueado_hasta.replace(tzinfo=UTC) > datetime.now(UTC)


def test_refresh_rotado_revoca_la_familia_si_se_reutiliza(api):
    client, session_factory = api
    assert register(client).status_code == 201
    original = login(client).json()["refresh_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert rotated.status_code == 200
    replacement = rotated.json()["refresh_token"]
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert reuse.status_code == 401
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": replacement}
        ).status_code
        == 401
    )
    with session_factory() as db:
        tokens = db.scalars(select(models.RefreshToken)).all()
        assert all(token.revocado_en is not None for token in tokens)


def test_socio_no_puede_administrar_autores(api):
    client, _ = api
    assert register(client).status_code == 201
    access = login(client).json()["access_token"]

    response = client.post(
        "/api/v1/autores",
        headers={"Authorization": f"Bearer {access}"},
        json={"nombre": "Autor no permitido"},
    )

    assert response.status_code == 403


def test_socio_solo_consulta_su_propio_registro(api):
    client, _ = api
    own_member = register(client, "first@example.com").json()["socio_id"]
    other_member = register(client, "second@example.com").json()["socio_id"]
    access = login(client, "first@example.com").json()["access_token"]

    own = client.get(
        f"/api/v1/socios/{own_member}",
        headers={"Authorization": f"Bearer {access}"},
    )
    other = client.get(
        f"/api/v1/socios/{other_member}",
        headers={"Authorization": f"Bearer {access}"},
    )

    assert own.status_code == 200
    assert other.status_code == 404


def test_administrador_puede_crear_autores(api):
    client, session_factory = api
    with session_factory() as db:
        db.add(
            models.Usuario(
                email="admin@example.com",
                nombre="Administrador",
                password_hash=security.hash_password("BibliotecaSegura123"),
                rol="administrador",
                activo=True,
            )
        )
        db.commit()
    access = login(client, "admin@example.com").json()["access_token"]

    response = client.post(
        "/api/v1/autores",
        headers={"Authorization": f"Bearer {access}"},
        json={"nombre": "Autora Administradora"},
    )

    assert response.status_code == 201


def test_administrador_crea_bibliotecario_y_el_socio_no(api):
    client, session_factory = api
    with session_factory() as db:
        db.add(
            models.Usuario(
                email="admin@example.com",
                nombre="Administrador",
                password_hash=security.hash_password("BibliotecaSegura123"),
                rol="administrador",
            )
        )
        db.commit()
    admin_token = login(client, "admin@example.com").json()["access_token"]
    librarian = client.post(
        "/api/v1/auth/bibliotecarios",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "nombre": "Bibliotecaria",
            "email": "librarian@example.com",
            "password": "BibliotecaSegura123",
        },
    )
    assert librarian.status_code == 201
    librarian_token = login(client, "librarian@example.com").json()["access_token"]
    author_response = client.post(
        "/api/v1/autores",
        headers={"Authorization": f"Bearer {librarian_token}"},
        json={"nombre": "Autora de Biblioteca"},
    )
    assert author_response.status_code == 201

    assert register(client).status_code == 201
    socio_token = login(client).json()["access_token"]
    forbidden = client.post(
        "/api/v1/auth/bibliotecarios",
        headers={"Authorization": f"Bearer {socio_token}"},
        json={
            "nombre": "No autorizada",
            "email": "not-allowed@example.com",
            "password": "BibliotecaSegura123",
        },
    )
    assert forbidden.status_code == 403


def test_request_id_se_incluye_incluso_en_respuestas_401(api):
    client, _ = api

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["x-request-id"]


def test_rate_limit_limita_el_registro_a_cinco_por_minuto(api):
    client, _ = api
    responses = [register(client, f"reader{index}@example.com") for index in range(6)]

    assert [response.status_code for response in responses] == [
        201,
        201,
        201,
        201,
        201,
        429,
    ]


def test_api_v1_devuelve_pagina_con_total_real_y_catalogo_publico(api):
    client, session_factory = api
    with session_factory() as db:
        author = models.Autor(nombre="Autora de paginación")
        db.add(author)
        db.flush()
        db.add_all(
            [
                models.Libro(
                    titulo=f"Libro {number}",
                    isbn=f"97800000000{number:02d}",
                    anio_publicacion=2000 + number,
                    ejemplares=1,
                    autor_id=author.id,
                )
                for number in range(1, 4)
            ]
        )
        db.commit()

    response = client.get("/api/v1/libros?skip=1&limit=1")

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert response.json()["skip"] == 1
    assert response.json()["limit"] == 1
    assert len(response.json()["items"]) == 1


def test_reporte_paginado_v2_conserva_una_sola_consulta_sql(api):
    client, session_factory = api
    with session_factory() as db:
        db.add(
            models.Usuario(
                email="reporter@example.com",
                nombre="Administrador",
                password_hash=security.hash_password("BibliotecaSegura123"),
                rol="administrador",
            )
        )
        db.add(models.Categoria(nombre="Poesía"))
        db.commit()
    access = login(client, "reporter@example.com").json()["access_token"]
    engine = session_factory.kw["bind"]
    report_queries = []

    def capture_report_query(_, __, statement, *args):
        if "FROM categorias" in statement:
            report_queries.append(statement)

    event.listen(engine, "before_cursor_execute", capture_report_query)
    try:
        response = client.get(
            "/api/v1/reportes/categorias?skip=5&limit=2",
            headers={"Authorization": f"Bearer {access}"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_report_query)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"] == []
    assert len(report_queries) == 1


def test_administrador_puede_completar_flujos_crud_versionados(api):
    client, session_factory = api
    with session_factory() as db:
        db.add(
            models.Usuario(
                email="crud-admin@example.com",
                nombre="Administrador CRUD",
                password_hash=security.hash_password("BibliotecaSegura123"),
                rol="administrador",
            )
        )
        db.commit()
    access = login(client, "crud-admin@example.com").json()["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    author = client.post(
        "/api/v1/autores",
        headers=headers,
        json={"nombre": "Autora CRUD", "nacionalidad": "Mexicana"},
    ).json()
    assert client.get("/api/v1/autores", headers=headers).json()["total"] == 1
    assert (
        client.get(f"/api/v1/autores/{author['id']}", headers=headers).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/autores/{author['id']}/libros", headers=headers).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.patch(
            f"/api/v1/autores/{author['id']}",
            headers=headers,
            json={"nacionalidad": "Argentina"},
        ).status_code
        == 200
    )

    category = client.post(
        "/api/v1/categorias", headers=headers, json={"nombre": "Categoría CRUD"}
    ).json()
    assert client.get("/api/v1/categorias", headers=headers).json()["total"] == 1
    assert (
        client.get(f"/api/v1/categorias/{category['id']}", headers=headers).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/categorias/{category['id']}",
            headers=headers,
            json={"descripcion": "Actualizada"},
        ).status_code
        == 200
    )

    book = client.post(
        "/api/v1/libros",
        headers=headers,
        json={
            "titulo": "libro crud",
            "isbn": "9780000000001",
            "anio_publicacion": 2020,
            "ejemplares": 2,
            "autor_id": author["id"],
            "categoria_ids": [category["id"]],
        },
    ).json()
    assert client.get("/api/v1/libros", headers=headers).json()["total"] == 1
    assert (
        client.get(f"/api/v1/libros/{book['id']}", headers=headers).status_code == 200
    )
    assert (
        client.patch(
            f"/api/v1/libros/{book['id']}",
            headers=headers,
            json={"titulo": "libro actualizado"},
        ).json()["titulo"]
        == "Libro Actualizado"
    )

    member = client.post(
        "/api/v1/socios",
        headers=headers,
        json={"nombre": "Socia CRUD", "email": "socia-crud@example.com"},
    ).json()
    assert client.get("/api/v1/socios", headers=headers).json()["total"] == 1
    assert (
        client.get(f"/api/v1/socios/{member['id']}", headers=headers).status_code == 200
    )
    assert (
        client.patch(
            f"/api/v1/socios/{member['id']}",
            headers=headers,
            json={"telefono": "+1 555 555"},
        ).status_code
        == 200
    )

    loan = client.post(
        "/api/v1/prestamos",
        headers=headers,
        json={
            "libro_id": book["id"],
            "socio_id": member["id"],
            "fecha_prestamo": (date.today() - timedelta(days=7)).isoformat(),
        },
    ).json()
    assert client.get("/api/v1/prestamos", headers=headers).json()["total"] == 1
    assert (
        client.get(f"/api/v1/prestamos/{loan['id']}", headers=headers).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/socios/{member['id']}/prestamos", headers=headers).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.patch(
            f"/api/v1/prestamos/{loan['id']}",
            headers=headers,
            json={"fecha_limite": date.today().isoformat()},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/prestamos/{loan['id']}/devolucion",
            headers=headers,
            json={"fecha_devolucion": date.today().isoformat()},
        ).status_code
        == 200
    )

    for path in (
        "/api/v1/reportes/libros-mas-prestados",
        "/api/v1/reportes/categorias",
        "/api/v1/reportes/prestamos-vencidos",
        "/api/v1/reportes/socios-con-multas",
        "/api/v1/reportes/autores",
        "/api/v1/reportes/resumen",
    ):
        assert client.get(path, headers=headers).status_code == 200, path

    second_member = client.post(
        "/api/v1/socios",
        headers=headers,
        json={"nombre": "Otro Socio", "email": "otro-crud@example.com"},
    ).json()
    open_loan = client.post(
        "/api/v1/prestamos",
        headers=headers,
        json={"libro_id": book["id"], "socio_id": second_member["id"]},
    ).json()
    assert (
        client.delete(
            f"/api/v1/prestamos/{open_loan['id']}", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/socios/{second_member['id']}", headers=headers
        ).status_code
        == 204
    )

    assert (
        client.delete(f"/api/v1/prestamos/{loan['id']}", headers=headers).status_code
        == 409
    )
    unused_author = client.post(
        "/api/v1/autores", headers=headers, json={"nombre": "Autora para eliminar"}
    ).json()
    unused_category = client.post(
        "/api/v1/categorias",
        headers=headers,
        json={"nombre": "Categoría para eliminar"},
    ).json()
    unused_book = client.post(
        "/api/v1/libros",
        headers=headers,
        json={
            "titulo": "libro para eliminar",
            "isbn": "9780000000002",
            "anio_publicacion": 2021,
            "ejemplares": 1,
            "autor_id": unused_author["id"],
            "categoria_ids": [unused_category["id"]],
        },
    ).json()
    assert (
        client.delete(
            f"/api/v1/libros/{unused_book['id']}", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/autores/{unused_author['id']}", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/v1/categorias/{unused_category['id']}", headers=headers
        ).status_code
        == 204
    )
    assert (
        client.delete(f"/api/v1/socios/{member['id']}", headers=headers).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/socios/{member['id']}", headers=headers).json()["activo"]
        is False
    )
