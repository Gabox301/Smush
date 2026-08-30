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
    return ft.Icon(icon=ft.Icons.COMPRESS, size=min(width, height), color=INK)


def chip(label: str) -> ft.Container:
    return ft.Container(
        content=mono_text(value=label, size=12.5, color=INK),
        bgcolor=SURFACE,
        border=ft.Border.all(width=2, color=INK),
        border_radius=20,
        padding=ft.Padding(left=14, top=6, right=14, bottom=6),
    )


def format_badge(ext: str) -> ft.Container:
    return ft.Container(
        content=mono_text(value=ext, size=12.5, color=INK_SOFT),
        bgcolor=SURFACE,
        border=ft.Border.all(width=2, color=INK),
        border_radius=8,
        padding=ft.Padding(left=8, top=3, right=8, bottom=3),
    )


def sticker(label: str, bgcolor: str, color: str, offset: tuple[int, int], rot: float) -> ft.Container:
    left, top = offset
    return ft.Container(
        left=left,
        top=top,
        rotate=ft.Rotate(angle=rot),
        bgcolor=bgcolor,
        border=ft.Border.all(width=2, color=INK),
        border_radius=8,
        shadow=ft.BoxShadow(offset=ft.Offset(3, 3), blur_radius=0, color=INK),
        padding=ft.Padding(left=9, top=5, right=9, bottom=5),
        content=mono_text(value=label, size=12, color=color, weight=ft.FontWeight.W_500),
    )


def section_head(eyebrow: str, title: str) -> ft.Control:
    return ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        controls=[
            ft.Column(
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    mono_text(value=eyebrow.upper(), size=12.5, color=CORAL, weight=ft.FontWeight.W_600),
                    ft.Text(value=title, size=32, weight=ft.FontWeight.W_800, color=INK,
                            font_family=FONT_DISPLAY or None, text_align=ft.TextAlign.CENTER),
                ],
            ),
        ],
    )


def with_hover(card: ft.Container) -> ft.Container:
    """Efecto hover neobrutalista: escala + sombra dura."""
    card.animate_scale = ft.Animation(duration=180, curve=ft.AnimationCurve.EASE_OUT_BACK)

    def handle_hover(e: ft.Event) -> None:
        hovered = e.data == "true"
        card.scale = 1.03 if hovered else 1.0
        card.shadow = ft.BoxShadow(
            offset=ft.Offset(10, 10) if hovered else ft.Offset(6, 6),
            blur_radius=0,
            color=INK,
        )
        try:
            card.update()
        except RuntimeError:
            pass

    card.on_hover = handle_hover
    return card


def with_cols(cards: Sequence[ft.Control], cols: dict) -> list[ft.Control]:
    """Asigna ancho responsive (col) a cada card ya construida."""
    for card in cards:
        card.col = cols  # type: ignore[attr-defined]
    return list(cards)


def nav_link(app, label: str, target_key: str) -> ft.Container:  # noqa: ANN001
    link = ft.Container(
        content=ft.Text(value=label, size=14.5, weight=ft.FontWeight.W_600, color=INK),
        on_click=lambda _e: app.page.run_task(app.scroll_landing, target_key),
    )

    def handle_hover(e: ft.Event) -> None:
        link.border = ft.Border.only(bottom=ft.BorderSide(width=3 if e.data == "true" else 0, color=CORAL))
        link.padding = ft.Padding(left=0, top=0, right=0, bottom=4)
        try:
            link.update()
        except RuntimeError:
            pass

    link.on_hover = handle_hover
    return link
