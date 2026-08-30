"""
Controlador principal de la interfaz Flet de Smush.
Compone el fondo (dots + blobs), la landing y la herramienta, maneja la
navegación entre ambas y orquesta la compresión / guardado de resultados.
"""
from __future__ import annotations

import asyncio
import shutil
import uuid
import zipfile
from pathlib import Path

import flet as ft
import flet.canvas as cv

from .helpers import ASSETS, BASE_TMP, cleanup_old_jobs, ensure_assets, ext_of, register_fonts, squeeze_shapes
from .landing import build_landing
from .theme import ACCEPTED, BG
from .tool import build_tool, error_row, pending_row, result_row

from compressor_core import UnsupportedFormatError, compress_to_target


class SmushApp:
    # Estado del controlador
    page: ft.Page
    pending: list[Path]
    results: list[dict]
    compressing: bool

    # Vistas (asignadas en _build)
    tool_view: ft.Control
    landing_view: ft.Control

    # Atributos de la herramienta (asignados por build_tool)
    config_panel: ft.Container
    list_panel: ft.Container
    results_panel: ft.Container
    compress_btn: ft.Container
    zip_btn: ft.Container
    slider: ft.Slider
    ratio_readout: ft.Text
    squeeze_canvas: cv.Canvas
    file_list_col: ft.Column
    result_col: ft.Column
    main_column: ft.Column

    # Atributos de la landing (asignados por build_landing)
    landing_col: ft.ListView
    hero_shape: ft.Image

    def __init__(self, page: ft.Page):
        self.page = page
        self.pending = []
        self.results = []
        self.compressing = False

        ensure_assets()
        register_fonts(page)

        page.title = "Smush — compresor de imágenes"
        page.bgcolor = BG
        page.padding = 0
        page.scroll = None
        # Abrir maximizado (respeta la barra de tareas, a diferencia de full_screen).
        page.window.maximized = True
        page.window.width = 1280
        page.window.height = 800
        # Ícono de ventana (barra de título y barra de tareas).
        icon_ico = ASSETS / "img" / "favicon.ico"
        if icon_ico.exists():
            page.window.icon = str(icon_ico)

        self._build()

    # ---------------- Ensamblado ----------------
    def _build(self) -> None:
        background_dots = ft.Container(
            expand=True,
            image=ft.DecorationImage(src="dots-tile.png", repeat=ft.ImageRepeat.REPEAT),
        )

        blob_lime = _blob(size=360, right=-120, top=-120, colors=["#8cc6ff5e", "#00c6ff5e"])
        blob_coral = _blob(size=300, left=-100, bottom=-100, colors=["#59ff5d45", "#00ff5d45"])
        blob_blue = _blob(size=300, right=-120, bottom=260, colors=["#384f6dff", "#004f6dff"])

        # Vista de la herramienta (oculta al inicio) y landing (visible).
        self.tool_view = build_tool(self)  # noqa: (asigna panels/atributos)
        self.tool_view.visible = False
        self.landing_view = build_landing(self)
        self.landing_view.visible = True

        stack = ft.Stack(
            [
                background_dots,
                blob_lime,
                blob_coral,
                blob_blue,
                self.tool_view,
                self.landing_view,
            ],
            expand=True,
            fit=ft.StackFit.EXPAND,
            clip_behavior=ft.ClipBehavior.NONE,
        )
        self.page.add(stack)

        self.config_panel.visible = False
        self.list_panel.visible = False
        self.results_panel.visible = False
        # Altura acotada para ListView/Column dentro de Stack: sin esto el scroll se recorta.
        try:
            _h = self.page.height or self.page.window.height or 700
            if _h and _h > 100:
                self.landing_col.height = _h
                self.main_column.height = _h
        except Exception:
            pass

        def _on_resize(e: ft.WindowResizeEvent) -> None:  # type: ignore
            try:
                h = getattr(e, "height", None) or self.page.window.height or self.page.height
                if h and h > 100:
                    self.landing_col.height = h
                    self.main_column.height = h
                    self.page.update()
            except Exception:
                pass

        self.page.on_resized = _on_resize  # type: ignore[assignment]
        self.page.update()
        self.page.run_task(self._squish_loop)

    # ---------------- Navegación ----------------
    def go_tool(self, _e=None) -> None:
        self.landing_view.visible = False
        self.tool_view.visible = True
        self.page.update()

    def go_landing(self, _e=None) -> None:
        self.tool_view.visible = False
        self.landing_view.visible = True
        self.page.run_task(self._reset_landing_scroll)

    async def scroll_landing(self, key: str) -> None:
        # ScrollKey no era fiable dentro de ListView+Row (a veces no scrolleaba).
        # Usamos offsets calculados: hero ~0, features ~900, how ~1500.
        offsets = {"top": 0, "features": 850, "how": 1450}
        if key in offsets:
            await self.landing_col.scroll_to(offset=offsets[key], duration=450,
                                             curve=ft.AnimationCurve.EASE_OUT_CUBIC)
        else:
            await self.landing_col.scroll_to(scroll_key=ft.ScrollKey(key), duration=450,
                                             curve=ft.AnimationCurve.EASE_OUT_CUBIC)

    async def _reset_landing_scroll(self) -> None:
        await self.landing_col.scroll_to(offset=0, duration=200)

    # ---------------- Animación del hero ----------------
    async def _squish_loop(self) -> None:
        while True:
            await asyncio.sleep(1.8)
            if not getattr(self, "hero_shape", None) or not self.landing_view.visible:
                continue
            try:
                self.hero_shape.scale = ft.Scale(scale_x=1.14, scale_y=0.82)
                self.hero_shape.update()
                await asyncio.sleep(0.7)
                self.hero_shape.scale = ft.Scale(scale_x=0.96, scale_y=1.05)
                self.hero_shape.update()
                await asyncio.sleep(0.35)
                self.hero_shape.scale = ft.Scale()
                self.hero_shape.update()
            except RuntimeError:
                continue

    # ---------------- Eventos de la herramienta ----------------
    async def pick_files(self, _e) -> None:
        picker = ft.FilePicker()
        files = await picker.pick_files(
            dialog_title="Elegí imágenes para comprimir",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=[ext.lstrip(".") for ext in ACCEPTED],
            allow_multiple=True,
        )
        if not files:
            return
        added = 0
        for f in files:
            if not f.path or ext_of(f.name) not in ACCEPTED:
                continue
            path = Path(f.path)
            if path.exists() and path not in self.pending:
                self.pending.append(path)
                added += 1
        if added:
            self.refresh_lists()

    def on_slider_change(self, e) -> None:  # noqa: ANN001
        percent = int(e.control.value)
        self.ratio_readout.value = str(percent)
        self.squeeze_canvas.shapes = squeeze_shapes(percent)
        self.page.update()

    def remove_file(self, index: int, _e=None) -> None:
        if 0 <= index < len(self.pending):
            self.pending.pop(index)
            self.refresh_lists()

    def clear_all(self, _e=None) -> None:
        self.pending.clear()
        self.results.clear()
        self.result_col.controls.clear()
        self.zip_btn.visible = False
        self.results_panel.visible = False
        self.refresh_lists()

    # ---------------- Render de listas ----------------
    def refresh_lists(self) -> None:
        self.file_list_col.controls.clear()
        for i, path in enumerate(self.pending):
            self.file_list_col.controls.append(pending_row(i, path, self.remove_file))
        has_files = bool(self.pending)
        self.list_panel.visible = has_files
        self.config_panel.visible = has_files
        if not has_files:
            self.results_panel.visible = False
        self.page.update()

    # ---------------- Compresión ----------------
    async def compress_click(self, _e) -> None:
        if not self.pending or self.compressing:
            return
        self.compressing = True
        self.compress_btn.disabled = True
        self.compress_btn.opacity = 0.55
        _btn_content = self.compress_btn.content
        assert isinstance(_btn_content, ft.Text), "compress_btn content must be Text"
        _btn_content.value = "Comprimiendo…"
        self.page.update()

        _slider_val = self.slider.value
        ratio = int(_slider_val if _slider_val is not None else 50) / 100
        try:
            metas = await asyncio.to_thread(self._compress_sync, ratio)
            self.results = metas
            self.render_results()
        finally:
            self.compressing = False
            self.compress_btn.disabled = False
            self.compress_btn.opacity = 1.0
            _btn_content = self.compress_btn.content
            assert isinstance(_btn_content, ft.Text), "compress_btn content must be Text"
            _btn_content.value = "Comprimir todo"
            self.page.update()

    def _compress_sync(self, ratio: float) -> list[dict]:
        """CPU-bound vía Pillow; corre en un hilo aparte (asyncio.to_thread)."""
        cleanup_old_jobs()
        job_dir = BASE_TMP / uuid.uuid4().hex
        out_dir = job_dir / "out"
        out_dir.mkdir(parents=True)

        results: list[dict] = []
        used_names: set[str] = set()
        for path in self.pending:
            stem, ext = path.stem, path.suffix.lower()
            name = f"{stem}{ext}"
            counter = 1
            while name in used_names or (out_dir / name).exists():
                name = f"{stem}_{counter}{ext}"
                counter += 1
            used_names.add(name)
            out_path = out_dir / name

            try:
                meta = compress_to_target(path, out_path, ratio)
            except UnsupportedFormatError as err:
                results.append({"filename": name, "error": str(err)})
                continue
            except Exception as err:  # noqa: BLE001
                results.append({"filename": name, "error": f"Error al procesar: {err}"})
                continue

            pct = round(meta["new_size"] / meta["original_size"] * 100, 1)
            results.append(
                {
                    "filename": name,
                    "original_size": meta["original_size"],
                    "new_size": meta["new_size"],
                    "percent_of_original": pct,
                    "quality": meta["quality"],
                    "note": meta["note"],
                    "tmp_path": str(out_path),
                }
            )
        return results

    def render_results(self) -> None:
        self.result_col.controls.clear()
        any_ok = False
        for i, r in enumerate(self.results):
            if r.get("error"):
                self.result_col.controls.append(error_row(i, r["filename"], r["error"]))
                continue
            self.result_col.controls.append(result_row(self, i, r))
            any_ok = True
        self.zip_btn.visible = any_ok
        self.results_panel.visible = True
        self.page.update()

    # ---------------- Guardado ----------------
    def make_save_handler(self, result: dict):
        def handler(_e) -> None:
            self.page.run_task(self.save_one, result)

        return handler

    async def save_one(self, result: dict) -> None:
        picker = ft.FilePicker()
        dest = await picker.save_file(dialog_title="Guardar imagen comprimida",
                                      file_name=result["filename"])
        if not dest:
            return
        shutil.copyfile(result["tmp_path"], dest)
        self._snack(f"Guardada: {dest}")

    async def save_zip(self, _e) -> None:
        ok_results = [r for r in self.results if not r.get("error")]
        if not ok_results:
            return
        picker = ft.FilePicker()
        dest = await picker.save_file(dialog_title="Guardar ZIP",
                                      file_name="imagenes_comprimidas.zip")
        if not dest:
            return
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in ok_results:
                zf.write(r["tmp_path"], arcname=r["filename"])
        self._snack(f"ZIP guardado: {dest}")

    def _snack(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message)))


# ------------------------------------------------------------------
# Helpers de módulo
# ------------------------------------------------------------------
def _blob(size: int, colors: list[str], **pos) -> ft.Container:  # noqa: ANN003
    return ft.Container(
        width=size,
        height=size,
        border_radius=999,
        gradient=ft.RadialGradient(colors=colors),
        **pos,
    )


def main(page: ft.Page) -> None:
    SmushApp(page)
