"""Portadas con Cloudinary simulado; ninguna prueba transmite imágenes reales."""

from datetime import date
from importlib import import_module
from io import BytesIO

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cloudinary.exceptions import Error as CloudinaryError
from PIL import Image
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
)
from sqlalchemy.exc import IntegrityError

from backend.app.controllers import books
from backend.app.core import covers
from backend.app.core.config import Settings
from backend.app.core.exceptions import ReglaNegocio, ServicioNoDisponible
from backend.app.models import Autor, Categoria, Libro, Prestamo, Socio, Usuario
from backend.tests.test_auth import api as api  # noqa: PLC0414
from backend.tests.test_auth import login, register


def image_bytes(format: str = "PNG", size: tuple[int, int] = (30, 40)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "green").save(output, format=format)
    return output.getvalue()


@pytest.fixture(autouse=True)
def cloudinary(monkeypatch):
    settings = Settings(
        _env_file=None, database_url="postgresql://localhost/libreria",
        cloudinary_cloud_name="test-cloud", cloudinary_api_key="test-key",
        cloudinary_api_secret="test-secret",
    )
    monkeypatch.setattr(covers, "get_settings", lambda: settings)
    uploads = []
    deletions = []

    def upload(file, **options):
        with Image.open(file) as image:
            assert image.format == "JPEG"
            assert image.width <= 1200 and image.height <= 1600
        uploads.append(options)
        return {
            "secure_url": f"https://res.cloudinary.com/test-cloud/image/upload/{options['public_id']}.jpg"
        }

    def destroy(public_id, **options):
        deletions.append(public_id)
        return {"result": "ok"}

    monkeypatch.setattr(covers.cloudinary.uploader, "upload", upload)
    monkeypatch.setattr(covers.cloudinary.uploader, "destroy", destroy)
    return settings, uploads, deletions


def seed(api, role="administrador"):
    client, sessions = api
    assert register(client).status_code == 201
    with sessions() as db:
        user = db.query(Usuario).one()
        user.rol = role
        book = Libro(
            titulo="Libro Con Portada", isbn="9780000000099",
            anio_publicacion=2020, ejemplares=2,
            autor=Autor(nombre="Autor Portada"),
            categorias=[Categoria(nombre="novela")],
        )
        db.add(book)
        db.commit()
        book_id = book.id
    token = login(client).json()["access_token"]
    return book_id, {"Authorization": f"Bearer {token}"}


def test_upload_and_replace_cover_preserve_catalog_data(api, cloudinary):
    client, sessions = api
    book_id, headers = seed(api)
    path = f"/api/v1/libros/{book_id}/portada"
    first = client.post(path, headers=headers, files={"archivo": ("cover.png", image_bytes(), "image/png")})
    assert first.status_code == 200
    assert first.json()["portada_url"].startswith("https://res.cloudinary.com/")
    assert "portada_public_id" not in first.json()
    with sessions() as db:
        first_id = db.get(Libro, book_id).portada_public_id
    second = client.post(path, headers=headers, files={"archivo": ("cover.jpg", image_bytes("JPEG"), "image/jpeg")})
    assert second.status_code == 200
    assert second.json()["portada_url"] != first.json()["portada_url"]
    assert second.json()["titulo"] == first.json()["titulo"]
    assert cloudinary[2] == [first_id]
    options = cloudinary[1][0]
    assert options["overwrite"] is False
    assert options["timeout"] == 20
    assert options["resource_type"] == "image"
    assert client.get(f"/api/v1/libros/{book_id}").json()["portada_url"] == second.json()["portada_url"]


@pytest.mark.parametrize("role,expected", [("bibliotecario", 200), ("socio", 403)])
def test_cover_requires_staff_even_on_legacy_route(api, cloudinary, role, expected):
    client, _ = api
    book_id, headers = seed(api, role)
    response = client.post(f"/libros/{book_id}/portada", headers=headers,
                           files={"archivo": ("cover.png", image_bytes(), "image/png")})
    assert response.status_code == expected
    assert len(cloudinary[1]) == (1 if expected == 200 else 0)


def test_anonymous_cannot_upload(api, cloudinary):
    client, _ = api
    book_id, _ = seed(api)
    response = client.post(f"/api/v1/libros/{book_id}/portada",
                           files={"archivo": ("cover.png", image_bytes(), "image/png")})
    assert response.status_code == 401
    assert not cloudinary[1]


@pytest.mark.parametrize("data", [
    b"", b"not-an-image", b"<svg></svg>", image_bytes("GIF"),
    b"x" * (covers.MAX_COVER_BYTES + 1),
], ids=["empty", "corrupt", "svg", "gif", "oversized"])
def test_invalid_images_never_reach_cloudinary(api, cloudinary, data):
    client, _ = api
    book_id, headers = seed(api)
    response = client.post(f"/api/v1/libros/{book_id}/portada", headers=headers,
                           files={"archivo": ("cover.png", data, "image/png")})
    assert response.status_code == 422
    assert not cloudinary[1]


