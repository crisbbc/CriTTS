"""Tests for VoiceTab provider-driven voice reload behavior."""
import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock
import sys

# Mock customtkinter so the VoiceTab module can be imported in headless tests.
sys.modules.setdefault("customtkinter", MagicMock())

from src.gui import settings_window as settings_window_module
from src.gui.settings_window import SettingsWindow
from src.gui.settings_tabs.advanced_tab import AdvancedTab
from src.gui.settings_tabs.voice_tab import VoiceTab
from src.gui.theme_constants import (
    WINDOW_SETTINGS_HEIGHT,
    WINDOW_SETTINGS_MIN_HEIGHT,
    WINDOW_SETTINGS_MIN_WIDTH,
    WINDOW_SETTINGS_WIDTH,
)


import pytest


class _PersistenceAwareSettings:
    """Simple settings stub that tracks live values across save failures."""

    def __init__(self, values, save_result=True):
        self._values = dict(values)
        self._save_result = save_result

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value

    def get_all(self):
        return dict(self._values)

    def update(self, settings_dict):
        self._values.update(settings_dict)

    def save_settings(self):
        return self._save_result


class _PersistedSnapshotSettings(_PersistenceAwareSettings):
    """Settings stub with a persisted snapshot distinct from current live state."""

    def __init__(self, persisted_values, live_values, save_result=True):
        super().__init__(live_values, save_result=save_result)
        self._persisted_values = dict(persisted_values)

    def get_persisted_settings(self):
        return dict(self._persisted_values)

    def restore_last_persisted_settings(self):
        self._values = dict(self._persisted_values)


@pytest.mark.parametrize("provider_key", ["coqui", "piper"])
def test_reload_for_provider_triggers_load_with_override(provider_key):
    """reload_for_provider() should show loading state and call _load_voices(provider_override=...)."""
    tab = object.__new__(VoiceTab)
    tab.voice_dropdown = MagicMock()
    tab.voice_var = MagicMock()

    captured = {}

    def fake_load(provider_override=None):
        captured["provider_override"] = provider_override

    tab._load_voices = fake_load

    VoiceTab.reload_for_provider(tab, provider_key)

    tab.voice_dropdown.configure.assert_called_once_with(values=["Loading..."])
    tab.voice_var.set.assert_called_once_with("Loading...")
    assert captured["provider_override"] == provider_key


def test_settings_change_placeholder_remains_a_no_op():
    """Wave 1 foundation should not add cache-clearing behavior to the placeholder callback."""
    window = object.__new__(SettingsWindow)
    window.tts_engine = MagicMock()
    window.advanced_tab_obj = MagicMock()

    SettingsWindow._on_change_placeholder(window, "clear_cache")

    window.tts_engine.clear_voices_cache.assert_not_called()
    window.tts_engine.clear_audio_cache.assert_not_called()
    window.advanced_tab_obj._on_refresh_cache_stats.assert_not_called()


def test_settings_window_refreshes_advanced_tab_when_opening(monkeypatch):
    """Opening SettingsWindow should trigger the standard refresh flow for the Advanced tab."""
    advanced_tab = MagicMock()

    def fake_create_window(self):
        self.tabs = [advanced_tab]
        self.advanced_tab_obj = advanced_tab

    monkeypatch.setattr(SettingsWindow, "_create_window", fake_create_window)

    SettingsWindow(
        parent=MagicMock(),
        settings_manager=MagicMock(),
        tts_engine=MagicMock(),
        audio_router=MagicMock(),
    )

    advanced_tab._load_data.assert_called_once_with()


