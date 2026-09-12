"""
Formatos, constantes y validación de parámetros.

No depende de ningún otro módulo del paquete.
"""
from __future__ import annotations


class UnsupportedFormatError(Exception):
    """La extensión del archivo no está soportada."""


EXTENSION_TO_FORMAT: dict[str, str] = {
    ".avif": "AVIF",
    ".webp": "WEBP",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
}

SUPPORTED_EXTENSIONS: set[str] = set(EXTENSION_TO_FORMAT.keys())

# Formatos destino válidos para convert_format y su extensión de salida.
TARGET_FORMATS: tuple[str, ...] = ("AVIF", "WEBP", "JPEG", "PNG")
TARGET_FORMAT_TO_EXTENSION: dict[str, str] = {
    "AVIF": ".avif",
    "WEBP": ".webp",
    "JPEG": ".jpg",
    "PNG": ".png",
}

# Valores pensados para maximizar calidad por byte en backend.
AVIF_SPEED = 4  # 0 = más lento/mejor, 10 = más rápido/peor
WEBP_METHOD = 6

FLATTEN_BACKGROUND = (255, 255, 255)

# PNG: candidatos explícitos. Es preferible no asumir monotonicidad perfecta
# entre "quality" y tamaño cuando cambia la paleta.
PNG_COLOR_CANDIDATES = (16, 32, 64, 96, 128, 160, 192, 224, 256)
PNG_LOSSLESS_QUALITY = 100
PNG_LOSSLESS_THRESHOLD = 92  # a partir de esta "calidad" se intenta PNG sin pérdida

# Piso de calidad perceptual. Si el tamaño objetivo solo se logra por debajo
# de este PSNR, el resultado igual se entrega (el caller decide) pero
# `quality_acceptable` viene en False para que no pase desapercibido.
MIN_ACCEPTABLE_PSNR_DB = 40.0

# Claves opcionales que se pueden ir sacando de a una si el encoder las
# rechaza, en orden de "menos crítica primero".
_OPTIONAL_SAVE_KEYS: tuple[str, ...] = ("exif", "icc_profile", "method", "speed")


def format_for_extension(ext: str) -> str:
    ext = ext.lower()
    if ext not in EXTENSION_TO_FORMAT:
        raise UnsupportedFormatError(f"Extensión no soportada: {ext}")
    return EXTENSION_TO_FORMAT[ext]


def check_avif_support() -> bool:
    """Chequeo explícito de si este build de Pillow puede codificar AVIF.

    Útil para validar el entorno de despliegue en vez de descubrirlo con un
    error críptico a mitad de un request real.
    """
    try:
        from PIL import features
        return bool(features.check(feature="avif"))
    except Exception:  # noqa: BLE001
        # Cualquier fallo (módulo ausente, build vieja) = sin AVIF.
        return False


def _validate_parameters(target_ratio: float, min_quality: int, max_quality: int) -> None:
    if not 0 < target_ratio <= 1:
        raise ValueError("target_ratio debe estar entre 0 (exclusivo) y 1 (inclusive)")
    if not 1 <= min_quality <= 100:
        raise ValueError("min_quality debe estar entre 1 y 100")
    if not 1 <= max_quality <= 100:
        raise ValueError("max_quality debe estar entre 1 y 100")
    if min_quality > max_quality:
        raise ValueError("min_quality no puede ser mayor que max_quality")


__all__: list[str] = [
    "AVIF_SPEED",
    "EXTENSION_TO_FORMAT",
    "FLATTEN_BACKGROUND",
    "MIN_ACCEPTABLE_PSNR_DB",
    "PNG_COLOR_CANDIDATES",
    "PNG_LOSSLESS_QUALITY",
    "PNG_LOSSLESS_THRESHOLD",
    "SUPPORTED_EXTENSIONS",
    "TARGET_FORMATS",
    "TARGET_FORMAT_TO_EXTENSION",
    "WEBP_METHOD",
    "_OPTIONAL_SAVE_KEYS",
    "UnsupportedFormatError",
    "_validate_parameters",
    "check_avif_support",
    "format_for_extension",
]
