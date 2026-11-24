"""Pruebas Chromium contra FastAPI real y una base SQLite temporal."""

import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from time import monotonic, sleep

import pytest
import uvicorn
from PIL import Image
from playwright.sync_api import Browser, Page, Route, expect, sync_playwright
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app import main
from backend.app.core import covers
from backend.app.core.database import Base, get_db
from backend.app.core.exceptions import ServicioNoDisponible
from backend.app.core.security import hash_password
from backend.app.models import Autor, Categoria, Libro, Prestamo, Socio, Usuario
from backend.app.routes.auth import limiter

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
            timeout_graceful_shutdown=2,
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
    expect(ui.page.locator("#login-view")).to_be_visible()


def sign_in(ui: UI) -> None:
    ui.page.locator("#login-email").fill(TEST_EMAIL)
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-login").click()
    expect(ui.page.locator("#signed-in-user")).to_have_text("Administrador UI")
    expect(ui.page.locator("#login-view")).not_to_be_visible()


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


def test_catalog_search_and_empty_state(ui: UI) -> None:
    visit(ui)
    sign_in(ui)
    expect(ui.page.locator("#empty-title")).to_have_text(
        "Tu próxima lectura empieza aquí"
    )
    ui.page.locator("#search").fill("inexistente")
    expect(ui.page.locator("#empty-title")).to_have_text("No encontramos ese libro")
    expect(ui.page.locator("#add-book")).to_be_visible()
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
    ui.page.locator("#title").fill("Segundo - Libro")
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
    ui.page.locator("#title").fill("Libro - Modificado")
    ui.page.locator("#save-book").click()
    row = ui.page.locator("#book-list tr").filter(has_text="Libro Modificado")
    expect(row).to_have_count(1)
    ui.page.once("dialog", lambda dialog: dialog.accept())
    row.locator('[data-action="delete"]').click()
    expect(ui.page.locator("#book-list tr")).to_have_count(1)


def test_edit_copies_independently(ui: UI) -> None:
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    expect(ui.page.locator(".copies-form")).to_have_count(0)
    ui.page.locator('[data-view="ejemplares"]').click()
    expect(ui.page.locator("#breadcrumb-current")).to_have_text("Ejemplares")
    expect(ui.page.locator("#copies-list tr")).to_have_count(1)
    ui.page.locator("#copies-search").fill("inexistente")
    expect(ui.page.locator("#copies-empty")).to_be_visible()
    ui.page.locator("#copies-search").fill("ANA")
    input_field = ui.page.get_by_role("spinbutton", name="Ejemplares de Libro De Prueba")
    input_field.fill("4")
    ui.page.get_by_role("button", name="Guardar ejemplares de Libro De Prueba").click()
    expect(ui.page.get_by_role("spinbutton", name="Ejemplares de Libro De Prueba")).to_have_value("4")
    ui.page.locator('[data-view="libros"]').click()
    expect(ui.page.locator("#copy-count")).to_have_text("4")
    with ui.sessions() as db:
        assert db.scalars(select(Libro.ejemplares)).one() == 4
        assert db.scalars(select(Libro.titulo)).one() == "Libro De Prueba"


def test_edit_copies_shows_api_error(ui: UI) -> None:
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.locator('[data-view="ejemplares"]').click()
    ui.page.route(
        "**/api/v1/libros/1",
        lambda route: route.fulfill(
            status=422, json={"detail": "Hay préstamos sin devolver"}
        ),
    )
    ui.page.get_by_role("spinbutton", name="Ejemplares de Libro De Prueba").fill("1")
    ui.page.get_by_role("button", name="Guardar ejemplares de Libro De Prueba").click()
    expect(ui.page.locator("#copies-notice")).to_contain_text("Hay préstamos sin devolver")
    with ui.sessions() as db:
        assert db.scalars(select(Libro.ejemplares)).one() == 2


def test_copies_load_failure_and_retry(ui: UI) -> None:
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.route(
        "**/api/v1/libros?**",
        lambda route: route.fulfill(status=503, json={"detail": "Inventario no disponible"}),
    )
    ui.page.locator('[data-view="ejemplares"]').click()
    expect(ui.page.locator("#copies-notice")).to_contain_text("Inventario no disponible")
    ui.page.locator("#copies-search").fill("Libro")
    expect(ui.page.locator("#copies-list tr")).to_have_count(0)
    ui.page.unroute("**/api/v1/libros?**")
    ui.page.locator("#refresh-copies").click()
    expect(ui.page.locator("#copies-list tr")).to_have_count(1)
    expect(ui.page.locator("#copies-notice")).not_to_be_visible()