def test_settings_window_creation_applies_minimum_layout_guard_without_disabling_resize():
    """SettingsWindow creation should keep the shell resizable while enforcing the shared minimum size."""

    class _FakeWindowShell:
        def __init__(self):
            self.resizable_state = (True, True)
            self.geometry_calls = []
            self.minsize_call = None
            self.transient_parent = None
            self.grabbed = False

        def title(self, _value):
            return None

        def geometry(self, value):
            self.geometry_calls.append(value)

        def minsize(self, width, height):
            self.minsize_call = (width, height)

        def resizable(self, width=None, height=None):
            if width is None and height is None:
                return self.resizable_state
            self.resizable_state = (width, height)
            return self.resizable_state

        def transient(self, parent):
            self.transient_parent = parent

        def grab_set(self):
            self.grabbed = True

        def update_idletasks(self):
            return None

        def winfo_screenwidth(self):
            return 1600

        def winfo_screenheight(self):
            return 900

    settings_window_module.ctk.CTkToplevel.reset_mock()
    window_shell = _FakeWindowShell()
    settings_window_module.ctk.CTkToplevel.return_value = window_shell

    window = object.__new__(SettingsWindow)
    window.parent = MagicMock()
    window._build_window_content = MagicMock()

    SettingsWindow._create_window(window)

    settings_window_module.ctk.CTkToplevel.assert_called_once_with(window.parent)
    assert f"{WINDOW_SETTINGS_WIDTH}x{WINDOW_SETTINGS_HEIGHT}" in window_shell.geometry_calls
    assert (
        window_shell.minsize_call
        == (WINDOW_SETTINGS_MIN_WIDTH, WINDOW_SETTINGS_MIN_HEIGHT)
    )
    assert window_shell.resizable() == (True, True)
    assert window_shell.transient_parent is window.parent
    assert window_shell.grabbed is True
    window._build_window_content.assert_called_once_with()


def test_refresh_theme_rebuilds_in_place_without_recreating_settings_shell():
    """Theme refresh should preserve the existing settings toplevel while rebuilding its children."""
    settings_window_module.ctk.CTkToplevel.reset_mock()
    child = MagicMock()
    window = object.__new__(SettingsWindow)
    window.tabs = []
    window.tabview = MagicMock()
    window.tabview.get.return_value = "Behavior"
    window.window = MagicMock()
    window.window.winfo_children.return_value = [child]
    window._build_window_content = MagicMock()
    window._on_refresh = MagicMock()

    SettingsWindow.refresh_theme(window)

    settings_window_module.ctk.CTkToplevel.assert_not_called()
    child.destroy.assert_called_once_with()
    window._build_window_content.assert_called_once_with(selected_tab="Behavior")
    window._on_refresh.assert_called_once_with()
    window.window.transient.assert_not_called()
    window.window.grab_set.assert_not_called()


def test_collect_and_save_defers_settings_shell_refresh_until_after_apply_callback_returns():
    """Apply should schedule shell rebuilding after the button callback frame unwinds."""
    window = object.__new__(SettingsWindow)
    tab = MagicMock()
    call_order = []
    scheduled_callbacks = []
    tab.get_settings.return_value = {"appearance_mode": "Light"}
    tab.validate.return_value = []
    window.tabs = [tab]
    window.settings = MagicMock()
    window.on_save = MagicMock(side_effect=lambda: call_order.append("on_save"))
    window.window = MagicMock()
    window.window.after.side_effect = lambda delay, callback: scheduled_callbacks.append(callback)
    window.refresh_theme = MagicMock(side_effect=lambda: call_order.append("refresh_theme"))

    SettingsWindow._collect_and_save(window, close=False)

    window.settings.set.assert_called_once_with("appearance_mode", "Light")
    window.settings.save_settings.assert_called_once_with()
    window.on_save.assert_called_once_with()
    window.window.after.assert_called_once()
    assert window.refresh_theme.call_count == 0
    assert call_order == ["on_save"]

    scheduled_callbacks[0]()

    window.refresh_theme.assert_called_once_with()
    assert call_order == ["on_save", "refresh_theme"]
    window.window.destroy.assert_not_called()


def test_collect_and_save_skips_apply_refresh_schedule_for_true_noop():
    """Apply should not rebuild the settings shell when the collected values already match runtime settings."""
    window = object.__new__(SettingsWindow)
    tab = MagicMock()
    tab.get_settings.return_value = {"appearance_mode": "Dark"}
    tab.validate.return_value = []
    window.tabs = [tab]
    window.settings = MagicMock()
    window.settings.get_all.return_value = {"appearance_mode": "Dark"}
    window.settings.save_settings.return_value = True
    window.on_save = MagicMock()
    window.window = MagicMock()
    window.refresh_theme = MagicMock()

    SettingsWindow._collect_and_save(window, close=False)

    window.settings.set.assert_called_once_with("appearance_mode", "Dark")
    window.settings.save_settings.assert_called_once_with()
    window.on_save.assert_called_once_with()
    window.window.after.assert_not_called()
    window.refresh_theme.assert_not_called()
    window.window.destroy.assert_not_called()


