"""
Codificadores: JPEG/WEBP/AVIF a calidad dada y variantes PNG.
"""
from __future__ import annotations

import io
import logging
from collections.abc import Callable

from PIL import Image

from .formats import _OPTIONAL_SAVE_KEYS, AVIF_SPEED, FLATTEN_BACKGROUND, WEBP_METHOD
from .image_ops import _exif_bytes, _flatten_to_rgb, _has_transparency, _icc_profile

logger: logging.Logger = logging.getLogger(name=__name__)


def _save_with_optional_metadata(
    im: Image.Image,
    buf: io.BytesIO,
    save_kwargs: dict,
) -> None:
    """Guarda una imagen, soltando metadata opcional de a una si el encoder
    la rechaza, hasta que el guardado funcione o no quede nada que sacar."""
    remaining = dict(save_kwargs)
    while True:
        try:
            buf.seek(0)
            buf.truncate(0)
            im.save(fp=buf, **remaining)
            return
        except (TypeError, ValueError) as exc:
            dropped: str | None = next((k for k in _OPTIONAL_SAVE_KEYS if k in remaining), None)
            if dropped is None:
                raise
            logger.warning(
                "Guardado de %s falló con la opción '%s' (%s); reintentando sin ella.",
                remaining.get("format"), dropped, exc,
            )
            remaining.pop(dropped)


def _encode(
    im: Image.Image,
    fmt: str,
    quality: int,
    *,
    jpeg_background: tuple[int, int, int] = FLATTEN_BACKGROUND,
    preserve_exif: bool = False,
) -> bytes:
    """Codifica la imagen en memoria y devuelve los bytes resultantes."""
    buf = io.BytesIO()
    save_kwargs = {"format": fmt, "quality": quality}

    icc: bytes | None = _icc_profile(im)
    if icc:
        save_kwargs["icc_profile"] = icc

    exif: bytes | None = _exif_bytes(im, preserve_exif)
    if exif:
        save_kwargs["exif"] = exif

    work_im: Image.Image = im
    if fmt == "JPEG":
        work_im = _flatten_to_rgb(im, background=jpeg_background)
    elif fmt == "WEBP":
        save_kwargs["method"] = WEBP_METHOD
    elif fmt == "AVIF":
        save_kwargs["speed"] = AVIF_SPEED

    _save_with_optional_metadata(work_im, buf, save_kwargs)
    return buf.getvalue()


def _quantize_for_png(im: Image.Image, colors: int) -> Image.Image:
    """Cuantiza a una paleta de `colors` colores con buen fallback."""
    work_im: Image.Image = im
    if work_im.mode not in ("RGB", "RGBA"):
        use_alpha: bool = _has_transparency(im)
        work_im = work_im.convert(mode="RGBA" if use_alpha else "RGB")

    try:
        return work_im.quantize(
            colors=colors,
            method=Image.Quantize.LIBIMAGEQUANT,
            dither=Image.Dither.FLOYDSTEINBERG,
        )
    except Exception as exc:  # noqa: BLE001
        # Pillow varía por build (LIBIMAGEQUANT puede faltar): el fallback
        # FASTOCTREE siempre existe, así que el broad except es intencional.
        logger.debug(
            "Cuantización con LIBIMAGEQUANT no disponible/falló (%s); "
            "usando FASTOCTREE como fallback.", exc,
        )
        return work_im.quantize(
            colors=colors,
            method=Image.Quantize.FASTOCTREE,
            dither=Image.Dither.FLOYDSTEINBERG,
        )


def _colors_for_quality(quality: int) -> int:
    """Mapeo compatible con la API anterior, acotado a 16-256 colores."""
    return max(16, min(256, int(16 + (quality - 10) * (240 / 85))))


def _quality_for_colors(colors: int, min_quality: int, max_quality: int) -> int:
    """Inversa aproximada de `_colors_for_quality`, acotada al rango pedido."""
    return max(min_quality, min(max_quality, round(number=10 + (colors - 16) * 85 / 240)))


def _encode_png_lossless(
    im: Image.Image,
    *,
    preserve_exif: bool = False,
) -> bytes:
    """Codifica PNG sin cuantizar (sin pérdida de color)."""
    buf = io.BytesIO()
    icc: bytes | None = _icc_profile(im)
    exif: bytes | None = _exif_bytes(im, preserve_exif)

    save_kwargs = {
        "format": "PNG",
        "optimize": True,
        "compress_level": 9,
    }
    if icc:
        save_kwargs["icc_profile"] = icc
    if exif:
        save_kwargs["exif"] = exif

    _save_with_optional_metadata(im, buf, save_kwargs)
    return buf.getvalue()


def _encode_png_with_colors(
    im: Image.Image,
    colors: int,
    *,
    preserve_exif: bool = False,
) -> bytes:
    """Encode PNG usando un número explícito de colores (cuantizado)."""
    buf = io.BytesIO()
    icc: bytes | None = _icc_profile(im)
    exif: bytes | None = _exif_bytes(im, preserve_exif)
    q: Image.Image = _quantize_for_png(im, colors)
    save_kwargs = {
        "format": "PNG",
        "optimize": True,
        "compress_level": 9,
    }
    if icc:
        save_kwargs["icc_profile"] = icc
    if exif:
        save_kwargs["exif"] = exif
    _save_with_optional_metadata(q, buf, save_kwargs)
    return buf.getvalue()


def _memoize_encoder(fn: Callable[[int], bytes]) -> Callable[[int], bytes]:
    """Cachea por calidad dentro de un mismo request para no recodificar la
    misma calidad varias veces (pasa en el peor caso: shortcut-check +
    búsqueda binaria + fallback pueden pedir `min_quality` hasta 3 veces)."""
    cache: dict[int, bytes] = {}

    def wrapped(quality: int) -> bytes:
        if quality not in cache:
            cache[quality] = fn(quality)
        return cache[quality]

    return wrapped


__all__: list[str] = [
    "_colors_for_quality",
    "_encode",
    "_encode_png_lossless",
    "_encode_png_with_colors",
    "_memoize_encoder",
    "_quality_for_colors",
    "_quantize_for_png",
    "_save_with_optional_metadata",
]