def test_login_is_required_before_loading_catalog(ui: UI) -> None:
    requests = []
    ui.page.on("request", lambda request: requests.append(request.url))
    visit(ui)
    expect(ui.page.locator(".app-shell")).not_to_be_visible()
    ui.page.keyboard.press("Escape")
    expect(ui.page.locator("#login-view")).to_be_visible()
    assert not any("/api/v1/libros" in url for url in requests)
    sign_in(ui)
    expect(ui.page.locator("#books-view")).to_be_visible()
    assert ui.page.locator(".nav-link[data-view]").evaluate_all(
        "links => links.map(link => link.dataset.view)"
    ) == ["libros", "autores", "categorias", "socios", "prestamos", "ejemplares"]


def cover_file():
    image = BytesIO()
    Image.new("RGB", (30, 40), "blue").save(image, format="PNG")
    return {"name": "portada.png", "mimeType": "image/png", "buffer": image.getvalue()}


@pytest.mark.parametrize("first_upload_fails", [False, True])
def test_cover_new_book_preview_and_safe_retry(ui: UI, monkeypatch, first_upload_fails):
    seed_catalog(ui)
    uploads = []
    file = cover_file()
    ui.page.route("https://covers.test/**", lambda route: route.fulfill(
        content_type="image/png", body=file["buffer"],
    ))

    def upload(data):
        assert data == file["buffer"]
        uploads.append(data)
        if first_upload_fails and len(uploads) == 1:
            raise ServicioNoDisponible("Subida de prueba fallida")
        return covers.Cover(url="https://covers.test/new.png", public_id="new")

    monkeypatch.setattr(covers, "upload_cover", upload)
    ui.page.goto(ui.url, wait_until="domcontentloaded")
    sign_in(ui)
    ui.page.locator("#add-book").click()
    ui.page.locator("#title").fill("Libro Ilustrado")
    ui.page.locator("#isbn").fill("9780000000002")
    ui.page.locator("#author").select_option(label="Ana Escritora")
    ui.page.locator("#year").fill("2020")
    ui.page.locator("#copies").fill("2")
    ui.page.locator("#categories").select_option(label="novela")
    ui.page.locator("#cover-file").set_input_files(file)
    expect(ui.page.locator("#cover-preview")).to_be_visible()
    assert ui.page.locator("#cover-preview").get_attribute("src").startswith("blob:")
    with ui.page.expect_request("**/libros/*/portada") as request:
        ui.page.locator("#save-book").click()
    assert "multipart/form-data; boundary=" in request.value.headers["content-type"]
    if first_upload_fails:
        expect(ui.page.locator("#form-error")).to_contain_text("El libro fue guardado")
        expect(ui.page.locator("#book-dialog")).to_be_visible()
        expect(ui.page.locator("#save-book")).to_be_enabled()
        ui.page.locator("#save-book").click()
    expect(ui.page.locator("#book-dialog")).not_to_be_visible()
    row = ui.page.locator("#book-list tr").filter(has_text="Libro Ilustrado")
    expect(row.locator("img.book-cover")).to_have_attribute("src", "https://covers.test/new.png")
    expect(row.locator("img")).to_have_js_property("complete", True)
    assert row.locator("img").evaluate("(image) => image.naturalWidth > 0")
    with ui.sessions() as db:
        assert len(db.scalars(select(Libro)).all()) == 2
        book = db.scalar(select(Libro).where(Libro.titulo == "Libro Ilustrado"))
        assert book.portada_public_id == "new"
    assert len(uploads) == (2 if first_upload_fails else 1)


