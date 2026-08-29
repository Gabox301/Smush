"""
Núcleo de compresión de imágenes.

Comprime imágenes (AVIF, WEBP, JPEG, PNG) a un porcentaje objetivo de su
tamaño original en bytes, manteniendo siempre las dimensiones originales.
Usa búsqueda binaria sobre el parámetro "quality" para encontrar el valor
más alto que aún cumple el tamaño objetivo (mejor calidad posible dentro
del presupuesto de peso pedido).
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image

QUALITY_FORMATS = {"AVIF", "WEBP", "JPEG"}

EXTENSION_TO_FORMAT = {
    ".avif": "AVIF",
    ".webp": "WEBP",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
}

SUPPORTED_EXTENSIONS = set(EXTENSION_TO_FORMAT.keys())


class UnsupportedFormatError(Exception):
    pass


def format_for_extension(ext: str) -> str:
    ext = ext.lower()
    if ext not in EXTENSION_TO_FORMAT:
        raise UnsupportedFormatError(f"Extensión no soportada: {ext}")
    return EXTENSION_TO_FORMAT[ext]


def _save_with_quality(im: Image.Image, path: Path, fmt: str, quality: int) -> int:
    save_kwargs = {"format": fmt, "quality": quality}
    if fmt == "WEBP":
        save_kwargs["method"] = 6
    work_im = im
    if fmt == "JPEG" and im.mode in ("RGBA", "P"):
        work_im = im.convert("RGB")
    work_im.save(path, **save_kwargs)
    return path.stat().st_size


def compress_to_target(
    input_path: Path,
    output_path: Path,
    target_ratio: float,
    min_quality: int = 10,
    max_quality: int = 95,
) -> dict:
    """
    Comprime input_path buscando la calidad más alta que da un archivo
    de tamaño <= target_ratio * tamaño_original. No modifica dimensiones.
    Devuelve un dict con metadata del resultado.
    """
    im = Image.open(input_path)
    im.load()

    original_size = input_path.stat().st_size
    target_size = max(1, original_size * target_ratio)
    fmt = format_for_extension(input_path.suffix)

    if fmt not in QUALITY_FORMATS:
        im.save(output_path, format=fmt, optimize=True, compress_level=9)
        new_size = output_path.stat().st_size
        return {
            "original_size": original_size,
            "new_size": new_size,
            "quality": None,
            "width": im.size[0],
            "height": im.size[1],
            "note": "PNG comprimido sin pérdida (no admite 'quality' ajustable)",
        }

    lo, hi = min_quality, max_quality
    best_quality = None
    best_size = None

    while lo <= hi:
        mid = (lo + hi) // 2
        size = _save_with_quality(im, output_path, fmt, mid)
        if size <= target_size:
            best_quality = mid
            best_size = size
            lo = mid + 1
        else:
            hi = mid - 1

    if best_quality is None:
        best_quality = min_quality
        best_size = _save_with_quality(im, output_path, fmt, best_quality)
    else:
        # Re-guardar con la mejor calidad encontrada (por si la última
        # iteración del loop dejó el archivo en otra calidad)
        best_size = _save_with_quality(im, output_path, fmt, best_quality)

    return {
        "original_size": original_size,
        "new_size": best_size,
        "quality": best_quality,
        "width": im.size[0],
        "height": im.size[1],
        "note": None,
    }
