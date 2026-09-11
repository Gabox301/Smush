"""
Tokens de diseño "elastic neo-brutalism" y componentes base.
"""
from __future__ import annotations

import flet as ft

# ---- Colores ----
BG = "#f3ecd9"
SURFACE = "#fffcf3"
SURFACE_ALT = "#ece2c6"
INK = "#17170f"
INK_SOFT = "#5a5847"
LIME = "#c6ff5e"
LIME_DARK = "#97e023"
CORAL = "#ff5d45"
BLUE = "#4f6dff"

# ---- Métricas ----
RADIUS = 16
BW = 3  # ancho de borde neo

# ---- Tipografías (registradas en helpers.register_fonts) ----
FONT_DISPLAY = "Fraunces"
FONT_BODY = "WorkSans"
FONT_MONO = "PlexMono"

# ---- Formatos aceptados ----
ACCEPTED: list[str] = [".avif", ".webp", ".jpg", ".jpeg", ".png"]


def is_hovered(data: object) -> bool:
    """Normaliza e.data de on_hover: bool en Flet 0.86+, "true" en versiones viejas."""
    if isinstance(data, str):
        return data.lower() == "true"
    return bool(data)


def mono_text(
    value,
    size: float = 12,
    color: str = INK_SOFT,
    weight: ft.FontWeight = ft.FontWeight.W_400,
) -> ft.Text:
    """Texto en fuente mono, como los datos y chips del diseño."""
    return ft.Text(value, size=size, color=color, weight=weight, font_family=FONT_MONO)


def neo_panel(content: ft.Control, padding: int | ft.Padding = 22) -> ft.Container:
    """Equivalente a .panel: superficie clara, borde grueso y sombra dura."""
    return ft.Container(
        content=content,
        bgcolor=SURFACE,
        border=ft.Border.all(width=BW, color=INK),
        border_radius=RADIUS,
        padding=padding,
        shadow=ft.BoxShadow(offset=ft.Offset(6, 6), blur_radius=0, color=INK),
    )


def neo_button(
    label: str,
    bgcolor: str,
    color: str,
    on_click=None,
    border_color: str = INK,
    border_width: int = BW,
    shadow_offset: tuple[float, float] = (4, 4),
    weight: ft.FontWeight = ft.FontWeight.W_700,
) -> ft.Container:
    """Botón estilo .btn: sombra dura que se desplaza al pasar el mouse."""
    btn = ft.Container(
        content=ft.Text(value=label, size=14.5, weight=weight, color=color, font_family=FONT_BODY),
        bgcolor=bgcolor,
        border=ft.Border.all(width=border_width, color=border_color),
        border_radius=10,
        padding=ft.Padding(left=20, top=11, right=20, bottom=11),
        shadow=ft.BoxShadow(
            offset=ft.Offset(*shadow_offset),
            blur_radius=0,
            color=border_color if border_color == INK else INK,
        ),
        animate_scale=ft.Animation(duration=150, curve=ft.AnimationCurve.EASE_OUT_BACK),
        on_click=on_click,
    )

    def handle_hover(e: ft.Event) -> None:
        btn.scale = 1.04 if is_hovered(data=e.data) else 1.0
        try:
            btn.update()
        except RuntimeError:
            pass

    btn.on_hover = handle_hover
    return btn