def test_existing_cover_preview_replace_and_no_file_preserves_cover(ui: UI, monkeypatch):
    seed_catalog(ui)
    with ui.sessions() as db:
        book = db.scalar(select(Libro))
        book.portada_url = "https://covers.test/old.png"
        book.portada_public_id = "old"
        db.commit()
    file = cover_file()
    ui.page.route("https://covers.test/**", lambda route: route.fulfill(
        content_type="image/png", body=file["buffer"],
    ))
    deleted = []
    monkeypatch.setattr(covers, "upload_cover", lambda data: covers.Cover(
        url="https://covers.test/new.png", public_id="new",
    ))
    monkeypatch.setattr(covers, "delete_cover", deleted.append)
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.locator('#book-list [data-action="edit"]').click()
    expect(ui.page.locator("#cover-preview")).to_have_attribute("src", "https://covers.test/old.png")
    ui.page.locator("#title").fill("Libro Editado")
    ui.page.locator("#save-book").click()
    expect(ui.page.locator("#book-dialog")).not_to_be_visible()
    expect(ui.page.locator("img.book-cover")).to_have_attribute("src", "https://covers.test/old.png")
    assert not deleted
    ui.page.locator('#book-list [data-action="edit"]').click()
    ui.page.locator("#cover-file").set_input_files(file)
    ui.page.locator("#save-book").click()
    expect(ui.page.locator("#book-dialog")).not_to_be_visible()
    expect(ui.page.locator("img.book-cover")).to_have_attribute("src", "https://covers.test/new.png")
    assert deleted == ["old"]


def test_cover_input_validation_and_reset(ui: UI):
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.locator("#add-book").click()
    ui.page.locator("#cover-file").set_input_files({
        "name": "bad.svg", "mimeType": "image/svg+xml", "buffer": b"<svg></svg>",
    })
    expect(ui.page.locator("#form-error")).to_contain_text("JPEG, PNG o WebP")
    assert not ui.page.locator("#cover-file").evaluate("(input) => input.validity.valid")
    ui.page.locator("#cancel-dialog").click()
    ui.page.locator("#add-book").click()
    assert ui.page.locator("#cover-file").evaluate("(input) => input.validity.valid")
    expect(ui.page.locator("#cover-preview")).not_to_be_visible()


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


def test_overdue_loan_displays_fine_before_return(ui: UI) -> None:
    seed_catalog(ui)
    with ui.sessions() as db:
        db.add(
            Prestamo(
                libro_id=db.scalars(select(Libro.id)).one(),
                socio_id=db.scalars(select(Socio.id)).one(),
                fecha_prestamo=date.today() - timedelta(days=10),
                fecha_limite=date.today() - timedelta(days=2),
                multa=0,
            )
        )
        db.commit()
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.locator('[data-view="prestamos"]').click()
    row = ui.page.locator("#management-list tr")
    expect(row).to_contain_text("vencido")
    expect(row).to_contain_text("COP")
    expect(row).to_contain_text("40")
    ui.page.once("dialog", lambda dialog: dialog.accept())
    row.locator('[data-action="return"]').click()
    expect(row).to_contain_text("devuelto")
    expect(row).to_contain_text("COP")
    expect(row).to_contain_text("40")


def test_registration_login_permissions_and_logout(ui: UI) -> None:
    visit(ui)
    ui.page.locator("#open-register").click()
    ui.page.locator("#register-name").fill("Lector Nuevo")
    ui.page.locator("#register-email").fill("registro-ui@example.com")
    ui.page.locator("#register-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-register").click()
    expect(ui.page.locator("#login-view")).to_be_visible()
    expect(ui.page.locator("#login-status")).to_contain_text("Cuenta creada")
    expect(ui.page.locator("#login-email")).to_have_value("registro-ui@example.com")
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-login").click()
    expect(ui.page.locator("#signed-in-user")).to_have_text("Lector Nuevo")
    expect(ui.page.locator("#add-book")).not_to_be_visible()
    expect(ui.page.locator('[data-view="socios"]')).not_to_be_visible()
    expect(ui.page.locator('[data-view="ejemplares"]')).not_to_be_visible()
    ui.page.locator("#logout-button").click()
    expect(ui.page.locator("#login-view")).to_be_visible()
    expect(ui.page.locator(".app-shell")).not_to_be_visible()
    expect(ui.page.locator("#signed-in-user")).not_to_be_visible()


