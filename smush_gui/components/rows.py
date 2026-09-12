"""
Primitivos de filas para la herramienta — shell, meta y thumbs.
Extraídos de tool.py para reutilizar en otras vistas.
"""
from __future__ import annotations

from pathlib import Path

import flet as ft

from compressor_core import CompressRow, ConvertRow

from ..helpers import ext_of, make_thumb_png
from ..theme import (  # para badge
    BLUE,
    CORAL,
    FONT_MONO,
    INK,
    INK_SOFT,
    LIME,
    SURFACE,
    SURFACE_ALT,
    mono_text,
    neo_button,
)


def row_shell(i: int, controls: list[ft.Control]) -> ft.Container:
    return ft.Container(
        bgcolor=SURFACE_ALT,
        border=ft.Border.all(width=2, color=INK),
        border_radius=10,
        shadow=ft.BoxShadow(offset=ft.Offset(3, 3), blur_radius=0, color=INK),
        padding=ft.Padding(left=12, top=10, right=12, bottom=10),
        rotate=ft.Rotate(angle=-0.007 if i % 2 == 0 else 0.007),
        content=ft.Row(spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                       controls=controls),
    )


def meta_column(name: str, sub: ft.Control) -> ft.Column:
    return ft.Column(
        spacing=1,
        expand=True,
        controls=[
            ft.Text(value=name, size=13.5, color=INK, max_lines=1, weight=ft.FontWeight.W_500),
            sub,
        ],
    )


def thumb_control(path: Path | str) -> ft.Control:
    thumb_png: bytes | None = make_thumb_png(path=Path(path))
    if thumb_png:
        return ft.Container(
            width=36, height=36, bgcolor=SURFACE,
            border=ft.Border.all(width=2, color=INK), border_radius=8,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Image(src=thumb_png, width=36, height=36, fit=ft.BoxFit.COVER),
        )
    return ft.Container(
        width=36, height=36, bgcolor=SURFACE,
        border=ft.Border.all(width=2, color=INK), border_radius=8,
        alignment=ft.Alignment.CENTER,
        content=mono_text(value=ext_of(filename=str(object=path)).lstrip("."), size=10, color=INK_SOFT),
    )


def brand_icon(size: int) -> ft.Control:
    from ..helpers import ASSETS

    if (ASSETS / "img" / "smush-isotipo.svg").exists():
        return ft.Image(src="img/smush-isotipo.svg", width=size, height=size,
                        error_content=ft.Icon(icon=ft.Icons.COMPRESS, size=size - 2, color=INK))
    return ft.Icon(icon=ft.Icons.COMPRESS, size=size - 2, color=INK)


# ---- Filas de alto nivel (reutilizables) ----
def result_row(app, i: int, r: CompressRow) -> ft.Container:  # noqa: ANN001
    from ..helpers import human_size

    badge = ft.Container(
        bgcolor=LIME,
        border=ft.Border.all(width=2, color=INK),
        border_radius=20,
        padding=ft.Padding(left=10, top=4, right=10, bottom=4),
        content=mono_text(value=f"{r['percent_of_original']}%", size=12.5, color=INK,
                          weight=ft.FontWeight.W_700),
    )
    sizes = ft.Text(
        spans=[
            ft.TextSpan(text=human_size(num_bytes=r["original_size"])),
            ft.TextSpan(text=" → "),
            ft.TextSpan(text=human_size(num_bytes=r["new_size"]),
                        style=ft.TextStyle(weight=ft.FontWeight.W_700, color=INK)),
        ],
        size=12,
        color=INK_SOFT,
        font_family=FONT_MONO or None,
    )
    note: ft.Text = mono_text(
        value=f"calidad {r['quality']} — {r['note']}" if r.get("note") else f"calidad {r['quality']}",
        size=11,
        color=CORAL if not r.get("quality_acceptable", True) else INK_SOFT,
        weight=ft.FontWeight.W_600 if not r.get("quality_acceptable", True) else ft.FontWeight.W_400,
    )
    controls: list[ft.Control] = [
        meta_column(name=r["filename"], sub=ft.Column(spacing=0, controls=[sizes, note])),
        badge,
    ]
    psnr: float | None = r.get("psnr_db")
    if psnr is not None:
        low_quality: bool = not r.get("quality_acceptable", True)
        controls.append(
            ft.Container(
                bgcolor=SURFACE,
                border=ft.Border.all(width=2, color=CORAL if low_quality else INK),
                border_radius=20,
                padding=ft.Padding(left=10, top=4, right=10, bottom=4),
                tooltip="PSNR estimado vs el original (más alto = más fiel)",
                content=mono_text(
                    value=f"{round(psnr, 1)} dB",
                    size=12.5,
                    color=CORAL if low_quality else INK,
                    weight=ft.FontWeight.W_700,
                ),
            )
        )
    save_btn: ft.Container = neo_button(label="Guardar", bgcolor=BLUE, color="#fdfcf6", border_width=2, shadow_offset=(2, 2))
    save_btn.on_click = app.make_save_handler(r)
    controls.append(save_btn)
    return row_shell(i, controls=controls)


