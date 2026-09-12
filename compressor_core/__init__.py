"""
Núcleo de compresión y conversión de imágenes.

Comprime imágenes (AVIF, WEBP, JPEG, PNG) a un porcentaje objetivo de su
tamaño original en bytes, y convierte entre formatos, manteniendo siempre
las dimensiones originales.

Este paquete es el seam público: todo lo que la API, la GUI y los tests
usan se importa desde acá (`compressor_core.X`). Los tests parchan
`np`, `_HAS_NUMPY`, `_encode` y `check_avif_support` en este namespace,
así que `quality` y `pipeline` los resuelven a través del paquete.

Módulos:
    formats: constantes, error de formato, validación de parámetros.
    metadata: TypedDicts de resultados y guards de narrowing.
    image_ops: operaciones Pillow (orientación, alfa, EXIF/ICC).
    encode: codificadores por formato.
    search: estrategias de búsqueda de calidad/paleta.
    quality: PSNR con numpy opcional.
    pipeline: compress_to_target, convert_format y _finalize.
"""
from __future__ import annotations

try:
    import numpy as np  # type: ignore[no-redef]
    _HAS_NUMPY = True
except ImportError:  # numpy es opcional: solo se usa para PSNR
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

from .encode import (
    _colors_for_quality,
    _encode,
    _encode_png_lossless,
    _encode_png_with_colors,
    _memoize_encoder,
    _quality_for_colors,
    _quantize_for_png,
    _save_with_optional_metadata,
)
from .formats import (
    _OPTIONAL_SAVE_KEYS,
    AVIF_SPEED,
    EXTENSION_TO_FORMAT,
    FLATTEN_BACKGROUND,
    MIN_ACCEPTABLE_PSNR_DB,
    PNG_COLOR_CANDIDATES,
    PNG_LOSSLESS_QUALITY,
    PNG_LOSSLESS_THRESHOLD,
    SUPPORTED_EXTENSIONS,
    TARGET_FORMAT_TO_EXTENSION,
    TARGET_FORMATS,
    WEBP_METHOD,
    UnsupportedFormatError,
    _validate_parameters,
    check_avif_support,
    format_for_extension,
)
from .image_ops import (
    _close_quietly,
    _exif_bytes,
    _flatten_to_rgb,
    _has_transparency,
    _icc_profile,
    _prepare_image,
)
from .metadata import (
    CompressMeta,
    CompressResult,
    CompressRow,
    ConvertMeta,
    ConvertResult,
    ConvertRow,
    ErrorMeta,
    is_compress_error,
    is_compress_ok,
    is_convert_error,
    is_convert_ok,
)
from .pipeline import _finalize, compress_to_target, convert_format
from .quality import _psnr
from .search import (
    _best_effort_encode,
    _best_png_encode,
    _binary_search_quality,
)

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
    "_HAS_NUMPY",
    "_OPTIONAL_SAVE_KEYS",
    "CompressMeta",
    "CompressResult",
    "CompressRow",
    "ConvertMeta",
    "ConvertResult",
    "ConvertRow",
    "ErrorMeta",
    "UnsupportedFormatError",
    "_best_effort_encode",
    "_best_png_encode",
    "_binary_search_quality",
    "_close_quietly",
    "_colors_for_quality",
    "_encode",
    "_encode_png_lossless",
    "_encode_png_with_colors",
    "_exif_bytes",
    "_finalize",
    "_flatten_to_rgb",
    "_has_transparency",
    "_icc_profile",
    "_memoize_encoder",
    "_prepare_image",
    "_psnr",
    "_quality_for_colors",
    "_quantize_for_png",
    "_save_with_optional_metadata",
    "_validate_parameters",
    "check_avif_support",
    "compress_to_target",
    "convert_format",
    "format_for_extension",
    "is_compress_error",
    "is_compress_ok",
    "is_convert_error",
    "is_convert_ok",
    "np",
]
