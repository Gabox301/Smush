"""
Primitivos reutilizables de UI — chips, badges, stickers, headers
y helpers de layout. Extraídos de landing.py para DRY.
"""
from __future__ import annotations

from collections.abc import Sequence

import flet as ft

from ..helpers import ASSETS
from ..theme import (
    CORAL,
    INK,
    INK_SOFT,
    SURFACE,
    FONT_DISPLAY,
    mono_text,
)


def isotipo(width: int, height: int) -> ft.Control:
    if (ASSETS / "img" / "smush-isotipo.svg").exists():
        return ft.Image(src="img/smush-isotipo.svg", width=width, height=height)
    return ft.Icon(ft.Icons.COMPRESS, size=min(width, height), color=INK)


def chip(label: str) -> ft.Container:
    return ft.Container(
        content=mono_text(label, size=12.5, color=INK),
        bgcolor=SURFACE,
        border=ft.Border.all(2, INK),
        border_radius=20,
        padding=ft.Padding(14, 6, 14, 6),
    )


def format_badge(ext: str) -> ft.Container:
    return ft.Container(
        content=mono_text(ext, size=12.5, color=INK_SOFT),
        bgcolor=SURFACE,
        border=ft.Border.all(2, INK),
        border_radius=8,
        padding=ft.Padding(8, 3, 8, 3),
    )


def sticker(label: str, bgcolor: str, color: str, offset: tuple[int, int], rot: float) -> ft.Container:
    left, top = offset
    return ft.Container(
        left=left,
        top=top,
        rotate=ft.Rotate(rot),
        bgcolor=bgcolor,
        border=ft.Border.all(2, INK),
        border_radius=8,
        shadow=ft.BoxShadow(offset=ft.Offset(3, 3), blur_radius=0, color=INK),
        padding=ft.Padding(9, 5, 9, 5),
        content=mono_text(label, size=12, color=color, weight=ft.FontWeight.W_500),
    )


def section_head(eyebrow: str, title: str) -> ft.Control:
    return ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        controls=[
            ft.Column(
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    mono_text(eyebrow.upper(), size=12.5, color=CORAL, weight=ft.FontWeight.W_600),
                    ft.Text(title, size=32, weight=ft.FontWeight.W_800, color=INK,
                            font_family=FONT_DISPLAY or None, text_align=ft.TextAlign.CENTER),
                ],
            ),
        ],
    )


def with_hover(card: ft.Container) -> ft.Container:
    """Efecto hover neobrutalista: escala + sombra dura."""
    card.animate_scale = ft.Animation(180, ft.AnimationCurve.EASE_OUT_BACK)

    def handle_hover(e: ft.Event) -> None:
        hovered = bool(e.data)
        card.scale = 1.03 if hovered else 1.0
        card.shadow = ft.BoxShadow(
            offset=ft.Offset(10, 10) if hovered else ft.Offset(6, 6),
            blur_radius=0,
            color=INK,
        )
        card.update()

    card.on_hover = handle_hover
    return card


def with_cols(cards: Sequence[ft.Control], cols: dict) -> list[ft.Control]:
    """Asigna ancho responsive (col) a cada card ya construida."""
    for card in cards:
        card.col = cols  # type: ignore[attr-defined]
    return list(cards)


def nav_link(app, label: str, target_key: str) -> ft.Container:  # noqa: ANN001
    link = ft.Container(
        content=ft.Text(label, size=14.5, weight=ft.FontWeight.W_600, color=INK),
        on_click=lambda _e: app.page.run_task(app.scroll_landing, target_key),
    )

    def handle_hover(e: ft.Event) -> None:
        link.border = ft.Border.only(bottom=ft.BorderSide(3 if e.data else 0, CORAL))
        link.padding = ft.Padding(0, 0, 0, 4)
        link.update()

    link.on_hover = handle_hover
    return link
