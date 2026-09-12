"""Tests del controlador smush_gui/app.py (SmushApp) y de las vistas
landing.py / tool.py a través de su construcción.
"""
from __future__ import annotations

import asyncio
import zipfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest
from PIL import Image

import smush_gui.app as app_module
from compressor_core import (
    CompressRow,
    ConvertRow,
    ErrorMeta,
    UnsupportedFormatError,
    is_compress_error,
    is_compress_ok,
    is_convert_error,
    is_convert_ok,
)


class FakePage:
    """Mínimo Page de flet necesario para construir SmushApp."""

    def __init__(self) -> None:
        self.window = SimpleNamespace(maximized=False, width=0, height=800, icon=None)
        self.fonts = None
        self.theme = None
        self.title = None
        self.bgcolor = None
        self.padding = None
        self.scroll = None
        self.height = None
        self.on_resized = None
        self.add_calls: list[Any] = []
        self.update_calls = 0
        self.run_tasks: list[tuple] = []
        self.dialogs: list[Any] = []

    def add(self, control: Any) -> None:
        self.add_calls.append(control)

    def update(self) -> None:
        self.update_calls += 1

    def run_task(self, handler: Any, *args: Any, **kwargs: Any) -> None:
        self.run_tasks.append((handler, args, kwargs))

    def show_dialog(self, dialog: Any) -> None:
        self.dialogs.append(dialog)


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> tuple[app_module.SmushApp, FakePage]:
    monkeypatch.setattr(target=app_module, name="ensure_assets", value=lambda: None)
    monkeypatch.setattr(target=app_module, name="register_fonts", value=lambda page: None)
    fake = FakePage()
    app = app_module.SmushApp(page=cast(ft.Page, fake))
    return app, fake


def _make_jpg(path: Path, color: str = "red", size: tuple[int, int] = (40, 40)) -> None:
    Image.new("RGB", size, color=color).save(fp=path, format="JPEG", quality=95)


# ---------------- __init__ / _build ----------------


