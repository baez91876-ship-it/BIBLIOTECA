"""Traduce restricciones de integridad sin dejar transacciones abiertas."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .exceptions import Conflicto


def commit_or_conflict(db: Session, message: str) -> None:
    """Confirma cambios o revierte la sesión antes de informar el conflicto."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflicto(message) from exc
