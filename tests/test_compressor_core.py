import io
import random
from pathlib import Path
from typing import Any, Callable, Literal, NoReturn

import pytest
from PIL import Image

import compressor_core as cc
from compressor_core import (
    EXTENSION_TO_FORMAT,
    SUPPORTED_EXTENSIONS,
    TARGET_FORMATS,
    UnsupportedFormatError,
    _best_effort_encode,
    _binary_search_quality,
    _encode_png_lossless,
    _encode_png_with_colors,
    _exif_bytes,
    _finalize,
    _psnr,
    _quantize_for_png,
    _save_with_optional_metadata,
    compress_to_target,
    convert_format,
    format_for_extension,
)

# Helpers


def make_noisy_image(path: Path, size: tuple[int, int] = (600, 600), fmt: str = "JPEG") -> Image.Image:
    """Crea imagen con ruido para que la compresión tenga efecto medible."""
    w, h = size
    img: Image.Image = Image.new(mode="RGB", size=(w, h))
    rng = random.Random(42)
    img.putdata(data=[(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(w * h)])
    img.save(fp=path, format=fmt, quality=95)
    return img


def make_solid_image(path: Path, size: tuple[int, int] = (100, 100), color: str = "red", fmt: str = "JPEG", **save_kwargs: Any) -> Image.Image:
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
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=target_ratio)
    assert dst.exists()
    assert meta["original_size"] == original
    assert meta["new_size"] <= original * target_ratio + 500  # tolerancia por búsqueda binaria
    assert meta["quality"] is not None
    assert 10 <= meta["quality"] <= 95
    assert (meta["width"] == 800 and meta["height"] == 600) or meta["width"] == 800  # noisy 800x800
    # Piso de calidad: si el PSNR quedó bajo el mínimo, el note trae el aviso en vez de None.
    if meta["quality_acceptable"]:
        assert meta["note"] is None
    else:
        assert meta["note"] is not None and "PSNR" in meta["note"]
    # dimensiones preservadas
    with Image.open(fp=dst) as out:
        assert out.size == (800, 800)


def test_compute_psnr_false_skips_psnr(tmp_path: Path) -> None:
    src: Path = tmp_path / "src.jpg"
    dst: Path = tmp_path / "dst.jpg"
    make_noisy_image(path=src, size=(800, 800), fmt="JPEG")
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.5, compute_psnr=False)
    assert dst.exists()
    assert meta["psnr_db"] is None
    assert meta["quality_acceptable"] is True
    assert meta["note"] is None or "PSNR" not in meta["note"]


def test_min_psnr_db_zero_reports_value_without_warning(tmp_path: Path) -> None:
    src: Path = tmp_path / "src.jpg"
    dst: Path = tmp_path / "dst.jpg"
    make_noisy_image(path=src, size=(800, 800), fmt="JPEG")
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.5, min_psnr_db=0.0)
    assert dst.exists()
    assert meta["psnr_db"] is not None
    assert meta["quality_acceptable"] is True
    assert meta["note"] is None or "PSNR" not in meta["note"]


def test_min_psnr_db_strict_triggers_warning(tmp_path: Path) -> None:
    src: Path = tmp_path / "src.jpg"
    dst: Path = tmp_path / "dst.jpg"
    make_noisy_image(path=src, size=(800, 800), fmt="JPEG")
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.5, min_psnr_db=99.0)
    assert dst.exists()
    assert meta["quality_acceptable"] is False
    assert meta["note"] is not None and "99.0" in meta["note"]


def test_min_psnr_db_negative_raises(tmp_path: Path) -> None:
    src: Path = tmp_path / "src.jpg"
    make_noisy_image(path=src, size=(100, 100), fmt="JPEG")
    with pytest.raises(expected_exception=ValueError, match="min_psnr_db"):
        compress_to_target(input_path=src, output_path=tmp_path / "o.jpg",
                           target_ratio=0.5, min_psnr_db=-1.0)


def test_compress_jpeg_maintains_dimensions(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    dst: Path = tmp_path / "b.jpg"
    make_solid_image(path=src, size=(123, 77), fmt="JPEG")
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.7)
    assert meta["width"] == 123
    assert meta["height"] == 77
    with Image.open(fp=dst) as im:
        assert im.size == (123, 77)


