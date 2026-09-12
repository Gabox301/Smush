"""
Operaciones sobre imágenes Pillow: orientación, transparencia y metadata.
"""
from __future__ import annotations

import logging

from PIL import Image, ImageOps

from .formats import FLATTEN_BACKGROUND

logger: logging.Logger = logging.getLogger(name=__name__)


def _prepare_image(im: Image.Image) -> Image.Image:
    """Corrige orientación EXIF antes de cualquier otra operación."""
    return ImageOps.exif_transpose(image=im) or im


def _close_quietly(im: Image.Image) -> None:
    """Cierra sin romper: el caller ya tiene lo que necesita de la imagen."""
    try:
        im.close()
    except Exception:  # noqa: BLE001, S110
        pass


def _has_transparency(im: Image.Image) -> bool:
    if im.mode in ("RGBA", "LA"):
        return True
    if im.mode == "P" and "transparency" in im.info:
        return True
    return "A" in im.getbands()


def _flatten_to_rgb(
    im: Image.Image,
    background: tuple[int, int, int] = FLATTEN_BACKGROUND,
) -> Image.Image:
    """Compone la imagen sobre un fondo sólido y devuelve una versión RGB.

    Se usa para dos cosas distintas a propósito con la misma lógica:
    1) Preparar el guardado real en JPEG (que no admite alfa).
    2) Normalizar CUALQUIER imagen con transparencia (PNG/WEBP/AVIF) antes de
       compararla para PSNR, de forma que los píxeles totalmente invisibles
       -que suelen tener colores arbitrarios "de relleno"- no distorsionen
       la métrica de calidad.
    """
    if not _has_transparency(im):
        return im.convert(mode="RGB") if im.mode != "RGB" else im

    rgba: Image.Image = im.convert(mode="RGBA")
    flat: Image.Image = Image.new(mode="RGB", size=rgba.size, color=background)
    flat.paste(im=rgba, mask=rgba.getchannel(channel="A"))
    return flat


def _icc_profile(im: Image.Image) -> bytes | None:
    return im.info.get("icc_profile")


def _exif_bytes(im: Image.Image, preserve_exif: bool) -> bytes | None:
    if not preserve_exif:
        return None
    try:
        exif: Image.Exif = im.getexif()
        if not exif:
            return None
        # exif_transpose ha aplicado físicamente la orientación; para evitar
        # que un visor vuelva a rotarla, dejamos Orientation = 1.
        orientation_tag = 274
        if orientation_tag in exif:
            exif[orientation_tag] = 1
        return exif.tobytes()
    except Exception:
        logger.debug(msg="No se pudo leer/normalizar EXIF; se omite.", exc_info=True)
        return None


__all__: list[str] = [
    "_close_quietly",
    "_exif_bytes",
    "_flatten_to_rgb",
    "_has_transparency",
    "_icc_profile",
    "_prepare_image",
]