def test_missing_book_never_uploads(api, cloudinary):
    client, _ = api
    _, headers = seed(api)
    response = client.post("/api/v1/libros/999/portada", headers=headers,
                           files={"archivo": ("cover.png", image_bytes(), "image/png")})
    assert response.status_code == 404
    assert not cloudinary[1]


def test_missing_configuration_returns_explicit_503(api, cloudinary):
    cloudinary[0].cloudinary_api_secret = None
    client, sessions = api
    book_id, headers = seed(api)
    response = client.post(f"/api/v1/libros/{book_id}/portada", headers=headers,
                           files={"archivo": ("cover.png", image_bytes(), "image/png")})
    assert response.status_code == 503
    assert "Configura Cloudinary" in response.json()["detail"]
    with sessions() as db:
        assert db.get(Libro, book_id).portada_url is None


def test_cloudinary_failure_preserves_previous_cover(api, monkeypatch):
    client, sessions = api
    book_id, headers = seed(api)
    with sessions() as db:
        book = db.get(Libro, book_id)
        book.portada_url = "https://example.com/old.jpg"
        book.portada_public_id = "old"
        db.commit()

    def fail(*args, **kwargs):
        raise CloudinaryError("Provider unavailable")

    monkeypatch.setattr(covers.cloudinary.uploader, "upload", fail)
    response = client.post(f"/api/v1/libros/{book_id}/portada", headers=headers,
                           files={"archivo": ("cover.png", image_bytes(), "image/png")})
    assert response.status_code == 503
    with sessions() as db:
        assert db.get(Libro, book_id).portada_public_id == "old"


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_failed_database_commit_cleans_only_new_cover(api, cloudinary, monkeypatch, cleanup_fails, caplog):
    _, sessions = api
    book_id, _ = seed(api)
    with sessions() as db:
        book = db.get(Libro, book_id)
        book.portada_url = "https://example.com/old.jpg"
        book.portada_public_id = "old"
        db.commit()

        def fail():
            raise IntegrityError("update", {}, RuntimeError("failed"))

        monkeypatch.setattr(db, "commit", fail)
        if cleanup_fails:
            def fail_cleanup(public_id):
                cloudinary[2].append(public_id)
                raise ServicioNoDisponible("Cleanup failed")
            monkeypatch.setattr(covers, "delete_cover", fail_cleanup)
        with pytest.raises(IntegrityError):
            books.set_book_cover(book_id, image_bytes(), db)
    with sessions() as db:
        assert db.get(Libro, book_id).portada_public_id == "old"
    assert cloudinary[2] == [cloudinary[1][0]["public_id"]]
    if cleanup_fails:
        assert "No se pudo limpiar" in caplog.text


def test_delete_book_removes_cloudinary_image(api, cloudinary):
    client, _ = api
    book_id, headers = seed(api)
    assert client.post(f"/api/v1/libros/{book_id}/portada", headers=headers,
                       files={"archivo": ("cover.png", image_bytes(), "image/png")}).status_code == 200
    assert client.delete(f"/api/v1/libros/{book_id}", headers=headers).status_code == 204
    assert cloudinary[2] == [cloudinary[1][0]["public_id"]]


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_images_normalized_and_resized(format):
    cover = covers.upload_cover(image_bytes(format, (1500, 1800)))
    assert cover.url.startswith("https://")


def test_image_pixel_limit():
    with pytest.raises(ReglaNegocio, match="20 megap"):
        covers.upload_cover(image_bytes("PNG", (5000, 4001)))


def test_decompression_bomb_rejected(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ReglaNegocio, match="imagen válida"):
        covers.upload_cover(image_bytes())


@pytest.mark.parametrize("result", [{"secure_url": "http://example.com"}, {}])
def test_bad_upload_response_is_cleaned(cloudinary, monkeypatch, result):
    monkeypatch.setattr(covers.cloudinary.uploader, "upload", lambda *a, **kw: result)
    with pytest.raises(ServicioNoDisponible, match="HTTPS"):
        covers.upload_cover(image_bytes())
    assert len(cloudinary[2]) == 1


@pytest.mark.parametrize("result", ["ok", "not found", "bad"])
def test_delete_response_validation(monkeypatch, result):
    monkeypatch.setattr(covers.cloudinary.uploader, "destroy", lambda *a, **kw: {"result": result})
    if result == "bad":
        with pytest.raises(ServicioNoDisponible, match="confirmó"):
            covers.delete_cover("id")
    else:
        covers.delete_cover("id")