@pytest.fixture
def reader(ui: UI) -> UI:
    seed_catalog(ui)
    visit(ui)
    ui.page.locator("#open-register").click()
    ui.page.locator("#register-name").fill("Lector Normal")
    ui.page.locator("#register-email").fill("normal-ui@example.com")
    ui.page.locator("#register-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-register").click()
    expect(ui.page.locator("#register-dialog")).not_to_be_visible()
    expect(ui.page.locator("#login-status")).to_contain_text("Cuenta creada")
    return ui


@pytest.mark.parametrize("path", ["/", "/app/"])
@pytest.mark.parametrize("width", [320, 768, 1440])
def test_normal_user_full_journey(reader: UI, path: str, width: int) -> None:
    if path == "/app/" and not main.VUE_DIST.is_dir():
        pytest.skip("Compila Vue con npm run web:build para probar /app/")
    ui = reader
    ui.page.set_viewport_size({"width": width, "height": 900})
    ui.page.goto(f"{ui.url}{path}")
    expect(ui.page.locator(".login-view")).to_be_visible()
    expect(ui.page.locator("#search")).not_to_be_visible()
    ui.page.locator("#login-email").fill("normal-ui@example.com")
    ui.page.locator("#login-password").fill("incorrecta")
    ui.page.get_by_role("button", name="Entrar").click()
    expect(ui.page.get_by_role("alert")).to_be_visible()
    expect(ui.page.locator("#search")).not_to_be_visible()
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.get_by_role("button", name="Entrar").click()
    expect(ui.page.locator("#signed-in-user")).to_have_text("Lector Normal")
    expect(ui.page.locator("#add-book")).not_to_be_visible()
    expect(ui.page.locator(".copies-form")).to_have_count(0)
    assert ui.page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")

    if path == "/":
        rows = ui.page.locator("#book-list tr")
        for view in ("autores", "categorias", "socios", "prestamos", "ejemplares"):
            expect(ui.page.locator(f'[data-view="{view}"]')).not_to_be_visible()
        expect(rows.locator("button")).to_have_count(0)
    else:
        rows = ui.page.locator(".book-card")
        expect(ui.page.locator("#tab-ejemplares")).to_have_count(0)
        expect(rows.locator("button")).to_have_count(0)
        ui.page.locator("#tab-categorias").click()
        expect(ui.page.locator(".category-card")).to_contain_text("novela")
        expect(ui.page.locator(".inline-form")).to_have_count(0)
        expect(ui.page.locator(".category-card button")).to_have_count(0)
        ui.page.locator("#tab-libros").click()

    expect(rows).to_have_count(1)
    expect(rows).to_contain_text("Libro De Prueba")
    expect(rows).to_contain_text("Ana Escritora")
    expect(rows).to_contain_text("novela")
    for query in ("LIBRO", "ana"):
        ui.page.locator("#search").fill(query)
        expect(rows).to_have_count(1)
    ui.page.locator("#search").fill("sin coincidencias")
    expect(rows).to_have_count(0)
    expect(ui.page.locator("#empty-state")).to_be_visible()
    expect(ui.page.locator("#empty-add-book")).not_to_be_visible()
    ui.page.locator("#search").fill("")
    expect(rows).to_have_count(1)

    ui.page.locator("#logout-button").click()
    expect(ui.page.locator(".login-view")).to_be_visible()
    expect(ui.page.locator("#search")).not_to_be_visible()
    ui.page.reload()
    expect(ui.page.locator(".login-view")).to_be_visible()
    expect(ui.page.locator("#search")).not_to_be_visible()
    with ui.sessions() as db:
        user = db.scalars(select(Usuario).where(Usuario.email == "normal-ui@example.com")).one()
        assert user.rol == "socio"
        assert user.socio_id is not None
        assert db.scalars(select(Libro.ejemplares)).one() == 2
        assert db.scalars(select(Prestamo)).first() is None


def test_normal_user_registration_errors(reader: UI) -> None:
    ui = reader
    ui.page.locator("#open-register").click()
    ui.page.locator("#register-name").fill("Otro Lector")
    ui.page.locator("#register-email").fill("otro-ui@example.com")
    ui.page.locator("#register-password").fill("SoloLetrasSinNumeros")
    ui.page.locator("#submit-register").click()
    expect(ui.page.locator("#register-error")).to_contain_text("letras y números")
    expect(ui.page.locator("#register-dialog")).to_be_visible()
    ui.page.locator("#register-email").fill("normal-ui@example.com")
    ui.page.locator("#register-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-register").click()
    expect(ui.page.locator("#register-error")).to_contain_text("registrado")
    expect(ui.page.locator("#submit-register")).to_be_enabled()
    ui.page.locator("#cancel-register").click()
    expect(ui.page.locator(".app-shell")).not_to_be_visible()
    with ui.sessions() as db:
        assert len(db.scalars(select(Usuario).where(Usuario.rol == "socio")).all()) == 1


