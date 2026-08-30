"""
Núcleo de compresión de imágenes.

Comprime imágenes (AVIF, WEBP, JPEG, PNG) a un porcentaje objetivo de su
 tamaño original en bytes, manteniendo las dimensiones originales.

Mejoras principales respecto a la versión anterior:
- Búsqueda binaria para JPEG/WEBP/AVIF y búsqueda discreta más segura para PNG.
- Optimización lossless de PNG antes de cuantizar.
- Validación de parámetros de entrada.
- Evita recomprimir si el objetivo no exige reducir el archivo o si la calidad
  mínima ya no puede mejorar el tamaño respecto del original.
- Preserva ICC y, opcionalmente, EXIF cuando el encoder lo admite.
- Para JPEG, permite elegir el fondo usado al aplanar transparencia.
- PSNR coherente con la representación visual final, incluyendo alfa/JPEG.
- Metadata de resultado más completa: ratio alcanzado, ahorro y si se logró
  el objetivo.
- No carga los bytes originales completos en memoria para conservar el archivo.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PIL import Image, ImageOps
from PIL.ImageFile import ImageFile
from numpy import float64
from numpy._typing._array_like import NDArray

if TYPE_CHECKING:
    import numpy as np

try:
    import numpy as np  # type: ignore[no-redef]
    _HAS_NUMPY = True
except ImportError:  # numpy es opcional: solo se usa para PSNR
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False


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


class UnsupportedFormatError(Exception):
    """La extensión del archivo no está soportada."""


def format_for_extension(ext: str) -> str:
    ext = ext.lower()
    if ext not in EXTENSION_TO_FORMAT:
        raise UnsupportedFormatError(f"Extensión no soportada: {ext}")
    return EXTENSION_TO_FORMAT[ext]


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


def _flatten_for_jpeg(
    im: Image.Image,
    background: tuple[int, int, int] = FLATTEN_BACKGROUND,
) -> Image.Image:
    """Aplana transparencia sobre un fondo sólido para JPEG."""
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
        return None


def _save_with_optional_metadata(
    im: Image.Image,
    buf: io.BytesIO,
    save_kwargs: dict,
) -> None:
    """Guarda una imagen y, si el encoder no admite algún metadata, reintenta."""
    try:
        im.save(fp=buf, **save_kwargs)
    except (TypeError, ValueError):
        # Algunos builds/formats de Pillow no aceptan EXIF u otras opciones.
        # Retiramos solo metadata opcional y reintentamos.
        reduced = dict(save_kwargs)
        reduced.pop("exif", None)
        buf.seek(0)
        buf.truncate(0)
        im.save(fp=buf, **reduced)


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
        work_im = _flatten_for_jpeg(im, background=jpeg_background)
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
    except Exception:
        return work_im.quantize(
            colors=colors,
            method=Image.Quantize.FASTOCTREE,
            dither=Image.Dither.FLOYDSTEINBERG,
        )


def _colors_for_quality(quality: int) -> int:
    """Mapeo compatible con la API anterior, acotado a 16-256 colores."""
    return max(16, min(256, int(16 + (quality - 10) * (240 / 85))))


def _encode_png(
    im: Image.Image,
    quality: int,
    *,
    preserve_exif: bool = False,
) -> bytes:
    """Codifica PNG. quality >= 92 conserva la imagen sin cuantizar."""
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

    if quality >= 92:
        _save_with_optional_metadata(im, buf, save_kwargs)
        return buf.getvalue()

    q: Image.Image = _quantize_for_png(im, colors=_colors_for_quality(quality))
    _save_with_optional_metadata(q, buf, save_kwargs)
    return buf.getvalue()


def _encode_png_with_colors(
    im: Image.Image,
    colors: int,
    *,
    preserve_exif: bool = False,
) -> bytes:
    """Encode PNG usando un número explícito de colores."""
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
    if max_quality >= 92:
        lossless: bytes = _encode_png(im, quality=PNG_LOSSLESS_QUALITY, preserve_exif=preserve_exif)
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
    quality: int = max(
        min_quality,
        min(
            max_quality,
            round(number=10 + (best_colors - 16) * 85 / 240),
        ),
    )
    return quality, best_bytes, True, f"PNG cuantizado a {best_colors} colores"


def _to_rgb_safe(img: Image.Image) -> Image.Image:
    if img.mode == "P":
        img = img.convert(mode="RGBA" if _has_transparency(im=img) else "RGB")
    return img.convert(mode="RGB")


def _visual_reference(
    original: Image.Image,
    *,
    fmt: str,
    jpeg_background: tuple[int, int, int],
) -> Image.Image:
    """Normaliza la imagen original a la misma representación que se evalúa."""
    if fmt == "JPEG":
        return _flatten_for_jpeg(im=original, background=jpeg_background)
    return _to_rgb_safe(img=original)


def _psnr(
    original: Image.Image,
    compressed_bytes: bytes,
    *,
    fmt: str,
    jpeg_background: tuple[int, int, int],
) -> Optional[float]:
    """Calcula PSNR sobre la representación visual final."""
    if not _HAS_NUMPY or np is None:
        return None

    try:
        decoded: ImageFile = Image.open(fp=io.BytesIO(initial_bytes=compressed_bytes))
        decoded.load()
    except Exception:
        return None

    try:
        a: NDArray[float64] = np.asarray(
            a=_visual_reference(
                original,
                fmt=fmt,
                jpeg_background=jpeg_background,
            ),
            dtype=np.float64,
        )
        b: NDArray[float64] = np.asarray(a=_to_rgb_safe(img=decoded), dtype=np.float64)
    except Exception:
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
) -> dict:
    """Escribe el resultado y devuelve metadata detallada."""
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
        "width": im.size[0],
        "height": im.size[1],
        "preserve_exif": preserve_exif,
        "icc_preserved": bool(_icc_profile(im)),
        "note": note,
        "psnr_db": _psnr(
            original=im,
            compressed_bytes=encoded_bytes,
            fmt=fmt,
            jpeg_background=jpeg_background,
        ),
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
) -> dict:
    """Comprime `input_path` buscando la mejor calidad dentro del target.

    `target_ratio` debe estar en (0, 1] y representa el tamaño máximo como
    fracción del original. Las dimensiones no se modifican.
    """
    _validate_parameters(target_ratio, min_quality, max_quality)

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

        # Si no se pide reducir el archivo, no tiene sentido recompresionar.
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
            encode_fn: Callable[..., bytes] = lambda q: _encode(
                im,
                fmt,
                quality=q,
                jpeg_background=jpeg_background,
                preserve_exif=preserve_exif,
            )

            # Atajo: si incluso la calidad mínima no reduce el archivo, no
            # desperdiciamos el resto de la búsqueda.
            min_data = encode_fn(min_quality)
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
        )
    finally:
        try:
            raw_im.close()
        except Exception:
            pass