def test_compress_jpeg_rgba_converts_to_rgb(tmp_path: Path) -> None:
    # Código refactorizado: _save_with_quality fue reemplazado por _flatten_to_rgb + _encode.
    # JPEG no soporta RGBA/P con transparencia; debe aplanarse a RGB.
    from compressor_core import _encode, _flatten_to_rgb

    im_rgba: Image.Image = Image.new(mode="RGBA", size=(20, 20), color=(10, 20, 30, 100))
    flat: Image.Image = _flatten_to_rgb(im=im_rgba)
    assert flat.mode == "RGB"
    data: bytes = _encode(im=im_rgba, fmt="JPEG", quality=50)
    assert len(data) > 0
    with Image.open(fp=io.BytesIO(initial_bytes=data)) as im:
        im.load()
        assert im.mode == "RGB"

    # también con modo P
    im_p: Image.Image = Image.new(mode="P", size=(20, 20))
    flat_p: Image.Image = _flatten_to_rgb(im=im_p)
    assert flat_p.mode == "RGB"
    data_p: bytes = _encode(im=im_p, fmt="JPEG", quality=50)
    assert len(data_p) > 0
    with Image.open(fp=io.BytesIO(initial_bytes=data_p)) as im:
        im.load()
        assert im.mode == "RGB"

    # Integración: compress_to_target debe manejar PNG RGBA sin error (pipeline PNG)
    src_rgba: Path = tmp_path / "src_rgba.png"
    dst_rgba: Path = tmp_path / "dst_rgba.png"
    img2: Image.Image = Image.new(mode="RGBA", size=(30, 30), color=(0, 255, 0, 128))
    img2.save(fp=src_rgba, format="PNG")
    meta: cc.CompressMeta = compress_to_target(input_path=src_rgba, output_path=dst_rgba, target_ratio=0.8)
    assert dst_rgba.exists()
    assert meta["width"] == 30 and meta["height"] == 30


def test_compress_png_lossless_note(tmp_path: Path) -> None:
    src: Path = tmp_path / "img.png"
    dst: Path = tmp_path / "out.png"
    img: Image.Image = Image.new(mode="RGBA", size=(100, 100), color=(255, 0, 0, 128))
    img.save(fp=src, format="PNG")
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.5)
    # Código refactorizado: 100x100 RGBA sólido a 50% no alcanza ni con paleta mínima (172 > 157 target),
    # retorna paleta mínima con nota de fallo. Antes se esperaba lossless con quality None y frase distinta.
    assert meta["quality"] == 10
    assert meta["note"] is not None
    assert "paleta mínima" in meta["note"]
    assert dst.exists()
    assert meta["width"] == 100 and meta["height"] == 100
    with Image.open(fp=dst) as im:
        assert im.size == (100, 100)

    # Caso donde sí hay ahorro lossless: ratio muy permisivo 0.9 -> debe optimizar sin pérdida
    src2: Path = tmp_path / "img2.png"
    dst2: Path = tmp_path / "out2.png"
    img.save(fp=src2, format="PNG")
    meta2: cc.CompressMeta = compress_to_target(input_path=src2, output_path=dst2, target_ratio=0.9)
    # Con 0.9 el target es 283 bytes (315*0.9), el PNG optimizado 221 sí entra, por lo que usa lossless
    assert meta2["quality"] == 100
    assert meta2["note"] is not None
    assert "PNG optimizado sin pérdida" in meta2["note"]


def test_compress_webp(tmp_path: Path) -> None:
    src: Path = tmp_path / "in.webp"
    dst: Path = tmp_path / "out.webp"
    make_noisy_image(path=src, size=(400, 400), fmt="WEBP")
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.6)
    assert meta["quality"] is not None
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
    except Exception as e:  # noqa: BLE001
        pytest.skip(reason=f"AVIF no soportado en esta build de Pillow: {e}")
    try:
        meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.6)
    except Exception as e:  # noqa: BLE001
        pytest.skip(reason=f"AVIF compress falló (plugin faltante): {e}")
    assert meta["quality"] is not None
    assert 10 <= meta["quality"] <= 95


def test_compress_quality_bounds_respected(tmp_path: Path) -> None:
    src: Path = tmp_path / "src.jpg"
    dst: Path = tmp_path / "dst.jpg"
    make_noisy_image(path=src, size=(500, 500), fmt="JPEG")
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.3, min_quality=20, max_quality=80)
    assert meta["quality"] is not None
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
    # Pedir 5% de una imagen ya mínima: probablemente no se alcanza, debe caer a min_quality
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.05)
    assert meta["quality"] == 10
    assert dst.exists()