@pytest.mark.parametrize("path", ["/", "/app/"])
def test_normal_user_session_expiry(reader: UI, path: str) -> None:
    if path == "/app/" and not main.VUE_DIST.is_dir():
        pytest.skip("Compila Vue con npm run web:build para probar /app/")
    ui = reader
    ui.page.goto(f"{ui.url}{path}")
    ui.page.locator("#login-email").fill("normal-ui@example.com")
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.get_by_role("button", name="Entrar").click()
    expect(ui.page.locator("#signed-in-user")).to_have_text("Lector Normal")
    expect(ui.page.locator("#search")).to_be_visible()
    ui.page.route(
        "**/api/v1/categorias?**",
        lambda route: route.fulfill(status=401, json={"detail": "Sesion expirada"}),
    )
    ui.page.route(
        "**/api/v1/auth/refresh",
        lambda route: route.fulfill(status=401, json={"detail": "Refresh expirado"}),
    )
    if path == "/":
        ui.page.locator("#refresh-books").click()
    else:
        ui.page.locator("#tab-categorias").click()
    expect(ui.page.locator(".login-view")).to_be_visible()
    expect(ui.page.locator("#search")).not_to_be_visible()
    expect(ui.page.locator(".login-view [role=status]")).to_be_visible()


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
    expect(ui.page.locator("#login-view")).to_be_visible()
    expect(ui.page.locator("#login-status")).to_contain_text("no se pudo revocar el token")


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
    expect(ui.page.locator("#login-view")).to_be_visible()
    expect(ui.page.locator("#login-status")).to_contain_text("caducado")
    expect(ui.page.locator("#book-list button")).to_have_count(0)
    ui.page.unroute("**/api/v1/libros?**")
    ui.page.unroute("**/api/v1/auth/refresh")
    sign_in(ui)
    expect(ui.page.locator('#book-list [data-action="edit"]')).to_have_count(1)


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
    visit(ui)
    sign_in(ui)
    ui.page.route("**/api/v1/**", lambda route: route.abort("failed"))
    ui.page.locator("#refresh-books").click()
    expect(ui.page.locator("#connection-label")).to_have_text("Catálogo estático")
    expect(ui.page.locator("#notice")).to_contain_text("catálogo guardado")
    expect(ui.page.locator("#logout-button")).to_be_visible()
    expect(ui.page.locator("#book-list button")).to_have_count(0)
    ui.page.unroute("**/api/v1/**")
    ui.page.locator("#refresh-books").click()
    expect(ui.page.locator("#connection-label")).to_have_text("Biblioteca conectada")
    expect(ui.page.locator("#logout-button")).to_be_visible()
    expect(ui.page.locator("#notice")).not_to_be_visible()


@pytest.mark.parametrize("width", [320, 390, 768, 1024, 1440, 1920])
def test_responsive_layout_and_login_view(ui: UI, width: int) -> None:
    ui.page.set_viewport_size({"width": width, "height": 900})
    visit(ui)
    assert ui.page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    box = ui.page.locator(".login-panel").bounding_box()
    assert box is not None
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    expect(ui.page.locator(".app-shell")).not_to_be_visible()


