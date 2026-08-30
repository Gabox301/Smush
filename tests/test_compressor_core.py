import io
import random
from pathlib import Path
from typing import Literal

import pytest
from PIL import Image

from compressor_core import (
    EXTENSION_TO_FORMAT,
    SUPPORTED_EXTENSIONS,
    UnsupportedFormatError,
    compress_to_target,
    format_for_extension,
)


# Helpers


def make_noisy_image(path: Path, size=(600, 600), fmt="JPEG") -> Image.Image:
    """Crea imagen con ruido para que la compresión tenga efecto medible."""
    w, h = size
    img: Image.Image = Image.new(mode="RGB", size=(w, h))
    rng = random.Random(42)
    img.putdata(data=[(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(w * h)])
    img.save(fp=path, format=fmt, quality=95)
    return img


def make_solid_image(path: Path, size=(100, 100), color="red", fmt="JPEG", **save_kwargs) -> Image.Image:
    img: Image.Image = Image.new("RGB", size, color=color)
    img.save(fp=path, format=fmt, quality=95, **save_kwargs)
    return img


# Tests format_for_extension


@pytest.mark.parametrize(
    argnames="ext,expected",
    argvalues=[
        (".jpg", "JPEG"),
        (".jpeg", "JPEG"),
        (".JPG", "JPEG"),
        (".JPEG", "JPEG"),
        (".png", "PNG"),
        (".PNG", "PNG"),
        (".webp", "WEBP"),
        (".WEBP", "WEBP"),
        (".avif", "AVIF"),
    ],
)
def test_format_for_extension_ok(ext: Literal['.jpg'] | Literal['.jpeg'] | Literal['.JPG'] | Literal['.JPEG'] | Literal['.png'] | Literal['.PNG'] | Literal['.webp'] | Literal['.WEBP'] | Literal['.avif'], expected: Literal['JPEG'] | Literal['PNG'] | Literal['WEBP'] | Literal['AVIF']) -> None:
    assert format_for_extension(ext) == expected


def test_format_for_extension_unsupported_raises() -> None:
    with pytest.raises(expected_exception=UnsupportedFormatError, match="Extensión no soportada"):
        format_for_extension(ext=".txt")
    with pytest.raises(expected_exception=UnsupportedFormatError):
        format_for_extension(ext=".gif")
    with pytest.raises(expected_exception=UnsupportedFormatError):
        format_for_extension(ext="")


def test_supported_extensions_contains_expected() -> None:
    assert ".jpg" in SUPPORTED_EXTENSIONS
    assert ".jpeg" in SUPPORTED_EXTENSIONS
    assert ".png" in SUPPORTED_EXTENSIONS
    assert ".webp" in SUPPORTED_EXTENSIONS
    assert ".avif" in SUPPORTED_EXTENSIONS
    assert EXTENSION_TO_FORMAT[".jpg"] == "JPEG"


# Tests compress_to_target


def test_compress_jpeg_reduces_to_target(tmp_path: Path) -> None:
    src: Path = tmp_path / "src.jpg"
    dst: Path = tmp_path / "dst.jpg"
    make_noisy_image(path=src, size=(800, 800), fmt="JPEG")
    original: int = src.stat().st_size
    target_ratio = 0.5
    meta = compress_to_target(input_path=src, output_path=dst, target_ratio=target_ratio)
    assert dst.exists()
    assert meta["original_size"] == original
    assert meta["new_size"] <= original * target_ratio + 500  # tolerancia por búsqueda binaria
    assert 10 <= meta["quality"] <= 95
    assert meta["width"] == 800 and meta["height"] == 600 or meta["width"] == 800  # noisy 800x800
    assert meta["note"] is None
    # dimensiones preservadas
    with Image.open(fp=dst) as out:
        assert out.size == (800, 800)


def test_compress_jpeg_maintains_dimensions(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    dst: Path = tmp_path / "b.jpg"
    make_solid_image(path=src, size=(123, 77), fmt="JPEG")
    meta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.7)
    assert meta["width"] == 123
    assert meta["height"] == 77
    with Image.open(fp=dst) as im:
        assert im.size == (123, 77)


def test_compress_jpeg_rgba_converts_to_rgb(tmp_path: Path) -> None:
    # JPEG no soporta RGBA, _save_with_quality debe convertir a RGB
    from compressor_core import _save_with_quality

    im_rgba: Image.Image = Image.new(mode="RGBA", size=(20, 20), color=(10, 20, 30, 100))
    out: Path = tmp_path / "rgba_out.jpg"
    size = _save_with_quality(im_rgba, out, "JPEG", 50)
    assert out.exists()
    assert size > 0
    with Image.open(fp=out) as im:
        assert im.mode == "RGB"

    # también con modo P
    im_p: Image.Image = Image.new(mode="P", size=(20, 20))
    out2: Path = tmp_path / "p_out.jpg"
    size2 = _save_with_quality(im_p, out2, "JPEG", 50)
    assert out2.exists()
    assert size2 > 0


def test_compress_png_lossless_note(tmp_path: Path) -> None:
    src: Path = tmp_path / "img.png"
    dst: Path = tmp_path / "out.png"
    img: Image.Image = Image.new(mode="RGBA", size=(100, 100), color=(255, 0, 0, 128))
    img.save(fp=src, format="PNG")
    meta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.5)
    assert meta["quality"] is None
    assert "PNG comprimido sin pérdida" in meta["note"]
    assert dst.exists()
    assert meta["width"] == 100 and meta["height"] == 100
    with Image.open(fp=dst) as im:
        assert im.size == (100, 100)


