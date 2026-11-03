"""Pruebas Chromium contra FastAPI real y una base SQLite temporal."""

import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, Route, expect, sync_playwright
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import main
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models import Autor, Categoria, Libro, Socio, Usuario
from app.routes.auth import limiter

TEST_EMAIL = "admin-ui@example.com"
TEST_PASSWORD = "BibliotecaPruebas123"


@dataclass
class UI:
    page: Page
    url: str
    sessions: sessionmaker[Session]


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def ui(browser: Browser, tmp_path: Path) -> Iterator[UI]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'ui.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as db:
        db.add(
            Usuario(
                email=TEST_EMAIL,
                nombre="Administrador UI",
                password_hash=hash_password(TEST_PASSWORD),
                rol="administrador",
            )
        )
        db.commit()

    def override_db() -> Iterator[Session]:
        with sessions() as db:
            yield db

    main.app.dependency_overrides[get_db] = override_db
    limiter.reset()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(
        uvicorn.Config(
            main.app,
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
    context = browser.new_context()
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    thread.start()
    try:
        deadline = monotonic() + 10
        while not server.started and thread.is_alive() and monotonic() < deadline:
            sleep(0.01)
        assert server.started, "El servidor de pruebas no pudo iniciar"
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        yield UI(page, url, sessions)
        assert not errors, f"Errores JavaScript: {errors}"
    finally:
        context.close()
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        main.app.dependency_overrides.clear()
        limiter.reset()
        engine.dispose()
        assert not thread.is_alive(), "El servidor de pruebas no se detuvo"


def visit(ui: UI) -> None:
    ui.page.goto(ui.url)
    expect(ui.page.locator("#total-count")).to_have_text("0")


def sign_in(ui: UI) -> None:
    ui.page.locator("#login-button").click()
    ui.page.locator("#login-email").fill(TEST_EMAIL)
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-login").click()
    expect(ui.page.locator("#signed-in-user")).to_contain_text("administrador")
    expect(ui.page.locator("#login-dialog")).not_to_be_visible()


def seed_catalog(ui: UI) -> None:
    with ui.sessions() as db:
        author = Autor(
            nombre="Ana Escritora", nacionalidad="Colombia", anio_nacimiento=1980
        )
        category = Categoria(nombre="novela", descripcion="Una descripcion")
        db.add_all(
            [
                Libro(
                    titulo="Libro De Prueba",
                    isbn="9780000000001",
                    anio_publicacion=2020,
                    ejemplares=2,
                    autor=author,
                    categorias=[category],
                ),
                Socio(
                    nombre="Lector Prueba",
                    email="lector-ui@example.com",
                    telefono="1234567",
                ),
            ]
        )
        db.commit()


def test_public_catalog_search_and_empty_state(ui: UI) -> None:
    visit(ui)
    expect(ui.page.locator("#empty-title")).to_have_text(
        "Tu próxima lectura empieza aquí"
    )
    ui.page.locator("#search").fill("inexistente")
    expect(ui.page.locator("#empty-title")).to_have_text("No encontramos ese libro")
    expect(ui.page.locator("#add-book")).not_to_be_visible()
    seed_catalog(ui)
    ui.page.locator("#search").fill("")
    ui.page.locator("#refresh-books").click()
    expect(ui.page.locator("#result-count")).to_have_text("1 libro")
    ui.page.locator("#search").fill("ANA")
    expect(ui.page.locator("#book-list tr")).to_have_count(1)
    ui.page.locator("#search").fill("inexistente")
    expect(ui.page.locator("#book-list tr")).to_have_count(0)
    expect(ui.page.locator("#empty-title")).to_have_text("No encontramos ese libro")


@pytest.mark.parametrize(
    ("view", "fields", "model", "attribute"),
    [
        ("autores", ["nacionalidad", "anio_nacimiento"], Autor, "nacionalidad"),
        ("categorias", ["descripcion"], Categoria, "descripcion"),
        ("socios", ["telefono"], Socio, "telefono"),
    ],
)
def test_edit_can_clear_optional_fields(
    ui: UI,
    view: str,
    fields: list[str],
    model: type[Autor] | type[Categoria] | type[Socio],
    attribute: str,
) -> None:
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.locator(f'[data-view="{view}"]').click()
    ui.page.locator('#management-list [data-action="edit"]').click()
    for field in fields:
        ui.page.locator(f"#record-{field}").fill("")
    ui.page.locator("#save-record").click()
    expect(ui.page.locator("#record-dialog")).not_to_be_visible()
    ui.page.locator('#management-list [data-action="edit"]').click()
    for field in fields:
        expect(ui.page.locator(f"#record-{field}")).to_have_value("")
    with ui.sessions() as db:
        record = db.scalars(select(model)).one()
        assert getattr(record, attribute) is None


@pytest.mark.parametrize(
    ("view", "values"),
    [
        ("autores", {"nombre": "Autor Nuevo", "nacionalidad": "Chile"}),
        ("categorias", {"nombre": "Historia", "descripcion": "Nueva categoria"}),
        ("socios", {"nombre": "Socio Nuevo", "email": "nuevo-ui@example.com"}),
    ],
)
def test_management_create_edit_search_delete(
    ui: UI, view: str, values: dict[str, str]
) -> None:
    visit(ui)
    sign_in(ui)
    ui.page.locator(f'[data-view="{view}"]').click()
    expect(ui.page.locator("#management-empty")).to_be_visible()
    ui.page.locator("#add-record").click()
    for field, value in values.items():
        ui.page.locator(f"#record-{field}").fill(value)
    if view == "socios":
        ui.page.locator("#record-activo").select_option("true")
    ui.page.locator("#save-record").click()
    expect(ui.page.locator("#management-list tr")).to_have_count(1)
    ui.page.locator('#management-list [data-action="edit"]').click()
    ui.page.locator("#record-nombre").fill("Registro Modificado")
    ui.page.locator("#save-record").click()
    expect(ui.page.locator("#management-list")).to_contain_text(
        "modificado", ignore_case=True
    )
    ui.page.locator("#management-search").fill("inexistente")
    expect(ui.page.locator("#management-list tr")).to_have_count(0)
    ui.page.locator("#management-search").fill("")
    ui.page.once("dialog", lambda dialog: dialog.accept())
    ui.page.locator('#management-list [data-action="delete"]').click()
    expect(ui.page.locator("#management-list tr")).to_have_count(0)


def test_book_create_validation_edit_and_delete(ui: UI) -> None:
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.locator("#add-book").click()
    ui.page.locator("#title").fill("Segundo Libro")
    ui.page.locator("#isbn").fill("9780000000002")
    ui.page.locator("#author").select_option(label="Ana Escritora")
    ui.page.locator("#year").fill("2020")
    ui.page.locator("#copies").fill("0")
    ui.page.locator("#categories").select_option(label="novela")
    ui.page.locator("#save-book").click()
    expect(ui.page.locator("#book-dialog")).to_be_visible()
    assert not ui.page.locator("#copies").evaluate("(input) => input.validity.valid")
    ui.page.locator("#copies").fill("3")
    ui.page.locator("#save-book").click()
    expect(ui.page.locator("#book-list tr")).to_have_count(2)
    row = ui.page.locator("#book-list tr").filter(has_text="Segundo Libro")
    row.locator('[data-action="edit"]').click()
    ui.page.locator("#title").fill("Libro Modificado")
    ui.page.locator("#save-book").click()
    row = ui.page.locator("#book-list tr").filter(has_text="Libro Modificado")
    expect(row).to_have_count(1)
    ui.page.once("dialog", lambda dialog: dialog.accept())
    row.locator('[data-action="delete"]').click()
    expect(ui.page.locator("#book-list tr")).to_have_count(1)


def test_loan_create_edit_return_and_protected_history(ui: UI) -> None:
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.locator('[data-view="prestamos"]').click()
    ui.page.locator("#add-record").click()
    ui.page.locator("#record-libro_id").select_option(label="Libro De Prueba")
    ui.page.locator("#record-socio_id").select_option(label="Lector Prueba")
    ui.page.locator("#save-record").click()
    expect(ui.page.locator("#management-list tr")).to_have_count(1)
    ui.page.locator('#management-list [data-action="edit"]').click()
    ui.page.locator("#save-record").click()
    expect(ui.page.locator("#record-dialog")).not_to_be_visible()
    ui.page.once("dialog", lambda dialog: dialog.accept())
    ui.page.locator('#management-list [data-action="return"]').click()
    expect(ui.page.locator("#management-list")).to_contain_text("devuelto")
    expect(ui.page.locator("#management-list button")).to_have_count(0)


def test_registration_login_permissions_and_logout(ui: UI) -> None:
    visit(ui)
    ui.page.locator("#login-button").click()
    ui.page.locator("#open-register").click()
    ui.page.locator("#register-name").fill("Lector Nuevo")
    ui.page.locator("#register-email").fill("registro-ui@example.com")
    ui.page.locator("#register-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-register").click()
    expect(ui.page.locator("#login-dialog")).to_be_visible()
    expect(ui.page.locator("#login-email")).to_have_value("registro-ui@example.com")
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-login").click()
    expect(ui.page.locator("#signed-in-user")).to_contain_text("socio")
    expect(ui.page.locator("#add-book")).not_to_be_visible()
    expect(ui.page.locator('[data-view="socios"]')).not_to_be_visible()
    ui.page.locator("#logout-button").click()
    expect(ui.page.locator("#login-button")).to_be_visible()
    expect(ui.page.locator("#signed-in-user")).not_to_be_visible()


@pytest.mark.parametrize("failure", ["http", "network"])
def test_logout_failure_is_visible_after_local_logout(ui: UI, failure: str) -> None:
    visit(ui)
    sign_in(ui)

    def fail_logout(route: Route) -> None:
        if failure == "network":
            route.abort("failed")
        else:
            route.fulfill(status=503, json={"detail": "Servicio no disponible"})

    ui.page.route("**/api/v1/auth/logout", fail_logout)
    ui.page.locator("#logout-button").click()
    expect(ui.page.locator("#login-button")).to_be_visible()
    expect(ui.page.locator("#notice")).to_contain_text("no se pudo revocar el token")


def test_session_expiration_removes_stale_book_actions(ui: UI) -> None:
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    expect(ui.page.locator('#book-list [data-action="edit"]')).to_have_count(1)
    ui.page.route(
        "**/api/v1/libros?**",
        lambda route: route.fulfill(
            status=401,
            json={"detail": "Sesion expirada"},
        ),
    )
    ui.page.route(
        "**/api/v1/auth/refresh",
        lambda route: route.fulfill(
            status=401,
            json={"detail": "Refresh expirado"},
        ),
    )
    ui.page.locator("#refresh-books").click()
    expect(ui.page.locator("#logout-button")).not_to_be_visible()
    expect(ui.page.locator("#book-list button")).to_have_count(0)


def test_refresh_rotates_session_and_retries_request(ui: UI) -> None:
    visit(ui)
    sign_in(ui)
    calls = 0

    def expire_once(route: Route) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            route.fulfill(status=401, json={"detail": "Access expirado"})
        else:
            route.continue_()

    ui.page.route("**/api/v1/libros?**", expire_once)
    with ui.page.expect_response("**/api/v1/auth/refresh") as refreshed:
        ui.page.locator("#refresh-books").click()
    assert refreshed.value.status == 200
    expect(ui.page.locator("#total-count")).to_have_text("0")
    expect(ui.page.locator("#logout-button")).to_be_visible()
    expect(ui.page.locator("#notice")).not_to_be_visible()
    assert calls == 2


def test_api_failure_loads_static_readonly_catalog(ui: UI) -> None:
    ui.page.route("**/api/v1/**", lambda route: route.abort("failed"))
    ui.page.goto(ui.url)
    expect(ui.page.locator("#connection-label")).to_have_text("Catálogo estático")
    expect(ui.page.locator("#notice")).to_contain_text("catálogo guardado")
    expect(ui.page.locator("#login-button")).not_to_be_visible()
    expect(ui.page.locator("#book-list button")).to_have_count(0)


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_responsive_layout_and_dialog(ui: UI, width: int) -> None:
    ui.page.set_viewport_size({"width": width, "height": 900})
    visit(ui)
    assert ui.page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    ui.page.locator("#login-button").click()
    box = ui.page.locator("#login-dialog").bounding_box()
    assert box is not None
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    ui.page.locator("#cancel-login").click()
    expect(ui.page.locator("#login-dialog")).not_to_be_visible()


def test_swagger_panel_and_openapi(ui: UI) -> None:
    visit(ui)
    ui.page.locator("#api-docs summary").click()
    expect(ui.page.locator("#api-docs-frame")).to_have_attribute("src", "/docs")
    response = ui.page.request.get(f"{ui.url}/openapi.json")
    assert response.ok
    assert "/api/v1/libros" in response.json()["paths"]


def test_catalog_loads_more_than_one_api_page(ui: UI) -> None:
    with ui.sessions() as db:
        author = Autor(nombre="Autor Paginado")
        category = Categoria(nombre="coleccion")
        db.add_all(
            [
                Libro(
                    titulo=f"Libro {index:03}",
                    isbn=f"978000000{index:04}",
                    anio_publicacion=2020,
                    ejemplares=1,
                    autor=author,
                    categorias=[category],
                )
                for index in range(101)
            ]
        )
        db.commit()
    ui.page.goto(ui.url)
    expect(ui.page.locator("#result-count")).to_have_text("101 libros")
    expect(ui.page.locator("#book-list tr")).to_have_count(101)
    ui.page.locator("#search").fill("Libro 100")
    expect(ui.page.locator("#book-list tr")).to_have_count(1)


def test_invalid_login_displays_error_and_allows_retry(ui: UI) -> None:
    visit(ui)
    ui.page.locator("#login-button").click()
    ui.page.locator("#login-email").fill(TEST_EMAIL)
    ui.page.locator("#login-password").fill("incorrecta")
    ui.page.locator("#submit-login").click()
    expect(ui.page.locator("#login-error")).to_be_visible()
    expect(ui.page.locator("#submit-login")).to_be_enabled()
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-login").click()
    expect(ui.page.locator("#signed-in-user")).to_contain_text("administrador")


@pytest.mark.parametrize("json_response", [True, False])
def test_record_error_stays_in_dialog_and_restores_button(
    ui: UI,
    json_response: bool,
) -> None:
    visit(ui)
    sign_in(ui)
    ui.page.locator('[data-view="categorias"]').click()
    ui.page.locator("#add-record").click()
    ui.page.locator("#record-nombre").fill("Historia")

    def reject_record(route: Route) -> None:
        if route.request.method != "POST":
            route.continue_()
        elif json_response:
            route.fulfill(status=409, json={"detail": "La categoria ya existe"})
        else:
            route.fulfill(status=503, content_type="text/html", body="Unavailable")

    ui.page.route("**/api/v1/categorias", reject_record)
    ui.page.locator("#save-record").click()
    expect(ui.page.locator("#record-error")).to_contain_text(
        "ya existe" if json_response else "Error 503",
    )
    expect(ui.page.locator("#record-dialog")).to_be_visible()
    expect(ui.page.locator("#save-record")).to_be_enabled()
