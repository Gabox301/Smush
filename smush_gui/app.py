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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import flet as ft
import flet.canvas as cv

from compressor_core import (
    TARGET_FORMAT_TO_EXTENSION,
    CompressResult,
    CompressRow,
    ConvertResult,
    ConvertRow,
    UnsupportedFormatError,
    compress_to_target,
    convert_format,
    is_compress_error,
    is_compress_ok,
    is_convert_error,
    is_convert_ok,
)

from .helpers import (
    ASSETS,
    BASE_TMP,
    cleanup_old_jobs,
    ensure_assets,
    ext_of,
    register_fonts,
    squeeze_shapes,
)
from .landing import build_landing
from .theme import ACCEPTED, BG, BW, INK, LIME, SURFACE
from .tool import build_tool, convert_result_row, error_row, pending_row, result_row


class SmushApp:
    # Estado del controlador
    page: ft.Page
    pending: list[Path]
    results: list[CompressResult]
    compressing: bool
    pending_convert: list[Path]
    convert_results: list[ConvertResult]
    converting: bool
    convert_target: str

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

    # Atributos de conversión (asignados por build_tool)
    convert_card: ft.Container
    convert_list_panel: ft.Container
    convert_results_panel: ft.Container
    convert_btn: ft.Container
    convert_slider: ft.Slider
    convert_quality_readout: ft.Text
    convert_size_slider: ft.Slider
    convert_size_readout: ft.Text
    convert_file_col: ft.Column
    convert_result_col: ft.Column
    convert_chips: dict[str, ft.Container]
    convert_dropzone: ft.Container

    # Atributos de la landing (asignados por build_landing)
    landing_col: ft.ListView
    hero_shape: ft.Image

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.pending = []
        self.results = []
        self.compressing = False
        self.pending_convert = []
        self.convert_results = []
        self.converting = False
        self.convert_target = "WEBP"

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
        icon_ico: Path = ASSETS / "img" / "favicon.ico"
        if icon_ico.exists():
            page.window.icon = str(object=icon_ico)

        self._build()

    # ---------------- Ensamblado ----------------
    def _build(self) -> None:
        background_dots = ft.Container(
            expand=True,
            image=ft.DecorationImage(src="dots-tile.png", repeat=ft.ImageRepeat.REPEAT),
        )

        blob_lime: ft.Container = _blob(size=360, right=-120, top=-120, colors=["#8cc6ff5e", "#00c6ff5e"])
        blob_coral: ft.Container = _blob(size=300, left=-100, bottom=-100, colors=["#59ff5d45", "#00ff5d45"])
        blob_blue: ft.Container = _blob(size=300, right=-120, bottom=260, colors=["#384f6dff", "#004f6dff"])

        # Vista de la herramienta (oculta al inicio) y landing (visible).
        self.tool_view = build_tool(app=self)  # asigna panels/atributos
        self.tool_view.visible = False
        self.landing_view = build_landing(app=self)
        self.landing_view.visible = True

        stack = ft.Stack(
            controls=[
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
        self.convert_list_panel.visible = False
        self.convert_results_panel.visible = False
        self.convert_card.visible = False
        self.refresh_convert_chips()
        # Altura acotada para ListView/Column dentro de Stack: sin esto el scroll se recorta.
        # Best-effort: si la página aún no reporta tamaño, se deja el default.
        try:
            _h: int | float = self.page.height or self.page.window.height or 700
            if _h and _h > 100:
                self.landing_col.height = _h
                self.main_column.height = _h
        except Exception:  # noqa: BLE001, S110
            pass

        def _on_resize(e: ft.WindowResizeEvent) -> None:  # type: ignore
            # Best-effort: un resize nunca debe romper la app.
            try:
                h: Any | int | float | None = getattr(e, "height", None) or self.page.window.height or self.page.height
                if h and h > 100:
                    self.landing_col.height = h
                    self.main_column.height = h
                    self.page.update()
            except Exception:  # noqa: BLE001, S110
                pass

        self.page.on_resized = _on_resize  # type: ignore[assignment]
        self.page.update()
        self.page.run_task(handler=self._squish_loop)

    # ---------------- Navegación ----------------
    def go_tool(self, _e: ft.Event | None = None) -> None:
        self.landing_view.visible = False
        self.tool_view.visible = True
        self.page.update()

    def go_landing(self, _e: ft.Event | None = None) -> None:
        self.tool_view.visible = False
        self.landing_view.visible = True
        self.page.run_task(handler=self._reset_landing_scroll)

    async def scroll_landing(self, key: str) -> None:
        # ScrollKey no era fiable dentro de ListView+Row (a veces no scrolleaba).
        # Usamos offsets calculados: hero ~0, features ~900, how ~1500.
        offsets: dict[str, int] = {"top": 0, "features": 850, "how": 1450}
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
            await asyncio.sleep(delay=1.8)
            if not getattr(self, "hero_shape", None) or not self.landing_view.visible:
                continue
            try:
                self.hero_shape.scale = ft.Scale(scale_x=1.14, scale_y=0.82)
                self.hero_shape.update()
                await asyncio.sleep(delay=0.7)
                self.hero_shape.scale = ft.Scale(scale_x=0.96, scale_y=1.05)
                self.hero_shape.update()
                await asyncio.sleep(delay=0.35)
                self.hero_shape.scale = ft.Scale()
                self.hero_shape.update()
            except RuntimeError:
                continue

    # ---------------- Eventos de la herramienta ----------------
    async def _pick_images(self, dialog_title: str, pending: list[Path], refresh: Callable[[], None]) -> None:
        """Selector de archivos genérico: filtra por extensión, evita duplicados."""
        picker = ft.FilePicker()
        files: list[ft.FilePickerFile] = await picker.pick_files(
            dialog_title=dialog_title,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=[ext.lstrip(".") for ext in ACCEPTED],
            allow_multiple=True,
        )
        if not files:
            return
        added = 0
        for f in files:
            if not f.path or ext_of(filename=f.name) not in ACCEPTED:
                continue
            path = Path(f.path)
            if path.exists() and path not in pending:
                pending.append(path)
                added += 1
        if added:
            refresh()

    async def pick_files(self, _e: ft.Event | None) -> None:
        await self._pick_images("Elegí imágenes para comprimir", self.pending, self.refresh_lists)

    @contextmanager
    def _busy_button(self, btn: ft.Container, busy_label: str, idle_label: str) -> Iterator[None]:
        """Deshabilita el botón con etiqueta de progreso y lo restaura al salir."""
        content = btn.content
        assert isinstance(content, ft.Text), "job button content must be Text"
        btn.disabled = True
        btn.opacity = 0.55
        content.value = busy_label
        self.page.update()
        try:
            yield
        finally:
            btn.disabled = False
            btn.opacity = 1.0
            content.value = idle_label
            self.page.update()

    def on_slider_change(self, e) -> None:  # noqa: ANN001
        percent = int(e.control.value)
        self.ratio_readout.value = str(object=percent)
        self.squeeze_canvas.shapes = squeeze_shapes(percent)
        self.page.update()

    def remove_file(self, index: int, _e: ft.Event | None = None) -> None:
        if 0 <= index < len(self.pending):
            self.pending.pop(index)
            self.refresh_lists()

    def clear_all(self, _e: ft.Event | None = None) -> None:
        self.pending.clear()
        self.results.clear()
        self.result_col.controls.clear()
        self.zip_btn.visible = False
        self.results_panel.visible = False
        self.refresh_lists()

    # ---------------- Render de listas ----------------
    def refresh_lists(self) -> None:
        self.file_list_col.controls.clear()
        for i, path in enumerate(iterable=self.pending):
            self.file_list_col.controls.append(pending_row(i, path, remove_cb=self.remove_file))
        has_files = bool(self.pending)
        self.list_panel.visible = has_files
        self.config_panel.visible = has_files
        if not has_files:
            self.results_panel.visible = False
        self.page.update()

    # ---------------- Conversión de formato ----------------
    async def pick_convert_files(self, _e: ft.Event | None) -> None:
        await self._pick_images("Elegí imágenes para convertir", self.pending_convert, self.refresh_convert_lists)

    def set_convert_target(self, fmt: str, _e: ft.Event | None = None) -> None:
        self.convert_target = fmt
        self.refresh_convert_chips()

    def refresh_convert_chips(self) -> None:
        for fmt, chip in self.convert_chips.items():
            selected: bool = fmt == self.convert_target
            chip.bgcolor = LIME if selected else SURFACE
            chip.border = ft.Border.all(width=BW if selected else 2, color=INK)
        try:
            self.page.update()
        except RuntimeError:
            pass

    def on_convert_quality_change(self, e) -> None:  # noqa: ANN001
        self.convert_quality_readout.value = str(object=int(e.control.value))
        self.page.update()

    def on_convert_size_change(self, e) -> None:  # noqa: ANN001
        self.convert_size_readout.value = str(object=int(e.control.value))
        self.page.update()

    def remove_convert_file(self, index: int, _e: ft.Event | None = None) -> None:
        if 0 <= index < len(self.pending_convert):
            self.pending_convert.pop(index)
            self.refresh_convert_lists()

    def clear_convert(self, _e: ft.Event | None = None) -> None:
        self.pending_convert.clear()
        self.convert_results.clear()
        self.convert_result_col.controls.clear()
        self.convert_results_panel.visible = False
        self.refresh_convert_lists()

    def refresh_convert_lists(self) -> None:
        self.convert_file_col.controls.clear()
        for i, path in enumerate(iterable=self.pending_convert):
            self.convert_file_col.controls.append(
                pending_row(i, path, remove_cb=self.remove_convert_file))
        has_files = bool(self.pending_convert)
        self.convert_list_panel.visible = has_files
        self.convert_card.visible = has_files
        if not has_files:
            self.convert_results_panel.visible = False
        self.page.update()

    async def convert_click(self, _e: ft.Event | None) -> None:
        if not self.pending_convert or self.converting:
            return
        self.converting = True
        try:
            with self._busy_button(self.convert_btn, "Convirtiendo…", "Convertir"):
                _quality_val: int | float | None = self.convert_slider.value
                quality: int = int(_quality_val if _quality_val is not None else 85)
                _size_val: int | float | None = self.convert_size_slider.value
                ratio: float = int(_size_val if _size_val is not None else 100) / 100
                metas = await asyncio.to_thread(self._convert_sync, self.convert_target, quality, ratio)
                self.convert_results = metas
                self.render_convert_results()
        finally:
            self.converting = False

    def _convert_sync(self, target_format: str, quality: int, ratio: float = 1.0) -> list[ConvertResult]:
        """Convierte cada pendiente al formato destino en un hilo aparte."""
        out_dir: Path = _job_out_dir()

        new_ext: str = TARGET_FORMAT_TO_EXTENSION[target_format]
        results: list[ConvertResult] = []
        used_names: set[str] = set()
        for path in self.pending_convert:
            name: str = _next_available_name(out_dir, path.stem, new_ext, used_names)
            out_path: Path = out_dir / name

            try:
                meta = convert_format(input_path=path, output_path=out_path,
                                      target_format=target_format, quality=quality,
                                      target_ratio=ratio)
            except UnsupportedFormatError as err:
                results.append({"filename": name, "error": str(object=err)})
                continue
            except Exception as err:  # noqa: BLE001
                results.append({"filename": name, "error": f"Error al convertir: {err}"})
                continue

            results.append(ConvertRow(**meta, filename=name, tmp_path=str(object=out_path)))
        return results

    def render_convert_results(self) -> None:
        self.convert_result_col.controls.clear()
        for i, r in enumerate(iterable=self.convert_results):
            if is_convert_ok(r):
                ctl = convert_result_row(self, i, r)
            else:
                assert is_convert_error(r)
                ctl = error_row(i, filename=r["filename"], error=r["error"])
            self.convert_result_col.controls.append(ctl)
        self.convert_results_panel.visible = True
        self.page.update()

    # ---------------- Compresión ----------------
    async def compress_click(self, _e: ft.Event | None) -> None:
        if not self.pending or self.compressing:
            return
        self.compressing = True
        try:
            with self._busy_button(self.compress_btn, "Comprimiendo…", "Comprimir todo"):
                _slider_val: int | float | None = self.slider.value
                ratio: float = int(_slider_val if _slider_val is not None else 50) / 100
                metas = await asyncio.to_thread(self._compress_sync, ratio)
                self.results = metas
                self.render_results()
        finally:
            self.compressing = False

    def _compress_sync(self, ratio: float) -> list[CompressResult]:
        """CPU-bound vía Pillow; corre en un hilo aparte (asyncio.to_thread)."""
        out_dir: Path = _job_out_dir()

        results: list[CompressResult] = []
        used_names: set[str] = set()
        for path in self.pending:
            stem, ext = path.stem, path.suffix.lower()
            name: str = _next_available_name(out_dir, stem, ext, used_names)
            out_path: Path = out_dir / name

            try:
                meta = compress_to_target(input_path=path, output_path=out_path, target_ratio=ratio)
            except UnsupportedFormatError as err:
                results.append({"filename": name, "error": str(object=err)})
                continue
            except Exception as err:  # noqa: BLE001
                results.append({"filename": name, "error": f"Error al procesar: {err}"})
                continue

            pct = round(number=meta["new_size"] / meta["original_size"] * 100, ndigits=1)
            results.append(
                {
                    "filename": name,
                    "original_size": meta["original_size"],
                    "new_size": meta["new_size"],
                    "percent_of_original": pct,
                    "quality": meta["quality"],
                    "note": meta["note"],
                    "tmp_path": str(object=out_path),
                    "psnr_db": meta["psnr_db"],
                    "quality_acceptable": meta["quality_acceptable"],
                }
            )
        return results

    def render_results(self) -> None:
        self.result_col.controls.clear()
        any_ok = False
        for i, r in enumerate(iterable=self.results):
            if is_compress_ok(r):
                self.result_col.controls.append(result_row(self, i, r))
                any_ok = True
            else:
                assert is_compress_error(r)
                self.result_col.controls.append(error_row(i, filename=r["filename"], error=r["error"]))
        self.zip_btn.visible = any_ok
        self.results_panel.visible = True
        self.page.update()

    # ---------------- Guardado ----------------
    def make_save_handler(self, result: dict) -> Callable[..., None]:
        def handler(_e: ft.Event | None) -> None:
            self.page.run_task(self.save_one, result)

        return handler

    async def save_one(self, result: dict) -> None:
        picker = ft.FilePicker()
        dest: str | None = await picker.save_file(dialog_title="Guardar imagen comprimida",
                                      file_name=result["filename"])
        if not dest:
            return
        shutil.copyfile(src=result["tmp_path"], dst=dest)
        self._snack(message=f"Guardada: {dest}")

    async def save_zip(self, _e: ft.Event | None) -> None:
        ok_results: list[CompressRow] = [r for r in self.results if is_compress_ok(r)]
        if not ok_results:
            return
        picker = ft.FilePicker()
        dest: str | None = await picker.save_file(dialog_title="Guardar ZIP",
                                      file_name="imagenes_comprimidas.zip")
        if not dest:
            return
        with zipfile.ZipFile(file=dest, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for r in ok_results:
                zf.write(filename=r["tmp_path"], arcname=r["filename"])
        self._snack(message=f"ZIP guardado: {dest}")

    def _snack(self, message: str) -> None:
        self.page.show_dialog(dialog=ft.SnackBar(content=ft.Text(value=message)))


# ------------------------------------------------------------------
# Helpers de módulo
# ------------------------------------------------------------------
def _job_out_dir() -> Path:
    """Crea y devuelve el dir de salida de un job temporal (hilo aparte)."""
    cleanup_old_jobs()
    out_dir: Path = BASE_TMP / uuid.uuid4().hex / "out"
    out_dir.mkdir(parents=True)
    return out_dir


def _next_available_name(out_dir: Path, stem: str, ext: str, used: set[str]) -> str:
    """Nombre sin colisiones dentro del job (ni en memoria ni en disco)."""
    name: str = f"{stem}{ext}"
    counter = 1
    while name in used or (out_dir / name).exists():
        name = f"{stem}_{counter}{ext}"
        counter += 1
    used.add(name)
    return name


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
