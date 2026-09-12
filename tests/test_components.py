"""Tests de smush_gui/components: cards, primitives y rows."""
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest
from PIL import Image

from compressor_core import CompressRow
from smush_gui import helpers
from smush_gui.components import cards as cards_mod
from smush_gui.components import primitives as prim
from smush_gui.components import rows as rows_mod
from smush_gui.theme import INK, INK_SOFT, SURFACE, SURFACE_ALT


def fire(callable_like: Any, *args: Any, **kwargs: Any) -> None:
    cast(Callable[..., None], callable_like)(*args, **kwargs)


def text_values(c: Any, seen: set[int] | None = None) -> list[str]:
    """Recorre el árbol de controles y junta los valores de los ft.Text."""
    seen = set() if seen is None else seen
    if id(c) in seen:
        return []
    seen.add(id(c))
    vals: list[str] = []
    if isinstance(c, ft.Text):
        vals.append(c.value or "")
    for sub in list(getattr(c, "controls", None) or []):
        vals += text_values(sub, seen)
    content: Any | None = getattr(c, "content", None)
    if content is not None:
        vals += text_values(content, seen)
    return vals


def make_svg(tmp_path: Path) -> Path:
    assets: Path = tmp_path / "assets"
    (assets / "img").mkdir(parents=True)
    (assets / "img" / "smush-isotipo.svg").write_text(data="<svg/>", encoding="utf-8")
    return assets


# ---------------- primitives ----------------


def test_isotipo_with_svg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target=prim, name="ASSETS", value=make_svg(tmp_path))
    out: ft.Control = prim.isotipo(width=40, height=30)
    assert isinstance(out, ft.Image)
    assert out.width == 40
    assert out.height == 30


def test_isotipo_fallback_without_svg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target=prim, name="ASSETS", value=tmp_path / "no-assets")
    out: ft.Control = prim.isotipo(width=40, height=30)
    assert isinstance(out, ft.Icon)
    assert out.size == 30
    assert out.color == INK


def test_chip() -> None:
    out: ft.Container = prim.chip(label="100% en tu máquina")
    assert out.bgcolor == SURFACE
    assert out.border is not None
    assert out.border.top.width == 2
    assert isinstance(out.content, ft.Text)
    assert out.content.value == "100% en tu máquina"
    assert out.content.font_family is not None


def test_format_badge() -> None:
    out: ft.Container = prim.format_badge(ext=".jpg")
    assert isinstance(out.content, ft.Text)
    assert out.content.value == ".jpg"
    assert out.content.color == INK_SOFT


def test_sticker() -> None:
    out: ft.Container = prim.sticker(label=".png", bgcolor=SURFACE, color=INK, offset=(14, 27), rot=-0.105)
    assert out.left == 14
    assert out.top == 27
    assert out.rotate is not None
    assert isinstance(out.rotate, ft.Rotate)
    assert out.rotate.angle == -0.105
    assert isinstance(out.content, ft.Text)
    assert out.content.value == ".png"


def test_section_head() -> None:
    out: ft.Control = prim.section_head(eyebrow="Qué hace", title="Todo lo que necesitás")
    assert isinstance(out, ft.Row)
    assert "Todo lo que necesitás" in text_values(c=out)
    assert "QUÉ HACE" in text_values(c=out)  # uppercase


def test_with_hover_changes_scale_and_shadow() -> None:
    card = ft.Container(content=ft.Text(value="x"))
    result: ft.Container = prim.with_hover(card)
    assert result is card
    assert card.animate_scale is not None
    fire(card.on_hover, SimpleNamespace(data="true"))
    assert card.scale == 1.03
    assert card.shadow is not None
    assert isinstance(card.shadow, ft.BoxShadow)
    assert card.shadow.offset == ft.Offset(10, 10)
    fire(card.on_hover, SimpleNamespace(data="false"))
    assert card.scale == 1.0
    assert isinstance(card.shadow, ft.BoxShadow)
    assert card.shadow.offset == ft.Offset(6, 6)