# --- Tests adicionales: validaciones, metadata (ICC/EXIF), fallbacks y ramas ---
# (antes en tests/test_compressor_core_extra.py)


# _validate_parameters vía compress_to_target


@pytest.mark.parametrize(argnames="bad_ratio", argvalues=[0, -0.1, 1.01, 2.0])
def test_invalid_target_ratio_raises(tmp_path: Path, bad_ratio: float) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    with pytest.raises(expected_exception=ValueError, match="target_ratio"):
        compress_to_target(input_path=src, output_path=tmp_path / "o.jpg", target_ratio=bad_ratio)


@pytest.mark.parametrize(
    argnames="kwargs",
    argvalues=[
        {"min_quality": 0},
        {"max_quality": 101},
        {"min_quality": 60, "max_quality": 40},
    ],
)
def test_invalid_quality_bounds_raise(tmp_path: Path, kwargs: dict) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    with pytest.raises(expected_exception=ValueError, match="quality"):
        compress_to_target(input_path=src, output_path=tmp_path / "o.jpg", target_ratio=0.5, **kwargs)


# Validaciones de paths / fondo


def test_input_file_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(expected_exception=FileNotFoundError, match="No existe"):
        compress_to_target(input_path=tmp_path / "missing.jpg", output_path=tmp_path / "o.jpg", target_ratio=0.5)


def test_input_and_output_same_path_raises(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    with pytest.raises(expected_exception=ValueError, match="distintos"):
        compress_to_target(input_path=src, output_path=src, target_ratio=0.5)


@pytest.mark.parametrize(argnames="background", argvalues=[(0, 0), (300, 0, 0), (1, 2, 3, 4), (1, 2, -3)])
def test_invalid_jpeg_background_raises(tmp_path: Path, background: tuple) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    with pytest.raises(expected_exception=ValueError, match="jpeg_background"):
        compress_to_target(input_path=src, output_path=tmp_path / "o.jpg", target_ratio=0.5, jpeg_background=background)


# Ramas de flujo principal


def test_target_ratio_one_preserves_original(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src, size=(300, 300))
    dst: Path = tmp_path / "o.jpg"
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=1.0)
    assert meta["compression_applied"] is False
    assert meta["target_reached"] is True
    assert meta["new_size"] == meta["original_size"]
    assert meta["quality"] is None
    assert meta["note"] is not None
    assert "no exige reducir" in meta["note"]
    assert dst.read_bytes() == src.read_bytes()


def test_compress_png_quantized_success(tmp_path: Path) -> None:
    """Imagen PNG con ruido: el lossless no alcanza y la cuantización sí."""
    src: Path = tmp_path / "noisy.png"
    make_noisy_image(path=src, size=(400, 400), fmt="PNG")
    dst: Path = tmp_path / "out.png"
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.3)
    assert meta["compression_applied"] is True
    assert meta["target_reached"] is True
    assert meta["note"] is not None
    assert "PNG cuantizado a" in meta["note"]
    assert dst.exists()


