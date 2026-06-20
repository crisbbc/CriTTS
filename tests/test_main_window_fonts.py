from unittest.mock import MagicMock
from src.gui.main_window import MainWindow
from src.gui.font_cache import FontCache
from src.gui.theme_constants import (
    ScaleManager, FONT_MD, FONT_SM, FONT_LG,
)


def _make_bare_window():
    """Bypass __init__; inject the widget attrs the font methods touch."""
    window = MainWindow.__new__(MainWindow)
    window._scale_manager = ScaleManager()
    window._font_cache = FontCache()
    window._last_text_font_size = None
    window._last_control_font_sizes = None
    window.text_input = MagicMock()
    window.voice_indicator_label = MagicMock()
    window.voice_indicator_value = MagicMock()
    window.text_label = MagicMock()
    window.speak_button = MagicMock()
    window.stop_button = MagicMock()
    window.clear_button = MagicMock()
    window.voice_button = MagicMock()
    window.overlay_button = MagicMock()
    window.controls_toggle_button = MagicMock()
    window.settings_button = MagicMock()
    window.status_label = MagicMock()
    window.activity_indicator = MagicMock()
    window.progress_label = MagicMock()
    return window


def _all_widgets(window):
    return [
        window.text_input, window.voice_indicator_label, window.voice_indicator_value,
        window.text_label, window.speak_button, window.stop_button, window.clear_button,
        window.voice_button, window.overlay_button, window.controls_toggle_button,
        window.settings_button, window.status_label, window.activity_indicator,
        window.progress_label,
    ]


def test_update_text_font_uses_cached_font(ctk_root):
    window = _make_bare_window()
    window._scale_manager.update(1200)
    expected = window._font_cache.get(window._scale_manager.font(FONT_MD))
    window._update_text_font()
    _, kwargs = window.text_input.configure.call_args
    assert kwargs["font"] is expected


def test_update_text_font_skips_when_unchanged(ctk_root):
    window = _make_bare_window()
    window._scale_manager.update(1200)
    window._update_text_font()
    for w in _all_widgets(window):
        w.configure.reset_mock()
    window._update_text_font()  # same scale -> no reconfigure
    for w in _all_widgets(window):
        w.configure.assert_not_called()


def test_update_control_fonts_skips_when_unchanged(ctk_root):
    window = _make_bare_window()
    window._scale_manager.update(1200)
    window._update_control_fonts()
    for w in _all_widgets(window):
        w.configure.reset_mock()
    window._update_control_fonts()  # same sizes -> no reconfigure
    for w in _all_widgets(window):
        w.configure.assert_not_called()


def test_update_control_fonts_reconfigures_when_scale_changes(ctk_root):
    window = _make_bare_window()
    window._scale_manager.update(1200)
    window._update_control_fonts()
    for w in _all_widgets(window):
        w.configure.reset_mock()
    window._scale_manager.update(700)  # narrower -> different font sizes
    window._update_control_fonts()
    window.voice_indicator_label.configure.assert_called()
    window.text_label.configure.assert_called()
