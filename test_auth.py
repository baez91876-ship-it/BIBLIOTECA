"""Pruebas de seguridad para registro, sesiones y autorización de la API V2."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.controllers.auth as auth_controller
import app.routes.auth as auth_router
from app import main, models
from app.controllers import members as members_controller
from app.core import database, dependencies, security
from app.schemas.socio import SocioPatch


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
    assert (
        client.get(
            "/api/v1/reportes/libros-mas-prestados?limit=2&limite=3",
            headers=headers,
        ).status_code
        == 422
    )

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


def test_login_covers_unknown_inactive_expired_lock_and_successful_reset(api):
    client, session_factory = api
    assert (
        client.post(
            "/api/v1/auth/login",
            data={"username": "missing@example.com", "password": "no-importa"},
        ).status_code
        == 401
    )
    assert register(client).status_code == 201
    with session_factory() as db:
        user = db.scalar(select(models.Usuario))
        user.bloqueado_hasta = datetime.now(UTC) + timedelta(minutes=5)
        with pytest.raises(auth_controller.CuentaBloqueada):
            auth_controller.login("reader@example.com", "wrong", db)

    with session_factory() as db:
        user = db.scalar(select(models.Usuario))
        user.intentos_fallidos = 4
        user.bloqueado_hasta = datetime(2000, 1, 1)
        db.commit()
    with session_factory() as db, pytest.raises(auth_controller.CuentaBloqueada):
        auth_controller.login("reader@example.com", "wrong", db)

    with session_factory() as db:
        user = db.scalar(select(models.Usuario))
        user.intentos_fallidos = 4
        user.bloqueado_hasta = datetime(2000, 1, 1)
        db.commit()
    success = login(client)
    assert success.status_code == 200
    with session_factory() as db:
        user = db.scalar(select(models.Usuario))
        assert user.intentos_fallidos == 0
        assert user.bloqueado_hasta is None
        user.activo = False
        db.commit()
    assert login(client).status_code == 401


def test_refresh_unknown_expired_inactive_and_logout_are_handled(api):
    client, session_factory = api
    assert register(client).status_code == 201
    refresh = login(client).json()["refresh_token"]

    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "unknown-token"}
        ).status_code
        == 401
    )
    unknown_signed_token, _, _ = security.create_token(
        999,
        "socio",
        "refresh",
        timedelta(days=1),
        jti="unregistered-refresh-token",
    )
    assert (
        client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": unknown_signed_token},
        ).status_code
        == 401
    )
    with session_factory() as db:
        stored = db.scalar(select(models.RefreshToken))
        stored.expira_en = datetime(2000, 1, 1)
        db.commit()
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code
        == 401
    )

    with session_factory() as db:
        user = db.scalar(select(models.Usuario))
        user.activo = False
        db.scalar(select(models.RefreshToken)).expira_en = datetime(2999, 1, 1)
        db.commit()
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code
        == 401
    )

    assert (
        client.post("/api/v1/auth/logout", json={"refresh_token": refresh}).status_code
        == 204
    )
    assert (
        client.post("/api/v1/auth/logout", json={"refresh_token": refresh}).status_code
        == 204
    )


def test_refresh_rotation_handles_timezone_aware_expiry(api):
    client, session_factory = api
    assert register(client).status_code == 201
    refresh = login(client).json()["refresh_token"]

    with session_factory() as db:
        stored = db.scalar(select(models.RefreshToken))
        stored.expira_en = datetime.now(UTC) + timedelta(days=1)
        rotated = auth_controller.rotate_refresh_token(refresh, db)

    assert rotated.refresh_token != refresh


@pytest.mark.parametrize("role", ["socio", "bibliotecario"])
def test_admin_and_public_routes_cover_role_and_catalog_permissions(api, role):
    client, session_factory = api
    with session_factory() as db:
        user = models.Usuario(
            email=f"{role}@example.com",
            nombre=role.title(),
            password_hash=security.hash_password("BibliotecaSegura123"),
            rol=role,
        )
        db.add(user)
        db.commit()
    token = login(client, f"{role}@example.com").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/libros", headers=headers).status_code == 200
    assert client.get("/api/v1/autores", headers=headers).status_code == 200
    assert client.get("/api/v1/categorias", headers=headers).status_code == 200
    assert client.get("/api/v1/reportes/resumen", headers=headers).status_code == (
        403 if role == "socio" else 200
    )
    assert client.post(
        "/api/v1/autores",
        headers=headers,
        json={"nombre": f"Autora {role}"},
    ).status_code == (403 if role == "socio" else 201)
    assert (
        client.post(
            "/api/v1/auth/bibliotecarios",
            headers=headers,
            json={
                "nombre": "Nuevo",
                "email": f"new-{role}@example.com",
                "password": "BibliotecaSegura123",
            },
        ).status_code
        == 403
    )


def test_social_account_ownership_and_disabled_member_are_enforced(api):
    client, session_factory = api
    member_id = register(client).json()["socio_id"]
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    member = client.get(f"/api/v1/socios/{member_id}", headers=headers)
    assert member.status_code == 200
    assert client.get("/api/v1/socios", headers=headers).json()["total"] == 1
    assert (
        client.patch(
            f"/api/v1/socios/{member_id}",
            headers=headers,
            json={"nombre": "Nombre actualizado"},
        ).status_code
        == 200
    )
    with session_factory() as db:
        members_controller.patch_member(member_id, SocioPatch(activo=True), db)
    other_member_id = register(client, "other-member@example.com").json()["socio_id"]
    assert (
        client.patch(
            f"/api/v1/socios/{other_member_id}",
            headers=headers,
            json={"nombre": "No autorizado"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/socios/{member_id}",
            headers=headers,
            json={"activo": False},
        ).status_code
        == 422
    )

    with session_factory() as db:
        db.get(models.Socio, member_id).activo = False
        db.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 423
    with session_factory() as db:
        members_controller.delete_member(member_id, db)
        assert db.get(models.Socio, member_id) is None
        assert (
            db.scalar(
                select(models.Usuario).where(
                    models.Usuario.email == "reader@example.com"
                )
            )
            is None
        )


def test_current_user_rejects_malformed_claims_and_missing_accounts(api, monkeypatch):
    _, session_factory = api
    with session_factory() as db:
        for claims in ({}, {"sub": None}, {"sub": "not-an-id"}):
            monkeypatch.setattr(
                dependencies, "decode_token", lambda *_, claims=claims: claims
            )
            with pytest.raises(auth_controller.NoAutenticado):
                dependencies.get_current_user("token", db)

        monkeypatch.setattr(
            dependencies, "decode_token", lambda *_: {"sub": "999", "rol": "socio"}
        )
        with pytest.raises(auth_controller.NoAutenticado):
            dependencies.get_current_user("token", db)


def test_protected_api_requires_authentication(api):
    client, _ = api
    assert client.get("/api/v1/socios").status_code == 401


def test_auth_registration_and_librarian_creation_handle_database_conflicts(
    api, monkeypatch
):
    client, session_factory = api
    with session_factory() as db:
        db.add(
            models.Usuario(
                email="collision@example.com",
                nombre="Existing",
                password_hash="already-hashed",
                rol="bibliotecario",
            )
        )
        db.commit()
    data = {
        "nombre": "Nuevo usuario",
        "email": "new@example.com",
        "password": "BibliotecaSegura123",
    }

    with session_factory() as db:
        monkeypatch.setattr(
            db,
            "commit",
            lambda: (_ for _ in ()).throw(
                IntegrityError("insert", {}, RuntimeError("duplicate"))
            ),
        )
        with pytest.raises(auth_controller.Conflicto):
            auth_controller.register(auth_router.RegistroCreate(**data), db)
    with session_factory() as db:
        monkeypatch.setattr(
            db,
            "commit",
            lambda: (_ for _ in ()).throw(
                IntegrityError("insert", {}, RuntimeError("duplicate"))
            ),
        )
        with pytest.raises(auth_controller.Conflicto):
            auth_controller.create_librarian(
                auth_router.RegistroCreate(**{**data, "email": "staff@example.com"}),
                db,
            )
    assert client.post("/api/v1/auth/registro", json=data).status_code == 201
    with session_factory() as db, pytest.raises(auth_controller.Conflicto):
        auth_controller.create_librarian(
            auth_router.RegistroCreate(
                nombre="Duplicado",
                email="collision@example.com",
                password="BibliotecaSegura123",
            ),
            db,
        )


def test_socio_without_member_link_gets_empty_lists_and_cannot_borrow(api):
    client, session_factory = api
    with session_factory() as db:
        db.add(
            models.Usuario(
                email="unlinked@example.com",
                nombre="Socio sin vínculo",
                password_hash=security.hash_password("BibliotecaSegura123"),
                rol="socio",
            )
        )
        db.commit()
    token = login(client, "unlinked@example.com").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/prestamos", headers=headers).json() == {
        "items": [],
        "total": 0,
        "skip": 0,
        "limit": 20,
    }
    assert client.get("/api/v1/socios", headers=headers).json() == []
    assert client.get("/socios").json() == []
    assert client.get("/api/v1/prestamos/1", headers=headers).status_code == 404
    assert client.get("/api/v1/socios/1", headers=headers).status_code == 404
    assert client.get("/api/v1/socios/1/prestamos", headers=headers).status_code == 404
    assert (
        client.post(
            "/api/v1/prestamos",
            headers=headers,
            json={"libro_id": 1, "socio_id": 1},
        ).status_code
        == 403
    )


def test_socio_can_only_borrow_and_list_their_own_loans(api):
    client, session_factory = api
    own_member_id = register(client).json()["socio_id"]
    with session_factory() as db:
        author = models.Autor(nombre="Autora Socia")
        category = models.Categoria(nombre="socia")
        db.add_all((author, category))
        db.flush()
        book = models.Libro(
            titulo="Libro de Socia",
            isbn="9780000000006",
            anio_publicacion=2020,
            ejemplares=1,
            autor_id=author.id,
            categorias=[category],
        )
        other_member = models.Socio(
            nombre="Otra Socia",
            email="other-owner@example.com",
        )
        db.add_all((book, other_member))
        db.commit()
        book_id = book.id
        other_member_id = other_member.id
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    own_loan = client.post(
        "/api/v1/prestamos",
        headers=headers,
        json={"libro_id": book_id, "socio_id": own_member_id},
    )
    assert own_loan.status_code == 201
    assert client.get("/api/v1/prestamos", headers=headers).json()["total"] == 1
    assert (
        client.get(f"/api/v1/socios/{own_member_id}/prestamos", headers=headers).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.get(
            f"/api/v1/socios/{other_member_id}/prestamos", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/prestamos",
            headers=headers,
            json={"libro_id": book_id, "socio_id": other_member_id},
        ).status_code
        == 403
    )
