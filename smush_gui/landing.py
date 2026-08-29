"""
Vista de landing — replica el diseño de la landing web original.
Solo construye el árbol de controles; la navegación y la animación del
squash las maneja el controlador (app.py) mediante callbacks.
"""
from __future__ import annotations

import time

import flet as ft

from .components.cards import feature_card, step_card
from .components.primitives import (
    chip,
    format_badge,
    isotipo,
    nav_link,
    section_head,
    sticker,
)
from .helpers import ASSETS
from .theme import (
    ACCEPTED,
    BLUE,
    BW,
    CORAL,
    INK,
    INK_SOFT,
    LIME,
    LIME_DARK,
    RADIUS,
    SURFACE,
    FONT_DISPLAY,
    mono_text,
    neo_button,
)


def build_landing(app) -> ft.Control:  # noqa: ANN001
    """
    Construye y retorna la vista de landing completa.
    ``app`` es el controlador SmushApp (necesita: landing_col, hero_shape,
    go_tool, scroll_landing).
    """
    nav = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        wrap=True,
        spacing=16,
        controls=[
            ft.Row(spacing=10, controls=[
                isotipo(38, 38),
                ft.Text("Smush", size=22, weight=ft.FontWeight.W_900, color=INK,
                        font_family=FONT_DISPLAY or None),
            ]),
            ft.Row(
                spacing=26,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    nav_link(app, "Qué hace", "features"),
                    nav_link(app, "Cómo funciona", "how"),
                    neo_button("Comprimir ahora", LIME, INK, on_click=app.go_tool),
                ],
            ),
        ],
    )

    h1_line2 = ft.Row(
        spacing=12,
        wrap=True,
        controls=[
            ft.Text("Dejá", size=46, weight=ft.FontWeight.W_900, color=INK,
                    font_family=FONT_DISPLAY or None),
            ft.Container(
                bgcolor=CORAL,
                border=ft.Border.all(BW, INK),
                border_radius=8,
                rotate=ft.Rotate(-0.035),
                shadow=ft.BoxShadow(offset=ft.Offset(4, 4), blur_radius=0, color=INK),
                padding=ft.Padding(10, 0, 10, 4),
                content=ft.Text("la imagen", size=46, weight=ft.FontWeight.W_900,
                                italic=True, color=INK, font_family=FONT_DISPLAY or None),
            ),
            ft.Text("intacta.", size=46, weight=ft.FontWeight.W_900, color=INK,
                    font_family=FONT_DISPLAY or None),
        ],
    )

    hero_copy = ft.Column(
        spacing=0,
        controls=[
            chip("100% en tu máquina · sin cuentas"),
            ft.Container(height=18),
            ft.Text("Achicá el peso.", size=46, weight=ft.FontWeight.W_900, color=INK,
                    font_family=FONT_DISPLAY or None),
            ft.Container(height=6),
            h1_line2,
            ft.Container(height=20),
            ft.Container(
                content=ft.Text(
                    "Elegí tus fotos, decidí cuánto querés apretar y listo. Smush le saca "
                    "el peso de más a tus AVIF, WEBP, JPEG y PNG sin que se note.",
                    size=17,
                    color=INK_SOFT,
                ),
            ),
            ft.Container(height=26),
            ft.Row(
                wrap=True,
                spacing=14,
                controls=[
                    neo_button("Comprimir mis imágenes", LIME, INK, on_click=app.go_tool),
                    neo_button(
                        "Ver cómo funciona", SURFACE, INK,
                        on_click=lambda _e: app.page.run_task(app.scroll_landing, "how"),
                    ),
                ],
            ),
            ft.Container(height=26),
            ft.Row(
                spacing=10,
                wrap=True,
                controls=[format_badge(ext) for ext in ACCEPTED],
            ),
        ],
    )

    app.hero_shape = ft.Image(
        src="img/smush-isotipo.svg" if (ASSETS / "img" / "smush-isotipo.svg").exists() else "",
        width=160,
        height=160,
        animate_scale=ft.Animation(450, ft.AnimationCurve.EASE_OUT_BACK),
        error_content=ft.Icon(ft.Icons.COMPRESS, size=110, color=INK),
    )
    stage = ft.Container(
        width=340,
        height=340,
        bgcolor=SURFACE,
        border=ft.Border.all(BW, INK),
        border_radius=24,
        shadow=ft.BoxShadow(offset=ft.Offset(8, 8), blur_radius=0, color=INK),
        alignment=ft.Alignment.CENTER,
        content=app.hero_shape,
    )

    hero_visual = ft.Stack(
        [
            stage,
            sticker(".jpg", LIME, INK, (14, 27), -0.105),
            sticker(".png", SURFACE, INK, (250, 48), 0.087),
            sticker(".webp", BLUE, "#ffffff", (0, 250), 0.07),
            sticker(".avif", CORAL, "#ffffff", (268, 272), -0.087),
        ],
        width=340,
        height=340,
    )

    hero_section = ft.Row(
        wrap=True,
        spacing=40,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[hero_copy, hero_visual],
    )

    trust = ft.Container(
        padding=ft.Padding(0, 10, 0, 40),
        content=ft.Row(
            wrap=True,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
            controls=[
                chip("sin límite de imágenes por tanda"),
                chip("se procesa todo en tu máquina"),
                chip("no hace falta instalar nada"),
            ],
        ),
    )

    # FIX scroll: ListView + Row wrap (ancho fijo) es la única que da
    # top correcto y "how"/CTA/footer visibles. Column recortaba top,
    # ResponsiveRow no calculaba altura y ScrollKey quedaba en top.
    _lv_h = getattr(app.page, "height", None) or getattr(app.page.window, "height", 800) or 800
    if not _lv_h or _lv_h < 400:
        _lv_h = 700
    app.landing_col = ft.ListView(
        expand=True,
        height=_lv_h,
        spacing=0,
        padding=ft.Padding(0, 0, 0, 0),
        auto_scroll=False,
        build_controls_on_demand=False,
        clip_behavior=ft.ClipBehavior.NONE,
        controls=[
            ft.Container(
                padding=ft.Padding(28, 22, 28, 0),
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[nav],
                ),
            ),
            ft.Container(
                padding=ft.Padding(28, 40, 28, 60),
                alignment=ft.Alignment.CENTER,
                key=ft.ScrollKey("top"),
                content=hero_section,
            ),
            ft.Container(
                padding=ft.Padding(28, 0, 28, 0),
                alignment=ft.Alignment.CENTER,
                content=trust,
            ),
            ft.Container(
                key=ft.ScrollKey("features"),
                padding=ft.Padding(28, 20, 28, 20),
                alignment=ft.Alignment.CENTER,
                content=_features(),
            ),
            ft.Container(
                key=ft.ScrollKey("how"),
                padding=ft.Padding(28, 40, 28, 40),
                alignment=ft.Alignment.CENTER,
                content=_how(),
            ),
            ft.Container(
                padding=ft.Padding(28, 10, 28, 50),
                alignment=ft.Alignment.CENTER,
                content=_cta(app),
            ),
            ft.Container(
                padding=ft.Padding(28, 0, 28, 30),
                alignment=ft.Alignment.CENTER,
                content=_foot(),
            ),
        ],
    )
    return app.landing_col


