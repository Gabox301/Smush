"""
Orquestación: comprimir a ratio objetivo y convertir de formato.

`_encode` y `check_avif_support` se resuelven a través del namespace
del paquete en cada llamada para que los tests los parcheen en el
seam público (`compressor_core.X`).
"""
from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from PIL import Image
from PIL.ImageFile import ImageFile

import compressor_core as _core

from .encode import _memoize_encoder
from .formats import (
    FLATTEN_BACKGROUND,
    MIN_ACCEPTABLE_PSNR_DB,
    PNG_LOSSLESS_QUALITY,
    TARGET_FORMATS,
    UnsupportedFormatError,
    _validate_parameters,
    format_for_extension,
)
from .image_ops import _close_quietly, _icc_profile, _prepare_image
from .metadata import CompressMeta, ConvertMeta
from .quality import _psnr
from .search import _best_effort_encode, _best_png_encode

logger: logging.Logger = logging.getLogger(name=__name__)


def _finalize(
    output_path: Path,
    input_path: Path,
    original_size: int,
    encoded_bytes: bytes,
    quality: int,
    note: str | None,
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
) -> CompressMeta:
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

    psnr_db: float | None = (
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
) -> CompressMeta:
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
            def raw_encode_fn(q: int) -> bytes:
                # Vía namespace del paquete: los tests parchan _encode en el seam público.
                return _core._encode(
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
        _close_quietly(raw_im)


def convert_format(
    input_path: Path,
    output_path: Path,
    target_format: str,
    quality: int = 85,
    *,
    target_ratio: float = 1.0,
    min_quality: int = 10,
    preserve_exif: bool = False,
    jpeg_background: tuple[int, int, int] = FLATTEN_BACKGROUND,
) -> ConvertMeta:
    """Convierte `input_path` a `target_format` manteniendo las dimensiones.

    `target_format` es uno de AVIF, WEBP, JPEG o PNG. Además de convertir,
    comprime: busca la mejor calidad (hasta `quality`, desde `min_quality`)
    cuyo peso no supere `target_ratio` del original. Con el default
    `target_ratio=1.0` el resultado nunca pesa más que el original salvo que
    ni la calidad mínima alcance, caso que se avisa en `note`.
    PNG siempre se guarda sin pérdida si entra en el objetivo.
    Las dimensiones no se modifican.
    """
    fmt: str = target_format.upper()
    if fmt not in TARGET_FORMATS:
        raise ValueError(f"target_format debe ser uno de {list(TARGET_FORMATS)}")
    _validate_parameters(target_ratio, min_quality, max_quality=quality)

    if not input_path.is_file():
        raise FileNotFoundError(f"No existe el archivo de entrada: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("input_path y output_path deben ser archivos distintos")

    # Vía namespace del paquete: los tests parchan check_avif_support en el seam público.
    if fmt == "AVIF" and not _core.check_avif_support():
        raise UnsupportedFormatError("Este build de Pillow no puede codificar AVIF")

    raw_im: ImageFile = Image.open(fp=input_path)
    try:
        raw_im.load()
        im: Image.Image = _prepare_image(im=raw_im)

        original_size: int = input_path.stat().st_size
        target_size: int = max(1, int(original_size * target_ratio))
        if fmt == "PNG":
            png_quality, data, reached, png_note = _best_png_encode(
                im, target_size, min_quality, max_quality=PNG_LOSSLESS_QUALITY,
                preserve_exif=preserve_exif,
            )
            if reached and png_quality == PNG_LOSSLESS_QUALITY:
                used_quality: int | None = None
                note: str | None = "PNG sin pérdida"
            else:
                used_quality = png_quality
                note = png_note
        else:
            def encode_at(q: int) -> bytes:
                # Vía namespace del paquete (ver raw_encode_fn).
                return _core._encode(
                    im,
                    fmt,
                    quality=q,
                    jpeg_background=jpeg_background,
                    preserve_exif=preserve_exif,
                )

            used_quality, data, reached = _best_effort_encode(
                encode_at, target_size, min_quality, max_quality=quality,
            )
            note = None
            if not reached:
                pct: float = round(number=target_ratio * 100, ndigits=1)
                note = (f"No se llegó al {pct}% del peso original ni con calidad mínima")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data=data)
        return {
            "format": fmt,
            "target_format": fmt,
            "original_size": original_size,
            "new_size": len(data),
            "target_reached": reached,
            "quality": used_quality,
            "note": note,
            "width": im.size[0],
            "height": im.size[1],
            "preserve_exif": preserve_exif,
            "icc_preserved": bool(_icc_profile(im)),
        }
    finally:
        _close_quietly(raw_im)
