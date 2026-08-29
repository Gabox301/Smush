"""
smush_gui.components — primitivos reutilizables.
"""
from .cards import feature_card, step_card
from .primitives import (
    chip,
    format_badge,
    isotipo,
    nav_link,
    section_head,
    sticker,
    with_cols,
    with_hover,
)
from .rows import brand_icon, error_row, meta_column, pending_row, result_row, row_shell, thumb_control

__all__ = [
    "brand_icon",
    "chip",
    "error_row",
    "feature_card",
    "format_badge",
    "isotipo",
    "meta_column",
    "nav_link",
    "pending_row",
    "result_row",
    "row_shell",
    "section_head",
    "step_card",
    "sticker",
    "thumb_control",
    "with_cols",
    "with_hover",
]