@pytest.mark.parametrize("width", [320, 390, 768, 1024, 1440, 1920])
def test_readable_text_and_touch_targets_in_all_views(ui: UI, width: int) -> None:
    ui.page.set_viewport_size({"width": width, "height": 900})
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    for view in ("libros", "ejemplares", "autores", "categorias", "socios", "prestamos"):
        ui.page.locator(f'[data-view="{view}"]').click()
        if view == "libros":
            expect(ui.page.locator("#book-list tr")).to_have_count(1)
        elif view == "ejemplares":
            expect(ui.page.locator("#copies-list tr")).to_have_count(1)
        else:
            expect(ui.page.locator("#add-record")).to_be_enabled()
        measurements = ui.page.evaluate("""() => {
            const visible = (element) => element.getClientRects().length > 0;
            const fonts = [...document.querySelectorAll(
                '.nav-link, .subtitle, .button, .stat-label, .stat-detail, th, td, ' +
                '.collection-header p, .search-box input, .table-footer, .text-button'
            )].filter(visible).map(element => ({
                selector: element.className || element.tagName,
                size: parseFloat(getComputedStyle(element).fontSize)
            }));
            const controls = [...document.querySelectorAll('button, .search-box')]
                .filter(visible).map(element => ({
                    name: element.textContent.trim(),
                    height: element.getBoundingClientRect().height,
                    width: element.getBoundingClientRect().width
                }));
            return {fonts, controls,
                overflow: document.documentElement.scrollWidth > innerWidth};
        }""")
        assert not measurements["overflow"], (width, view)
        assert all(item["size"] >= 14 for item in measurements["fonts"]), measurements
        assert all(
            item["height"] >= 44 and item["width"] >= 44
            for item in measurements["controls"]
        ), measurements
        if view == "ejemplares":
            continue
        ui.page.locator("#add-book" if view == "libros" else "#add-record").click()
        modal = ui.page.locator(
            "#book-dialog" if view == "libros" else "#record-dialog"
        )
        expect(modal).to_be_visible()
        assert modal.locator("input, select").evaluate_all(
            """elements => elements.every(element =>
                parseFloat(getComputedStyle(element).fontSize) >= 16 &&
                element.getBoundingClientRect().height >= 44)"""
        )
        box = modal.bounding_box()
        assert box is not None
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        ui.page.keyboard.press("Escape")


def test_tables_are_keyboard_scrollable_on_small_screens(ui: UI) -> None:
    ui.page.set_viewport_size({"width": 320, "height": 700})
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    table = ui.page.locator("#books-view .table-wrap")
    expect(ui.page.locator("#book-list tr")).to_have_count(1)
    assert table.evaluate("(element) => element.scrollWidth > element.clientWidth")
    table.focus()
    ui.page.keyboard.press("ArrowRight")
    expect(table).to_be_focused()
    ui.page.wait_for_function("(element) => element.scrollLeft > 0", arg=table.element_handle())


def test_sidebar_scrolls_on_short_desktop(ui: UI) -> None:
    ui.page.set_viewport_size({"width": 1024, "height": 480})
    visit(ui)
    sign_in(ui)
    sidebar = ui.page.locator(".sidebar")
    assert sidebar.evaluate("(element) => element.scrollHeight > element.clientHeight")
    assert sidebar.locator(".nav-link").evaluate_all(
        "links => links.every(link => link.getBoundingClientRect().height >= 44)"
    )
    ui.page.locator(".sidebar-footer").scroll_into_view_if_needed()
    assert sidebar.evaluate("(element) => element.scrollTop > 0")
    ui.page.locator('[data-view="ejemplares"]').click()
    expect(ui.page.locator("#copies-view")).to_be_visible()


def test_catalog_actions_fit_desktop_table(ui: UI) -> None:
    ui.page.set_viewport_size({"width": 1366, "height": 900})
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    expect(ui.page.locator("#book-list tr")).to_have_count(1)
    table = ui.page.locator("#books-view .table-wrap")
    assert table.evaluate("(element) => element.scrollWidth <= element.clientWidth")
    expect(ui.page.locator('#book-list [data-action="edit"]')).to_be_visible()


