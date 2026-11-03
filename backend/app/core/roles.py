"""Roles del sistema y matriz de permisos por recurso."""

from enum import StrEnum


class Rol(StrEnum):
    """Roles asignables a usuarios autenticados."""

    socio = "socio"
    bibliotecario = "bibliotecario"
    administrador = "administrador"