def test_min_quality_shortcut_preserves_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si ni la calidad mínima reduce, no se busca más y se conserva el original."""
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    original_size: int = src.stat().st_size

    def fake_encode(*args: Any, **kwargs: Any) -> bytes:
        return b"\x00" * (original_size + 128)

    monkeypatch.setattr(target=cc, name="_encode", value=fake_encode)
    dst: Path = tmp_path / "o.jpg"
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.5)
    assert meta["compression_applied"] is False
    assert meta["quality"] is None
    assert meta["note"] is not None
    assert "resultado no era más pequeño" in meta["note"]
    assert dst.read_bytes() == src.read_bytes()


# Metadata: ICC y EXIF


def _image_with_metadata(mode: str = "RGB") -> Image.Image:
    im: Image.Image = Image.new(mode, size=(64, 64), color="red")
    im.info["icc_profile"] = bytes(range(256)) * 4
    ex = Image.Exif()
    ex[274] = 6  # orientation
    im.info["exif"] = ex.tobytes()
    return im


def test_encode_png_keeps_icc_and_exif() -> None:
    im: Image.Image = _image_with_metadata()
    data: bytes = _encode_png_lossless(im=im, preserve_exif=True)
    assert len(data) > 0
    with Image.open(fp=io.BytesIO(initial_bytes=data)) as out:
        out.load()
        assert out.info.get("icc_profile")


def test_encode_png_with_colors_keeps_icc_and_exif() -> None:
    im: Image.Image = _image_with_metadata()
    data: bytes = _encode_png_with_colors(im=im, colors=64, preserve_exif=True)
    assert len(data) > 0
    with Image.open(fp=io.BytesIO(initial_bytes=data)) as out:
        out.load()
        assert out.info.get("icc_profile")


def test_compress_jpeg_preserves_icc_profile(tmp_path: Path) -> None:
    src: Path = tmp_path / "icc.jpg"
    img: Image.Image = Image.new(mode="RGB", size=(100, 100), color="blue")
    img.save(fp=src, format="JPEG", quality=92, icc_profile=bytes(range(256)) * 4)
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=tmp_path / "o.jpg", target_ratio=0.7)
    assert meta["icc_preserved"] is True


def test_compress_preserves_exif_and_resets_orientation(tmp_path: Path) -> None:
    src: Path = tmp_path / "exif.jpg"
    img: Image.Image = Image.new(mode="RGB", size=(80, 80), color="green")
    ex = Image.Exif()
    ex[274] = 6
    img.save(fp=src, format="JPEG", quality=92, exif=ex.tobytes())
    dst: Path = tmp_path / "o.jpg"
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.7, preserve_exif=True)
    assert meta["preserve_exif"] is True
    assert dst.exists()
    # el EXIF original debe seguir en el archivo resultante con Orientation = 1
    with Image.open(fp=dst) as out:
        out.load()
        exif: Image.Exif = out.getexif()
        assert exif.get(274) in (1, None)  # 1 = ya aplicada físicamente


def test_exif_bytes_handles_empty_exif() -> None:
    im: Image.Image = Image.new(mode="RGB", size=(10, 10), color="red")
    assert _exif_bytes(im=im, preserve_exif=True) is None


# Fallbacks internos


def test_save_with_optional_metadata_fallback_drops_exif() -> None:
    im: Image.Image = Image.new(mode="RGB", size=(32, 32), color="red")
    buf = io.BytesIO()
    # exif inválido fuerza el reintento sin exif
    _save_with_optional_metadata(
        im=im,
        buf=buf,
        save_kwargs={"format": "PNG", "optimize": True, "compress_level": 9, "exif": b"garbage"},
    )
    assert len(buf.getvalue()) > 0
    with Image.open(fp=io.BytesIO(initial_bytes=buf.getvalue())) as out:
        out.load()
        assert out.format == "PNG"


def test_quantize_for_png_converts_non_rgb_and_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Modo L fuerza la conversión; y si LIBIMAGEQUANT falla, se usa FASTOCTREE."""
    im_gray: Image.Image = Image.new(mode="L", size=(40, 40), color="gray")
    q: Image.Image = _quantize_for_png(im=im_gray, colors=16)
    assert q.mode == "P"

    im_rgb: Image.Image = Image.new(mode="RGB", size=(40, 40), color="red")
    original_quantize: Callable[..., Image.Image] = Image.Image.quantize
    calls: dict[str, int] = {"n": 0}

    def raiser(self: Image.Image, *args: Any, **kwargs: Any) -> Image.Image:
        if calls["n"] == 0:
            calls["n"] += 1
            raise RuntimeError("libimagequant unavailable")
        return original_quantize(self, *args, **kwargs)

    monkeypatch.setattr(target=Image.Image, name="quantize", value=raiser)
    q2: Image.Image = _quantize_for_png(im=im_rgb, colors=16)
    assert q2.mode == "P"
    assert calls["n"] == 1


def test_binary_search_returns_none_when_no_quality_fits() -> None:
    encode_fn: Callable[..., bytes] = lambda q: b"x" * 1000  # noqa: E731
    quality, data = _binary_search_quality(encode_fn=encode_fn, target_size=100, min_quality=10, max_quality=95)
    assert quality is None
    assert data is None
    quality, data, reached = _best_effort_encode(encode_fn=encode_fn, target_size=100, min_quality=10, max_quality=95)
    assert reached is False
    assert quality == 10
    assert len(data) == 1000


# _psnr / _finalize


