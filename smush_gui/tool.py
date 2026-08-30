"""
Vista de la herramienta — replica el diseño web original en Flet.
Sponsorre: dropzone, slider de objetivo, lista de pendientes, resultados.
El estado y la lógica de compresión viven en el controlador (app.py).
"""
from __future__ import annotations
from typing import Any, Literal

import flet as ft
import flet.canvas as cv

from .components.rows import brand_icon, error_row, pending_row, result_row
from .helpers import squeeze_shapes
from .theme import (
    BLUE,
    BW,
    CORAL,
    FONT_DISPLAY,
    INK,
    INK_SOFT,
    LIME,
    LIME_DARK,
    SURFACE,
    SURFACE_ALT,
    mono_text,
    neo_button,
    neo_panel,
)

# Re-export para compatibilidad: app.py importa desde .tool
__all__: list[str] = ["build_tool", "error_row", "pending_row", "result_row"]


# ---------------- Estado y lógica lived en el controlador ----------------
def build_tool(app) -> ft.Control:  # noqa: ANN001
    """
    Construye la vista de la herramienta completa.
    ``app`` es el controlador SmushApp (necesita: go_landing, pick_files,
    on_slider_change, compress_click, clear_all, refresh_lists, remove_file,
    save_zip, make_save_handler, config_panel, list_panel, results_panel,
    squeeze_canvas, ratio_readout, slider, compress_btn, file_list_col,
    results_col, zip_btn).
    """
    app.ratio_readout = mono_text(value="50", size=14, color=INK, weight=ft.FontWeight.W_500)
    ratio_badge = ft.Container(
        bgcolor=LIME,
        border=ft.Border.all(width=2, color=INK),
        border_radius=8,
        padding=ft.Padding(left=8, top=1, right=8, bottom=1),
        content=app.ratio_readout,
    )
    app.squeeze_canvas = cv.Canvas(width=160, height=44, shapes=squeeze_shapes(percent=50))

    app.compress_btn = neo_button(label="Comprimir todo", bgcolor=LIME, color=INK, on_click=app.compress_click)
    clear_btn: ft.Container = neo_button(
        label="Vaciar lista", bgcolor=SURFACE, color=INK_SOFT, border_width=2, shadow_offset=(0, 0),
        on_click=app.clear_all,
    )

    app.slider = ft.Slider(
        min=10,
        max=90,
        divisions=16,
        value=50,
        label="{value}%",
        active_color=CORAL,
        inactive_color=SURFACE_ALT,
        on_change=app.on_slider_change,
    )
    label_row = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ft.Text(value="Tamaño objetivo", size=16, weight=ft.FontWeight.W_700, color=INK,
                    font_family=FONT_DISPLAY or None),
            ratio_badge,
        ],
    )
    hint: ft.Text = mono_text(value="del peso original — misma resolución, menor calidad de compresión")

    app.config_panel = neo_panel(
        content=ft.Column(
            spacing=12,
            controls=[
                label_row,
                app.slider,
                hint,
                ft.Container(
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding(left=0, top=8, right=0, bottom=0),
                    content=app.squeeze_canvas,
                ),
                ft.Row(spacing=12, controls=[app.compress_btn, clear_btn]),
            ],
        ),
    )

    # ---- Dropzone — panel = área arrastrable (cuadro centrado) ----
    app.dropzone_icon = ft.Icon(icon=ft.Icons.UPLOAD, size=38, color=INK_SOFT)
    app.dropzone_sub = mono_text(value="o hacé clic para elegirlas — AVIF, WEBP, JPEG, PNG", size=13)
    dropzone_content = ft.Column(
        spacing=8,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            app.dropzone_icon,
            ft.Text(value="Arrastrá imágenes acá", size=20, weight=ft.FontWeight.W_700,
                    color=INK, font_family=FONT_DISPLAY or None, text_align=ft.TextAlign.CENTER),
            ft.Container(height=4),
            app.dropzone_sub,
        ],
    )
    # El neo_panel ES el cuadro: compacto (260) para que entren controles sin scrollear
    dropzone: ft.Container = neo_panel(content=dropzone_content)
    dropzone.width = 260
    dropzone.height = 260
    dropzone.alignment = ft.Alignment.CENTER
    dropzone.on_click = app.pick_files
    # Borde inicial suave, hover lo oscurece
    dropzone.border = ft.Border.all(width=BW, color=INK_SOFT)

    def handle_hover(e: ft.Event) -> None:
        hovered = bool(e.data)
        dropzone.border = ft.Border.all(width=BW, color=LIME_DARK if hovered else INK_SOFT)
        new_color: Literal['#17170f'] | Literal['#5a5847'] = INK if hovered else INK_SOFT
        app.dropzone_icon.color = new_color
        app.dropzone_sub.color = new_color
        dropzone.update()

    dropzone.on_hover = handle_hover
    # Row centrado para que el panel cuadrado no estire a todo el ancho del ListView
    dropzone_panel = ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        controls=[dropzone],
    )

    # ---- Lista de pendientes / resultados ----
    app.file_list_col = ft.Column(spacing=12)
    list_panel: ft.Container = neo_panel(content=app.file_list_col)

    app.result_col = ft.Column(spacing=12)
    app.zip_btn = neo_button(label="Guardar todo (.zip)", bgcolor=BLUE, color="#fdfcf6", on_click=app.save_zip)
    app.zip_btn.visible = False
    title = ft.Text(value="Resultado", size=20, weight=ft.FontWeight.W_800, color=INK,
                    font_family=FONT_DISPLAY or None)
    results_panel: ft.Container = neo_panel(
        content=ft.Column(
            spacing=16,
            controls=[
                ft.Row(wrap=True, alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                       controls=[title, app.zip_btn]),
                app.result_col,
            ],
        ),
    )

    # ---- Topbar ----
    brand_mark = ft.Container(
        width=40,
        height=40,
        bgcolor=LIME,
        border=ft.Border.all(width=BW, color=INK),
        border_radius=999,
        alignment=ft.Alignment.CENTER,
        shadow=ft.BoxShadow(offset=ft.Offset(x=3, y=3), blur_radius=0, color=INK),
        content=brand_icon(size=22),
    )
    brand_name = ft.Text(value="Smush", size=30, weight=ft.FontWeight.W_900, color=INK,
                         font_family=FONT_DISPLAY or None)
    brand = ft.Container(on_click=app.go_landing,
                         content=ft.Row(spacing=10, controls=[brand_mark, brand_name]))
    back_btn: ft.Container = neo_button(
        label="← Volver al inicio",
        bgcolor=SURFACE,
        color=INK,
        on_click=app.go_landing,
        border_width=2,
        shadow_offset=(2, 2),
    )
    tagline = ft.Container(
        bgcolor=SURFACE,
        border=ft.Border.all(width=2, color=INK),
        border_radius=20,
        rotate=ft.Rotate(angle=-0.035),
        padding=ft.Padding(left=14, top=6, right=14, bottom=6),
        content=mono_text(value="achica el peso, no la imagen", size=12.5, color=INK),
    )
    topbar = ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True,
                    controls=[brand, tagline, back_btn])
    footer = ft.Container(
        alignment=ft.Alignment.CENTER,
        content=mono_text(value="Las imágenes se procesan en tu máquina y se guardan solo donde elijas."),
    )

    # Column scrolleable necesita altura acotada (docs: height + width + scroll).
    # Altura = ventana - padding (70+40) para que quepa sin recorte y el slider se vea.
    _h: Any | int = getattr(app.page, "height", None) or getattr(app.page.window, "height", 700) or 700
    _h = max(380, int(_h * 0.85))  # 85% de la ventana, deja ver controles sin scrollear
    app.main_column = ft.Column(
        spacing=26,
        height=_h,
        width=float("inf"),
        scroll=ft.ScrollMode.ALWAYS,
        expand=True,
        controls=[topbar, dropzone_panel, app.config_panel, list_panel,
                  results_panel, footer],
    )

    app.list_panel = list_panel
    app.results_panel = results_panel

    return ft.Container(
        expand=True,
        clip_behavior=ft.ClipBehavior.NONE,
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            expand=True,
            clip_behavior=ft.ClipBehavior.NONE,
            padding=ft.Padding(left=24, top=40, right=24, bottom=70),
            content=app.main_column,
        ),
    )