def test_compress_webp(tmp_path: Path) -> None:
    src: Path = tmp_path / "in.webp"
    dst: Path = tmp_path / "out.webp"
    make_noisy_image(path=src, size=(400, 400), fmt="WEBP")
    meta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.6)
    assert 10 <= meta["quality"] <= 95
    assert dst.exists()
    with Image.open(fp=dst) as im:
        assert im.size == (400, 400)


def test_compress_avif_if_supported(tmp_path: Path) -> None:
    # AVIF puede no estar disponible en todas las builds de Pillow
    src: Path = tmp_path / "in.avif"
    dst: Path = tmp_path / "out.avif"
    try:
        make_noisy_image(path=src, size=(200, 200), fmt="AVIF")
    except Exception as e:
        pytest.skip(reason=f"AVIF no soportado en esta build de Pillow: {e}")
    try:
        meta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.6)
    except Exception as e:
        pytest.skip(reason=f"AVIF compress falló (plugin faltante): {e}")
    assert 10 <= meta["quality"] <= 95


def test_compress_quality_bounds_respected(tmp_path: Path) -> None:
    src: Path = tmp_path / "src.jpg"
    dst: Path = tmp_path / "dst.jpg"
    make_noisy_image(path=src, size=(500, 500), fmt="JPEG")
    meta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.3, min_quality=20, max_quality=80)
    assert 20 <= meta["quality"] <= 80


def test_compress_unsupported_extension_raises(tmp_path: Path) -> None:
    # Crear una imagen válida pero con extensión no soportada (.txt)
    # Así Image.open sucede pero format_for_extension falla
    src: Path = tmp_path / "file.txt"
    img: Image.Image = Image.new(mode="RGB", size=(10, 10), color="red")
    # guardar como JPEG pero con nombre .txt
    buf = io.BytesIO()
    img.save(fp=buf, format="JPEG", quality=95)
    src.write_bytes(data=buf.getvalue())
    dst: Path = tmp_path / "out.txt"
    with pytest.raises(expected_exception=UnsupportedFormatError):
        compress_to_target(input_path=src, output_path=dst, target_ratio=0.5)


def test_compress_small_image_fallback_to_min_quality(tmp_path: Path) -> None:
    # Imagen muy pequeña donde incluso quality 10 no baja del target
    src: Path = tmp_path / "tiny.jpg"
    dst: Path = tmp_path / "out.jpg"
    make_solid_image(path=src, size=(10, 10), fmt="JPEG")
    original: int = src.stat().st_size
    # Pedir 5% de una imagen ya mínima: probablemente no se alcanza, debe caer a min_quality
    meta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.05)
    assert meta["quality"] == 10
    assert dst.exists()
