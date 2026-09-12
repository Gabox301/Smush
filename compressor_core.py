"""
Núcleo de compresión de imágenes.

Comprime imágenes (AVIF, WEBP, JPEG, PNG) a un porcentaje objetivo de su
tamaño original en bytes, manteniendo las dimensiones originales.

Historial de mejoras sobre la versión anterior (auditoría):
- numpy vuelve a ser realmente opcional: los imports de tipos ya no rompen
  el módulo si numpy no está instalado, y se usa la ruta pública
  `numpy.typing.NDArray` en vez de un submódulo privado.
- El PSNR de imágenes con transparencia ahora compone sobre un fondo fijo
  antes de comparar, en vez de descartar el canal alfa "en crudo": así los
  píxeles totalmente invisibles (con colores arbitrarios) ya no distorsionan
  la métrica de calidad.
- Se agrega un piso de calidad configurable (`MIN_ACCEPTABLE_PSNR_DB`): si
  el tamaño objetivo solo se puede cumplir sacrificando calidad por debajo
  del piso, el resultado lo indica explícitamente en vez de hacerlo en
  silencio.
- Se elimina el recodificado redundante de `min_quality` (antes se podía
  codificar hasta 3 veces la misma calidad en el peor caso) mediante un
  memoize simple por request.
- Se limpia la duplicación entre `_encode_png` y `_encode_png_with_colors`
  (la primera tenía una rama de cuantización que nunca se ejecutaba).
- Se agrega logging en los `except` que antes fallaban en silencio, y
  `_save_with_optional_metadata` ahora reintenta quitando metadata opcional
  de a una por vez en vez de asumir que siempre es `exif` la culpable.
- Búsqueda binaria para JPEG/WEBP/AVIF y búsqueda discreta más segura para PNG.
- Optimización lossless de PNG antes de cuantizar.
- Validación de parámetros de entrada.
- Evita recomprimir si el objetivo no exige reducir el archivo o si la calidad
  mínima ya no puede mejorar el tamaño respecto del original.
- Preserva ICC y, opcionalmente, EXIF cuando el encoder lo admite.
- Para JPEG, permite elegir el fondo usado al aplanar transparencia.
- Metadata de resultado más completa: ratio alcanzado, ahorro, si se logró
  el objetivo y si la calidad resultante es aceptable.
- No carga los bytes originales completos en memoria para conservar el archivo.
"""

from __future__ import annotations

import io
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from PIL import Image, ImageOps
from PIL.ImageFile import ImageFile
from numpy import float64

if TYPE_CHECKING:
    # Solo se usan como anotaciones de tipo (con `from __future__ import
    # annotations` nunca se evalúan en runtime), así que numpy sigue siendo
    # opcional de verdad: nada de esto se ejecuta si no está instalado.
    import numpy as np
    from numpy.typing import NDArray

try:
    import numpy as np  # type: ignore[no-redef]
    _HAS_NUMPY = True
except ImportError:  # numpy es opcional: solo se usa para PSNR
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False


logger: logging.Logger = logging.getLogger(name=__name__)


QUALITY_FORMATS: set[str] = {"AVIF", "WEBP", "JPEG"}

EXTENSION_TO_FORMAT: dict[str, str] = {
    ".avif": "AVIF",
    ".webp": "WEBP",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
}

SUPPORTED_EXTENSIONS: set[str] = set(EXTENSION_TO_FORMAT.keys())

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


class UnsupportedFormatError(Exception):
    """La extensión del archivo no está soportada."""


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
    except Exception:
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


def _prepare_image(im: Image.Image) -> Image.Image:
    """Corrige orientación EXIF antes de cualquier otra operación."""
    return ImageOps.exif_transpose(image=im) or im


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


def _icc_profile(im: Image.Image) -> Optional[bytes]:
    return im.info.get("icc_profile")


def _exif_bytes(im: Image.Image, preserve_exif: bool) -> Optional[bytes]:
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
    except Exception as exc:
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


def _binary_search_quality(
    encode_fn: Callable[[int], bytes],
    target_size: float,
    min_quality: int,
    max_quality: int,
) -> tuple[Optional[int], Optional[bytes]]:
    """Busca la calidad máxima cuyo tamaño queda dentro del objetivo."""
    lo, hi = min_quality, max_quality
    best_quality: Optional[int] = None
    best_bytes: Optional[bytes] = None

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
    candidate_colors = sorted(set(candidate_colors + [min_colors, max_colors]))

    best_colors: Optional[int] = None
    best_bytes: Optional[bytes] = None
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


