"""Excepciones de dominio traducidas a respuestas HTTP por FastAPI."""


class ErrorAplicacion(Exception):
    """Error de aplicación con el código HTTP que debe devolver la API."""

    status_code = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class NoEncontrado(ErrorAplicacion):
    """Indica que el recurso solicitado no existe."""

    status_code = 404


class Conflicto(ErrorAplicacion):
    """Indica que la operación entra en conflicto con el estado actual."""

    status_code = 409


class ReglaNegocio(ErrorAplicacion):
    """Indica que la solicitud incumple una regla de negocio."""

    status_code = 422


class NoAutenticado(ErrorAplicacion):
    """Credenciales ausentes, expiradas o no válidas."""

    status_code = 401


class Prohibido(ErrorAplicacion):
    """El usuario autenticado no tiene permiso para esta acción."""

    status_code = 403


class CuentaBloqueada(ErrorAplicacion):
    """La cuenta superó el número permitido de intentos fallidos."""

    status_code = 423
