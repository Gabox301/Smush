"""
Primitivos de filas para la herramienta — shell, meta y thumbs.
Extraídos de tool.py para reutilizar en otras vistas.
"""
from __future__ import annotations

from pathlib import Path

import flet as ft

from ..helpers import ext_of, make_thumb_png
from ..theme import CORAL, INK, INK_SOFT, SURFACE, SURFACE_ALT, FONT_MONO, mono_text, neo_button
from ..theme import BLUE, LIME  # para badge


def row_shell(i: int, controls: list[ft.Control]) -> ft.Container:
    return ft.Container(
        bgcolor=SURFACE_ALT,
        border=ft.Border.all(2, INK),
        border_radius=10,
        shadow=ft.BoxShadow(offset=ft.Offset(3, 3), blur_radius=0, color=INK),
        padding=ft.Padding(12, 10, 12, 10),
        rotate=ft.Rotate(-0.007 if i % 2 == 0 else 0.007),
        content=ft.Row(spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                       controls=controls),
    )


def meta_column(name: str, sub: ft.Control) -> ft.Column:
    return ft.Column(
        spacing=1,
        expand=True,
        controls=[
            ft.Text(name, size=13.5, color=INK, max_lines=1, weight=ft.FontWeight.W_500),
            sub,
        ],
    )


def thumb_control(path: Path | str) -> ft.Control:
    thumb_png = make_thumb_png(Path(path))
    if thumb_png:
        return ft.Container(
            width=42, height=42, bgcolor=SURFACE,
            border=ft.Border.all(2, INK), border_radius=8,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Image(src=thumb_png, width=42, height=42, fit=ft.BoxFit.COVER),
        )
    return ft.Container(
        width=42, height=42, bgcolor=SURFACE,
        border=ft.Border.all(2, INK), border_radius=8,
        alignment=ft.Alignment.CENTER,
        content=mono_text(ext_of(str(path)).lstrip("."), size=10, color=INK_SOFT),
    )


def brand_icon(size: int) -> ft.Control:
    from ..helpers import ASSETS

    if (ASSETS / "img" / "smush-isotipo.svg").exists():
        return ft.Image(src="img/smush-isotipo.svg", width=size, height=size,
                        error_content=ft.Icon(ft.Icons.COMPRESS, size=size - 2, color=INK))
    return ft.Icon(ft.Icons.COMPRESS, size=size - 2, color=INK)


# ---- Filas de alto nivel (reutilizables) ----
def result_row(app, i: int, r: dict) -> ft.Container:  # noqa: ANN001
    from ..helpers import human_size

    badge = ft.Container(
        bgcolor=LIME,
        border=ft.Border.all(2, INK),
        border_radius=20,
        padding=ft.Padding(10, 4, 10, 4),
        content=mono_text(f"{r['percent_of_original']}%", size=12.5, color=INK,
                          weight=ft.FontWeight.W_700),
    )
    sizes = ft.Text(
        spans=[
            ft.TextSpan(human_size(r["original_size"])),
            ft.TextSpan(" → "),
            ft.TextSpan(human_size(r["new_size"]),
                        ft.TextStyle(weight=ft.FontWeight.W_700, color=INK)),
        ],
        size=12,
        color=INK_SOFT,
        font_family=FONT_MONO or None,
    )
    note = mono_text(
        f"calidad {r['quality']} — {r['note']}" if r.get("note") else f"calidad {r['quality']}",
        size=11,
    )
    save_btn = neo_button("Guardar", BLUE, "#fdfcf6", border_width=2, shadow_offset=(2, 2))
    save_btn.on_click = app.make_save_handler(r)
    return row_shell(
        i,
        [meta_column(r["filename"], ft.Column(spacing=0, controls=[sizes, note])),
         badge, save_btn],
    )


def error_row(i: int, filename: str, error: str) -> ft.Container:
    return row_shell(
        i,
        [ft.Icon(ft.Icons.ERROR_OUTLINE, size=22, color=CORAL),
         meta_column(filename,
                      ft.Text(error, size=13, weight=ft.FontWeight.W_600, color=CORAL))],
    )


def pending_row(i: int, path, remove_cb) -> ft.Container:  # noqa: ANN001
    from ..helpers import human_size

    remove_btn = ft.Container(
        width=26, height=26, bgcolor=SURFACE,
        border=ft.Border.all(2, INK), border_radius=999,
        alignment=ft.Alignment.CENTER,
        on_click=lambda _e: remove_cb(i),
        content=ft.Icon(ft.Icons.CLOSE, size=13, color=INK),
    )
    return row_shell(
        i,
        [thumb_control(path),
         meta_column(Path(path).name, mono_text(human_size(Path(path).stat().st_size))),
         remove_btn],
    )
