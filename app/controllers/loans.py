from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..core.dependencies import Pagination
from ..core.exceptions import Conflicto, NoEncontrado, ReglaNegocio
from ..models import Libro, Prestamo, Socio
from ..schemas.prestamo import DevolucionCreate, EstadoPrestamo, PrestamoCreate


def _loan_options():
    return joinedload(Prestamo.socio), joinedload(Prestamo.libro).selectinload(
        Libro.autor
    ), joinedload(Prestamo.libro).selectinload(
        Libro.categorias
    ), joinedload(Prestamo.libro).selectinload(Libro.prestamos)


def list_loans(
    db: Session,
    pagination: Pagination,
    estado: EstadoPrestamo | None = None,
    socio_id: int | None = None,
    libro_id: int | None = None,
) -> list[Prestamo]:
    query = select(Prestamo).options(*_loan_options())
    if estado == EstadoPrestamo.devuelto:
        query = query.where(Prestamo.fecha_devolucion.is_not(None))
    elif estado == EstadoPrestamo.vencido:
        query = query.where(
            Prestamo.fecha_devolucion.is_(None),
            Prestamo.fecha_limite < date.today(),
        )
    elif estado == EstadoPrestamo.activo:
        query = query.where(
            Prestamo.fecha_devolucion.is_(None),
            Prestamo.fecha_limite >= date.today(),
        )
    if socio_id is not None:
        query = query.where(Prestamo.socio_id == socio_id)
    if libro_id is not None:
        query = query.where(Prestamo.libro_id == libro_id)
    return db.scalars(
        query.order_by(Prestamo.fecha_prestamo.desc(), Prestamo.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    ).unique().all()


def get_loan(loan_id: int, db: Session) -> Prestamo:
    loan = db.scalar(
        select(Prestamo)
        .where(Prestamo.id == loan_id)
        .options(*_loan_options())
    )
    if loan is None:
        raise NoEncontrado("Préstamo no encontrado")
    return loan


def create_loan(data: PrestamoCreate, db: Session) -> Prestamo:
    member = db.scalar(
        select(Socio).where(Socio.id == data.socio_id).with_for_update()
    )
    if member is None:
        raise NoEncontrado("Socio no encontrado")
    book = db.scalar(select(Libro).where(Libro.id == data.libro_id).with_for_update())
    if book is None:
        raise NoEncontrado("Libro no encontrado")
    if not member.activo:
        raise ReglaNegocio("El socio no está activo")
    today = date.today()
    overdue = db.scalar(
        select(Prestamo.id).where(
            Prestamo.socio_id == member.id,
            Prestamo.fecha_devolucion.is_(None),
            Prestamo.fecha_limite < today,
        )
    )
    if overdue is not None:
        raise ReglaNegocio("El socio tiene préstamos vencidos")
    active_for_member = db.scalar(
        select(func.count(Prestamo.id)).where(
            Prestamo.socio_id == member.id,
            Prestamo.fecha_devolucion.is_(None),
        )
    )
    if active_for_member >= 3:
        raise ReglaNegocio("Máximo de 3 préstamos")
    duplicate = db.scalar(
        select(Prestamo.id).where(
            Prestamo.socio_id == member.id,
            Prestamo.libro_id == book.id,
            Prestamo.fecha_devolucion.is_(None),
        )
    )
    if duplicate is not None:
        raise Conflicto("El socio ya tiene este libro sin devolver")
    active_for_book = db.scalar(
        select(func.count(Prestamo.id)).where(
            Prestamo.libro_id == book.id,
            Prestamo.fecha_devolucion.is_(None),
        )
    )
    if book.ejemplares - active_for_book <= 0:
        raise ReglaNegocio("No hay ejemplares disponibles")
    loan_date = data.fecha_prestamo or today
    if loan_date > today:
        raise ReglaNegocio("La fecha del préstamo no puede ser futura")
    loan = Prestamo(
        socio_id=member.id,
        libro_id=book.id,
        fecha_prestamo=loan_date,
        fecha_limite=loan_date + timedelta(days=data.dias),
        multa=Decimal("0"),
    )
    db.add(loan)
    _commit(db)
    return get_loan(loan.id, db)


def return_loan(
    loan_id: int, data: DevolucionCreate, db: Session
) -> Prestamo:
    loan = db.scalar(
        select(Prestamo).where(Prestamo.id == loan_id).with_for_update()
    )
    if loan is None:
        raise NoEncontrado("Préstamo no encontrado")
    if loan.fecha_devolucion is not None:
        raise Conflicto("El préstamo ya fue devuelto")
    if data.fecha_devolucion < loan.fecha_prestamo:
        raise ReglaNegocio("La devolución no puede ser anterior al préstamo")
    late_days = max((data.fecha_devolucion - loan.fecha_limite).days, 0)
    loan.fecha_devolucion = data.fecha_devolucion
    loan.multa = Decimal(late_days) * Decimal("0.50")
    _commit(db)
    return get_loan(loan.id, db)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto("No se pudo guardar el préstamo") from exc
