"""Pruebas aisladas para los comandos de administración y migración."""

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine, select
from sqlalchemy.orm import sessionmaker

import app.scripts.crear_admin as create_admin
from app.core.database import Base
from app.core.security import verify_password
from app.models import Usuario
from app.scripts import migrate


@pytest.fixture
def admin_database(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(create_admin, "SessionLocal", session_factory)
    yield session_factory
    engine.dispose()


def provide_admin_input(monkeypatch, email, name, password, confirmation):
    prompts = iter((email, name))
    passwords = iter((password, confirmation))
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))
    monkeypatch.setattr(create_admin, "getpass", lambda _: next(passwords))


def test_create_admin_normalizes_email_and_hashes_password(
    admin_database, monkeypatch, capsys
):
    provide_admin_input(
        monkeypatch,
        "Admin@Example.com",
        "Administradora",
        "BibliotecaSegura123",
        "BibliotecaSegura123",
    )

    create_admin.main()

    with admin_database() as db:
        admin = db.scalar(select(Usuario))
        assert admin.email == "admin@example.com"
        assert admin.nombre == "Administradora"
        assert admin.rol == "administrador"
        assert verify_password("BibliotecaSegura123", admin.password_hash)
    assert "Administrador creado correctamente." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("name", "password", "confirmation", "error"),
    [
        ("A", "BibliotecaSegura123", "BibliotecaSegura123", "nombre"),
        ("Administradora", "weak", "weak", "contraseña"),
        (
            "Administradora",
            "BibliotecaSegura123",
            "OtraClaveSegura123",
            "no coinciden",
        ),
    ],
)
def test_create_admin_rejects_invalid_credentials(
    admin_database, monkeypatch, name, password, confirmation, error
):
    provide_admin_input(monkeypatch, "admin@example.com", name, password, confirmation)

    with pytest.raises(ValueError, match=error):
        create_admin.main()

    with admin_database() as db:
        assert db.scalar(select(Usuario)) is None


def test_create_admin_does_not_create_second_administrator(admin_database, monkeypatch):
    with admin_database() as db:
        db.add(
            Usuario(
                email="existing@example.com",
                nombre="Administrador existente",
                password_hash="already-hashed",
                rol="administrador",
            )
        )
        db.commit()
    provide_admin_input(
        monkeypatch,
        "new@example.com",
        "Nueva Administradora",
        "BibliotecaSegura123",
        "BibliotecaSegura123",
    )

    with pytest.raises(RuntimeError, match="Ya existe un administrador"):
        create_admin.main()


@pytest.fixture
def migration_database(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(migrate.database, "engine", engine)
    stamped_revisions = []
    monkeypatch.setattr(
        migrate.command,
        "stamp",
        lambda config, revision: stamped_revisions.append(revision),
    )
    yield engine, stamped_revisions
    engine.dispose()


def create_legacy_schema(engine, include_paid_fines=False):
    metadata = MetaData()
    for table_name, required_columns in migrate.LEGACY_COLUMNS.items():
        columns = [Column(column_name, String) for column_name in required_columns]
        if table_name == "prestamos" and include_paid_fines:
            columns.append(Column("multa_pagada", String))
        Table(table_name, metadata, *columns)
    metadata.create_all(engine)


def test_migration_skips_empty_or_already_managed_database(migration_database):
    engine, stamped_revisions = migration_database

    migrate.stamp_legacy_schema()
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR)")
    migrate.stamp_legacy_schema()

    assert stamped_revisions == []


def test_migration_rejects_unrecognized_or_incomplete_legacy_schemas(
    migration_database, monkeypatch
):
    engine, _ = migration_database
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unrelated (id INTEGER)")

    with pytest.raises(RuntimeError, match="Faltan tablas"):
        migrate.stamp_legacy_schema()

    engine2 = create_engine("sqlite://")
    try:
        create_legacy_schema(engine2)
        with engine2.begin() as connection:
            connection.exec_driver_sql("DROP TABLE autores")
            connection.exec_driver_sql("CREATE TABLE autores (id INTEGER)")
        monkeypatch.setattr(migrate.database, "engine", engine2)
        with pytest.raises(RuntimeError, match="esquema Taller 1.*incompleto"):
            migrate.stamp_legacy_schema()
    finally:
        engine2.dispose()


@pytest.mark.parametrize(
    ("include_paid_fines", "revision"),
    [
        (False, "0001_estado_inicial"),
        (True, "0002_multa_pagada"),
    ],
)
def test_migration_stamps_matching_legacy_baseline(
    migration_database, include_paid_fines, revision
):
    engine, stamped_revisions = migration_database
    create_legacy_schema(engine, include_paid_fines)

    migrate.stamp_legacy_schema()

    assert stamped_revisions == [revision]


def test_migration_main_stamps_then_upgrades(migration_database, monkeypatch):
    calls = []
    monkeypatch.setattr(migrate, "stamp_legacy_schema", lambda: calls.append("stamp"))
    monkeypatch.setattr(
        migrate.command,
        "upgrade",
        lambda config, revision: calls.append((config, revision)),
    )

    migrate.main()

    assert calls == ["stamp", (migrate.ALEMBIC_CONFIG, "head")]
