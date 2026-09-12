"""
Vista de la herramienta — replica el diseño web original en Flet.
Sponsorre: dropzone, slider de objetivo, lista de pendientes, resultados.
El estado y la lógica de compresión viven en el controlador (app.py).
"""
from __future__ import annotations

from typing import Any, Literal

import flet as ft
import flet.canvas as cv

from .components.rows import (
    brand_icon,
    convert_result_row,
    error_row,
    pending_row,
    result_row,
)
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
    is_hovered,
    mono_text,
    neo_button,
    neo_panel,
)

# Re-export para compatibilidad: app.py importa desde .tool
__all__: list[str] = ["build_tool", "convert_result_row", "error_row", "pending_row", "result_row"]


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
        hovered: bool = is_hovered(data=e.data)
        dropzone.border = ft.Border.all(width=BW, color=LIME_DARK if hovered else INK_SOFT)
        new_color: Literal['#17170f'] | Literal['#5a5847'] = INK if hovered else INK_SOFT
        app.dropzone_icon.color = new_color
        app.dropzone_sub.color = new_color
        dropzone.update()

    dropzone.on_hover = handle_hover

    # ---- Conversión de formato: dropzone + destino + calidad ----
    app.convert_dropzone_icon = ft.Icon(icon=ft.Icons.TRANSFORM, size=38, color=INK_SOFT)
    app.convert_dropzone_sub = mono_text(value="o hacé clic para elegirlas — se convierten al formato de al lado", size=13)
    convert_dropzone_content = ft.Column(
        spacing=8,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            app.convert_dropzone_icon,
            ft.Text(value="Convertir formato", size=20, weight=ft.FontWeight.W_700,
                    color=INK, font_family=FONT_DISPLAY or None, text_align=ft.TextAlign.CENTER),
            ft.Container(height=4),
            app.convert_dropzone_sub,
        ],
    )
    convert_dropzone: ft.Container = neo_panel(content=convert_dropzone_content)
    convert_dropzone.width = 260
    convert_dropzone.height = 260
    convert_dropzone.alignment = ft.Alignment.CENTER
    convert_dropzone.on_click = app.pick_convert_files
    convert_dropzone.border = ft.Border.all(width=BW, color=INK_SOFT)

    def handle_convert_hover(e: ft.Event) -> None:
        hovered: bool = is_hovered(data=e.data)
        convert_dropzone.border = ft.Border.all(width=BW, color=LIME_DARK if hovered else INK_SOFT)
        convert_color: Literal['#17170f'] | Literal['#5a5847'] = INK if hovered else INK_SOFT
        app.convert_dropzone_icon.color = convert_color
        app.convert_dropzone_sub.color = convert_color
        convert_dropzone.update()

    convert_dropzone.on_hover = handle_convert_hover
    app.convert_dropzone = convert_dropzone

    # Chips de formato destino (selección única, default WEBP).
    app.convert_chips = {}
    format_chips = ft.Row(
        spacing=8,
        wrap=True,
        alignment=ft.MainAxisAlignment.CENTER,
        controls=[],
    )
    for _fmt in ("AVIF", "WEBP", "JPEG", "PNG"):
        _chip = ft.Container(
            content=mono_text(value=f".{_fmt.lower()}", size=12.5, color=INK,
                              weight=ft.FontWeight.W_700),
            bgcolor=SURFACE,
            border=ft.Border.all(width=2, color=INK),
            border_radius=20,
            padding=ft.Padding(left=12, top=6, right=12, bottom=6),
            on_click=lambda _e, f=_fmt: app.set_convert_target(f),
        )
        app.convert_chips[_fmt] = _chip
        format_chips.controls.append(_chip)

    app.convert_quality_readout = mono_text(value="85", size=14, color=INK, weight=ft.FontWeight.W_500)
    convert_quality_badge = ft.Container(
        bgcolor=LIME,
        border=ft.Border.all(width=2, color=INK),
        border_radius=8,
        padding=ft.Padding(left=8, top=1, right=8, bottom=1),
        content=app.convert_quality_readout,
    )
    app.convert_slider = ft.Slider(
        min=10,
        max=100,
        divisions=18,
        value=85,
        label="{value}%",
        active_color=BLUE,
        inactive_color=SURFACE_ALT,
        on_change=app.on_convert_quality_change,
    )
    app.convert_size_readout = mono_text(value="100", size=14, color=INK, weight=ft.FontWeight.W_500)
    convert_size_badge = ft.Container(
        bgcolor=LIME,
        border=ft.Border.all(width=2, color=INK),
        border_radius=8,
        padding=ft.Padding(left=8, top=1, right=8, bottom=1),
        content=app.convert_size_readout,
    )
    app.convert_size_slider = ft.Slider(
        min=10,
        max=100,
        divisions=18,
        value=100,
        label="{value}%",
        active_color=CORAL,
        inactive_color=SURFACE_ALT,
        on_change=app.on_convert_size_change,
    )
    app.convert_btn = neo_button(label="Convertir", bgcolor=BLUE, color="#fdfcf6", on_click=app.convert_click)
    clear_convert_btn: ft.Container = neo_button(
        label="Vaciar", bgcolor=SURFACE, color=INK_SOFT, border_width=2, shadow_offset=(0, 0),
        on_click=app.clear_convert,
    )
    convert_card: ft.Container = neo_panel(
        content=ft.Column(
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(value="Destino", size=16, weight=ft.FontWeight.W_700, color=INK,
                        font_family=FONT_DISPLAY or None),
                format_chips,
                ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                       controls=[
                           mono_text(value="Calidad"),
                           convert_quality_badge,
                       ]),
                app.convert_slider,
                ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                       controls=[
                           mono_text(value="Peso máx."),
                           convert_size_badge,
                       ]),
                app.convert_size_slider,
                mono_text(value="100% = que no pese más que el original", size=11),
                ft.Row(spacing=12, alignment=ft.MainAxisAlignment.CENTER,
                       controls=[app.convert_btn, clear_convert_btn]),
            ],
        ),
    )
    app.convert_card = convert_card

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

    # ---- Pendientes / resultados de conversión ----
    app.convert_file_col = ft.Column(spacing=12)
    convert_list_panel: ft.Container = neo_panel(content=app.convert_file_col)

    app.convert_result_col = ft.Column(spacing=12)
    convert_title = ft.Text(value="Convertidos", size=20, weight=ft.FontWeight.W_800, color=INK,
                            font_family=FONT_DISPLAY or None)
    convert_results_panel: ft.Container = neo_panel(
        content=ft.Column(
            spacing=16,
            controls=[convert_title, app.convert_result_col],
        ),
    )

    # ---- Layout: cada flujo autocontenido en su columna ----
    # Compresión a la izquierda (upload + config + listas), conversión a la
    # derecha. Lado a lado en desktop (lg), apilados en mobile (sm).
    flows_row = ft.Container(
        content=ft.ResponsiveRow(
            spacing=20,
            run_spacing=20,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(
                    col={"sm": 12, "lg": 6},
                    content=ft.Column(
                        spacing=26,
                        controls=[
                            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[dropzone]),
                            app.config_panel,
                            list_panel,
                            results_panel,
                        ],
                    ),
                ),
                ft.Container(
                    col={"sm": 12, "lg": 6},
                    content=ft.Column(
                        spacing=26,
                        controls=[
                            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[convert_dropzone]),
                            convert_card,
                            convert_list_panel,
                            convert_results_panel,
                        ],
                    ),
                ),
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
        controls=[topbar, flows_row, footer],
    )

    app.list_panel = list_panel
    app.results_panel = results_panel
    app.convert_list_panel = convert_list_panel
    app.convert_results_panel = convert_results_panel

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