def test_with_cols_assigns_responsive_col() -> None:
    a = ft.Container()
    b = ft.Container()
    out: list[ft.Control] = prim.with_cols(cards=[a, b], cols={"sm": 12, "lg": 6})
    assert out == [a, b]
    assert a.col == {"sm": 12, "lg": 6}
    assert b.col == {"sm": 12, "lg": 6}


def test_nav_link_click_scrolls_and_hover() -> None:
    class FakeNavApp:
        def __init__(self) -> None:
            self.calls: list[tuple] = []
            self.page = SimpleNamespace(run_task=self._run_task)

        def _run_task(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
            self.calls.append((fn, args, kwargs))

        async def scroll_landing(self, key: str) -> None:
            self.calls.append(("scroll", key))

    app = FakeNavApp()
    link: ft.Container = prim.nav_link(app, label="Cómo funciona", target_key="how")
    fire(link.on_click, None)
    assert len(app.calls) == 1
    fn, args, _kw = app.calls[0]
    assert fn == app.scroll_landing
    assert args == ("how",)

    fire(link.on_hover, SimpleNamespace(data="true"))
    assert link.border is not None
    assert link.border.bottom.width == 3
    fire(link.on_hover, SimpleNamespace(data="false"))
    assert link.border.bottom.width == 0


# ---------------- cards ----------------


def test_feature_card_contains_title() -> None:
    card: ft.Container = cards_mod.feature_card(i=0, icon=ft.Icons.UPLOAD_FILE, title="Arrastrar y listo", text="Descripción")
    assert isinstance(card, ft.Container)
    assert card.on_hover is not None
    assert "Arrastrar y listo" in text_values(c=card)
    assert "Descripción" in text_values(c=card)


def test_feature_card_cycles_icon_bg() -> None:
    c0: ft.Container = cards_mod.feature_card(i=0, icon=ft.Icons.TUNE, title="A", text="B")
    c4: ft.Container = cards_mod.feature_card(i=4, icon=ft.Icons.TUNE, title="A", text="B")
    # i=0 y i=4 comparten color de ícono (ciclo de 4)
    c0_icon = c0.content.controls[0]  # type: ignore[union-attr]
    c4_icon = c4.content.controls[0]  # type: ignore[union-attr]
    assert c0_icon.bgcolor == c4_icon.bgcolor


def test_step_card_contains_title_and_number() -> None:
    card: ft.Container = cards_mod.step_card(num=2, title="Ajustá el objetivo", text="Movés el control")
    assert "Ajustá el objetivo" in text_values(c=card)
    assert "Movés el control" in text_values(c=card)
    assert "2" in text_values(c=card)


# ---------------- rows ----------------


def test_row_shell_rotates_by_parity() -> None:
    even: ft.Container = rows_mod.row_shell(i=0, controls=[ft.Text(value="a")])
    odd: ft.Container = rows_mod.row_shell(i=1, controls=[ft.Text(value="a")])
    assert even.bgcolor == SURFACE_ALT
    assert even.border is not None
    assert even.rotate is not None
    assert isinstance(even.rotate, ft.Rotate)
    assert even.rotate.angle == -0.007
    assert odd.rotate is not None
    assert isinstance(odd.rotate, ft.Rotate)
    assert odd.rotate.angle == 0.007
    assert isinstance(even.content, ft.Row)
    assert len(even.content.controls) == 1


def test_meta_column() -> None:
    sub = ft.Text(value="subtítulo")
    col: ft.Column = rows_mod.meta_column(name="foto.jpg", sub=sub)
    assert col.expand is True
    assert isinstance(col.controls[0], ft.Text)
    assert col.controls[0].value == "foto.jpg"
    assert col.controls[1] is sub


def test_thumb_control_with_valid_image(tmp_path: Path) -> None:
    img: Image.Image = Image.new(mode="RGB", size=(60, 40), color="coral")
    path: Path = tmp_path / "t.png"
    img.save(fp=path, format="PNG")
    out: ft.Control = rows_mod.thumb_control(path)
    assert isinstance(out, ft.Container)
    assert isinstance(out.content, ft.Image)


def test_thumb_control_fallback_to_extension(tmp_path: Path) -> None:
    bad: Path = tmp_path / "broken.jpg"
    bad.write_bytes(data=b"not an image")
    out: ft.Control = rows_mod.thumb_control(path=bad)
    assert isinstance(out, ft.Container)
    assert isinstance(out.content, ft.Text)
    assert out.content.value == "jpg"


def test_brand_icon_with_svg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target=helpers, name="ASSETS", value=make_svg(tmp_path))
    out: ft.Control = rows_mod.brand_icon(size=22)
    assert isinstance(out, ft.Image)


