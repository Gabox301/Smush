"""
Descarga las fuentes de la marca (TTF estáticos por peso) desde la API
de Google Fonts y los guarda en assets/fonts/ para usarlos en la UI
de escritorio (Flet).

Uso:
    uv run python scripts/fetch_fonts.py
"""

from __future__ import annotations

import re
from typing import Any
import urllib.request
from pathlib import Path

CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Fraunces:wght@600;700;900"
    "&family=Work+Sans:wght@400;500;600;700;800"
    "&family=IBM+Plex+Mono:wght@400;500"
    "&display=swap"
)

OUT_DIR: Path = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Sin User-Agent de navegador, la API sirve TTF en lugar de WOFF2.
OPENER: urllib.request.OpenerDirector = urllib.request.build_opener()
OPENER.addheaders = [("User-Agent", "curl/7.64.1")]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    css = OPENER.open(fullurl=CSS_URL, timeout=30).read().decode("utf-8")

    blocks: list[Any] = re.findall(pattern=r"@font-face\s*\{([^}]+)", string=css)
    # (familia, peso) -> URL; nos quedamos con la última variante de cada
    # uno porque el subset "latin" es el último bloque que aparece.
    found: dict[tuple[str, str], str] = {}
    for block in blocks:
        if "font-style: italic" in block:
            continue
        fam_m: re.Match[str] | None = re.search(pattern=r"font-family:\s*'([^']+)'", string=block)
        weight_m: re.Match[str] | None = re.search(pattern=r"font-weight:\s*(\d+)", string=block)
        url_m: re.Match[str] | None = re.search(pattern=r"url\((https://[^)]+\.ttf)\)", string=block)
        if not (fam_m and weight_m and url_m):
            continue
        found[(fam_m.group(1), weight_m.group(1))] = url_m.group(1)

    if not found:
        raise SystemExit("No se encontraron fuentes TTF en la respuesta.")

    for (family, weight), url in sorted(found.items()):
        filename: str = f"{family.replace(' ', '')}-{weight}.ttf"
        dest: Path = OUT_DIR / filename
        data = OPENER.open(fullurl=url, timeout=60).read()
        dest.write_bytes(data)
        print(f"OK  {filename}  ({len(data) // 1024} KB)")

    print(f"\n{len(found)} fuentes guardadas en {OUT_DIR}")


if __name__ == "__main__":
    main()
