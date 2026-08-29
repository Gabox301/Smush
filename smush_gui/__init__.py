"""Smush — interfaz multiplataforma en Flet (web, desktop, mobile)."""

from .app import SmushApp
from .helpers import ensure_assets, register_fonts

__all__ = ["SmushApp", "ensure_assets", "register_fonts"]