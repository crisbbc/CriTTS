from unittest.mock import MagicMock
from src.gui.main_window import MainWindow


def test_animate_voice_indicator_sets_text_and_color_directly():
    window = MainWindow.__new__(MainWindow)
    window.voice_indicator_value = MagicMock()
    window.voice_indicator_value.cget.return_value = "OldText"  # differs from new
    window._animate_voice_indicator("NewVoice (Auto: English)", "green")
    window.voice_indicator_value.configure.assert_called_once_with(
        text="NewVoice (Auto: English)", text_color="green"
    )


def test_animate_voice_indicator_skips_when_text_unchanged():
    window = MainWindow.__new__(MainWindow)
    window.voice_indicator_value = MagicMock()
    window.voice_indicator_value.cget.return_value = "SameText"
    window._animate_voice_indicator("SameText", "green")
    window.voice_indicator_value.configure.assert_not_called()


def test_no_op_fade_methods_are_gone():
    from src.gui import main_window as mw
    # _fade_out_text / _fade_in_text / _fade_in_text_safe were only used by the
    # old voice-indicator fade chain and are now removed.
    for dead in ("_fade_out_text", "_fade_in_text", "_fade_in_text_safe"):
        assert not hasattr(mw.MainWindow, dead), f"{dead} should be removed"
    # _pulse_label is a documented no-op (body is `pass`) but is STILL called by
    # the status-label and activity-indicator chains (_fade_in_status at line ~2191
    # and _animate_indicator_color at line ~2213), so it must be retained.
    assert hasattr(mw.MainWindow, "_pulse_label"), "_pulse_label has external callers"
