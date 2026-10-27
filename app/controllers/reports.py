"""Consultas agregadas para los informes de actividad de la biblioteca."""

from datetime import date

from sqlalchemy import Integer, case, distinct, func, select
from sqlalchemy.orm import Session

from ..core.dependencies import Pagination
from ..models import Autor, Categoria, Libro, Prestamo, Socio, libro_categoria


def most_borrowed_books(
    db: Session, skip: int, limit: int
) -> list[dict]:
    """Devuelve el ranking de libros ordenado por cantidad de préstamos."""
    query = (
        select(
            Libro.id.label("libro_id"),
            Libro.titulo.label("titulo"),
            Autor.nombre.label("autor"),
            func.count(Prestamo.id).label("total_prestamos"),
        )
        .join(Libro.autor)
        .join(Prestamo, Prestamo.libro_id == Libro.id)
        .group_by(Libro.id, Libro.titulo, Autor.nombre)
        .order_by(func.count(Prestamo.id).desc(), Libro.titulo, Libro.id)
        .offset(skip)
        .limit(limit)
    )
    return [dict(row._mapping) for row in db.execute(query)]


def books_by_category(db: Session, pagination: Pagination) -> list[dict]:
    """Cuenta libros por categoría, incluidas las categorías vacías."""
    query = (
        select(
            Categoria.id.label("categoria_id"),
            Categoria.nombre.label("nombre"),
            func.count(distinct(libro_categoria.c.libro_id)).label("total_libros"),
        )
        .outerjoin(
            libro_categoria, libro_categoria.c.categoria_id == Categoria.id
        )
        .group_by(Categoria.id, Categoria.nombre)
        .order_by(Categoria.nombre, Categoria.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    return [dict(row._mapping) for row in db.execute(query)]


def overdue_loans(db: Session, pagination: Pagination) -> list[dict]:
    """Lista préstamos sin devolver y calcula sus días de retraso."""
    late_days = _days_late_expression(db)
    query = (
        select(
            Prestamo.id.label("prestamo_id"),
            Libro.titulo.label("titulo"),
            Socio.nombre.label("socio"),
            Socio.email.label("email"),
            Prestamo.fecha_limite.label("fecha_limite"),
            late_days.label("dias_retraso"),
        )
        .join(Prestamo.libro)
        .join(Prestamo.socio)
        .where(
            Prestamo.fecha_devolucion.is_(None),
            Prestamo.fecha_limite < date.today(),
        )
        .order_by(Prestamo.fecha_limite, Prestamo.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    return [dict(row._mapping) for row in db.execute(query)]


def members_with_fines(db: Session, pagination: Pagination) -> list[dict]:
    """Agrupa multas positivas por socio y ordena por importe acumulado."""
    fine_total = func.sum(Prestamo.multa)
    fine_loans = func.count(case((Prestamo.multa > 0, Prestamo.id)))
    query = (
        select(
            Socio.id.label("socio_id"),
            Socio.nombre.label("nombre"),
            Socio.email.label("email"),
            fine_total.label("total_multas"),
            fine_loans.label("prestamos_con_multa"),
        )
        .join(Prestamo, Prestamo.socio_id == Socio.id)
        .group_by(Socio.id, Socio.nombre, Socio.email)
        .having(fine_total > 0)
        .order_by(fine_total.desc(), Socio.nombre)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    return [dict(row._mapping) for row in db.execute(query)]


def authors_summary(db: Session, pagination: Pagination) -> list[dict]:
    """Resume libros, ejemplares y préstamos por autor sin duplicar agregados."""
    book_totals = (
        select(
            Libro.autor_id.label("autor_id"),
            func.count(Libro.id).label("total_libros"),
            func.sum(Libro.ejemplares).label("total_ejemplares"),
        )
        .group_by(Libro.autor_id)
        .subquery()
    )
    loan_totals = (
        select(
            Libro.autor_id.label("autor_id"),
            func.count(Prestamo.id).label("total_prestamos"),
        )
        .join(Prestamo, Prestamo.libro_id == Libro.id)
        .group_by(Libro.autor_id)
        .subquery()
    )
    query = (
        select(
            Autor.id.label("autor_id"),
            Autor.nombre.label("nombre"),
            func.coalesce(book_totals.c.total_libros, 0).label("total_libros"),
            func.coalesce(book_totals.c.total_ejemplares, 0).label(
                "total_ejemplares"
            ),
            func.coalesce(loan_totals.c.total_prestamos, 0).label(
                "total_prestamos"
            ),
        )
        .outerjoin(book_totals, book_totals.c.autor_id == Autor.id)
        .outerjoin(loan_totals, loan_totals.c.autor_id == Autor.id)
        .group_by(
            Autor.id,
            Autor.nombre,
            book_totals.c.total_libros,
            book_totals.c.total_ejemplares,
            loan_totals.c.total_prestamos,
        )
        .order_by(Autor.nombre, Autor.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    return [dict(row._mapping) for row in db.execute(query)]


def library_summary(db: Session) -> dict:
    """Calcula los indicadores globales en una sola consulta."""
    active_loans = select(func.count(Prestamo.id)).where(
        Prestamo.fecha_devolucion.is_(None)
    ).scalar_subquery()
    overdue = select(func.count(Prestamo.id)).where(
        Prestamo.fecha_devolucion.is_(None),
        Prestamo.fecha_limite < date.today(),
    ).scalar_subquery()
    query = select(
        select(func.count(Libro.id)).scalar_subquery().label("total_libros"),
        select(func.coalesce(func.sum(Libro.ejemplares), 0))
        .select_from(Libro)
        .scalar_subquery()
        .label("total_ejemplares"),
        active_loans.label("prestamos_activos"),
        select(func.count(Socio.id))
        .where(Socio.activo.is_(True))
        .scalar_subquery()
        .label("socios_activos"),
        overdue.label("prestamos_vencidos"),
        select(func.coalesce(func.sum(Prestamo.multa), 0))
        .select_from(Prestamo)
        .scalar_subquery()
        .label("multas_totales"),
    )
    return dict(db.execute(query).one()._mapping)


def _days_late_expression(db: Session):
    """Calcula días de retraso con una expresión compatible con PostgreSQL y SQLite."""
    today = date.today()
    if db.get_bind().dialect.name == "postgresql":
        return today - Prestamo.fecha_limite
    return func.cast(
        func.julianday(today)
        - func.julianday(Prestamo.fecha_limite),
        Integer,
    )
