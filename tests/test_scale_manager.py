"""Tests for ScaleManager — dynamic window resize scaling."""
import sys
import importlib
from unittest.mock import MagicMock

# Block heavy imports that would pull in GUI/tts dependencies
_BLOCKED = ['tkinter', 'tkinter.ttk', 'customtkinter',
            'edge_tts', 'pydub', 'torch', 'torchaudio',
            'numpy', 'sounddevice', 'pyttsx3', 'pynput',
            'keyboard', 'pyperclip', 'PIL', 'PIL.Image',
            'playsound', 'pygame', 'winrt', 'pywinstyles']
for mod in _BLOCKED:
    sys.modules[mod] = MagicMock()

# Import theme_constants directly via importlib to bypass src.gui.__init__
import importlib.util
spec = importlib.util.spec_from_file_location(
    "theme_constants",
    "/mnt/c/Users/bbccris/Desktop/CriTTS-main/src/gui/theme_constants.py"
)
theme_constants = importlib.util.module_from_spec(spec)
spec.loader.exec_module(theme_constants)

ScaleManager = theme_constants.ScaleManager
BUTTON_WIDTH_DEFAULT = theme_constants.BUTTON_WIDTH_DEFAULT


class TestScaleManager:
    """Unit tests for the ScaleManager class."""

    def test_scale_default_is_one(self):
        sm = ScaleManager(1200)
        sm.update(1200)
        assert sm.scale == 1.0

    def test_scale_at_half_width(self):
        """At half width the raw ratio is 0.5 but defaults clamp to 0.65."""
        sm = ScaleManager(1200)
        sm.update(600)
        assert sm.scale == 0.65  # Clamped to min_scale default

    def test_scale_at_half_width_no_min_clamp(self):
        """With min_scale=0.0, half width yields 0.5."""
        sm = ScaleManager(1200)
        sm.update(600, min_scale=0.0)
        assert sm.scale == 0.5

    def test_scale_clamps_to_min(self):
        sm = ScaleManager(1200)
        sm.update(100)  # way below 0.65*1200
        assert sm.scale == 0.65

    def test_scale_clamps_to_max(self):
        sm = ScaleManager(1200)
        sm.update(4000)
        assert sm.scale == 1.4

    def test_font_scales_proportionally(self):
        sm = ScaleManager(1200)
        sm.update(1200)
        assert sm.font(14) == 14  # scale 1.0

        # scale = 0.5 (with min_scale=0.0), raw=7, clamped to 9
        sm.update(600, min_scale=0.0)
        assert sm.font(14) == 9  # max(9, int(14*0.5)) = max(9, 7) = 9

    def test_font_clamps_to_nine(self):
        sm = ScaleManager(1200)
        sm.update(100)  # scale clamped to 0.65
        result = sm.font(10)  # int(10 * 0.65) = 6, but clamped to 9
        assert result == 9

    def test_dimension_scales_and_clamps(self):
        sm = ScaleManager(1200)
        sm.update(1200)
        assert sm.dimension(100) == 100

        sm.update(600, min_scale=0.0)
        # int(100 * 0.5) = 50
        assert sm.dimension(100) == 50

        # min clamp is 1
        sm.update(10, min_scale=0.0)
        assert sm.dimension(100) == 1  # would be 0 but clamped

    def test_button_width_uses_BUTTON_WIDTH_DEFAULT(self):
        sm = ScaleManager(1200)
        sm.update(1200)
        assert sm.button_width() == BUTTON_WIDTH_DEFAULT  # 140

        sm.update(600, min_scale=0.0)
        # int(140 * 0.5) = 70
        assert sm.button_width() == 70

    def test_update_returns_none(self):
        sm = ScaleManager(1200)
        result = sm.update(1200)
        assert result is None

    def test_custom_reference_width(self):
        sm = ScaleManager(800)
        sm.update(800)
        assert sm.scale == 1.0

        sm.update(400)
        assert sm.scale == 0.65  # clamped

    def test_multiple_updates(self):
        sm = ScaleManager(1200)
        sm.update(600, min_scale=0.0)
        assert sm.scale == 0.5
        sm.update(2400)
        assert sm.scale == 1.4  # clamped to max
        sm.update(1200)
        assert sm.scale == 1.0
