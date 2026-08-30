"""Tests de smush_gui/theme: tokens de diseño y componentes base."""
from types import SimpleNamespace
from typing import Any, Callable, cast

import flet as ft

from smush_gui import theme as t


def fire(callable_like: Any, *args: Any, **kwargs: Any) -> None:
    """Invoca un handler de flet (opcional) de forma segura para el checker."""
    cast(Callable[..., None], callable_like)(*args, **kwargs)


def test_color_tokens() -> None:
    assert t.BG == "#f3ecd9"
    assert t.SURFACE == "#fffcf3"
    assert t.SURFACE_ALT == "#ece2c6"
    assert t.INK == "#17170f"
    assert t.INK_SOFT == "#5a5847"
    assert t.LIME == "#c6ff5e"
    assert t.LIME_DARK == "#97e023"
    assert t.CORAL == "#ff5d45"
    assert t.BLUE == "#4f6dff"


def test_metrics_fonts_and_accepted() -> None:
    assert t.RADIUS == 16
    assert t.BW == 3
    assert t.FONT_DISPLAY == "Fraunces"
    assert t.FONT_BODY == "WorkSans"
    assert t.FONT_MONO == "PlexMono"
    assert t.ACCEPTED == [".avif", ".webp", ".jpg", ".jpeg", ".png"]


def test_mono_text() -> None:
    txt: ft.Text = t.mono_text(value="42%", size=14, color=t.INK_SOFT, weight=ft.FontWeight.W_500)
    assert txt.value == "42%"
    assert txt.size == 14
    assert txt.color == t.INK_SOFT
    assert txt.weight == ft.FontWeight.W_500
    assert txt.font_family == t.FONT_MONO


def test_neo_panel() -> None:
    inner = ft.Text(value="contenido")
    panel: ft.Container = t.neo_panel(content=inner)
    assert panel.bgcolor == t.SURFACE
    assert panel.border_radius == t.RADIUS
    assert panel.border is not None
    assert panel.border.top.width == t.BW
    assert panel.border.top.color == t.INK
    assert panel.content is inner
    assert panel.shadow is not None
    assert panel.shadow.offset == ft.Offset(6, 6)


def test_neo_panel_custom_padding() -> None:
    panel: ft.Container = t.neo_panel(content=ft.Text(value="x"), padding=10)
    assert panel.padding == 10


def test_neo_button_style_and_label() -> None:
    onclick: Callable[..., None] = lambda _e: None  # noqa: E731
    btn: ft.Container = t.neo_button(label="Aceptar", bgcolor=t.LIME, color=t.INK,
                       on_click=onclick, border_width=2, shadow_offset=(2, 2))
    assert btn.bgcolor == t.LIME
    assert isinstance(btn.content, ft.Text)
    assert btn.content.value == "Aceptar"
    assert btn.content.color == t.INK
    assert btn.border is not None
    assert btn.border.top.width == 2
    assert btn.border.top.color == t.INK
    assert btn.on_click is onclick
    assert btn.on_hover is not None


def test_neo_button_hover_changes_scale() -> None:
    btn: ft.Container = t.neo_button(label="Hover", bgcolor=t.LIME, color=t.INK)
    btn.update = lambda: None  # type: ignore[method-assign]
    fire(btn.on_hover, SimpleNamespace(data="true"))
    assert btn.scale == 1.04
    fire(btn.on_hover, SimpleNamespace(data="false"))
    assert btn.scale == 1.0
