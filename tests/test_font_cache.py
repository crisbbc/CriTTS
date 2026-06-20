import customtkinter as ctk
from src.gui.font_cache import FontCache
from src.gui.theme_constants import FONT_WEIGHT_BOLD


def test_returns_same_object_for_same_key(ctk_root):
    cache = FontCache()
    a = cache.get(13)
    b = cache.get(13)
    assert a is b


def test_returns_same_object_for_same_size_weight(ctk_root):
    cache = FontCache()
    a = cache.get(13, weight=FONT_WEIGHT_BOLD)
    b = cache.get(13, weight=FONT_WEIGHT_BOLD)
    assert a is b


def test_distinct_keys_yield_distinct_fonts(ctk_root):
    cache = FontCache()
    a = cache.get(13)
    b = cache.get(14)
    c = cache.get(13, weight=FONT_WEIGHT_BOLD)
    assert a is not b
    assert a is not c
    assert b is not c


def test_font_is_a_real_ctkfont(ctk_root):
    cache = FontCache()
    f = cache.get(13)
    assert isinstance(f, ctk.CTkFont)
