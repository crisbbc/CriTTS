"""Cached CTkFont factory.

CustomTkinter's `CTkFont` allocates a Tcl font object per construction and
never frees it. Allocating a new font on every widget build and on every
resize tick leaks font resources and slows redraws. This cache returns a
single shared `CTkFont` per `(size, weight)` key.

A live Tk root MUST exist before `FontCache.get` is called (CTkFont requires
one). Instantiate the cache after the root exists, never at import time.
"""
from __future__ import annotations

import customtkinter as ctk

from .theme_constants import FONT_WEIGHT_BOLD

_CACHE: dict[tuple[int, str], ctk.CTkFont] = {}


class FontCache:
    """Return shared CTkFont objects keyed by (size, weight)."""

    def get(self, size: int, weight: str = "normal") -> ctk.CTkFont:
        key = (int(size), weight)
        font = _CACHE.get(key)
        if font is None:
            font = ctk.CTkFont(size=int(size), weight=weight)
            _CACHE[key] = font
        return font
