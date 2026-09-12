"""
Contratos de metadata: lo que el core produce y la GUI consume.

Sin dependencias: solo tipos.
"""
from __future__ import annotations

from typing import TypedDict, TypeGuard


class CompressMeta(TypedDict):
    """Metadata que devuelven compress_to_target y _finalize."""

    format: str
    original_size: int
    new_size: int
    target_size: int
    target_ratio: float
    achieved_ratio: float
    savings_percent: float
    target_reached: bool
    compression_applied: bool
    quality: int | None
    quality_acceptable: bool
    width: int
    height: int
    preserve_exif: bool
    icc_preserved: bool
    note: str | None
    psnr_db: float | None


class ConvertMeta(TypedDict):
    """Metadata que devuelve convert_format."""

    format: str
    target_format: str
    original_size: int
    new_size: int
    target_reached: bool
    quality: int | None
    note: str | None
    width: int
    height: int
    preserve_exif: bool
    icc_preserved: bool


class ErrorMeta(TypedDict):
    """Fila de error en las listas de resultados (compresión y conversión)."""

    filename: str
    error: str


class CompressRow(TypedDict):
    """Fila de resultado de compresión para la GUI.

    Proyección explícita de CompressMeta con lo que la vista muestra,
    más los datos del job (filename/tmp_path).
    """

    filename: str
    original_size: int
    new_size: int
    percent_of_original: float
    quality: int | None
    note: str | None
    tmp_path: str
    psnr_db: float | None
    quality_acceptable: bool


class ConvertRow(ConvertMeta):
    """Fila de resultado de conversión: metadata del core + datos del job GUI."""

    filename: str
    tmp_path: str


CompressResult = CompressRow | ErrorMeta
ConvertResult = ConvertRow | ErrorMeta


def is_compress_error(r: CompressResult) -> TypeGuard[ErrorMeta]:
    """Angosta una fila de compresión a su variante de error."""
    return "error" in r


def is_compress_ok(r: CompressResult) -> TypeGuard[CompressRow]:
    """Angosta una fila de compresión a su variante exitosa."""
    return "error" not in r


def is_convert_error(r: ConvertResult) -> TypeGuard[ErrorMeta]:
    """Angosta una fila de conversión a su variante de error."""
    return "error" in r


def is_convert_ok(r: ConvertResult) -> TypeGuard[ConvertRow]:
    """Angosta una fila de conversión a su variante exitosa."""
    return "error" not in r