def test_schedule_refresh_theme_deduplicates_pending_apply_refresh():
    """Apply refresh scheduling should coalesce duplicate requests until the deferred rebuild runs."""
    window = object.__new__(SettingsWindow)
    scheduled_callbacks = []
    window.window = MagicMock()
    window.window.after.side_effect = lambda delay, callback: scheduled_callbacks.append(callback)
    window.refresh_theme = MagicMock()

    SettingsWindow._schedule_refresh_theme(window)
    SettingsWindow._schedule_refresh_theme(window)

    window.window.after.assert_called_once()
    assert len(scheduled_callbacks) == 1

    scheduled_callbacks[0]()

    window.refresh_theme.assert_called_once_with()

    SettingsWindow._schedule_refresh_theme(window)

    assert window.window.after.call_count == 2


def test_refresh_theme_stops_active_voice_preview_before_rebuilding():
    """Refreshing the settings shell should cancel any in-flight preview on the stale VoiceTab."""
    window = object.__new__(SettingsWindow)
    voice_tab = object.__new__(VoiceTab)
    voice_tab._async_callbacks_active = True
    voice_tab._preview_playing = True
    voice_tab._preview_stop_event = threading.Event()
    voice_tab.audio_router = MagicMock()
    child = MagicMock()
    window.tabs = [voice_tab]
    window.tabview = MagicMock()
    window.tabview.get.return_value = "Voice"
    window.window = MagicMock()
    window.window.winfo_children.return_value = [child]
    window._build_window_content = MagicMock()
    window._on_refresh = MagicMock()

    SettingsWindow.refresh_theme(window)

    assert voice_tab._async_callbacks_active is False
    assert voice_tab._preview_stop_event.is_set()
    assert voice_tab._preview_playing is False
    voice_tab.audio_router.stop_playback.assert_called_once_with()
    child.destroy.assert_called_once_with()
    window._build_window_content.assert_called_once_with(selected_tab="Voice")
    window._on_refresh.assert_called_once_with()


def test_reset_to_defaults_triggers_live_save_callback_before_closing():
    """Reset should reuse the live save/apply callback path before the settings shell closes."""
    settings_window_module.ctk.CTkButton.reset_mock()
    settings_window_module.ctk.CTkToplevel.reset_mock()
    confirm_dialog = MagicMock()
    settings_window_module.ctk.CTkToplevel.return_value = confirm_dialog

    window = object.__new__(SettingsWindow)
    window.settings = MagicMock()
    window.on_save = MagicMock()
    window.window = MagicMock()

    SettingsWindow._on_reset_to_defaults(window)

    reset_command = next(
        call.kwargs["command"]
        for call in settings_window_module.ctk.CTkButton.call_args_list
        if call.kwargs.get("text") == "Reset"
    )

    reset_command()

    window.settings.reset_to_defaults.assert_called_once_with()
    window.on_save.assert_called_once_with()
    confirm_dialog.destroy.assert_called_once_with()
    window.window.destroy.assert_called_once_with()


def test_cancel_and_refresh_buttons_use_surface_theme_neutral_tokens_in_light_mode(monkeypatch):
    """Cancel and Refresh buttons must use appearance-aware neutral tokens, not dark hard-codes."""
    import src.gui.settings_window as sw_module
    from src.gui.theme_constants import get_settings_surface_theme, COLOR_NEUTRAL_MEDIUM, COLOR_NEUTRAL_DARK

    # Use the ctk bound to settings_window at import time — not sys.modules, which other
    # test files can replace with a fresh MagicMock() after the initial setdefault().
    ctk = sw_module.ctk
    ctk.get_appearance_mode.return_value = "Light"
    ctk.CTkButton.reset_mock()

    for name in (
        "VoiceTab", "AudioOutputTab", "AppearanceTab", "AbbreviationsTab",
        "KeybindsTab", "BehaviorTab", "SoundboardTab", "VRChatOSCTab",
        "AdvancedTab", "TTSProviderTab",
    ):
        monkeypatch.setattr(sw_module, name, MagicMock())

    window = object.__new__(SettingsWindow)
    window.window = MagicMock()
    window.parent = MagicMock()
    window.settings = MagicMock()
    window.tts_engine = MagicMock()
    window.audio_router = MagicMock()
    window.on_save = MagicMock()

    surface_theme = get_settings_surface_theme("Light")

    SettingsWindow._build_window_content(window)

    button_kw = {
        call.kwargs.get("text"): call.kwargs
        for call in ctk.CTkButton.call_args_list
        if call.kwargs.get("text") in ("Cancel", "Refresh")
    }

    for btn_name in ("Cancel", "Refresh"):
        assert btn_name in button_kw, f"{btn_name} button not found in CTkButton calls"
        assert button_kw[btn_name]["fg_color"] != COLOR_NEUTRAL_MEDIUM, (
            f"{btn_name} fg_color still uses hardcoded dark COLOR_NEUTRAL_MEDIUM"
        )
        assert button_kw[btn_name]["hover_color"] != COLOR_NEUTRAL_DARK, (
            f"{btn_name} hover_color still uses hardcoded dark COLOR_NEUTRAL_DARK"
        )
        assert button_kw[btn_name]["fg_color"] == surface_theme["button_neutral"], (
            f"{btn_name} fg_color should equal surface_theme['button_neutral'] in Light mode"
        )
        assert button_kw[btn_name]["hover_color"] == surface_theme["button_neutral_hover"], (
            f"{btn_name} hover_color should equal surface_theme['button_neutral_hover'] in Light mode"
        )