def test_brand_icon_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(target=helpers, name="ASSETS", value=tmp_path / "no-assets")
    out: ft.Control = rows_mod.brand_icon(size=22)
    assert isinstance(out, ft.Icon)
    assert out.size == 20


def test_result_row_badge_and_note() -> None:
    app = SimpleNamespace(make_save_handler=lambda r: (lambda _e: None))
    r: CompressRow = {
        "filename": "f.jpg",
        "percent_of_original": 50.0,
        "original_size": 1000,
        "new_size": 500,
        "quality": 50,
        "note": None,
        "tmp_path": "x",
        "psnr_db": None,
        "quality_acceptable": True,
    }
    row: ft.Container = rows_mod.result_row(app, 0, r)
    vals: list[str] = text_values(c=row)
    assert "50.0%" in vals
    assert "calidad 50" in vals


def test_result_row_shows_psnr_chip() -> None:
    from smush_gui.theme import CORAL, INK_SOFT

    app = SimpleNamespace(make_save_handler=lambda r: (lambda _e: None))

    def make_row(psnr: float | None, acceptable: bool, note: str | None) -> CompressRow:
        return {
            "filename": "f.jpg",
            "percent_of_original": 50.0,
            "original_size": 1000,
            "new_size": 500,
            "quality": 50,
            "note": note,
            "tmp_path": "x",
            "psnr_db": psnr,
            "quality_acceptable": acceptable,
        }

    # Sin psnr no hay chip
    row: ft.Container = rows_mod.result_row(app, 0, make_row(None, True, None))
    assert "dB" not in " ".join(text_values(c=row))

    # Con psnr bueno: chip visible, colores normales
    row_ok: ft.Container = rows_mod.result_row(app, 0, make_row(45.12, True, None))
    assert "45.1 dB" in text_values(c=row_ok)

    # Con calidad baja: chip + nota en coral
    row_bad: ft.Container = rows_mod.result_row(app, 0, make_row(24.33, False, "aviso de piso"))
    assert "24.3 dB" in text_values(c=row_bad)

    def all_texts(c: Any) -> list[ft.Text]:
        found: list[ft.Text] = []
        if isinstance(c, ft.Text):
            found.append(c)
        for sub in list(getattr(c, "controls", None) or []):
            found += all_texts(sub)
        content: Any | None = getattr(c, "content", None)
        if content is not None:
            found += all_texts(content)
        return found

    bad_texts: dict[str, str | ft.Colors | ft.CupertinoColors | None] = {t.value: t.color for t in all_texts(row_bad)}
    assert bad_texts.get("24.3 dB") == CORAL
    ok_texts: dict[str, str | ft.Colors | ft.CupertinoColors | None] = {t.value: t.color for t in all_texts(row_ok)}
    assert ok_texts.get("45.1 dB") != CORAL
    assert INK_SOFT not in {t.color for t in all_texts(row_bad) if t.value and t.value.startswith("calidad")}


def test_error_row_contains_message() -> None:
    row: ft.Container = rows_mod.error_row(i=0, filename="a.jpg", error="Formato no soportado")
    vals: list[str] = text_values(c=row)
    assert "a.jpg" in vals
    assert "Formato no soportado" in vals


def test_pending_row_remove_callback(tmp_path: Path) -> None:
    p: Path = tmp_path / "f.png"
    p.write_bytes(data=b"data")
    removed: list[int] = []

    def remove_cb(i: int) -> None:
        removed.append(i)

    row: ft.Container = rows_mod.pending_row(0, p, remove_cb)
    assert isinstance(row.content, ft.Row)
    remove_btn: ft.Control = row.content.controls[2]
    assert isinstance(remove_btn, ft.Container)
    fire(remove_btn.on_click, None)
    assert removed == [0]