def test_psnr_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    im: Image.Image = Image.new(mode="RGB", size=(40, 40), color="red")
    # decode falla -> None
    assert _psnr(original=im, compressed_bytes=b"nope", background=(255, 255, 255)) is None
    # shape mismatch -> None
    small: Image.Image = Image.new(mode="RGB", size=(20, 20), color="red")
    small_buf = io.BytesIO()
    small.save(fp=small_buf, format="PNG")
    assert _psnr(original=im, compressed_bytes=small_buf.getvalue(), background=(255, 255, 255)) is None
    # idénticas -> 99.0
    buf = io.BytesIO()
    im.save(fp=buf, format="PNG")
    assert _psnr(original=im, compressed_bytes=buf.getvalue(), background=(255, 255, 255)) == 99.0
    # np.asarray falla -> None

    def flaky_asarray(*args: Any, **kwargs: Any) -> NoReturn:
        raise ValueError("shape raro")

    monkeypatch.setattr(target=cc.np, name="asarray", value=flaky_asarray)
    assert _psnr(original=im, compressed_bytes=buf.getvalue(), background=(255, 255, 255)) is None
    # sin numpy -> None
    monkeypatch.setattr(target=cc, name="_HAS_NUMPY", value=False)
    monkeypatch.setattr(target=cc, name="np", value=None)
    assert _psnr(original=im, compressed_bytes=buf.getvalue(), background=(255, 255, 255)) is None


def test_finalize_copies_original_when_not_smaller(tmp_path: Path) -> None:
    src: Path = tmp_path / "in.jpg"
    make_solid_image(path=src, size=(50, 50))
    dst: Path = tmp_path / "out.jpg"
    im: Image.Image = Image.new(mode="RGB", size=(50, 50), color="red")
    meta: cc.CompressMeta = _finalize(
        output_path=dst,
        input_path=src,
        original_size=100,
        encoded_bytes=b"\xff" * 300,  # mayor al original
        quality=10,
        note="n/a",
        im=im,
        target_size=50,
        target_reached=True,
        target_ratio=0.5,
        fmt="JPEG",
        jpeg_background=(255, 255, 255),
        preserve_exif=False,
    )
    assert meta["compression_applied"] is False
    assert meta["new_size"] == 100
    assert meta["quality"] is None
    assert dst.read_bytes() == src.read_bytes()


def test_encode_includes_icc_and_exif() -> None:
    im: Image.Image = Image.new(mode="RGB", size=(32, 32), color="red")
    im.info["icc_profile"] = bytes(range(256)) * 2
    ex = Image.Exif()
    ex[274] = 6
    im.info["exif"] = ex.tobytes()
    data: bytes = cc._encode(im=im, fmt="JPEG", quality=50, preserve_exif=True)
    assert len(data) > 0


def test_exif_bytes_error_path(monkeypatch: pytest.MonkeyPatch) -> None:
    im: Image.Image = Image.new(mode="RGB", size=(32, 32), color="red")

    def boom() -> object:
        raise ValueError("exif corrupto")

    monkeypatch.setattr(target=im, name="getexif", value=boom)
    assert _exif_bytes(im=im, preserve_exif=True) is None


def test_save_with_optional_metadata_retries_on_type_error(monkeypatch: pytest.MonkeyPatch) -> None:
    im: Image.Image = Image.new(mode="RGB", size=(32, 32), color="red")
    buf = io.BytesIO()
    original_save: Callable[..., None] = im.save
    calls: dict[str, int] = {"n": 0}

    def flaky_save(*args: Any, **kwargs: Any) -> None:
        if calls["n"] == 0:
            calls["n"] += 1
            raise TypeError("opción no soportada")
        original_save(*args, **kwargs)

    monkeypatch.setattr(target=im, name="save", value=flaky_save)
    _save_with_optional_metadata(
        im=im,
        buf=buf,
        save_kwargs={"format": "PNG", "optimize": True, "compress_level": 9, "exif": b"x"},
    )
    assert calls["n"] == 1
    assert len(buf.getvalue()) > 0


def test_compress_swallows_close_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """El finally tolera que la imagen no se pueda cerrar."""
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)

    def boom_close(self: Image.Image) -> None:
        raise RuntimeError("close falló")

    monkeypatch.setattr(target=Image.Image, name="close", value=boom_close)
    dst: Path = tmp_path / "out.jpg"
    meta: cc.CompressMeta = compress_to_target(input_path=src, output_path=dst, target_ratio=0.5)
    assert dst.exists()
    assert "new_size" in meta


# Tests convert_format