@pytest.mark.parametrize("path", ["/", "/app/"])
@pytest.mark.parametrize("width", [320, 768, 1366])
def test_long_book_titles_are_fully_visible(ui: UI, path: str, width: int) -> None:
    if path == "/app/" and not main.VUE_DIST.is_dir():
        pytest.skip("Compila Vue con npm run web:build para probar /app/")
    seed_catalog(ui)
    title = "Una biblioteca de historias extraordinarias para todos los lectores " + "Lectura" * 10
    with ui.sessions() as db:
        db.scalars(select(Libro)).one().titulo = title
        db.commit()
    ui.page.set_viewport_size({"width": width, "height": 900})
    ui.page.goto(f"{ui.url}{path}")
    ui.page.locator("#login-email").fill(TEST_EMAIL)
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.get_by_role("button", name="Entrar").click()
    heading = ui.page.locator(
        ".book-title span:last-child" if path == "/" else ".book-card h3"
    )
    expect(heading).to_have_text(title)
    assert heading.evaluate("""element => {
        const range = document.createRange();
        range.selectNodeContents(element);
        const text = range.getBoundingClientRect();
        const box = element.getBoundingClientRect();
        return range.getClientRects().length > 1 &&
            text.width <= box.width + 1 &&
            text.height <= box.height + 1 &&
            element.scrollWidth <= element.clientWidth &&
            element.scrollHeight <= element.clientHeight;
    }"""), "El título debe ajustarse en varias líneas sin quedar recortado"
    assert ui.page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [320, 390, 768, 1440])
def test_vue_views_fit_the_viewport(ui: UI, width: int) -> None:
    if not main.VUE_DIST.is_dir():
        pytest.skip("Compila Vue con npm run web:build para probar /app/")
    ui.page.set_viewport_size({"width": width, "height": 700})
    seed_catalog(ui)
    ui.page.goto(f"{ui.url}/app/")
    ui.page.locator("#login-email").fill(TEST_EMAIL)
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.get_by_role("button", name="Entrar").click()
    expect(ui.page.locator("#search")).to_be_visible()

    def assert_layout() -> None:
        assert ui.page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        controls = ui.page.locator("button:visible, input:not([type=checkbox]):visible, select:visible")
        assert controls.evaluate_all(
            "elements => elements.every(element => element.getBoundingClientRect().height >= 44)"
        )

    for tab in ("#tab-libros", "#tab-categorias", "#tab-ejemplares"):
        ui.page.locator(tab).click()
        assert_layout()

    ui.page.locator("#tab-libros").click()
    ui.page.locator("#add-book").click()
    modal = ui.page.locator(".overlay .dialog")
    expect(modal).to_be_visible()
    box = modal.bounding_box()
    assert box is not None
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert_layout()


def test_text_can_scale_to_two_hundred_percent(ui: UI) -> None:
    ui.page.set_viewport_size({"width": 640, "height": 900})
    seed_catalog(ui)
    ui.page.goto(ui.url)
    sign_in(ui)
    ui.page.add_style_tag(content=":root { font-size: 32px; }")
    assert ui.page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
    assert (
        ui.page.locator("#books-view .subtitle").evaluate(
            "element => parseFloat(getComputedStyle(element).fontSize)"
        )
        == 32
    )
    ui.page.locator("#add-book").click()
    expect(ui.page.locator("#book-dialog")).to_be_visible()
    ui.page.locator("#cancel-dialog").click()
    expect(ui.page.locator("#book-dialog")).not_to_be_visible()


def test_keyboard_focus_is_visible(ui: UI) -> None:
    visit(ui)
    ui.page.locator("#submit-login").focus()
    assert ui.page.locator("#submit-login").evaluate(
        """element => getComputedStyle(element).outlineStyle !== 'none' &&
            parseFloat(getComputedStyle(element).outlineWidth) >= 2"""
    )
    ui.page.keyboard.press("Escape")
    expect(ui.page.locator("#login-view")).to_be_visible()


def test_swagger_panel_and_openapi(ui: UI) -> None:
    visit(ui)
    sign_in(ui)
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
    sign_in(ui)
    expect(ui.page.locator("#result-count")).to_have_text("101 libros")
    expect(ui.page.locator("#book-list tr")).to_have_count(101)
    ui.page.locator("#search").fill("Libro 100")
    expect(ui.page.locator("#book-list tr")).to_have_count(1)


def test_invalid_login_displays_error_and_allows_retry(ui: UI) -> None:
    visit(ui)
    ui.page.locator("#login-email").fill(TEST_EMAIL)
    ui.page.locator("#login-password").fill("incorrecta")
    ui.page.locator("#submit-login").click()
    expect(ui.page.locator("#login-error")).to_be_visible()
    expect(ui.page.locator("#submit-login")).to_be_enabled()
    ui.page.locator("#login-password").fill(TEST_PASSWORD)
    ui.page.locator("#submit-login").click()
    expect(ui.page.locator("#signed-in-user")).to_have_text("Administrador UI")


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
