"""Tests de smush_gui/helpers: texto, miniaturas, assets, fuentes y limpieza."""
import os
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import flet as ft
import flet.canvas as cv
from flet.canvas import Shape
import pytest
from PIL import Image

from smush_gui import helpers as h


def make_page() -> ft.Page:
    """Página Flet falsa con los atributos mínimos que usa register_fonts."""
    return cast(ft.Page, SimpleNamespace(fonts=None, theme=None))


def test_ext_of() -> None:
    assert h.ext_of(filename="photo.JPG") == ".jpg"
    assert h.ext_of(filename="archive.tar.gz") == ".gz"
    assert h.ext_of(filename="no_extension") == ""
    assert h.ext_of(filename=".hidden") == ".hidden"


def test_human_size() -> None:
    assert h.human_size(num_bytes=0) == "0.0B"
    assert h.human_size(num_bytes=500) == "500.0B"
    assert h.human_size(num_bytes=2048) == "2.0KB"
    assert h.human_size(num_bytes=1024**2) == "1.0MB"
    assert h.human_size(num_bytes=1024**3) == "1.0GB"
    assert h.human_size(num_bytes=-1024) == "-1.0KB"


def test_make_thumb_png_ok(tmp_path: Path) -> None:
    import io

    img: Image.Image = Image.new(mode="RGB", size=(300, 200), color="coral")
    path: Path = tmp_path / "big.png"
    img.save(fp=path, format="PNG")
    thumb: bytes | None = h.make_thumb_png(path)
    assert thumb is not None
    with Image.open(fp=io.BytesIO(initial_bytes=thumb)) as out:
        out.load()
        assert out.size[0] <= 84
        assert out.size[1] <= 84


def test_make_thumb_png_corrupt_returns_none(tmp_path: Path) -> None:
    path: Path = tmp_path / "bad.png"
    path.write_bytes(data=b"not an image")
    assert h.make_thumb_png(path) is None


def test_ensure_assets_generates_dots_tile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assets: Path = tmp_path / "assets"
    monkeypatch.setattr(target=h, name="ASSETS", value=assets)
    h.ensure_assets()
    assert (assets / "dots-tile.png").exists()
    # idempotente: si ya existe, no falla
    before_mtime: float = (assets / "dots-tile.png").stat().st_mtime
    h.ensure_assets()
    assert (assets / "dots-tile.png").stat().st_mtime == before_mtime


def test_register_fonts_sets_page_fonts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fonts_dir: Path = tmp_path / "assets" / "fonts"
    fonts_dir.mkdir(parents=True)
    for fname in ["WorkSans-400.ttf", "WorkSans-700.ttf", "Fraunces-600.ttf", "IBMPlexMono-400.ttf"]:
        (fonts_dir / fname).write_bytes(data=b"ttf")
    assets: Path = tmp_path / "assets"
    monkeypatch.setattr(target=h, name="ASSETS", value=assets)

    page: ft.Page = make_page()
    h.register_fonts(page=page)

    fonts: dict[str, str] | None = page.fonts
    assert fonts is not None
    assert h.FONT_BODY in fonts
    assert h.FONT_DISPLAY in fonts
    assert h.FONT_MONO in fonts
    assert fonts[h.FONT_BODY] == ["fonts/WorkSans-400.ttf", "fonts/WorkSans-700.ttf"]
    assert page.theme is not None


def test_register_fonts_no_fonts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target=h, name="ASSETS", value=tmp_path / "no-assets")
    page: ft.Page = make_page()
    h.register_fonts(page=page)
    assert page.fonts == {}
    assert page.theme is None


def test_squeeze_shapes_vary_with_percent() -> None:
    low: list[Shape] = h.squeeze_shapes(percent=0)  # máximo pliegues
    high: list[Shape] = h.squeeze_shapes(percent=100)  # mínimo pliegues
    assert len(low) == 2
    assert len(high) == 2
    elements_low: int = len(cast(cv.Path, low[0]).elements)
    elements_high: int = len(cast(cv.Path, high[0]).elements)
    assert elements_low == 15  # 14 pliegues -> 15 puntos
    assert elements_high == 4  # 3 pliegues -> 4 puntos
    assert elements_low > elements_high


def test_cleanup_old_jobs_removes_stale_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base: Path = tmp_path / "base"
    base.mkdir()
    old: Path = base / "old"
    new: Path = base / "new"
    old.mkdir()
    new.mkdir()
    now: float = time.time()
    stale_mtime: float = now - h.JOB_TTL_SECONDS - 120
    os.utime(path=old, times=(stale_mtime, stale_mtime))
    os.utime(path=new, times=(now, now))

    monkeypatch.setattr(target=h, name="BASE_TMP", value=base)
    h.cleanup_old_jobs()
    assert not old.exists()
    assert new.exists()


def test_make_thumb_png_converts_gray(tmp_path: Path) -> None:
    import io

    img: Image.Image = Image.new(mode="L", size=(50, 50), color="gray")
    path: Path = tmp_path / "gray.png"
    img.save(fp=path, format="PNG")
    thumb: bytes | None = h.make_thumb_png(path)
    assert thumb is not None
    with Image.open(fp=io.BytesIO(initial_bytes=thumb)) as out:
        assert out.mode == "RGBA"


def test_cleanup_old_jobs_no_base_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target=h, name="BASE_TMP", value=tmp_path / "no-base")
    h.cleanup_old_jobs()  # no debe fallar


def test_cleanup_old_jobs_ignores_stat_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base: Path = tmp_path / "base"
    (base / "boom").mkdir(parents=True)
    (base / "keep").mkdir()
    monkeypatch.setattr(target=h, name="BASE_TMP", value=base)

    original_stat = Path.stat

    def flaky_stat(self, *args, **kwargs) -> os.stat_result:
        if self.name == "boom":
            raise OSError("acceso denegado")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(target=Path, name="stat", value=flaky_stat)
    h.cleanup_old_jobs()
    assert (base / "boom").exists()  # no pudo leerse: se ignora
    assert (base / "keep").exists()