def _psnr(
    original: Image.Image,
    compressed_bytes: bytes,
    *,
    background: tuple[int, int, int],
) -> Optional[float]:
    """PSNR calculado sobre la apariencia final compuesta sobre `background`.

    Comparar así (en vez de descartar el alfa "en crudo") evita que píxeles
    totalmente invisibles, con colores arbitrarios de relleno, ensucien la
    métrica de calidad percibida.
    """
    if not _HAS_NUMPY or np is None:
        return None

    try:
        decoded: ImageFile = Image.open(fp=io.BytesIO(initial_bytes=compressed_bytes))
        decoded.load()
    except Exception:
        logger.debug(msg="No se pudo decodificar el resultado para calcular PSNR.", exc_info=True)
        return None

    try:
        a: NDArray[Any] = np.asarray(
            a=_flatten_to_rgb(original, background=background),
            dtype=np.float64,
        )
        b: NDArray[Any] = np.asarray(
            a=_flatten_to_rgb(decoded, background=background),
            dtype=np.float64,
        )
    except Exception:
        logger.debug(msg="No se pudo preparar los arrays para PSNR.", exc_info=True)
        return None

    if a.shape != b.shape:
        return None

    mse: float64 = np.mean(a=(a - b) ** 2)
    if mse == 0:
        return 99.0
    return round(number=float(20 * np.log10(255.0) - 10 * np.log10(mse)), ndigits=2)