def test_init_builds_views_and_sets_page(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, fake = ctx
    assert app.pending == []
    assert app.results == []
    assert app.compressing is False
    assert app.pending_convert == []
    assert app.convert_results == []
    assert app.converting is False
    assert app.convert_target == "WEBP"
    assert isinstance(app.tool_view, ft.Container)
    assert isinstance(app.landing_view, ft.ListView)
    assert app.tool_view.visible is False
    assert app.landing_view.visible is True
    assert fake.title == "Smush — compresor de imágenes"
    assert fake.bgcolor is not None
    assert fake.window.maximized is True
    assert fake.window.height == 800
    assert fake.add_calls
    assert app.ratio_readout.value == "50"
    assert app.slider is not None
    assert app.slider.value == 50
    assert app.config_panel.visible is False
    assert app.list_panel.visible is False
    assert app.results_panel.visible is False
    assert app.zip_btn.visible is False
    assert app.convert_list_panel.visible is False
    assert app.convert_results_panel.visible is False
    assert app.convert_card.visible is False
    assert app.convert_slider.value == 85
    assert app.convert_size_slider.value == 100
    assert set(app.convert_chips) == {"AVIF", "WEBP", "JPEG", "PNG"}
    # se lanzan las tareas internas (loop de animación, etc.)
    names = {handler.__name__ for handler, _, _ in fake.run_tasks}
    assert "_squish_loop" in names


def test_tool_layout_flows_side_by_side(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    """Compresión a la izquierda y conversión a la derecha, no apiladas."""
    app, _fake = ctx
    _topbar, flows_row, _footer = app.main_column.controls
    assert isinstance(flows_row, ft.Container)
    responsive: ft.Control | None = flows_row.content
    assert isinstance(responsive, ft.ResponsiveRow)
    left, right = (cast(ft.Container, c) for c in responsive.controls)
    assert left.col == {"sm": 12, "lg": 6}
    assert right.col == {"sm": 12, "lg": 6}
    assert isinstance(left.content, ft.Column)
    assert isinstance(right.content, ft.Column)
    left_controls: list[ft.Control] = left.content.controls
    right_controls: list[ft.Control] = right.content.controls
    assert app.config_panel in left_controls
    assert app.list_panel in left_controls
    assert app.results_panel in left_controls
    assert app.convert_list_panel in right_controls
    assert app.convert_results_panel in right_controls


def test_package_exports() -> None:
    import smush_gui

    assert smush_gui.SmushApp
    assert callable(smush_gui.ensure_assets)
    assert callable(smush_gui.register_fonts)


def test_tool_module_exports() -> None:
    from smush_gui.tool import __all__

    assert set(__all__) == {"build_tool", "convert_result_row", "error_row", "pending_row", "result_row"}


# ---------------- Navegación ----------------


def test_go_tool(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, fake = ctx
    app.go_tool()
    assert app.tool_view.visible is True
    assert app.landing_view.visible is False
    assert fake.update_calls > 0


def test_go_landing_queues_scroll_reset(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, fake = ctx
    app.landing_view.visible = True
    app.tool_view.visible = True
    app.go_landing()
    assert app.tool_view.visible is False
    assert app.landing_view.visible is True
    names = {handler.__name__ for handler, _, _ in fake.run_tasks}
    assert "_reset_landing_scroll" in names


def test_scroll_landing_offsets(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    calls: list[dict] = []

    class FakeListView:
        async def scroll_to(self, **kw: Any) -> None:
            calls.append(kw)

    app.landing_col = cast(Any, FakeListView())
    asyncio.run(main=app.scroll_landing(key="features"))
    assert calls[0]["offset"] == 850
    asyncio.run(main=app.scroll_landing(key="how"))
    assert calls[1]["offset"] == 1450
    asyncio.run(main=app.scroll_landing(key="other"))
    assert "scroll_key" in calls[2]


# ---------------- Eventos de la herramienta ----------------


def test_on_slider_change(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    e = SimpleNamespace(control=SimpleNamespace(value=42))
    app.on_slider_change(e)
    assert app.ratio_readout.value == "42"
    assert app.squeeze_canvas.shapes


def test_remove_file_in_bounds(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path) -> None:
    app, _fake = ctx
    p1: Path = tmp_path / "a.jpg"
    p2: Path = tmp_path / "b.jpg"
    _make_jpg(path=p1)
    _make_jpg(path=p2)
    app.pending = [p1, p2]
    app.remove_file(index=1)
    assert app.pending == [p1]
    # índice fuera de rango no rompe
    app.remove_file(index=99)
    assert app.pending == [p1]


def test_clear_all_resets_state(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    app.pending = [Path("x.jpg")]
    app.results = [{"filename": "x", "error": "boom"}]
    app.zip_btn.visible = True
    app.results_panel.visible = True
    app.clear_all()
    assert app.pending == []
    assert app.results == []
    assert app.zip_btn.visible is False
    assert app.results_panel.visible is False


def test_refresh_lists_toggles_panels(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path) -> None:
    app, _fake = ctx
    assert app.list_panel.visible is False
    p: Path = tmp_path / "x.jpg"
    _make_jpg(path=p)
    app.pending = [p]
    app.refresh_lists()
    assert app.list_panel.visible is True
    assert app.config_panel.visible is True
    assert len(app.file_list_col.controls) == 1
    app.pending = []
    app.refresh_lists()
    assert app.list_panel.visible is False
    assert app.config_panel.visible is False


# ---------------- pick_files ----------------


def test_pick_files_adds_valid_and_skips_rest(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    valid: Path = tmp_path / "a.jpg"
    _make_jpg(path=valid)

    class FakePicker:
        async def pick_files(self, **kw: Any) -> list:
            return [
                SimpleNamespace(path=str(object=valid), name="a.jpg"),
                SimpleNamespace(path=str(object=valid), name="a.jpg"),  # duplicado
                SimpleNamespace(path=str(object=tmp_path / "b.txt"), name="b.txt"),  # ext no aceptada
                SimpleNamespace(path=None, name="c.jpg"),  # sin path
            ]

    monkeypatch.setattr(target=app_module.ft, name="FilePicker", value=lambda: FakePicker())
    asyncio.run(main=app.pick_files(_e=None))
    assert app.pending == [valid]
    assert app.file_list_col.controls


def test_pick_files_empty_selection_keeps_pending(ctx: tuple[app_module.SmushApp, FakePage], monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    app.pending = [Path("x.jpg")]

    class EmptyPicker:
        async def pick_files(self, **kw: Any) -> list:
            return []

    monkeypatch.setattr(target=app_module.ft, name="FilePicker", value=lambda: EmptyPicker())
    asyncio.run(main=app.pick_files(_e=None))
    assert app.pending == [Path("x.jpg")]


# ---------------- Conversión ----------------


def test_pick_convert_files_adds_valid(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    valid: Path = tmp_path / "a.png"
    Image.new("RGB", (40, 40), color="blue").save(fp=valid, format="PNG")

    class FakePicker:
        async def pick_files(self, **kw: Any) -> list:
            return [
                SimpleNamespace(path=str(object=valid), name="a.png"),
                SimpleNamespace(path=str(object=tmp_path / "b.txt"), name="b.txt"),
            ]

    monkeypatch.setattr(target=app_module.ft, name="FilePicker", value=lambda: FakePicker())
    asyncio.run(main=app.pick_convert_files(_e=None))
    assert app.pending_convert == [valid]
    assert app.convert_list_panel.visible is True
    assert app.convert_card.visible is True
    assert app.convert_file_col.controls


def test_set_convert_target_repaints_chips(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    from smush_gui.theme import LIME, SURFACE

    app, _fake = ctx
    assert app.convert_target == "WEBP"
    app.set_convert_target("PNG")
    assert app.convert_target == "PNG"
    assert app.convert_chips["PNG"].bgcolor == LIME
    assert app.convert_chips["WEBP"].bgcolor == SURFACE


def test_on_convert_quality_change(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    app.on_convert_quality_change(SimpleNamespace(control=SimpleNamespace(value=70)))
    assert app.convert_quality_readout.value == "70"


def test_on_convert_size_change(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    app.on_convert_size_change(SimpleNamespace(control=SimpleNamespace(value=60)))
    assert app.convert_size_readout.value == "60"


def test_remove_and_clear_convert(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path) -> None:
    app, _fake = ctx
    pa: Path = tmp_path / "a.jpg"
    pb: Path = tmp_path / "b.jpg"
    _make_jpg(path=pa)
    _make_jpg(path=pb)
    app.pending_convert = [pa, pb]
    app.remove_convert_file(0)
    assert app.pending_convert == [pb]
    app.clear_convert()
    assert app.pending_convert == []
    assert app.convert_results == []
    assert app.convert_list_panel.visible is False
    assert app.convert_card.visible is False
    assert app.convert_results_panel.visible is False


def test_convert_sync_success(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    _prepare_compress(app, tmp_path, monkeypatch)
    p1: Path = tmp_path / "a.jpg"
    p2: Path = tmp_path / "b.png"
    _make_jpg(path=p1)
    Image.new("RGB", (40, 40), color="green").save(fp=p2, format="PNG")
    app.pending_convert = [p1, p2]
    app.convert_target = "WEBP"
    results: list[ConvertRow | ErrorMeta] = app._convert_sync(target_format="WEBP", quality=80)
    assert len(results) == 2
    for r in results:
        assert is_convert_ok(r)
        assert r["filename"].endswith(".webp")
        assert Path(r["tmp_path"]).exists()
        assert r["target_format"] == "WEBP"


def test_convert_sync_renames_collisions(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    _prepare_compress(app, tmp_path, monkeypatch)
    d1: Path = tmp_path / "d1"
    d2: Path = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    _make_jpg(path=d1 / "photo.jpg", color="red")
    _make_jpg(path=d2 / "photo.png", color="blue")
    app.pending_convert = [d1 / "photo.jpg", d2 / "photo.png"]
    results: list[ConvertRow | ErrorMeta] = app._convert_sync(target_format="JPEG", quality=80)
    assert {r["filename"] for r in results} == {"photo.jpg", "photo_1.jpg"}


def test_convert_sync_reports_errors(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    _prepare_compress(app, tmp_path, monkeypatch)
    ok: Path = tmp_path / "ok.jpg"
    bad: Path = tmp_path / "bad.jpg"
    _make_jpg(path=ok)
    _make_jpg(path=bad)

    def fake_convert(input_path: Path, output_path: Path, target_format: str, quality: int, target_ratio: float = 1.0) -> dict:
        if input_path.name == "bad.jpg":
            raise UnsupportedFormatError("AVIF no soportado")
        output_path.write_bytes(data=b"data")
        return {"format": target_format, "target_format": target_format, "original_size": 100,
                "new_size": 50, "target_reached": True, "quality": quality, "note": None,
                "width": 40, "height": 40, "preserve_exif": False, "icc_preserved": False}

    monkeypatch.setattr(target=app_module, name="convert_format", value=fake_convert)
    app.pending_convert = [ok, bad]
    results: list[ConvertRow | ErrorMeta] = app._convert_sync(target_format="AVIF", quality=80)
    by_name: dict[str, ConvertRow | ErrorMeta] = {r["filename"]: r for r in results}
    assert "error" not in by_name["ok.avif"]
    bad_row: ConvertRow | ErrorMeta = by_name["bad.avif"]
    assert is_convert_error(bad_row)
    assert bad_row["error"] == "AVIF no soportado"


def test_render_convert_results(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    app.convert_results = [
        ErrorMeta(filename="a.webp", error="falló"),
        ConvertRow(
            filename="b.webp",
            target_format="WEBP",
            format="WEBP",
            original_size=100,
            new_size=50,
            target_reached=True,
            quality=80,
            note=None,
            tmp_path="x",
            width=100,
            height=100,
            preserve_exif=False,
            icc_preserved=False,
        ),
    ]
    app.render_convert_results()
    assert len(app.convert_result_col.controls) == 2
    assert app.convert_results_panel.visible is True


def test_convert_click_without_pending_returns_early(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    app.pending_convert = []
    asyncio.run(main=app.convert_click(_e=None))
    assert app.converting is False


def test_convert_click_runs_and_restores_button(ctx: tuple[app_module.SmushApp, FakePage], monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    app.pending_convert = [Path("x.jpg")]
    app.convert_slider.value = 85
    app.convert_size_slider.value = 100
    results = [
        {
            "filename": "x.webp",
            "target_format": "WEBP",
            "original_size": 100,
            "new_size": 50,
            "target_reached": True,
            "quality": 80,
            "note": None,
            "tmp_path": "y",
        }
    ]
    monkeypatch.setattr(target=app, name="_convert_sync", value=lambda *a: results)
    asyncio.run(main=app.convert_click(_e=None))
    assert app.convert_results == results
    assert app.converting is False
    assert app.convert_btn.disabled is False
    assert app.convert_btn.opacity == 1.0
    assert isinstance(app.convert_btn.content, ft.Text)
    assert app.convert_btn.content.value == "Convertir"
    assert app.convert_results_panel.visible is True


# ---------------- Compresión ----------------


def _prepare_compress(app: app_module.SmushApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target=app_module, name="cleanup_old_jobs", value=lambda: None)
    monkeypatch.setattr(target=app_module, name="BASE_TMP", value=tmp_path / "base")


def test_compress_sync_success(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    _prepare_compress(app, tmp_path, monkeypatch)
    p1: Path = tmp_path / "a.jpg"
    p2: Path = tmp_path / "b.jpg"
    _make_jpg(path=p1)
    _make_jpg(path=p2)
    app.pending = [p1, p2]
    results: list[CompressRow | ErrorMeta] = app._compress_sync(ratio=0.5)
    assert len(results) == 2
    for r in results:
        assert is_compress_ok(r)
        assert r["filename"] in ("a.jpg", "b.jpg")
        assert r["original_size"] > 0
        assert r["new_size"] > 0
        assert r["percent_of_original"] > 0
        assert Path(r["tmp_path"]).exists()


def test_compress_sync_renames_collisions(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    _prepare_compress(app, tmp_path, monkeypatch)
    d1: Path = tmp_path / "d1"
    d2: Path = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    _make_jpg(path=d1 / "photo.jpg", color="red")
    _make_jpg(path=d2 / "photo.jpg", color="blue")
    app.pending = [d1 / "photo.jpg", d2 / "photo.jpg"]
    results: list[CompressRow | ErrorMeta] = app._compress_sync(ratio=0.5)
    names: set[str] = {r["filename"] for r in results}
    assert names == {"photo.jpg", "photo_1.jpg"}


def test_compress_sync_reports_errors(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    _prepare_compress(app, tmp_path, monkeypatch)
    ok: Path = tmp_path / "ok.jpg"
    bad1: Path = tmp_path / "bad1.jpg"
    bad2: Path = tmp_path / "bad2.jpg"
    _make_jpg(path=ok)
    _make_jpg(path=bad1)
    _make_jpg(path=bad2)

    def fake_compress(input_path: Path, output_path: Path, target_ratio: float) -> dict:
        if input_path.name == "bad1.jpg":
            raise UnsupportedFormatError("formato no soportado")
        if input_path.name == "bad2.jpg":
            raise RuntimeError("crashed")
        meta = {
            "original_size": 100,
            "new_size": 50,
            "quality": 50,
            "note": None,
            "psnr_db": 40.0,
            "quality_acceptable": True,
        }
        output_path.write_bytes(data=b"data")
        return meta

    monkeypatch.setattr(target=app_module, name="compress_to_target", value=fake_compress)
    app.pending = [ok, bad1, bad2]
    results: list[CompressRow | ErrorMeta] = app._compress_sync(ratio=0.5)
    by_name: dict[str, CompressRow | ErrorMeta] = {r["filename"]: r for r in results}
    assert "error" not in by_name["ok.jpg"]
    bad1_row: CompressRow | ErrorMeta = by_name["bad1.jpg"]
    assert is_compress_error(bad1_row)
    assert bad1_row["error"] == "formato no soportado"
    bad2_row: CompressRow | ErrorMeta = by_name["bad2.jpg"]
    assert is_compress_error(bad2_row)
    assert bad2_row["error"].startswith("Error al procesar")


def test_render_results_with_errors_and_ok(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    app.results = [
        ErrorMeta(filename="a.jpg", error="falló"),
        CompressRow(
            filename="b.jpg",
            original_size=100,
            new_size=50,
            percent_of_original=50.0,
            quality=50,
            note=None,
            tmp_path="x",
            psnr_db=45.0,
            quality_acceptable=True,
        ),
    ]
    app.render_results()
    assert len(app.result_col.controls) == 2
    assert app.zip_btn.visible is True
    assert app.results_panel.visible is True


def test_render_results_all_errors_hides_zip(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    app.results = [{"filename": "a.jpg", "error": "falló"}]
    app.zip_btn.visible = True
    app.render_results()
    assert app.zip_btn.visible is False
    assert app.results_panel.visible is True


# ---------------- Guardado ----------------


def test_make_save_handler_runs_save_one(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, fake = ctx
    r: dict[str, str] = {"filename": "x.jpg"}
    handler: Callable[..., None] = app.make_save_handler(result=r)
    handler(None)
    fn, args, _kw = fake.run_tasks[-1]
    assert fn.__name__ == "save_one"
    assert args[0] is r


def test_save_one_copies_file(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, fake = ctx
    src: Path = tmp_path / "src.jpg"
    src.write_bytes(data=b"data123")
    dest: Path = tmp_path / "dest.jpg"

    class FakePicker:
        async def save_file(self, **kw: Any) -> str:
            return str(object=dest)

    monkeypatch.setattr(target=app_module.ft, name="FilePicker", value=lambda: FakePicker())
    asyncio.run(main=app.save_one(result={"filename": "out.jpg", "tmp_path": str(object=src)}))
    assert dest.read_bytes() == b"data123"
    assert len(fake.dialogs) == 1


def test_save_one_cancelled_noop(ctx: tuple[app_module.SmushApp, FakePage], monkeypatch: pytest.MonkeyPatch) -> None:
    app, fake = ctx

    class FakePicker:
        async def save_file(self, **kw: Any) -> None:
            return None

    monkeypatch.setattr(target=app_module.ft, name="FilePicker", value=lambda: FakePicker())
    asyncio.run(main=app.save_one(result={"filename": "out.jpg", "tmp_path": "nope"}))
    assert fake.dialogs == []


def test_save_zip_writes_only_ok_results(ctx: tuple[app_module.SmushApp, FakePage], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    f1: Path = tmp_path / "a.jpg"
    f2: Path = tmp_path / "b.jpg"
    f1.write_bytes(data=b"aaa")
    f2.write_bytes(data=b"bbb")
    dest: Path = tmp_path / "out.zip"

    class FakePicker:
        async def save_file(self, **kw: Any) -> str:
            return str(object=dest)

    monkeypatch.setattr(target=app_module.ft, name="FilePicker", value=lambda: FakePicker())
    app.results = [
        CompressRow(
            filename="a.jpg",
            tmp_path=str(object=f1),
            original_size=3,
            new_size=3,
            percent_of_original=100.0,
            quality=None,
            note=None,
            psnr_db=None,
            quality_acceptable=True,
        ),
        CompressRow(
            filename="b.jpg",
            tmp_path=str(object=f2),
            original_size=3,
            new_size=3,
            percent_of_original=100.0,
            quality=None,
            note=None,
            psnr_db=None,
            quality_acceptable=True,
        ),
        ErrorMeta(filename="bad.jpg", error="x"),
    ]
    asyncio.run(main=app.save_zip(_e=None))
    with zipfile.ZipFile(file=dest) as zf:
        assert set(zf.namelist()) == {"a.jpg", "b.jpg"}


def test_save_zip_without_results_skips_picker(ctx: tuple[app_module.SmushApp, FakePage], monkeypatch: pytest.MonkeyPatch) -> None:
    app, fake = ctx
    called: dict[str, int] = {"n": 0}
    monkeypatch.setattr(target=app_module.ft, name="FilePicker", value=lambda: called.__setitem__("n", called["n"] + 1) or object())
    app.results = [{"filename": "x", "error": "falló"}]
    asyncio.run(main=app.save_zip(_e=None))
    assert called["n"] == 0
    assert fake.dialogs == []


# ---------------- compress_click ----------------


def test_compress_click_runs_and_restores_button(ctx: tuple[app_module.SmushApp, FakePage], monkeypatch: pytest.MonkeyPatch) -> None:
    app, _fake = ctx
    app.pending = [Path("x.jpg")]
    app.slider.value = 50
    results = [
        {
            "filename": "x.jpg",
            "original_size": 100,
            "new_size": 50,
            "percent_of_original": 50.0,
            "quality": 50,
            "note": None,
            "tmp_path": "y",
            "psnr_db": 45.0,
            "quality_acceptable": True,
        }
    ]
    monkeypatch.setattr(target=app, name="_compress_sync", value=lambda ratio: results)
    asyncio.run(main=app.compress_click(_e=None))
    assert app.results == results
    assert app.compressing is False
    assert app.compress_btn.disabled is False
    assert app.compress_btn.opacity == 1.0
    assert isinstance(app.compress_btn.content, ft.Text)
    assert app.compress_btn.content.value == "Comprimir todo"


def test_compress_click_without_pending_returns_early(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, _fake = ctx
    app.pending = []
    asyncio.run(main=app.compress_click(None))
    assert app.results == []


# ---------------- Helpers / misc ----------------


def test_snack_shows_dialog(ctx: tuple[app_module.SmushApp, FakePage]) -> None:
    app, fake = ctx
    app._snack(message="Guardada: /tmp/x.jpg")
    assert len(fake.dialogs) == 1
    assert isinstance(fake.dialogs[0], ft.SnackBar)


def test_blob_container() -> None:
    blob: ft.Container = app_module._blob(size=360, colors=["#aabbcc", "#ddeeff"], right=-120, top=-120)
    assert blob.width == 360
    assert blob.height == 360
    assert blob.border_radius == 999
    assert blob.gradient is not None
    assert blob.gradient.colors == ["#aabbcc", "#ddeeff"]
    assert blob.right == -120
    assert blob.top == -120


def test_main_creates_app(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePage()
    created: list[Any] = []

    class FakeApp:
        def __init__(self, page: Any) -> None:
            created.append(page)

    monkeypatch.setattr(target=app_module, name="SmushApp", value=FakeApp)
    app_module.main(page=cast(ft.Page, fake))
    assert created == [fake]