def error_row(i: int, filename: str, error: str) -> ft.Container:
    return row_shell(
        i,
        controls=[ft.Icon(icon=ft.Icons.ERROR_OUTLINE, size=22, color=CORAL),
         meta_column(name=filename,
                      sub=ft.Text(value=error, size=13, weight=ft.FontWeight.W_600, color=CORAL))],
    )


def convert_result_row(app, i: int, r: ConvertRow) -> ft.Container:  # noqa: ANN001
    """Fila de un archivo convertido: badge del formato destino + guardar."""
    from ..helpers import human_size

    badge = ft.Container(
        bgcolor=LIME,
        border=ft.Border.all(width=2, color=INK),
        border_radius=20,
        padding=ft.Padding(left=10, top=4, right=10, bottom=4),
        content=mono_text(value=f".{r['target_format'].lower()}", size=12.5, color=INK,
                          weight=ft.FontWeight.W_700),
    )
    sizes = ft.Text(
        spans=[
            ft.TextSpan(text=human_size(num_bytes=r["original_size"])),
            ft.TextSpan(text=" → "),
            ft.TextSpan(text=human_size(num_bytes=r["new_size"]),
                        style=ft.TextStyle(weight=ft.FontWeight.W_700, color=INK)),
        ],
        size=12,
        color=INK_SOFT,
        font_family=FONT_MONO or None,
    )
    detail: str = f"calidad {r['quality']}" if r.get("quality") else "sin pérdida"
    if r.get("note"):
        detail = f"{detail} — {r['note']}"
    save_btn: ft.Container = neo_button(label="Guardar", bgcolor=BLUE, color="#fdfcf6", border_width=2, shadow_offset=(2, 2))
    save_btn.on_click = app.make_save_handler(r)
    return row_shell(
        i,
        controls=[meta_column(name=r["filename"], sub=ft.Column(spacing=0, controls=[sizes, mono_text(value=detail, size=11)])),
         badge, save_btn],
    )


def pending_row(i: int, path, remove_cb) -> ft.Container:  # noqa: ANN001
    from ..helpers import human_size

    remove_btn = ft.Container(
        width=26, height=26, bgcolor=SURFACE,
        border=ft.Border.all(width=2, color=INK), border_radius=999,
        alignment=ft.Alignment.CENTER,
        on_click=lambda _e: remove_cb(i),
        content=ft.Icon(icon=ft.Icons.CLOSE, size=13, color=INK),
    )
    return row_shell(
        i,
        controls=[thumb_control(path),
         meta_column(name=Path(path).name, sub=mono_text(value=human_size(num_bytes=Path(path).stat().st_size))),
         remove_btn],
    )