def _features() -> ft.Control:
    data = [
        (ft.Icons.UPLOAD_FILE, "Arrastrar y listo",
         "Cargá una imagen o cien a la vez. Smush arma la lista y te muestra el peso de cada una al instante."),
        (ft.Icons.TUNE, "Vos elegís el punto justo",
         "Un control simple para definir cuánto querés comprimir — más liviano o más fiel al original, a tu gusto."),
        (ft.Icons.FILE_COPY, "Por lote",
         "Comprimí toda la tanda de una sola vez y guardá cada resultado suelto o todo junto en un .zip."),
        (ft.Icons.SHIELD, "Nada se queda guardado",
         "Las imágenes se procesan en tu propia máquina: no se suben a ningún servidor."),
    ]
    cards: list[ft.Control] = [feature_card(i, *item) for i, item in enumerate(data)]
    for c in cards:
        c.width = 520  # type: ignore[attr-defined]
    return ft.Container(
        width=1100,
        content=ft.Column(
            spacing=44,
            controls=[
                section_head("Qué hace", "Todo lo que necesitás, nada de lo que sobra"),
                ft.Row(
                    wrap=True,
                    spacing=20,
                    run_spacing=20,
                    controls=cards,
                ),
            ],
        ),
    )


def _how() -> ft.Control:
    step_cards: list[ft.Control] = [
        step_card(1, "Elegí tus imágenes",
                   "Abrilas desde el botón de carga. AVIF, WEBP, JPEG y PNG."),
        step_card(2, "Ajustá el objetivo",
                   "Movés el control hasta encontrar el balance entre peso final y calidad que te sirve."),
        step_card(3, "Guardá el resultado",
                   "Guardá cada imagen comprimida por separado o todo el lote junto en un .zip."),
    ]
    for c in step_cards:
        c.width = 340  # type: ignore[attr-defined]
    return ft.Container(
        width=1100,
        content=ft.Column(
            spacing=44,
            controls=[
                section_head("Cómo funciona", "Tres pasos, cero vueltas"),
                ft.Row(
                    wrap=True,
                    spacing=22,
                    run_spacing=22,
                    controls=step_cards,
                ),
            ],
        ),
    )


def _cta(app) -> ft.Control:  # noqa: ANN001
    btn = neo_button("Empezar a comprimir", LIME, INK, on_click=app.go_tool)
    btn.shadow = ft.BoxShadow(offset=ft.Offset(4, 4), blur_radius=0, color=LIME_DARK)
    return ft.Container(
        bgcolor=INK,
        border=ft.Border.all(BW, INK),
        border_radius=RADIUS,
        shadow=ft.BoxShadow(offset=ft.Offset(6, 6), blur_radius=0, color=INK),
        padding=ft.Padding(32, 48, 32, 48),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Dejá de subir fotos de 8MB por ahí.", size=34,
                        weight=ft.FontWeight.W_800, color=SURFACE,
                        font_family=FONT_DISPLAY or None, text_align=ft.TextAlign.CENTER),
                ft.Container(height=12),
                mono_text("Es gratis y corre entero en tu máquina.", size=15.5, color="#cfcdbe"),
                ft.Container(height=26),
                btn,
            ],
        ),
    )


def _foot() -> ft.Control:
    year = time.strftime("%Y")
    return ft.Container(
        border=ft.Border.only(top=ft.BorderSide(2, INK)),
        padding=ft.Padding(0, 30, 0, 20),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            spacing=16,
            controls=[
                ft.Row(spacing=8, controls=[
                    isotipo(22, 22),
                    mono_text("Smush — achica el peso, no la imagen", size=12.5),
                ]),
                mono_text(f"© {year} Smush", size=12.5),
            ],
        ),
    )