def test_delete_provider_error(monkeypatch):
    def fail(*a, **kw):
        raise CloudinaryError("Failed")
    monkeypatch.setattr(covers.cloudinary.uploader, "destroy", fail)
    with pytest.raises(ServicioNoDisponible):
        covers.delete_cover("id")


def test_invalid_upload_cleanup_failure_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(covers.cloudinary.uploader, "upload", lambda *a, **kw: {})
    def fail(*a, **kw):
        raise CloudinaryError("Failed")
    monkeypatch.setattr(covers.cloudinary.uploader, "destroy", fail)
    with pytest.raises(ServicioNoDisponible, match="HTTPS"):
        covers.upload_cover(image_bytes())
    assert "No se pudo limpiar" in caplog.text


def test_book_deleted_even_when_image_cleanup_fails(api, monkeypatch):
    client, sessions = api
    book_id, headers = seed(api)
    with sessions() as db:
        db.get(Libro, book_id).portada_public_id = "old"
        db.commit()
    def fail(public_id):
        raise ServicioNoDisponible("Failed")
    monkeypatch.setattr(covers, "delete_cover", fail)
    response = client.delete(f"/api/v1/libros/{book_id}", headers=headers)
    assert response.status_code == 503
    assert "libro fue eliminado" in response.json()["detail"]
    with sessions() as db:
        assert db.get(Libro, book_id) is None


@pytest.mark.parametrize("returned", [False, True])
def test_loan_history_protects_book_and_cover(api, cloudinary, returned):
    client, sessions = api
    book_id, headers = seed(api)
    with sessions() as db:
        db.get(Libro, book_id).portada_public_id = "old"
        db.add(Prestamo(
            libro_id=book_id, socio=Socio(nombre="Lector Prueba", email="covers@example.com"),
            fecha_limite=date.today(),
            fecha_devolucion=date.today() if returned else None,
        ))
        db.commit()
    response = client.delete(f"/api/v1/libros/{book_id}", headers=headers)
    assert response.status_code == 409
    assert not cloudinary[2]
    with sessions() as db:
        assert db.get(Libro, book_id).portada_public_id == "old"


def test_delete_missing_book(api):
    _, sessions = api
    with sessions() as db:
        from backend.app.core.exceptions import NoEncontrado
        with pytest.raises(NoEncontrado):
            books.delete_book(999, db)


def test_exif_orientation_and_metadata_removal():
    output = BytesIO()
    image = Image.new("RGB", (30, 40), "green")
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "Private metadata"
    image.save(output, format="JPEG", exif=exif)
    normalized = covers._normalize_image(output.getvalue())
    with Image.open(normalized) as result:
        assert result.size == (40, 30)
        assert not result.getexif()


def test_transparency_has_white_background():
    output = BytesIO()
    Image.new("RGBA", (30, 40), (0, 0, 0, 0)).save(output, format="PNG")
    with Image.open(covers._normalize_image(output.getvalue())) as result:
        assert result.getpixel((0, 0)) == (255, 255, 255)


def test_old_cover_cleanup_failure_is_explicit_and_new_cover_is_saved(api, monkeypatch):
    client, sessions = api
    book_id, headers = seed(api)
    with sessions() as db:
        db.get(Libro, book_id).portada_public_id = "old"
        db.commit()
    def fail(*a, **kw):
        raise CloudinaryError("Failed")
    monkeypatch.setattr(covers.cloudinary.uploader, "destroy", fail)
    response = client.post(f"/api/v1/libros/{book_id}/portada", headers=headers,
                           files={"archivo": ("cover.png", image_bytes(), "image/png")})
    assert response.status_code == 503
    assert "nueva portada fue guardada" in response.json()["detail"]
    with sessions() as db:
        assert db.get(Libro, book_id).portada_public_id != "old"


def test_cover_migration_preserves_existing_books():
    migration = import_module("database.alembic.versions.0004_portadas")
    engine = create_engine("sqlite://")
    metadata = MetaData()
    table = Table("libros", metadata, Column("id", Integer, primary_key=True),
                  Column("titulo", String(200), nullable=False))
    metadata.create_all(engine)
    try:
        with engine.begin() as connection:
            connection.execute(table.insert().values(id=1, titulo="Libro existente"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                upgraded = Table("libros", MetaData(), autoload_with=connection)
                row = connection.execute(select(upgraded)).one()
                assert row.titulo == "Libro existente"
                assert row.portada_url is None and row.portada_public_id is None
                migration.downgrade()
            assert {column["name"] for column in inspect(connection).get_columns("libros")} == {"id", "titulo"}
            assert connection.execute(select(table.c.titulo)).scalar_one() == "Libro existente"
    finally:
        engine.dispose()
