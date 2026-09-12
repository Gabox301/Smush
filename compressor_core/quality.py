"""
Calidad perceptual (PSNR) con numpy opcional.

El estado del entorno (`np` / `_HAS_NUMPY`) vive en la raíz del paquete
para que los tests lo parcheen en el namespace público; acá se lee
a través del paquete en cada llamada.
"""
from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Any

from PIL import Image
from PIL.ImageFile import ImageFile

import compressor_core as _core

from .image_ops import _flatten_to_rgb

if TYPE_CHECKING:
    # Solo para anotaciones (nunca se evalúa en runtime).
    from numpy.typing import NDArray

logger: logging.Logger = logging.getLogger(name=__name__)


def _psnr(
    original: Image.Image,
    compressed_bytes: bytes,
    *,
    background: tuple[int, int, int],
) -> float | None:
    """PSNR calculado sobre la apariencia final compuesta sobre `background`.

    Comparar así (en vez de descartar el alfa "en crudo") evita que píxeles
    totalmente invisibles, con colores arbitrarios de relleno, ensucien la
    métrica de calidad percibida.
    """
    numpy: Any = _core.np
    if not _core._HAS_NUMPY or numpy is None:
        return None

    try:
        decoded: ImageFile = Image.open(fp=io.BytesIO(initial_bytes=compressed_bytes))
        decoded.load()
    except Exception:
        logger.debug(msg="No se pudo decodificar el resultado para calcular PSNR.", exc_info=True)
        return None

    try:
        a: NDArray[Any] = numpy.asarray(
            a=_flatten_to_rgb(original, background=background),
            dtype=numpy.float64,
        )
        b: NDArray[Any] = numpy.asarray(
            a=_flatten_to_rgb(decoded, background=background),
            dtype=numpy.float64,
        )
    except Exception:
        logger.debug(msg="No se pudo preparar los arrays para PSNR.", exc_info=True)
        return None

    if a.shape != b.shape:
        return None

    mse: float = numpy.mean(a=(a - b) ** 2)
    if mse == 0:
        return 99.0
    return round(number=float(20 * numpy.log10(255.0) - 10 * numpy.log10(mse)), ndigits=2)


__all__: list[str] = ["_psnr"]
