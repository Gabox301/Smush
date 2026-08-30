"""
Cards de la landing — feature y step. Reutilizables para futuras secciones.
"""
from __future__ import annotations

import flet as ft

from ..theme import (
    BLUE,
    CORAL,
    INK,
    INK_SOFT,
    LIME,
    SURFACE,
    SURFACE_ALT,
    FONT_DISPLAY,
    neo_panel,
)

from .primitives import with_hover


def feature_card(i: int, icon: ft.IconData, title: str, text: str) -> ft.Container:
    icon_bgs: list[str] = [LIME, CORAL, BLUE, SURFACE_ALT]
    icon_colors: list[str] = [INK, "#ffffff", "#ffffff", INK_SOFT]
    return with_hover(
        card=neo_panel(
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Container(
                        width=46,
                        height=46,
                        bgcolor=icon_bgs[i % 4],
                        border=ft.Border.all(width=2, color=INK),
                        border_radius=10,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(icon, size=22, color=icon_colors[i % 4]),
                    ),
                    ft.Container(height=14),
                    ft.Text(value=title, size=17, weight=ft.FontWeight.W_700, color=INK,
                            font_family=FONT_DISPLAY or None),
                    ft.Container(height=6),
                    ft.Text(value=text, size=13.5, color=INK_SOFT),
                ],
            ),
            padding=22,
        )
    )


def step_card(num: int, title: str, text: str) -> ft.Container:
    return with_hover(
        card=neo_panel(
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Container(
                        width=46,
                        height=46,
                        bgcolor=INK,
                        border_radius=999,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Text(value=str(object=num), size=24, weight=ft.FontWeight.W_900,
                                        color=SURFACE, font_family=FONT_DISPLAY or None),
                    ),
                    ft.Container(height=14),
                    ft.Text(value=title, size=17, weight=ft.FontWeight.W_700, color=INK,
                            font_family=FONT_DISPLAY or None),
                    ft.Container(height=6),
                    ft.Text(value=text, size=13.5, color=INK_SOFT),
                ],
            ),
            padding=24,
        )
    )
