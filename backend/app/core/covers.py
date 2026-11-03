"""Subida firmada de portadas, sin exponer credenciales al navegador."""

import logging
import warnings
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import get_settings
from .exceptions import ReglaNegocio, ServicioNoDisponible

logger = logging.getLogger("uvicorn.error")
MAX_COVER_BYTES = 5 * 1024 * 1024
MAX_COVER_PIXELS = 20_000_000


@dataclass(frozen=True)
class Cover:
    url: str
    public_id: str


def _credentials() -> dict[str, str]:
    settings = get_settings()
    if not (
        settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret
        and settings.cloudinary_api_key.get_secret_value()
        and settings.cloudinary_api_secret.get_secret_value()
    ):
        logger.warning("Subida de portada rechazada: Cloudinary no está configurado.")
        raise ServicioNoDisponible("Configura Cloudinary en el backend para subir portadas.")
    return {
        "cloud_name": settings.cloudinary_cloud_name,
        "api_key": settings.cloudinary_api_key.get_secret_value(),
        "api_secret": settings.cloudinary_api_secret.get_secret_value(),
    }


def _normalize_image(data: bytes) -> BytesIO:
    if not data or len(data) > MAX_COVER_BYTES:
        raise ReglaNegocio("La portada debe ocupar entre 1 byte y 5 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ReglaNegocio("La portada debe ser una imagen JPEG, PNG o WebP.")
                if image.width * image.height > MAX_COVER_PIXELS:
                    raise ReglaNegocio("La portada no puede superar 20 megapíxeles.")
                image.load()
                normalized = ImageOps.exif_transpose(image)
                normalized.thumbnail((1200, 1600))
                background = Image.new("RGBA", normalized.size, "white")
                normalized = Image.alpha_composite(background, normalized.convert("RGBA"))
                result = BytesIO()
                normalized.convert("RGB").save(result, format="JPEG", quality=85)
                result.seek(0)
                return result
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ReglaNegocio("El archivo no es una imagen válida o es demasiado grande.") from exc


def upload_cover(data: bytes) -> Cover:
    image = _normalize_image(data)
    credentials = _credentials()
    public_id = f"biblioteca/portadas/{uuid4()}"
    try:
        result = cloudinary.uploader.upload(
            image, **credentials, public_id=public_id, resource_type="image",
            overwrite=False, allowed_formats=["jpg"], timeout=20,
        )
    except CloudinaryError as exc:
        logger.error("Cloudinary no pudo subir la portada (%s).", type(exc).__name__)
        raise ServicioNoDisponible("No se pudo subir la portada a Cloudinary. Inténtalo de nuevo.") from exc
    url = result.get("secure_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        logger.error("Cloudinary devolvió una respuesta de subida inválida.")
        try:
            delete_cover(public_id)
        except ServicioNoDisponible:
            logger.error("No se pudo limpiar la portada de una respuesta inválida.")
        raise ServicioNoDisponible("Cloudinary no devolvió una URL HTTPS de la portada.")
    return Cover(url=url, public_id=public_id)


def delete_cover(public_id: str) -> None:
    try:
        result = cloudinary.uploader.destroy(
            public_id, **_credentials(), resource_type="image",
            invalidate=True, timeout=20,
        )
    except CloudinaryError as exc:
        logger.error("Cloudinary no pudo borrar la portada (%s).", type(exc).__name__)
        raise ServicioNoDisponible("No se pudo eliminar la portada anterior de Cloudinary.") from exc
    if result.get("result") not in {"ok", "not found"}:
        logger.error("Cloudinary devolvió una respuesta de borrado inválida.")
        raise ServicioNoDisponible("Cloudinary no confirmó el borrado de la portada.")
