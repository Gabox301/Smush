"""
Núcleo de compresión de imágenes.

Comprime imágenes (AVIF, WEBP, JPEG, PNG) a un porcentaje objetivo de su
tamaño original en bytes, manteniendo siempre las dimensiones originales.
Usa búsqueda binaria sobre el parámetro "quality" (o la paleta de colores,
en el caso de PNG) para encontrar el valor más alto que aún cumple el
tamaño objetivo (mejor calidad posible dentro del presupuesto de peso
pedido).

Cambios respecto a la versión anterior:
- La búsqueda binaria codifica en memoria (io.BytesIO) en vez de escribir
  a disco en cada iteración: mismo resultado, mucho más rápido, y sin
  desgaste de disco en un backend que procesa muchos requests.
- Se corrige la orientación EXIF antes de comprimir (fotos de celular que
  antes podían terminar rotadas al perder el tag de orientación).
- Al convertir a JPEG una imagen con transparencia (RGBA o paleta con
  transparencia) ahora se aplana sobre un fondo en vez de descartar el
  canal alfa a lo bruto, lo que evitaba bordes oscuros/artefactos.
- Se conserva el perfil de color (ICC) al guardar, para no perder
  fidelidad de color.
- Cuantización de PNG: intenta primero el cuantizador libimagequant
  (mejor calidad perceptual) y cae a FASTOCTREE con dithering si no está
  disponible en el build de Pillow instalado.
- AVIF/WEBP usan parámetros de encoder pensados para mejor calidad por
  byte (speed bajo en AVIF, method=6 en WEBP), aceptable porque esto
  corre server-side y no en tiempo real.
- Salvaguarda: si ni siquiera con la calidad mínima se logra un archivo
  más chico que el original, se conserva el original en vez de "mejorar"
  a un archivo más pesado (antes esto solo estaba cubierto para PNG).
- El resultado incluye una estimación de calidad (PSNR en dB) para poder
  mostrarle al usuario cuánta pérdida perceptual implicó la compresión,
  no solo el ratio de tamaño logrado. numpy es opcional: si no está
  instalado, el compresor funciona igual y simplemente no calcula PSNR
  (psnr_db queda en None).
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PIL import Image, ImageOps

if TYPE_CHECKING:
    import numpy as np

try:
    import numpy as np  # type: ignore[no-redef]
    _HAS_NUMPY = True
except ImportError:  # numpy es opcional: solo se usa para la métrica PSNR
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

QUALITY_FORMATS = {"AVIF", "WEBP", "JPEG"}

EXTENSION_TO_FORMAT = {
    ".avif": "AVIF",
    ".webp": "WEBP",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
}

SUPPORTED_EXTENSIONS = set(EXTENSION_TO_FORMAT.keys())

# Valores de encoder pensados para maximizar calidad por byte. Esto corre
# en un backend, no en tiempo real, así que preferimos "lento pero mejor".
AVIF_SPEED = 4  # 0 = más lento/mejor compresión, 10 = más rápido/peor
WEBP_METHOD = 6  # método de compresión más exhaustivo (0-6)

FLATTEN_BACKGROUND = (255, 255, 255)  # fondo usado al aplanar transparencia para JPEG


class UnsupportedFormatError(Exception):
    pass


def format_for_extension(ext: str) -> str:
    ext = ext.lower()
    if ext not in EXTENSION_TO_FORMAT:
        raise UnsupportedFormatError(f"Extensión no soportada: {ext}")
    return EXTENSION_TO_FORMAT[ext]


def _prepare_image(im: Image.Image) -> Image.Image:
    """Corrige orientación EXIF antes de cualquier otra operación."""
    return ImageOps.exif_transpose(im) or im


def _has_transparency(im: Image.Image) -> bool:
    if im.mode in ("RGBA", "LA"):
        return True
    if im.mode == "P" and "transparency" in im.info:
        return True
    return False


def _flatten_for_jpeg(im: Image.Image, background=FLATTEN_BACKGROUND) -> Image.Image:
    """Aplana transparencia sobre un fondo sólido en vez de descartar el
    canal alfa directamente (lo que dejaba bordes oscuros en PNG/WEBP con
    transparencia parcial al convertir a JPEG)."""
    if not _has_transparency(im):
        return im.convert("RGB") if im.mode != "RGB" else im
    rgba = im.convert("RGBA")
    flat = Image.new("RGB", rgba.size, background)
    flat.paste(rgba, mask=rgba.split()[3])
    return flat


def _icc_profile(im: Image.Image) -> Optional[bytes]:
    return im.info.get("icc_profile")


def _encode(im: Image.Image, fmt: str, quality: int) -> bytes:
    """Codifica la imagen en memoria y devuelve los bytes resultantes."""
    buf = io.BytesIO()
    save_kwargs = {"format": fmt, "quality": quality}
    icc = _icc_profile(im)
    if icc:
        save_kwargs["icc_profile"] = icc

    work_im = im
    if fmt == "JPEG":
        work_im = _flatten_for_jpeg(im)
    elif fmt == "WEBP":
        save_kwargs["method"] = WEBP_METHOD
    elif fmt == "AVIF":
        save_kwargs["speed"] = AVIF_SPEED

    work_im.save(buf, **save_kwargs)
    return buf.getvalue()


def _quantize_for_png(im: Image.Image, colors: int) -> Image.Image:
    """Cuantiza a una paleta de `colors` colores. Prueba libimagequant
    (mejor calidad perceptual) y cae a FASTOCTREE con dithering si el
    build de Pillow no lo tiene compilado."""
    work_im = im
    if work_im.mode not in ("RGB", "RGBA"):
        work_im = work_im.convert("RGBA" if "transparency" in im.info or "A" in im.getbands() else "RGB")
    try:
        return work_im.quantize(colors=colors, method=Image.Quantize.LIBIMAGEQUANT, dither=Image.Dither.FLOYDSTEINBERG)
    except Exception:
        return work_im.quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)


def _colors_for_quality(quality: int) -> int:
    return max(16, min(256, int(16 + (quality - 10) * (240 / 85))))


def _encode_png(im: Image.Image, quality: int) -> bytes:
    """PNG sin pérdida no tiene 'quality'; lo simulamos cuantizando la paleta.
    quality >= 92: sin cuantizar (máxima fidelidad, solo optimize).
    quality 10-91: mapeado a 16-256 colores de paleta."""
    buf = io.BytesIO()
    icc = _icc_profile(im)
    save_kwargs = {"format": "PNG", "optimize": True, "compress_level": 9}
    if icc:
        save_kwargs["icc_profile"] = icc

    if quality >= 92:
        im.save(buf, **save_kwargs)
        return buf.getvalue()

    colors = _colors_for_quality(quality)
    q = _quantize_for_png(im, colors)
    q.save(buf, **save_kwargs)
    return buf.getvalue()


def _binary_search_quality(
    encode_fn: Callable[[int], bytes],
    target_size: float,
    min_quality: int,
    max_quality: int,
) -> tuple[Optional[int], Optional[bytes]]:
    """Busca la calidad más alta cuyo tamaño codificado quede por debajo
    de target_size. Devuelve (quality, bytes) o (None, None) si ni la
    calidad mínima cumple el presupuesto."""
    lo, hi = min_quality, max_quality
    best_quality: Optional[int] = None
    best_bytes: Optional[bytes] = None
    while lo <= hi:
        mid = (lo + hi) // 2
        data = encode_fn(mid)
        if len(data) <= target_size:
            best_quality = mid
            best_bytes = data
            lo = mid + 1
        else:
            hi = mid - 1
    return best_quality, best_bytes


def _best_effort_encode(
    encode_fn: Callable[[int], bytes],
    target_size: float,
    min_quality: int,
    max_quality: int,
) -> tuple[int, bytes, bool]:
    """Envoltorio sobre _binary_search_quality que nunca devuelve None:
    si ni la calidad mínima entra en el presupuesto, devuelve igual la
    calidad mínima codificada (con reached_target=False) en vez de
    propagar un `bytes | None` que después habría que estar chequeando
    en cada punto de uso."""
    quality, data = _binary_search_quality(encode_fn, target_size, min_quality, max_quality)
    if quality is not None and data is not None:
        return quality, data, True
    return min_quality, encode_fn(min_quality), False


def _to_rgb_safe(img: Image.Image) -> Image.Image:
    """Evita el warning de Pillow al convertir paletas con transparencia
    en bytes directamente a RGB (recomienda pasar por RGBA primero)."""
    if img.mode == "P":
        img = img.convert("RGBA")
    return img.convert("RGB")


def _psnr(original: Image.Image, compressed_bytes: bytes) -> Optional[float]:
    """PSNR en dB entre la imagen original y el resultado comprimido, como
    estimación rápida de pérdida perceptual (no reemplaza una inspección
    visual, pero da una señal numérica de "cuánto se tocó" la imagen).
    Devuelve None si numpy no está instalado o si algo falla al decodificar."""
    if not _HAS_NUMPY or np is None:
        return None

    try:
        decoded = Image.open(io.BytesIO(compressed_bytes))
        decoded.load()
    except Exception:
        return None

    a = np.asarray(_to_rgb_safe(original), dtype=np.float64)
    b = np.asarray(_to_rgb_safe(decoded), dtype=np.float64)
    if a.shape != b.shape:
        return None

    mse = np.mean((a - b) ** 2)
    if mse == 0:
        return 99.0  # idéntico (o prácticamente idéntico)
    # round + float(): que el resultado sea un float nativo de Python,
    # no np.float64, para que sea serializable a JSON tal cual en el
    # endpoint /api/compress sin conversiones adicionales.
    return round(float(20 * np.log10(255.0) - 10 * np.log10(mse)), 2)


def _finalize(
    output_path: Path,
    original_bytes: bytes,
    original_size: int,
    encoded_bytes: bytes,
    quality: int,
    note: Optional[str],
    im: Image.Image,
) -> dict:
    """Escribe el resultado a disco y arma el dict de metadata. Si el
    resultado "comprimido" termina pesando igual o más que el original,
    conserva el original en vez de entregar un archivo peor."""
    if len(encoded_bytes) >= original_size:
        output_path.write_bytes(original_bytes)
        return {
            "original_size": original_size,
            "new_size": original_size,
            "quality": None,
            "width": im.size[0],
            "height": im.size[1],
            "note": "El original ya era más chico que cualquier recompresión; se conservó sin cambios",
            "psnr_db": None,
        }

    output_path.write_bytes(encoded_bytes)
    return {
        "original_size": original_size,
        "new_size": len(encoded_bytes),
        "quality": quality,
        "width": im.size[0],
        "height": im.size[1],
        "note": note,
        "psnr_db": _psnr(im, encoded_bytes),
    }


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
    raw_im = Image.open(input_path)
    raw_im.load()
    im = _prepare_image(raw_im)  # corrige orientación EXIF

    original_size = input_path.stat().st_size
    original_bytes = input_path.read_bytes()
    target_size = max(1, original_size * target_ratio)
    fmt = format_for_extension(input_path.suffix)

    if fmt not in QUALITY_FORMATS:
        quality, data, reached = _best_effort_encode(
            lambda q: _encode_png(im, q), target_size, min_quality, max_quality
        )
        if reached:
            note = (
                f"PNG cuantizado a {_colors_for_quality(quality)} colores"
                if quality < 92
                else "PNG optimizado sin pérdida"
            )
        else:
            note = "No se pudo alcanzar el objetivo ni con la paleta mínima"
        return _finalize(output_path, original_bytes, original_size, data, quality, note, im)

    quality, data, reached = _best_effort_encode(
        lambda q: _encode(im, fmt, q), target_size, min_quality, max_quality
    )
    note = None if reached else "No se pudo alcanzar el objetivo ni con la calidad mínima"
    return _finalize(output_path, original_bytes, original_size, data, quality, note, im)
