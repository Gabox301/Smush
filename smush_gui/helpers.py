"""
Utilidades de runtime: assets, fuentes, miniaturas y helpers de texto/visuales.
"""
from __future__ import annotations

import io
import shutil
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

import flet as ft
import flet.canvas as cv

from .theme import CORAL, FONT_BODY, FONT_DISPLAY, FONT_MONO, INK

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

BASE_TMP = Path(tempfile.gettempdir()) / "smush-jobs"
JOB_TTL_SECONDS = 60 * 30


# ------------------------------------------------------------------
# Assets de runtime
# ------------------------------------------------------------------
def ensure_assets() -> None:
    """Genera el tile punteado del fondo del app Flet en assets/."""
    (ASSETS / "img").mkdir(parents=True, exist_ok=True)

    dots = ASSETS / "dots-tile.png"
    if not dots.exists():
        tile = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
        ImageDraw.Draw(tile).ellipse([0, 0, 2, 2], fill=(23, 23, 15, 40))
        tile.save(dots)


def register_fonts(page: ft.Page) -> None:
    """Registra los TTF estáticos descargados por scripts/fetch_fonts.py."""
    fonts_dir = ASSETS / "fonts"
    families: dict[str, list[str]] = {FONT_DISPLAY: [], FONT_BODY: [], FONT_MONO: []}
    prefixes = {FONT_DISPLAY: "Fraunces-", FONT_BODY: "WorkSans-", FONT_MONO: "IBMPlexMono-"}
    if fonts_dir.exists():
        for family, prefix in prefixes.items():
            families[family] = sorted(
                str(p.relative_to(ASSETS)).replace("\\", "/")
                for p in fonts_dir.glob(f"{prefix}*.ttf")
            )
    page.fonts = {fam: files for fam, files in families.items() if files}  # type: ignore[assignment]
    if families[FONT_BODY]:
        page.theme = ft.Theme(font_family=FONT_BODY)


# ------------------------------------------------------------------
# Texto y archivos
# ------------------------------------------------------------------
def ext_of(filename: str) -> str:
    idx = filename.rfind(".")
    return filename[idx:].lower() if idx >= 0 else ""


def human_size(num_bytes: int | float) -> str:
    units = ["B", "KB", "MB", "GB"]
    n = float(num_bytes)
    i = 0
    while abs(n) >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.1f}{units[i]}"


def make_thumb_png(path: Path) -> bytes | None:
    """Miniatura 84x84 como bytes PNG para archivos pendientes."""
    try:
        with Image.open(path) as im:
            im.thumbnail((84, 84))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------
# Visuales
# ------------------------------------------------------------------
def squeeze_shapes(percent: int) -> list[cv.Shape]:
    """
    Zigzag cuya cantidad de pliegues crece al bajar el ratio (igual que
    renderSqueeze() del JS original). Se dibuja dos veces: sombra dura
    desplazada 2px y la línea coral encima.
    """
    width, height = 160.0, 40.0
    mid_y = height / 2
    amplitude = 12.0
    min_pleats, max_pleats = 3, 14
    t = 1 - percent / 100
    pleats = round(min_pleats + t * (max_pleats - min_pleats))

    points: list[tuple[float, float]] = []
    step = width / pleats
    for i in range(pleats + 1):
        x = i * step
        y = mid_y - amplitude if i % 2 == 0 else mid_y + amplitude
        points.append((round(x, 1), round(y, 1)))

    def polyline(dx: float, dy: float, color: str) -> cv.Path:
        elements = [cv.Path.MoveTo(x=points[0][0] + dx, y=points[0][1] + dy)]
        elements += [cv.Path.LineTo(x=px + dx, y=py + dy) for px, py in points[1:]]
        return cv.Path(
            paint=ft.Paint(
                color=color,
                stroke_width=2.5,
                style=ft.PaintingStyle.STROKE,
                stroke_cap=ft.StrokeCap.ROUND,
                stroke_join=ft.StrokeJoin.ROUND,
            ),
            elements=elements,
        )

    return [polyline(2, 2, INK), polyline(0, 0, CORAL)]


# ------------------------------------------------------------------
# Limpieza de temporales
# ------------------------------------------------------------------
def cleanup_old_jobs() -> None:
    now = time.time()
    if not BASE_TMP.exists():
        return
    for job_dir in BASE_TMP.iterdir():
        try:
            if now - job_dir.stat().st_mtime > JOB_TTL_SECONDS:
                shutil.rmtree(job_dir, ignore_errors=True)
        except OSError:
            pass
