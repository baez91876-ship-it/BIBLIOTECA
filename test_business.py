"""Casos límite de las reglas de negocio y sus transacciones."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import Request
from sqlalchemy import create_engine, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.controllers import authors, books, categories, loans, members, reports
from app.core.database import Base
from app.core.dependencies import Pagination
from app.core.exceptions import Conflicto, NoEncontrado, ReglaNegocio
from app.core.security import hash_password
from app.models import Autor, Categoria, Libro, Prestamo, RefreshToken, Socio, Usuario
from app.routes.loans import listar_prestamos
from app.schemas.autor import AutorCreate, AutorPatch
from app.schemas.categoria import CategoriaCreate, CategoriaPatch
from app.schemas.libro import LibroCreate, LibroPatch
from app.schemas.prestamo import (
    DevolucionCreate,
    EstadoPrestamo,
    PrestamoCreate,
    PrestamoPatch,
)
from app.schemas.socio import SocioCreate, SocioPatch


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def seed_catalog(db, *, copies=2, member_active=True):
    author = Autor(nombre="Autora Base")
    category = Categoria(nombre="categoría base")
    member = Socio(
        nombre="Socia Base",
        email="base@example.com",
        activo=member_active,
    )
    db.add_all((author, category, member))
    db.flush()
    book = Libro(
        titulo="Libro Base",
        isbn="9780000000001",
        anio_publicacion=2020,
        ejemplares=copies,
        autor=author,
        categorias=[category],
    )
    db.add(book)
    db.commit()
    return author, category, member, book


def add_loan(db, member, book, *, loan_date=None, due_date=None, returned=None):
    loan_date = loan_date or date.today()
    loan = Prestamo(
        socio_id=member.id,
        libro_id=book.id,
        fecha_prestamo=loan_date,
        fecha_limite=due_date or loan_date + timedelta(days=14),
        fecha_devolucion=returned,
        multa=Decimal(0),
    )
    db.add(loan)
    db.commit()
    return loan


def test_author_filters_patches_conflicts_and_delete(db):
    author, _, _, _ = seed_catalog(db)
    second = authors.create_author(
        AutorCreate(nombre="Otra Autora", nacionalidad="Chile"), db
    )

    assert len(authors.list_authors(db, Pagination(0, 10), "chi")) == 1
    assert authors.list_authors(db, Pagination(0, 10), include_total=True)[1] == 2
    assert authors.list_author_books(author.id, db, Pagination(0, 10))[0].id > 0
    assert (
        authors.list_author_books(author.id, db, Pagination(0, 10), include_total=True)[
            1
        ]
        == 1
    )
    with pytest.raises(NoEncontrado):
        authors.get_author(999, db)
    with pytest.raises(Conflicto):
        authors.create_author(AutorCreate(nombre=author.nombre), db)
    with pytest.raises(Conflicto):
        authors.patch_author(second.id, AutorPatch(nombre=author.nombre), db)
    assert (
        authors.patch_author(second.id, AutorPatch(nombre="Nueva Autora"), db).nombre
        == "Nueva Autora"
    )
    updated = authors.patch_author(second.id, AutorPatch(nacionalidad=None), db)
    assert updated.nacionalidad is None
    with pytest.raises(Conflicto):
        authors.delete_author(author.id, db)
    authors.delete_author(second.id, db)


def test_category_conflicts_patch_and_delete_relationships(db):
    author, category, _, book = seed_catalog(db)
    second = categories.create_category(CategoriaCreate(nombre="Otra Categoría"), db)

    assert categories.list_categories(db, Pagination(0, 10))[0].id > 0
    assert categories.list_categories(db, Pagination(0, 10), True)[1] == 2
    with pytest.raises(NoEncontrado):
        categories.get_category(999, db)
    with pytest.raises(Conflicto):
        categories.create_category(CategoriaCreate(nombre=category.nombre), db)
    with pytest.raises(Conflicto):
        categories.patch_category(second.id, CategoriaPatch(nombre=category.nombre), db)
    assert (
        categories.patch_category(
            second.id, CategoriaPatch(descripcion="Descripción"), db
        ).descripcion
        == "Descripción"
    )
    assert (
        categories.patch_category(
            second.id, CategoriaPatch(nombre="Nombre nuevo"), db
        ).nombre
        == "nombre nuevo"
    )
    categories.delete_category(category.id, db)
    assert db.get(Libro, book.id) is not None
    categories.delete_category(second.id, db)
    assert db.get(Autor, author.id) is not None


def test_book_filters_validation_conflicts_and_relations(db):
    author, category, member, book = seed_catalog(db)
    second_author = authors.create_author(AutorCreate(nombre="Otra Autora"), db)
    second_category = categories.create_category(
        CategoriaCreate(nombre="Otra Categoría"), db
    )
    second_book = books.create_book(
        LibroCreate(
            titulo="Otro Libro",
            isbn="9780000000002",
            anio_publicacion=2021,
            ejemplares=2,
            autor_id=second_author.id,
            categoria_ids=[second_category.id],
        ),
        db,
    )

    assert len(books.list_books(db, Pagination(0, 10), buscar="  base ")) == 1
    assert len(books.list_books(db, Pagination(0, 10), autor="otra")) == 1
    assert len(books.list_books(db, Pagination(0, 10), categoria_id=category.id)) == 1
    assert len(books.list_books(db, Pagination(0, 10), desde=2021)) == 1
    assert len(books.list_books(db, Pagination(0, 10), hasta=2020)) == 1
    assert (
        books.list_books(db, Pagination(0, 10), orden=books.OrdenLibro.anio)[0].id
        == book.id
    )
    assert (
        books.list_books(db, Pagination(0, 10), orden=books.OrdenLibro.anio_desc)[0].id
        == second_book.id
    )
    assert books.list_books(db, Pagination(0, 10), include_total=True)[1] == 2
    with pytest.raises(ReglaNegocio, match="desde"):
        books.list_books(db, Pagination(0, 10), desde=2022, hasta=2020)
    with pytest.raises(NoEncontrado):
        books.get_book(999, db)
    with pytest.raises(NoEncontrado, match="Autor"):
        books._validate_author_and_categories(db, 999, [])
    with pytest.raises(ReglaNegocio, match="repetidas"):
        books._validate_author_and_categories(db, author.id, [category.id, category.id])
    with pytest.raises(NoEncontrado, match="Categorías"):
        books._validate_author_and_categories(db, author.id, [999])
    with pytest.raises(Conflicto, match="ISBN"):
        books.create_book(
            LibroCreate(
                titulo="ISBN repetido",
                isbn=book.isbn,
                anio_publicacion=2022,
                ejemplares=1,
                autor_id=author.id,
                categoria_ids=[category.id],
            ),
            db,
        )
    with pytest.raises(Conflicto, match="ISBN"):
        books.patch_book(second_book.id, LibroPatch(isbn=book.isbn), db)
    assert (
        books.patch_book(
            second_book.id,
            LibroPatch(autor_id=author.id, categoria_ids=[category.id]),
            db,
        ).autor_id
        == author.id
    )
    assert (
        books.patch_book(
            second_book.id, LibroPatch(titulo="Título actualizado"), db
        ).titulo
        == "Título Actualizado"
    )
    nullable_title = LibroPatch.model_construct(_fields_set={"titulo"}, titulo=None)
    assert books.patch_book(second_book.id, nullable_title, db).titulo == (
        "Título Actualizado"
    )
    with pytest.raises(NoEncontrado, match="Categorías"):
        books.patch_book(second_book.id, LibroPatch(categoria_ids=[999]), db)
    active_loan = add_loan(db, member, second_book)
    another_member = members.create_member(
        SocioCreate(nombre="Otra Socia", email="another@example.com"), db
    )
    another_loan = add_loan(db, another_member, second_book)
    with pytest.raises(ReglaNegocio, match="ejemplares"):
        books.patch_book(second_book.id, LibroPatch(ejemplares=1), db)
    with pytest.raises(Conflicto, match="préstamos sin devolver"):
        books.delete_book(second_book.id, db)
    active_loan.fecha_devolucion = date.today()
    another_loan.fecha_devolucion = date.today()
    db.commit()
    with pytest.raises(Conflicto, match="historial"):
        books.delete_book(second_book.id, db)
    add_loan(db, member, book, returned=date.today())
    with pytest.raises(Conflicto, match="historial"):
        books.delete_book(book.id, db)


@pytest.mark.parametrize(
    ("scenario", "error", "match"),
    [
        ("member_missing", NoEncontrado, "Socio"),
        ("book_missing", NoEncontrado, "Libro"),
        ("inactive", ReglaNegocio, "activo"),
        ("overdue", ReglaNegocio, "vencidos"),
        ("limit", ReglaNegocio, "Máximo"),
        ("duplicate", Conflicto, "ya tiene"),
        ("no_copies", ReglaNegocio, "disponibles"),
        ("future", ReglaNegocio, "futura"),
    ],
)
def test_create_loan_rejects_each_invalid_business_state(db, scenario, error, match):
    _, _, member, book = seed_catalog(
        db, copies=1, member_active=scenario != "inactive"
    )
    if scenario == "overdue":
        add_loan(
            db,
            member,
            book,
            loan_date=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=1),
        )
    elif scenario == "limit":
        for index in range(3):
            extra_book = Libro(
                titulo=f"Libro Extra {index}",
                isbn=f"978000000000{index + 2}",
                anio_publicacion=2020,
                ejemplares=1,
                autor_id=book.autor_id,
            )
            db.add(extra_book)
            db.flush()
            add_loan(db, member, extra_book)
    elif scenario == "duplicate":
        add_loan(db, member, book)
    elif scenario == "no_copies":
        another_member = Socio(nombre="Otro Socio", email="other@example.com")
        db.add(another_member)
        db.flush()
        add_loan(db, another_member, book)

    member_id = 999 if scenario == "member_missing" else member.id
    book_id = 999 if scenario == "book_missing" else book.id
    loan_date = date.today() + timedelta(days=1) if scenario == "future" else None
    with pytest.raises(error, match=match):
        loans.create_loan(
            PrestamoCreate(
                socio_id=member_id,
                libro_id=book_id,
                fecha_prestamo=loan_date,
            ),
            db,
        )


def test_loan_list_return_patch_delete_and_date_errors(db):
    _, _, member, book = seed_catalog(db, copies=3)
    active = add_loan(db, member, book)
    overdue = add_loan(
        db,
        member,
        book,
        loan_date=date.today() - timedelta(days=30),
        due_date=date.today() - timedelta(days=10),
    )
    returned = add_loan(
        db,
        member,
        book,
        returned=date.today(),
    )
    assert len(loans.list_loans(db, Pagination(0, 20), EstadoPrestamo.activo)) == 1
    assert len(loans.list_loans(db, Pagination(0, 20), EstadoPrestamo.vencido)) == 1
    assert len(loans.list_loans(db, Pagination(0, 20), EstadoPrestamo.devuelto)) == 1
    assert (
        loans.list_loans(
            db,
            Pagination(0, 20),
            socio_id=member.id,
            libro_id=book.id,
            owner_id=member.id,
            include_total=True,
        )[1]
        == 3
    )
    with pytest.raises(NoEncontrado):
        loans.get_loan(999, db)
    with pytest.raises(NoEncontrado):
        loans.get_loan(active.id, db, owner_id=999)
    with pytest.raises(NoEncontrado):
        loans.return_loan(999, DevolucionCreate(), db)
    with pytest.raises(NoEncontrado):
        loans.patch_loan(999, PrestamoPatch(fecha_limite=date.today()), db)
    with pytest.raises(NoEncontrado):
        loans.delete_loan(999, db)
    with pytest.raises(ReglaNegocio, match="anterior"):
        loans.return_loan(
            active.id,
            DevolucionCreate(
                fecha_devolucion=active.fecha_prestamo - timedelta(days=1)
            ),
            db,
        )
    on_time = loans.return_loan(
        active.id, DevolucionCreate(fecha_devolucion=date.today()), db
    )
    assert on_time.multa == 0
    with pytest.raises(Conflicto):
        loans.return_loan(active.id, DevolucionCreate(), db)
    with pytest.raises(Conflicto):
        loans.patch_loan(returned.id, PrestamoPatch(fecha_limite=date.today()), db)
    with pytest.raises(ReglaNegocio, match="anterior"):
        loans.patch_loan(
            overdue.id,
            PrestamoPatch(fecha_limite=overdue.fecha_prestamo - timedelta(days=1)),
            db,
        )
    assert (
        loans.patch_loan(
            overdue.id, PrestamoPatch(fecha_limite=date.today()), db
        ).fecha_limite
        == date.today()
    )
    with pytest.raises(Conflicto, match="devuelto"):
        loans.delete_loan(returned.id, db)
    loans.delete_loan(overdue.id, db)


def test_member_updates_duplicates_history_deletion_and_pagination(db):
    author, category, member, book = seed_catalog(db)
    user = Usuario(
        email=member.email,
        nombre=member.nombre,
        password_hash=hash_password("BibliotecaSegura123"),
        rol="socio",
        socio=member,
    )
    db.add(user)
    db.flush()
    token = RefreshToken(
        jti="session-id",
        usuario_id=user.id,
        expira_en=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(token)
    other = members.create_member(
        SocioCreate(nombre="Otra Socia", email="other@example.com"), db
    )

    assert len(members.list_members(db, Pagination(0, 10), activo=True)) == 2
    assert (
        members.list_members(
            db, Pagination(0, 10), activo=True, owner_id=member.id, include_total=True
        )[1]
        == 1
    )
    with pytest.raises(NoEncontrado):
        members.get_member(999, db)
    with pytest.raises(Conflicto):
        members.create_member(SocioCreate(nombre="Duplicada", email=member.email), db)
    with pytest.raises(Conflicto):
        members.patch_member(member.id, SocioPatch(email=other.email), db)
    with pytest.raises(Conflicto):
        members.patch_member(other.id, SocioPatch(email=user.email), db)
    another_user = Usuario(
        email="staff@example.com",
        nombre="Bibliotecaria",
        password_hash=hash_password("BibliotecaSegura123"),
        rol="bibliotecario",
    )
    db.add(another_user)
    db.commit()
    with pytest.raises(Conflicto):
        members.patch_member(member.id, SocioPatch(email=another_user.email), db)

    updated = members.patch_member(
        member.id,
        SocioPatch(nombre="Nombre Nuevo", email="new@example.com", activo=False),
        db,
    )
    assert updated.usuario.nombre == "Nombre Nuevo"
    assert updated.usuario.email == "new@example.com"
    assert updated.usuario.activo is False
    db.refresh(token)
    assert token.revocado_en is not None

    active_loan = add_loan(db, other, book)
    with pytest.raises(Conflicto, match="sin devolver"):
        members.delete_member(other.id, db)
    active_loan.fecha_devolucion = date.today()
    db.commit()
    assert (
        members.list_member_loans(
            other.id, db, Pagination(0, 10), EstadoPrestamo.devuelto, include_total=True
        )[1]
        == 1
    )
    assert (
        members.list_member_loans(
            other.id, db, Pagination(0, 10), EstadoPrestamo.activo
        )
        == []
    )
    overdue_member = members.create_member(
        SocioCreate(nombre="Socio vencido", email="overdue@example.com"), db
    )
    overdue_book = books.create_book(
        LibroCreate(
            titulo="Libro vencido",
            isbn="9780000000003",
            anio_publicacion=2022,
            ejemplares=1,
            autor_id=author.id,
            categoria_ids=[category.id],
        ),
        db,
    )
    add_loan(
        db,
        overdue_member,
        overdue_book,
        loan_date=date.today() - timedelta(days=20),
        due_date=date.today() - timedelta(days=1),
    )
    assert (
        members.list_member_loans(
            overdue_member.id, db, Pagination(0, 10), EstadoPrestamo.vencido
        )[0].socio_id
        == overdue_member.id
    )
    assert (
        members.list_member_loans(
            other.id, db, Pagination(0, 10), None, owner_id=other.id
        )[0].id
        == active_loan.id
    )
    with pytest.raises(NoEncontrado):
        members.list_member_loans(other.id, db, Pagination(0, 10), None, owner_id=999)
    members.delete_member(other.id, db)
    assert db.get(Socio, other.id).activo is False

    member_with_user_history = members.create_member(
        SocioCreate(nombre="Socio con cuenta", email="account@example.com"), db
    )
    account = Usuario(
        email=member_with_user_history.email,
        nombre=member_with_user_history.nombre,
        password_hash=hash_password("BibliotecaSegura123"),
        rol="socio",
        socio=member_with_user_history,
    )
    db.add(account)
    db.flush()
    account_token = RefreshToken(
        jti="history-session",
        usuario_id=account.id,
        expira_en=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(account_token)
    history_book = books.create_book(
        LibroCreate(
            titulo="Libro de historial",
            isbn="9780000000004",
            anio_publicacion=2023,
            ejemplares=1,
            autor_id=author.id,
            categoria_ids=[category.id],
        ),
        db,
    )
    add_loan(
        db,
        member_with_user_history,
        history_book,
        returned=date.today(),
    )
    members.delete_member(member_with_user_history.id, db)
    db.refresh(account_token)
    assert account.activo is False
    assert account_token.revocado_en is not None

    fresh = members.create_member(
        SocioCreate(nombre="Socia Sin Historial", email="fresh@example.com"), db
    )
    members.delete_member(fresh.id, db)
    assert db.get(Socio, fresh.id) is None
    assert db.get(Autor, author.id) is not None
    assert db.get(Categoria, category.id) is not None


def test_controller_commit_failures_are_rolled_back_and_normalized(db, monkeypatch):
    author, category, member, book = seed_catalog(db)

    def fail_commit():
        raise IntegrityError("insert", {}, RuntimeError("duplicate"))

    monkeypatch.setattr(db, "commit", fail_commit)
    operations = (
        lambda: authors.create_author(AutorCreate(nombre="Commit Author"), db),
        lambda: categories.create_category(
            CategoriaCreate(nombre="Commit Category"), db
        ),
        lambda: books.create_book(
            LibroCreate(
                titulo="Commit Book",
                isbn="9780000000005",
                anio_publicacion=2024,
                ejemplares=1,
                autor_id=author.id,
                categoria_ids=[category.id],
            ),
            db,
        ),
        lambda: members.create_member(
            SocioCreate(nombre="Commit Member", email="commit@example.com"), db
        ),
        lambda: loans.create_loan(
            PrestamoCreate(libro_id=book.id, socio_id=member.id), db
        ),
    )
    for operation in operations:
        with pytest.raises(Conflicto):
            operation()


def test_report_helpers_cover_postgresql_and_empty_result_paths():
    class Dialect:
        name = "postgresql"

    class Bind:
        dialect = Dialect()

    class PostgreSQLSession:
        def get_bind(self):
            return Bind()

    assert reports._days_late_expression(PostgreSQLSession()) is not None

    class EmptyResultSession:
        def execute(self, _):
            class Result:
                def all(self):
                    return []

            return Result()

    assert reports._execute_report_page(
        EmptyResultSession(), select(literal("item").label("item"))
    ) == ([], 0)


def test_legacy_loan_route_returns_empty_for_unlinked_socio(db):
    user = Usuario(
        email="unlinked-legacy@example.com",
        nombre="Socio sin vínculo",
        password_hash="unused",
        rol="socio",
    )
    db.add(user)
    db.commit()
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/prestamos",
            "raw_path": b"/prestamos",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1),
        }
    )

    assert listar_prestamos(request, db, Pagination(0, 20), user) == []
