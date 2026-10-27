"""Crea de forma interactiva el primer administrador de la biblioteca."""

from getpass import getpass
import re

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from ..core.database import SessionLocal
from ..core.security import hash_password
from ..models import Usuario


def main() -> None:
    """Solicita credenciales sin eco y registra un administrador inicial."""
    email = TypeAdapter(EmailStr).validate_python(input("Correo del administrador: "))
    name = input("Nombre del administrador: ").strip()
    if not 2 <= len(name) <= 100:
        raise ValueError("El nombre debe tener entre 2 y 100 caracteres.")
    password = getpass("Contraseña (mínimo 12 caracteres): ")
    confirmation = getpass("Confirma la contraseña: ")
    if (
        len(password) < 12
        or not re.search(r"[A-Za-z]", password)
        or not re.search(r"\d", password)
    ):
        raise ValueError("La contraseña debe tener 12 caracteres, letras y números.")
    if password != confirmation:
        raise ValueError("Las contraseñas no coinciden.")

    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).where(Usuario.rol == "administrador")):
            raise RuntimeError("Ya existe un administrador; no se creó otra cuenta.")
        admin = Usuario(
            email=str(email).casefold(),
            nombre=name,
            password_hash=hash_password(password),
            rol="administrador",
        )
        db.add(admin)
        db.commit()
    print("Administrador creado correctamente.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, ValidationError) as error:
        raise SystemExit(str(error)) from error
