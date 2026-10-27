"""Consultas y reglas de negocio para socios y su historial de préstamos."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..core.dependencies import Pagination
from ..core.exceptions import Conflicto, NoEncontrado
from ..core.pagination import execute_page
from ..models import Libro, Prestamo, RefreshToken, Socio, Usuario
from ..schemas.prestamo import EstadoPrestamo
from ..schemas.socio import SocioCreate, SocioPatch


def list_members(
    db: Session,
    pagination: Pagination,
    activo: bool | None = None,
    owner_id: int | None = None,
    include_total: bool = False,
) -> list[Socio] | tuple[list[Socio], int]:
    """Lista socios en orden estable y permite filtrar por estado."""
    query = select(Socio).order_by(Socio.nombre, Socio.id)
    if activo is not None:
        query = query.where(Socio.activo.is_(activo))
    if owner_id is not None:
        query = query.where(Socio.id == owner_id)
    if include_total:
        return execute_page(db, query, pagination)
    return db.scalars(query.offset(pagination.skip).limit(pagination.limit)).all()


def get_member(member_id: int, db: Session, owner_id: int | None = None) -> Socio:
    """Obtiene un socio o informa que no existe."""
    query = select(Socio).where(Socio.id == member_id)
    if owner_id is not None:
        query = query.where(Socio.id == owner_id)
    member = db.scalar(query)
    if member is None:
        raise NoEncontrado("Socio no encontrado")
    return member


def create_member(data: SocioCreate, db: Session) -> Socio:
    """Crea un socio normalizando y protegiendo su correo electrónico."""
    if db.scalar(select(Socio.id).where(Socio.email == str(data.email).lower())):
        raise Conflicto("El correo electrónico ya está registrado")
    member = Socio(**data.model_dump())
    db.add(member)
    _commit(db)
    db.refresh(member)
    return member


def patch_member(member_id: int, data: SocioPatch, db: Session) -> Socio:
    """Actualiza los campos enviados y garantiza que el correo no se repita."""
    member = get_member(member_id, db)
    changes = data.model_dump(exclude_unset=True)
    email = changes.get("email")
    if email is not None and db.scalar(
        select(Socio.id).where(Socio.email == str(email).lower(), Socio.id != member_id)
    ):
        raise Conflicto("El correo electrónico ya está registrado")
    if email is not None and member.usuario is not None:
        duplicate_user = db.scalar(
            select(Usuario.id).where(
                Usuario.email == str(email).lower(),
                Usuario.id != member.usuario.id,
            )
        )
        if duplicate_user:
            raise Conflicto("El correo electrónico ya está registrado")
    for field, value in changes.items():
        setattr(member, field, value)
        if member.usuario is not None and field in {"email", "nombre"}:
            setattr(member.usuario, field, value)
        if member.usuario is not None and field == "activo":
            member.usuario.activo = value
            if not value:
                _revoke_user_refresh_tokens(db, member.usuario.id)
    _commit(db)
    db.refresh(member)
    return member


def delete_member(member_id: int, db: Session) -> None:
    """Impide borrar préstamos abiertos y conserva como inactivo el historial."""
    member = get_member(member_id, db)
    active_loan = db.scalar(
        select(Prestamo.id).where(
            Prestamo.socio_id == member_id, Prestamo.fecha_devolucion.is_(None)
        )
    )
    if active_loan is not None:
        raise Conflicto("No se puede eliminar un socio con préstamos sin devolver")
    history = db.scalar(select(Prestamo.id).where(Prestamo.socio_id == member_id))
    if history is not None:
        member.activo = False
        if member.usuario is not None:
            member.usuario.activo = False
            _revoke_user_refresh_tokens(db, member.usuario.id)
        db.commit()
        return
    if member.usuario is not None:
        db.delete(member.usuario)
    db.delete(member)
    db.commit()


def list_member_loans(
    member_id: int,
    db: Session,
    pagination: Pagination,
    estado: EstadoPrestamo | None,
    owner_id: int | None = None,
    include_total: bool = False,
) -> list[Prestamo] | tuple[list[Prestamo], int]:
    """Lista el historial de un socio, opcionalmente filtrado por estado."""
    get_member(member_id, db, owner_id)
    query = select(Prestamo).where(Prestamo.socio_id == member_id)
    query = query.options(
        joinedload(Prestamo.socio),
        joinedload(Prestamo.libro).selectinload(Libro.autor),
        joinedload(Prestamo.libro).selectinload(Libro.categorias),
        joinedload(Prestamo.libro).selectinload(Libro.prestamos),
    )
    query = _filter_state(query, estado)
    query = query.order_by(Prestamo.fecha_prestamo.desc(), Prestamo.id)
    if include_total:
        return execute_page(db, query, pagination)
    return db.scalars(
        query.offset(pagination.skip).limit(pagination.limit)
    ).unique().all()


def _filter_state(query, estado: EstadoPrestamo | None):
    """Añade al query las condiciones de estado vigentes según la fecha actual."""
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
    """Revierte la transacción y traduce correos duplicados a conflicto."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto("El correo electrónico ya está registrado") from exc


def _revoke_user_refresh_tokens(db: Session, user_id: int) -> None:
    """Revoca todas las sesiones vigentes de una cuenta desactivada."""
    db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.usuario_id == user_id,
            RefreshToken.revocado_en.is_(None),
        )
        .values(revocado_en=datetime.now(UTC))
    )
