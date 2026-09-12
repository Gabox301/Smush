"""
Estrategias de búsqueda: binaria para formatos con calidad continua
y discreta por paleta para PNG.
"""
from __future__ import annotations

from collections.abc import Callable

from PIL import Image

from .encode import (
    _colors_for_quality,
    _encode_png_lossless,
    _encode_png_with_colors,
    _quality_for_colors,
)
from .formats import PNG_COLOR_CANDIDATES, PNG_LOSSLESS_QUALITY, PNG_LOSSLESS_THRESHOLD


def _binary_search_quality(
    encode_fn: Callable[[int], bytes],
    target_size: float,
    min_quality: int,
    max_quality: int,
) -> tuple[int | None, bytes | None]:
    """Busca la calidad máxima cuyo tamaño queda dentro del objetivo."""
    lo, hi = min_quality, max_quality
    best_quality: int | None = None
    best_bytes: bytes | None = None

    while lo <= hi:
        mid: int = (lo + hi) // 2
        data: bytes = encode_fn(mid)
        if len(data) <= target_size:
            best_quality = mid
            best_bytes = data
            lo: int = mid + 1
        else:
            hi: int = mid - 1

    return best_quality, best_bytes


def _best_effort_encode(
    encode_fn: Callable[[int], bytes],
    target_size: float,
    min_quality: int,
    max_quality: int,
) -> tuple[int, bytes, bool]:
    """Versión segura de la búsqueda binaria."""
    quality, data = _binary_search_quality(
        encode_fn, target_size, min_quality, max_quality
    )
    if quality is not None and data is not None:
        return quality, data, True

    return min_quality, encode_fn(min_quality), False


def _best_png_encode(
    im: Image.Image,
    target_size: float,
    min_quality: int,
    max_quality: int,
    *,
    preserve_exif: bool = False,
) -> tuple[int, bytes, bool, str]:
    """Busca la mejor variante PNG sin asumir monotonicidad de quality->bytes.

    Primero prueba PNG lossless. Si no alcanza, prueba explícitamente varias
    paletas y escoge la de mayor número de colores que cumple el presupuesto.
    """
    if max_quality >= PNG_LOSSLESS_THRESHOLD:
        lossless: bytes = _encode_png_lossless(im, preserve_exif=preserve_exif)
        if len(lossless) <= target_size:
            return PNG_LOSSLESS_QUALITY, lossless, True, "PNG optimizado sin pérdida"

    candidate_colors = list(PNG_COLOR_CANDIDATES)
    # Convertimos los límites de quality a un rango de colores razonable.
    min_colors: int = _colors_for_quality(quality=min_quality)
    max_colors: int = _colors_for_quality(quality=max_quality)
    candidate_colors: list[int] = [c for c in candidate_colors if min_colors <= c <= max_colors]

    # Aseguramos que siempre haya al menos una prueba en cada extremo.
    candidate_colors = sorted({*candidate_colors, min_colors, max_colors})

    best_colors: int | None = None
    best_bytes: bytes | None = None
    for colors in candidate_colors:
        data: bytes = _encode_png_with_colors(
            im,
            colors,
            preserve_exif=preserve_exif,
        )
        if len(data) <= target_size and (
            best_colors is None or colors > best_colors
        ):
            best_colors = colors
            best_bytes = data

    if best_colors is None or best_bytes is None:
        # Probamos la paleta mínima incluso si cae fuera de los candidatos.
        data = _encode_png_with_colors(
            im,
            colors=min_colors,
            preserve_exif=preserve_exif,
        )
        return min_quality, data, False, "No se pudo alcanzar el objetivo ni con la paleta mínima"

    # La calidad devuelta es una aproximación consistente con la función
    # anterior; el dato realmente utilizado por PNG es el número de colores.
    quality: int = _quality_for_colors(best_colors, min_quality, max_quality)
    return quality, best_bytes, True, f"PNG cuantizado a {best_colors} colores"


__all__: list[str] = [
    "_best_effort_encode",
    "_best_png_encode",
    "_binary_search_quality",
]
