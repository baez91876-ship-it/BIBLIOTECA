from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..core.dependencies import Pagination
from ..core.exceptions import Conflicto, NoEncontrado
from ..models import Libro, Prestamo, Socio
from ..schemas.prestamo import EstadoPrestamo
from ..schemas.socio import SocioCreate, SocioPatch


def list_members(
    db: Session, pagination: Pagination, activo: bool | None = None
) -> list[Socio]:
    query = select(Socio).order_by(Socio.nombre, Socio.id)
    if activo is not None:
        query = query.where(Socio.activo.is_(activo))
    return db.scalars(query.offset(pagination.skip).limit(pagination.limit)).all()


def get_member(member_id: int, db: Session) -> Socio:
    member = db.get(Socio, member_id)
    if member is None:
        raise NoEncontrado("Socio no encontrado")
    return member


def create_member(data: SocioCreate, db: Session) -> Socio:
    if db.scalar(select(Socio.id).where(Socio.email == str(data.email).lower())):
        raise Conflicto("El correo electrónico ya está registrado")
    member = Socio(**data.model_dump())
    db.add(member)
    _commit(db)
    db.refresh(member)
    return member


def patch_member(member_id: int, data: SocioPatch, db: Session) -> Socio:
    member = get_member(member_id, db)
    changes = data.model_dump(exclude_unset=True)
    email = changes.get("email")
    if email is not None and db.scalar(
        select(Socio.id).where(
            Socio.email == str(email).lower(), Socio.id != member_id
        )
    ):
        raise Conflicto("El correo electrónico ya está registrado")
    for field, value in changes.items():
        setattr(member, field, value)
    _commit(db)
    db.refresh(member)
    return member


def delete_member(member_id: int, db: Session) -> None:
    member = get_member(member_id, db)
    active_loan = db.scalar(
        select(Prestamo.id).where(
            Prestamo.socio_id == member_id, Prestamo.fecha_devolucion.is_(None)
        )
    )
    if active_loan is not None:
        raise Conflicto("No se puede eliminar un socio con préstamos sin devolver")
    history = db.scalar(
        select(Prestamo.id).where(Prestamo.socio_id == member_id)
    )
    if history is not None:
        member.activo = False
        db.commit()
        return
    db.delete(member)
    db.commit()


def list_member_loans(
    member_id: int,
    db: Session,
    pagination: Pagination,
    estado: EstadoPrestamo | None,
) -> list[Prestamo]:
    get_member(member_id, db)
    query = select(Prestamo).where(Prestamo.socio_id == member_id)
    query = query.options(
        joinedload(Prestamo.socio),
        joinedload(Prestamo.libro).selectinload(Libro.autor),
        joinedload(Prestamo.libro).selectinload(Libro.categorias),
        joinedload(Prestamo.libro).selectinload(Libro.prestamos),
    )
    query = _filter_state(query, estado)
    return db.scalars(
        query.order_by(Prestamo.fecha_prestamo.desc(), Prestamo.id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    ).all()


def _filter_state(query, estado: EstadoPrestamo | None):
    from datetime import date

    if estado == EstadoPrestamo.devuelto:
        return query.where(Prestamo.fecha_devolucion.is_not(None))
    if estado == EstadoPrestamo.vencido:
        return query.where(
            Prestamo.fecha_devolucion.is_(None), Prestamo.fecha_limite < date.today()
        )
    if estado == EstadoPrestamo.activo:
        return query.where(
            Prestamo.fecha_devolucion.is_(None), Prestamo.fecha_limite >= date.today()
        )
    return query


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto("El correo electrónico ya está registrado") from exc
