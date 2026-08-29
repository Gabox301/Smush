"""
Smush — interfaz multiplataforma en Flet (web, escritorio y móvil).

Correr con:
    uv run python flet_app.py
"""
from __future__ import annotations

import flet as ft

from smush_gui.app import main

if __name__ == "__main__":
    ft.run(main)