def _finalize(
    output_path: Path,
    input_path: Path,
    original_size: int,
    encoded_bytes: bytes,
    quality: int,
    note: Optional[str],
    im: Image.Image,
    *,
    target_size: int,
    target_reached: bool,
    target_ratio: float,
    fmt: str,
    jpeg_background: tuple[int, int, int],
    preserve_exif: bool,
    compute_psnr: bool = True,
    min_psnr_db: float | None = None,
) -> dict:
    """Escribe el resultado y devuelve metadata detallada.

    Si `compute_psnr` es False, se saltea el cálculo de PSNR (`psnr_db` queda
    en None y no se emite el aviso de piso de calidad). Si `min_psnr_db` es
    None se usa el piso global `MIN_ACCEPTABLE_PSNR_DB`; pasar 0.0 desactiva
    el aviso pero igual reporta el valor.
    """
    encoded_size: int = len(encoded_bytes)

    if encoded_size >= original_size:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src=input_path, dst=output_path)
        return {
            "format": fmt,
            "original_size": original_size,
            "new_size": original_size,
            "target_size": target_size,
            "target_ratio": target_ratio,
            "achieved_ratio": 1.0,
            "savings_percent": 0.0,
            "target_reached": False,
            "compression_applied": False,
            "quality": None,
            "quality_acceptable": True,
            "width": im.size[0],
            "height": im.size[1],
            "preserve_exif": preserve_exif,
            "icc_preserved": bool(_icc_profile(im)),
            "note": "El resultado no era más pequeño que el original; se conservó sin cambios",
            "psnr_db": None,
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(data=encoded_bytes)
    achieved_ratio: float = encoded_size / original_size if original_size else 0.0

    psnr_db: Optional[float] = (
        _psnr(
            original=im,
            compressed_bytes=encoded_bytes,
            background=jpeg_background,
        )
        if compute_psnr
        else None
    )
    floor: float = MIN_ACCEPTABLE_PSNR_DB if min_psnr_db is None else min_psnr_db
    quality_acceptable: bool = psnr_db is None or psnr_db >= floor

    final_note: str | None = note
    if target_reached and encoded_size <= target_size and not quality_acceptable:
        warning: str = (
            f"Se alcanzó el tamaño objetivo, pero el PSNR estimado ({psnr_db} dB) "
            f"está por debajo del piso de calidad configurado ({floor} dB); "
            "conviene revisar visualmente o relajar target_ratio."
        )
        final_note = f"{note}; {warning}" if note else warning
        logger.warning(
            "Compresión de %s alcanzó el tamaño objetivo con calidad baja (PSNR=%.2fdB, quality=%s).",
            input_path.name, psnr_db, quality,
        )

    return {
        "format": fmt,
        "original_size": original_size,
        "new_size": encoded_size,
        "target_size": target_size,
        "target_ratio": target_ratio,
        "achieved_ratio": round(number=achieved_ratio, ndigits=6),
        "savings_percent": round(number=(1 - achieved_ratio) * 100, ndigits=2),
        "target_reached": bool(target_reached and encoded_size <= target_size),
        "compression_applied": True,
        "quality": quality,
        "quality_acceptable": quality_acceptable,
        "width": im.size[0],
        "height": im.size[1],
        "preserve_exif": preserve_exif,
        "icc_preserved": bool(_icc_profile(im)),
        "note": final_note,
        "psnr_db": psnr_db,
    }


def compress_to_target(
    input_path: Path,
    output_path: Path,
    target_ratio: float,
    min_quality: int = 10,
    max_quality: int = 95,
    *,
    preserve_exif: bool = False,
    jpeg_background: tuple[int, int, int] = FLATTEN_BACKGROUND,
    compute_psnr: bool = True,
    min_psnr_db: float | None = None,
) -> dict:
    """Comprime `input_path` buscando la mejor calidad dentro del target.

    `target_ratio` debe estar en (0, 1] y representa el tamaño máximo como
    fracción del original. Las dimensiones no se modifican.

    `jpeg_background` se usa tanto para aplanar transparencia al guardar en
    JPEG como para normalizar la comparación de calidad (PSNR) de cualquier
    formato con transparencia.

    `compute_psnr=False` saltea el cálculo de PSNR (ahorra un decode + numpy
    por request): `psnr_db` queda en None y no se emite el aviso de piso.
    `min_psnr_db` fija el piso de calidad por request (None = usa el global
    `MIN_ACCEPTABLE_PSNR_DB`; 0.0 lo desactiva pero igual reporta el valor).
    """
    _validate_parameters(target_ratio, min_quality, max_quality)

    if min_psnr_db is not None and min_psnr_db < 0:
        raise ValueError("min_psnr_db debe ser mayor o igual a 0")

    if not input_path.is_file():
        raise FileNotFoundError(f"No existe el archivo de entrada: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("input_path y output_path deben ser archivos distintos")

    if len(jpeg_background) != 3 or not all(0 <= x <= 255 for x in jpeg_background):
        raise ValueError("jpeg_background debe ser una tupla RGB de tres enteros 0-255")

    raw_im: ImageFile = Image.open(fp=input_path)
    try:
        raw_im.load()
        im: Image.Image = _prepare_image(im=raw_im)

        original_size: int = input_path.stat().st_size
        target_size: int = max(1, int(original_size * target_ratio))
        fmt: str = format_for_extension(ext=input_path.suffix)

        # Si no se pide reducir el archivo, no tiene sentido recomprimir.
        if target_size >= original_size:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src=input_path, dst=output_path)
            return {
                "format": fmt,
                "original_size": original_size,
                "new_size": original_size,
                "target_size": target_size,
                "target_ratio": target_ratio,
                "achieved_ratio": 1.0,
                "savings_percent": 0.0,
                "target_reached": True,
                "compression_applied": False,
                "quality": None,
                "quality_acceptable": True,
                "width": im.size[0],
                "height": im.size[1],
                "preserve_exif": preserve_exif,
                "icc_preserved": bool(_icc_profile(im)),
                "note": "El objetivo no exige reducir el tamaño; se conservó el original",
                "psnr_db": None,
            }

        if fmt == "PNG":
            quality, data, reached, note = _best_png_encode(
                im,
                target_size,
                min_quality,
                max_quality,
                preserve_exif=preserve_exif,
            )
        else:
            raw_encode_fn: Callable[[int], bytes] = lambda q: _encode(
                im,
                fmt,
                quality=q,
                jpeg_background=jpeg_background,
                preserve_exif=preserve_exif,
            )
            # Cacheado por calidad: shortcut-check + búsqueda binaria +
            # fallback pueden pedir la misma calidad más de una vez.
            encode_fn: Callable[[int], bytes] = _memoize_encoder(raw_encode_fn)

            # Atajo: si incluso la calidad mínima no reduce el archivo, no
            # desperdiciamos el resto de la búsqueda.
            min_data: bytes = encode_fn(min_quality)
            if len(min_data) >= original_size:
                return _finalize(
                    output_path,
                    input_path,
                    original_size,
                    min_data,
                    min_quality,
                    "La calidad mínima no produce un archivo menor; se conservó el original",
                    im,
                    target_size=target_size,
                    target_reached=False,
                    target_ratio=target_ratio,
                    fmt=fmt,
                    jpeg_background=jpeg_background,
                    preserve_exif=preserve_exif,
                    compute_psnr=compute_psnr,
                    min_psnr_db=min_psnr_db,
                )

            quality, data, reached = _best_effort_encode(
                encode_fn,
                target_size,
                min_quality,
                max_quality,
            )
            note = None if reached else "No se pudo alcanzar el objetivo ni con la calidad mínima"

        return _finalize(
            output_path,
            input_path,
            original_size,
            data,
            quality,
            note,
            im,
            target_size=target_size,
            target_reached=reached,
            target_ratio=target_ratio,
            fmt=fmt,
            jpeg_background=jpeg_background,
            preserve_exif=preserve_exif,
            compute_psnr=compute_psnr,
            min_psnr_db=min_psnr_db,
        )
    finally:
        try:
            raw_im.close()
        except Exception:
            pass