def test_build_window_content_resolves_surface_theme_once_for_tabview_style(monkeypatch):
    """Settings shell rebuilds should reuse one surface-theme snapshot for tabview chrome."""
    import src.gui.settings_window as sw_module

    ctk = sw_module.ctk
    ctk.get_appearance_mode.return_value = "Light"

    for name in (
        "VoiceTab", "AudioOutputTab", "AppearanceTab", "AbbreviationsTab",
        "KeybindsTab", "BehaviorTab", "SoundboardTab", "VRChatOSCTab",
        "AdvancedTab", "TTSProviderTab",
    ):
        monkeypatch.setattr(sw_module, name, MagicMock())

    real_get_settings_surface_theme = sw_module.get_settings_surface_theme
    resolved_modes = []

    def tracking_get_settings_surface_theme(mode=None):
        resolved_modes.append(mode)
        return real_get_settings_surface_theme(mode)

    monkeypatch.setattr(
        sw_module,
        "get_settings_surface_theme",
        tracking_get_settings_surface_theme,
    )

    window = object.__new__(SettingsWindow)
    window.window = MagicMock()
    window.parent = MagicMock()
    window.settings = MagicMock()
    window.tts_engine = MagicMock()
    window.audio_router = MagicMock()
    window.on_save = MagicMock()

    SettingsWindow._build_window_content(window)

    assert resolved_modes == ["Light"]


def test_on_cancel_invalidates_async_callbacks_before_destroy():
    """_on_cancel must call invalidate_async_callbacks on every tab before destroying the window."""
    voice_tab = MagicMock()
    call_order = []
    voice_tab.invalidate_async_callbacks.side_effect = lambda: call_order.append("invalidate")

    window = object.__new__(SettingsWindow)
    window.tabs = [voice_tab]
    window.window = MagicMock()
    window.window.destroy.side_effect = lambda: call_order.append("destroy")

    SettingsWindow._on_cancel(window)

    voice_tab.invalidate_async_callbacks.assert_called_once_with()
    window.window.destroy.assert_called_once_with()
    assert call_order == ["invalidate", "destroy"]


def test_on_cancel_restores_last_persisted_settings_before_destroy():
    """Cancel must roll back live-only voice state before tearing the settings shell down."""
    settings = _PersistedSnapshotSettings(
        persisted_values={"favorite_voices": [], "recent_voices": []},
        live_values={"favorite_voices": ["voice-a"], "recent_voices": ["voice-a"]},
    )
    voice_tab = MagicMock()
    call_order = []
    voice_tab.invalidate_async_callbacks.side_effect = lambda: call_order.append("invalidate")

    window = object.__new__(SettingsWindow)
    window.settings = settings
    window.tabs = [voice_tab]
    window.window = MagicMock()
    window.window.destroy.side_effect = lambda: call_order.append("destroy")

    SettingsWindow._on_cancel(window)

    assert settings.get("favorite_voices") == []
    assert settings.get("recent_voices") == []
    assert call_order == ["invalidate", "destroy"]


