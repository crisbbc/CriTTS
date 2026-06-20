from unittest.mock import MagicMock
from src.gui.main_window import MainWindow


def test_pulse_button_removed():
    from src.gui import main_window as mw
    assert not hasattr(mw.MainWindow, "_pulse_button"), "_pulse_button should be removed"
    assert not hasattr(mw.MainWindow, "_transition_button_color"), "_transition_button_color should be removed"


def test_animate_button_color_sets_target_in_one_call():
    window = MainWindow.__new__(MainWindow)
    window.speak_button = MagicMock()
    window.speak_button.cget.return_value = "#000000"  # current differs from target
    window._animate_button_color(window.speak_button, "#123456", 0.2)
    # Exactly one configure call, with only fg_color (no width toggle).
    window.speak_button.configure.assert_called_once_with(fg_color="#123456")


def test_animate_button_color_skips_when_color_unchanged():
    window = MainWindow.__new__(MainWindow)
    window.speak_button = MagicMock()
    window.speak_button.cget.return_value = "#123456"  # same as target
    window._animate_button_color(window.speak_button, "#123456", 0.2)
    window.speak_button.configure.assert_not_called()


def test_animate_button_color_handles_cget_exception():
    window = MainWindow.__new__(MainWindow)
    window.speak_button = MagicMock()
    window.speak_button.cget.side_effect = RuntimeError("boom")
    # cget raises -> current_color falls back to target -> colors equal -> skip.
    window._animate_button_color(window.speak_button, "#123456", 0.2)
    window.speak_button.configure.assert_not_called()