def test_convert_jpeg_to_png_lossless(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    dst: Path = tmp_path / "a.png"
    meta: cc.ConvertMeta = convert_format(input_path=src, output_path=dst, target_format="PNG")
    assert dst.exists()
    assert meta["format"] == "PNG"
    assert meta["quality"] is None
    assert meta["original_size"] > 0
    assert meta["new_size"] > 0
    with Image.open(fp=dst) as out:
        out.load()
        assert out.size == (100, 100)


def test_convert_png_rgba_to_jpeg_flattens(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.png"
    Image.new(mode="RGBA", size=(64, 64), color=(10, 20, 30, 100)).save(fp=src, format="PNG")
    dst: Path = tmp_path / "a.jpg"
    meta: cc.ConvertMeta = convert_format(input_path=src, output_path=dst, target_format="JPEG", quality=80)
    assert dst.exists()
    assert meta["quality"] is not None
    assert 10 <= meta["quality"] <= 80
    with Image.open(fp=dst) as out:
        out.load()
        assert out.mode == "RGB"
        assert out.size == (64, 64)


def test_convert_jpeg_to_webp(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_noisy_image(path=src, size=(200, 200))
    dst: Path = tmp_path / "a.webp"
    meta: cc.ConvertMeta = convert_format(input_path=src, output_path=dst, target_format="webp", quality=80)
    assert dst.exists()
    assert meta["format"] == "WEBP"
    with Image.open(fp=dst) as out:
        out.load()
        assert out.size == (200, 200)


def test_convert_invalid_format_raises(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    with pytest.raises(expected_exception=ValueError, match="target_format"):
        convert_format(input_path=src, output_path=tmp_path / "a.gif", target_format="GIF")


def test_convert_invalid_quality_raises(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    with pytest.raises(expected_exception=ValueError, match="quality"):
        convert_format(input_path=src, output_path=tmp_path / "a.png", target_format="PNG", quality=0)
    with pytest.raises(expected_exception=ValueError, match="quality"):
        convert_format(input_path=src, output_path=tmp_path / "a.png", target_format="PNG", quality=101)


def test_convert_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(expected_exception=FileNotFoundError):
        convert_format(input_path=tmp_path / "missing.jpg", output_path=tmp_path / "o.png",
                       target_format="PNG")


def test_convert_same_path_raises(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    with pytest.raises(expected_exception=ValueError, match="distintos"):
        convert_format(input_path=src, output_path=src, target_format="PNG")


def test_convert_avif_without_support_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    monkeypatch.setattr(target=cc, name="check_avif_support", value=lambda: False)
    with pytest.raises(expected_exception=UnsupportedFormatError, match="AVIF"):
        convert_format(input_path=src, output_path=tmp_path / "a.avif", target_format="AVIF")


def test_target_formats_contains_expected() -> None:
    assert set(TARGET_FORMATS) == {"AVIF", "WEBP", "JPEG", "PNG"}


def test_convert_compresses_to_target_ratio(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_noisy_image(path=src, size=(400, 400))
    original: int = src.stat().st_size
    dst: Path = tmp_path / "a.webp"
    meta: cc.ConvertMeta = convert_format(input_path=src, output_path=dst, target_format="WEBP",
                          quality=85, target_ratio=0.5)
    assert dst.exists()
    assert meta["target_reached"] is True
    assert meta["new_size"] <= original * 0.5 + 500
    assert meta["quality"] is not None
    assert 10 <= meta["quality"] <= 85


def test_convert_defaults_to_never_heavier(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.png"
    make_solid_image(path=src, size=(200, 200), fmt="PNG")
    original: int = src.stat().st_size
    dst: Path = tmp_path / "a.webp"
    meta: cc.ConvertMeta = convert_format(input_path=src, output_path=dst, target_format="WEBP")
    assert dst.exists()
    assert meta["target_reached"] is True
    assert meta["new_size"] <= original


def test_convert_png_target_uses_palette_when_needed(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_noisy_image(path=src, size=(300, 300))
    dst: Path = tmp_path / "a.png"
    convert_format(input_path=src, output_path=dst, target_format="PNG", target_ratio=0.3)
    assert dst.exists()
    with Image.open(fp=dst) as out:
        out.load()
        assert out.size == (300, 300)


def test_convert_invalid_ratio_raises(tmp_path: Path) -> None:
    src: Path = tmp_path / "a.jpg"
    make_solid_image(path=src)
    with pytest.raises(expected_exception=ValueError, match="target_ratio"):
        convert_format(input_path=src, output_path=tmp_path / "a.webp",
                       target_format="WEBP", target_ratio=0)
    with pytest.raises(expected_exception=ValueError, match="target_ratio"):
        convert_format(input_path=src, output_path=tmp_path / "a.webp",
                       target_format="WEBP", target_ratio=1.5)