def test_collect_and_save_close_path_invalidates_tabs_before_destroy():
    """_collect_and_save(close=True) must invalidate tab callbacks before destroying the window."""
    voice_tab = MagicMock()
    call_order = []
    voice_tab.invalidate_async_callbacks.side_effect = lambda: call_order.append("invalidate")
    voice_tab.get_settings.return_value = {}
    voice_tab.validate.return_value = []

    window = object.__new__(SettingsWindow)
    window.tabs = [voice_tab]
    window.settings = MagicMock()
    window.on_save = MagicMock()
    window.window = MagicMock()
    window.window.destroy.side_effect = lambda: call_order.append("destroy")

    SettingsWindow._collect_and_save(window, close=True)

    voice_tab.invalidate_async_callbacks.assert_called_once_with()
    window.window.destroy.assert_called_once_with()
    assert call_order == ["invalidate", "destroy"]


def test_reset_to_defaults_close_path_invalidates_tabs_before_destroy():
    """Reset's confirm-and-destroy path must invalidate tab callbacks before window teardown."""
    settings_window_module.ctk.CTkButton.reset_mock()
    settings_window_module.ctk.CTkToplevel.reset_mock()
    confirm_dialog = MagicMock()
    settings_window_module.ctk.CTkToplevel.return_value = confirm_dialog

    voice_tab = MagicMock()
    call_order = []
    voice_tab.invalidate_async_callbacks.side_effect = lambda: call_order.append("invalidate")

    window = object.__new__(SettingsWindow)
    window.settings = MagicMock()
    window.on_save = MagicMock()
    window.tabs = [voice_tab]
    window.window = MagicMock()
    window.window.destroy.side_effect = lambda: call_order.append("destroy")

    SettingsWindow._on_reset_to_defaults(window)

    reset_command = next(
        call.kwargs["command"]
        for call in settings_window_module.ctk.CTkButton.call_args_list
        if call.kwargs.get("text") == "Reset"
    )
    reset_command()

    voice_tab.invalidate_async_callbacks.assert_called_once_with()
    window.window.destroy.assert_called_once_with()
    assert call_order == ["invalidate", "destroy"]


def test_advanced_tab_load_data_refreshes_cache_stats():
    """AdvancedTab._load_data() should delegate to the cache statistics refresh handler."""
    tab = object.__new__(AdvancedTab)
    tab._on_refresh_cache_stats = MagicMock()

    AdvancedTab._load_data(tab)

    tab._on_refresh_cache_stats.assert_called_once_with()


def test_load_voices_skips_ui_scheduling_when_parent_window_is_closing(monkeypatch):
    """Background voice loads should not call after() once the settings window is closing."""
    tab = object.__new__(VoiceTab)
    tab._apply_voices_ui = MagicMock()
    tab.parent_window = MagicMock()
    tab.parent_window.winfo_exists.return_value = False

    async def fake_get_available_voices(provider_override=None):
        return [{"name": "Aria", "short_name": "en-US-AriaNeural"}]

    tab.tts_engine = MagicMock()
    tab.tts_engine.get_available_voices = fake_get_available_voices

    class _ImmediateThread:
        def __init__(self, target, daemon):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("src.gui.settings_tabs.voice_tab.threading.Thread", _ImmediateThread)

    VoiceTab._load_voices(tab)

    tab.parent_window.after.assert_not_called()
    tab._apply_voices_ui.assert_not_called()


def test_load_voices_ignores_scheduled_ui_work_after_refresh_destroys_widgets(monkeypatch):
    """Queued voice-load callbacks should no-op once refresh destroys the old tab widgets."""
    tab = object.__new__(VoiceTab)
    tab._apply_voices_ui = MagicMock()
    tab.parent_window = MagicMock()
    tab.parent_window.winfo_exists.return_value = True
    scheduled_callbacks = []
    tab.parent_window.after.side_effect = lambda delay, callback: scheduled_callbacks.append(callback)
    tab.tab = MagicMock()
    tab.tab.winfo_exists.return_value = True

    async def fake_get_available_voices(provider_override=None):
        return [{"name": "Aria", "short_name": "en-US-AriaNeural"}]

    tab.tts_engine = MagicMock()
    tab.tts_engine.get_available_voices = fake_get_available_voices

    class _ImmediateThread:
        def __init__(self, target, daemon):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("src.gui.settings_tabs.voice_tab.threading.Thread", _ImmediateThread)

    VoiceTab._load_voices(tab)

    assert len(scheduled_callbacks) == 1

    tab.tab.winfo_exists.return_value = False
    scheduled_callbacks[0]()

    tab._apply_voices_ui.assert_not_called()


