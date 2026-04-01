"""Tests for VoiceTab provider-driven voice reload behavior."""
from unittest.mock import MagicMock
import sys

# Mock customtkinter so the VoiceTab module can be imported in headless tests.
sys.modules.setdefault("customtkinter", MagicMock())

from src.gui.settings_tabs.voice_tab import VoiceTab


def test_reload_for_provider_triggers_load_with_override():
    """reload_for_provider() should show loading state and call _load_voices(provider_override=...)."""
    tab = object.__new__(VoiceTab)
    tab.voice_dropdown = MagicMock()
    tab.voice_var = MagicMock()

    captured = {}

    def fake_load(provider_override=None):
        captured["provider_override"] = provider_override

    tab._load_voices = fake_load

    VoiceTab.reload_for_provider(tab, "piper")

    tab.voice_dropdown.configure.assert_called_once_with(values=["Loading..."])
    tab.voice_var.set.assert_called_once_with("Loading...")
    assert captured["provider_override"] == "piper"