def test_load_voices_only_applies_latest_provider_result(monkeypatch):
    """Rapid provider reloads should ignore stale async voice results once a newer load starts."""
    tab = object.__new__(VoiceTab)
    tab._apply_voices_ui = MagicMock()
    tab.parent_window = MagicMock()
    tab.parent_window.winfo_exists.return_value = True
    scheduled_callbacks = []
    tab.parent_window.after.side_effect = lambda delay, callback: scheduled_callbacks.append(callback)
    tab.tab = MagicMock()
    tab.tab.winfo_exists.return_value = True
    pending_targets = []

    async def fake_get_available_voices(provider_override=None):
        return [{"name": provider_override, "short_name": provider_override}]

    tab.tts_engine = MagicMock()
    tab.tts_engine.get_available_voices = fake_get_available_voices

    class _QueuedThread:
        def __init__(self, target, daemon):
            self._target = target

        def start(self):
            pending_targets.append(self._target)

    monkeypatch.setattr("src.gui.settings_tabs.voice_tab.threading.Thread", _QueuedThread)

    VoiceTab._load_voices(tab, provider_override="edge")
    VoiceTab._load_voices(tab, provider_override="piper")

    pending_targets[1]()
    pending_targets[0]()

    assert len(scheduled_callbacks) == 2

    scheduled_callbacks[0]()
    scheduled_callbacks[1]()

    tab._apply_voices_ui.assert_called_once_with(
        [{"name": "piper", "short_name": "piper"}]
    )


@pytest.mark.parametrize("close", [False, True])
def test_collect_and_save_aborts_success_flow_when_persistence_fails(close):
    """Save/apply should not notify, retheme, or close when persistence fails."""
    settings_window_module.ctk.CTkToplevel.reset_mock()

    window = object.__new__(SettingsWindow)
    tab = MagicMock()
    tab.get_settings.return_value = {"appearance_mode": "Light"}
    tab.validate.return_value = []
    window.tabs = [tab]
    window.settings = MagicMock()
    window.settings.save_settings.return_value = False
    window.on_save = MagicMock()
    window.window = MagicMock()
    window.refresh_theme = MagicMock()

    SettingsWindow._collect_and_save(window, close=close)

    window.settings.set.assert_called_once_with("appearance_mode", "Light")
    window.settings.save_settings.assert_called_once_with()
    window.on_save.assert_not_called()
    window.refresh_theme.assert_not_called()
    window.window.destroy.assert_not_called()
    settings_window_module.ctk.CTkToplevel.assert_called_once_with(window.window)


def test_collect_and_save_rolls_back_live_settings_when_persistence_fails():
    """Failed save/apply should restore the last persisted in-memory settings snapshot."""
    settings_window_module.ctk.CTkToplevel.reset_mock()

    window = object.__new__(SettingsWindow)
    tab = MagicMock()
    tab.get_settings.return_value = {"appearance_mode": "Light"}
    tab.validate.return_value = []
    window.tabs = [tab]
    window.settings = _PersistenceAwareSettings({"appearance_mode": "Dark"}, save_result=False)
    window.on_save = MagicMock()
    window.window = MagicMock()
    window.refresh_theme = MagicMock()

    SettingsWindow._collect_and_save(window, close=False)

    assert window.settings.get("appearance_mode") == "Dark"
    window.on_save.assert_not_called()
    window.refresh_theme.assert_not_called()
    settings_window_module.ctk.CTkToplevel.assert_called_once_with(window.window)


def test_collect_and_save_rolls_back_to_last_persisted_snapshot_when_live_mutables_were_previously_changed():
    """Failed save/apply should discard unsaved mutable state and restore the persisted snapshot."""
    settings_window_module.ctk.CTkToplevel.reset_mock()

    window = object.__new__(SettingsWindow)
    tab = MagicMock()
    tab.get_settings.return_value = {"appearance_mode": "Light"}
    tab.validate.return_value = []
    window.tabs = [tab]
    window.settings = _PersistedSnapshotSettings(
        persisted_values={
            "appearance_mode": "Dark",
            "favorite_voices": ["saved-favorite"],
            "recent_voices": ["saved-recent"],
        },
        live_values={
            "appearance_mode": "Dark",
            "favorite_voices": ["unsaved-favorite"],
            "recent_voices": ["unsaved-recent"],
        },
        save_result=False,
    )
    window.on_save = MagicMock()
    window.window = MagicMock()
    window.refresh_theme = MagicMock()

    SettingsWindow._collect_and_save(window, close=False)

    assert window.settings.get("appearance_mode") == "Dark"
    assert window.settings.get("favorite_voices") == ["saved-favorite"]
    assert window.settings.get("recent_voices") == ["saved-recent"]
    window.on_save.assert_not_called()
    window.refresh_theme.assert_not_called()
    settings_window_module.ctk.CTkToplevel.assert_called_once_with(window.window)


def test_voice_preview_uses_unsaved_provider_override(monkeypatch):
    """Voice preview must target the provider currently shown in the settings UI."""

    class _ImmediateThread:
        def __init__(self, target, daemon):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("src.gui.settings_tabs.voice_tab.threading.Thread", _ImmediateThread)

    tab = object.__new__(VoiceTab)
    tab.settings = MagicMock()
    tab.settings.get.side_effect = lambda key, default=None: (
        "edge" if key == "tts_provider" else default
    )
    tab.tts_engine = MagicMock()
    tab.tts_engine.generate_speech = AsyncMock(return_value=(b"audio-bytes", None))
    tab.audio_router = MagicMock()
    tab.audio_router.play_audio_to_device = AsyncMock(return_value=True)
    tab._voice_name_to_short_name = {"Piper Voice": "piper-voice"}
    tab.voice_var = MagicMock()
    tab.voice_var.get.return_value = "Piper Voice"
    tab.preview_text_var = MagicMock()
    tab.preview_text_var.get.return_value = "Preview me"
    tab.rate_var = MagicMock()
    tab.rate_var.get.return_value = 0
    tab.volume_var = MagicMock()
    tab.volume_var.get.return_value = 100
    tab.pitch_var = MagicMock()
    tab.pitch_var.get.return_value = 0
    tab.preview_loading_label = MagicMock()
    tab.preview_button = MagicMock()
    tab.stop_preview_button = MagicMock()
    tab.preview_text_entry = MagicMock()
    tab._preview_playing = False
    tab._preview_stop_event = threading.Event()
    tab._active_provider_key = "piper"
    tab._validate_preview_text = MagicMock(return_value=True)
    tab._set_preview_ui_loading = MagicMock()
    tab._preview_done = MagicMock()
    tab._preview_loading_playing = MagicMock()
    tab.configure_surface_status_label = MagicMock()
    tab._schedule_on_ui_thread = lambda callback, delay_ms=0: callback()

    VoiceTab._on_voice_preview(tab)

    tab.tts_engine.generate_speech.assert_awaited_once_with(
        "Preview me",
        "piper-voice",
        0,
        100,
        0,
        tab._preview_stop_event,
        provider_override="piper",
    )
    tab.configure_surface_status_label.assert_any_call(
        tab.preview_loading_label,
        "Generating... (first use may download a Piper voice model)",
        "idle",
    )


def test_reset_to_defaults_aborts_success_flow_when_persistence_fails():
    """Reset should surface persistence failures without notifying or closing the window."""
    settings_window_module.ctk.CTkButton.reset_mock()
    settings_window_module.ctk.CTkToplevel.reset_mock()
    confirm_dialog = MagicMock()
    persistence_error_dialog = MagicMock()
    settings_window_module.ctk.CTkToplevel.side_effect = [confirm_dialog, persistence_error_dialog]

    window = object.__new__(SettingsWindow)
    window.settings = MagicMock()
    window.settings.reset_to_defaults.return_value = False
    window.on_save = MagicMock()
    window.tabs = [MagicMock()]
    window.window = MagicMock()

    SettingsWindow._on_reset_to_defaults(window)

    reset_command = next(
        call.kwargs["command"]
        for call in settings_window_module.ctk.CTkButton.call_args_list
        if call.kwargs.get("text") == "Reset"
    )

    reset_command()

    window.settings.reset_to_defaults.assert_called_once_with()
    window.on_save.assert_not_called()
    confirm_dialog.destroy.assert_not_called()
    window.window.destroy.assert_not_called()
    settings_window_module.ctk.CTkToplevel.assert_any_call(window.window)
