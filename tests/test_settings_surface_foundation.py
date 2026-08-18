"""Tests for the shared settings surface foundation contract."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys
import re

import pytest

# Mock customtkinter so GUI modules can be imported in headless tests.
sys.modules.setdefault("customtkinter", MagicMock())

from src.gui.settings_tabs.base_tab import (
    BaseTab,
    SETTINGS_CARD_BOUNDARY_RULES,
    SETTINGS_TAB_STYLE_AUDIT,
)
from src.gui.settings_tabs import base_tab as base_tab_module
from src.gui.settings_tabs.abbreviations_tab import AbbreviationsTab
from src.gui.settings_tabs.appearance_tab import AppearanceTab
from src.gui.settings_tabs.audio_output_tab import AudioOutputTab
from src.gui.settings_tabs.behavior_tab import BehaviorTab
from src.gui.settings_tabs.keybinds_tab import KeybindsTab
from src.gui.settings_tabs.soundboard_tab import SoundboardTab
from src.gui.settings_window import SETTINGS_TAB_ORDER, get_settings_tabview_style
from src.gui.theme_constants import (
    COLOR_BG_PRIMARY,
    COLOR_BG_PRIMARY_LIGHT,
    COLOR_BG_SECONDARY,
    COLOR_BG_SECONDARY_LIGHT,
    COLOR_BG_TERTIARY,
    COLOR_BG_TERTIARY_LIGHT,
    COLOR_NEUTRAL_LIGHTEST,
    COLOR_TEXT_PRIMARY_LIGHT,
    RADIUS_LG,
    RADIUS_MD,
    SETTINGS_TAB_SELECTED_COLOR,
    SETTINGS_TAB_SELECTED_HOVER,
    get_settings_surface_theme,
)


@pytest.fixture(autouse=True)
def _reset_customtkinter_appearance():
    """Keep appearance-mode-dependent theme tests isolated."""
    sys.modules["customtkinter"].get_appearance_mode.return_value = "Dark"
    yield
    sys.modules["customtkinter"].get_appearance_mode.return_value = "Dark"


def _relative_luminance(color: str) -> float:
    rgb_channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]

    def _normalize(channel: float) -> float:
        if channel <= 0.03928:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (_normalize(channel) for channel in rgb_channels)
    return (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


class _ConcreteBaseTab(BaseTab):
    def _create_content(self):
        return None

    def get_settings(self):
        return {}

    def validate(self):
        return []


def test_settings_surface_theme_matches_main_window_tokens():
    """Settings shell styling should reuse the main window surface tokens."""
    theme = get_settings_surface_theme()

    assert theme["window_fg"] == COLOR_BG_PRIMARY
    assert theme["pane_fg"] == COLOR_BG_SECONDARY
    assert theme["section_fg"] == COLOR_BG_TERTIARY
    assert theme["text_primary"] == COLOR_NEUTRAL_LIGHTEST
    assert theme["shell_corner_radius"] == RADIUS_LG
    assert theme["section_corner_radius"] == RADIUS_MD


def test_settings_surface_theme_adapts_to_light_mode():
    """Settings shell tokens should switch with the active appearance mode."""
    theme = get_settings_surface_theme("Light")

    assert theme["window_fg"] == COLOR_BG_PRIMARY_LIGHT
    assert theme["pane_fg"] == COLOR_BG_SECONDARY_LIGHT
    assert theme["section_fg"] == COLOR_BG_TERTIARY_LIGHT
    assert theme["text_primary"] == COLOR_TEXT_PRIMARY_LIGHT
    assert theme["sidebar_button_hover"] == COLOR_BG_TERTIARY_LIGHT
    assert theme["scrollbar_button_color"] == theme["border_color"]
    assert theme["scrollbar_button_hover_color"] == theme["text_muted"]


def test_settings_surface_theme_default_contract_stays_on_dark_baseline():
    """Default shared helpers should not drift with the process-wide appearance state."""
    sys.modules["customtkinter"].get_appearance_mode.return_value = "Light"

    theme = get_settings_surface_theme()

    assert theme["window_fg"] == COLOR_BG_PRIMARY
    assert theme["pane_fg"] == COLOR_BG_SECONDARY
    assert theme["section_fg"] == COLOR_BG_TERTIARY


def test_settings_surface_theme_system_mode_tracks_active_appearance():
    """Explicit system mode should still resolve through the active CTk appearance."""
    sys.modules["customtkinter"].get_appearance_mode.return_value = "Light"

    theme = get_settings_surface_theme("System")

    assert theme["window_fg"] == COLOR_BG_PRIMARY_LIGHT
    assert theme["pane_fg"] == COLOR_BG_SECONDARY_LIGHT
    assert theme["section_fg"] == COLOR_BG_TERTIARY_LIGHT


def test_settings_tabview_style_uses_shared_surface_theme():
    """Tab chrome should be derived from the shared settings surface theme."""
    style = get_settings_tabview_style()

    assert style["fg_color"] == COLOR_BG_SECONDARY
    assert style["segmented_button_fg_color"] == COLOR_BG_TERTIARY
    assert style["segmented_button_selected_color"] == SETTINGS_TAB_SELECTED_COLOR
    assert style["segmented_button_selected_hover_color"] == SETTINGS_TAB_SELECTED_HOVER
    assert style["corner_radius"] == RADIUS_LG


def test_settings_tabview_style_default_contract_stays_on_dark_baseline():
    """Default tabview chrome should remain stable when no appearance mode is supplied."""
    sys.modules["customtkinter"].get_appearance_mode.return_value = "Light"

    style = get_settings_tabview_style()

    assert style["fg_color"] == COLOR_BG_SECONDARY
    assert style["segmented_button_fg_color"] == COLOR_BG_TERTIARY
    assert style["text_color"] == COLOR_NEUTRAL_LIGHTEST


def test_settings_tabview_style_adapts_to_light_mode():
    """Tab chrome should follow the active light appearance palette."""
    style = get_settings_tabview_style("Light")

    assert style["fg_color"] == COLOR_BG_SECONDARY_LIGHT
    assert style["segmented_button_fg_color"] == COLOR_BG_TERTIARY_LIGHT
    assert style["text_color"] == COLOR_TEXT_PRIMARY_LIGHT


def test_settings_tabview_selected_label_contrast_is_accessible():
    """Selected tab labels must remain readable on the chosen accent surface."""
    style = get_settings_tabview_style()

    assert _contrast_ratio(
        style["text_color"],
        style["segmented_button_selected_color"],
    ) >= 4.5


def test_settings_tab_order_remains_stable():
    """The tab order contract must remain unchanged during the style refresh."""
    assert SETTINGS_TAB_ORDER == (
        "Voice",
        "Audio Output",
        "Appearance",
        "Abbreviations",
        "Keybinds",
        "Behavior",
        "Soundboard",
        "VRChat OSC",
        "Advanced",
        "TTS Provider",
    )


def test_settings_surface_foundation_records_wave2_adoption_audit():
    """Wave 1 should publish which tabs can adopt the shared helpers directly."""
    audit = {entry["tab"]: entry for entry in SETTINGS_TAB_STYLE_AUDIT}

    assert [entry["tab"] for entry in SETTINGS_TAB_STYLE_AUDIT] == list(SETTINGS_TAB_ORDER)
    assert audit["Appearance"]["surface_mode"] == "direct shared shell/base helpers"
    assert audit["Behavior"]["surface_mode"] == "direct shared shell/base helpers"
    assert "textbox" in " ".join(audit["Audio Output"]["manual_adapters"]).lower()
    assert "Favorites and recent scrollable frames" in audit["Voice"]["manual_adapters"]
    assert "Conditional Coqui settings frame" in audit["TTS Provider"]["manual_adapters"]


def test_settings_card_boundary_rules_keep_inner_controls_plain():
    """The shared contract should forbid blanket nested-card treatment."""
    rules_text = " ".join(SETTINGS_CARD_BOUNDARY_RULES).lower()

    assert "top-level section" in rules_text
    assert "inner rows" in rules_text
    assert "textboxes" in rules_text
    assert "lists" in rules_text
    assert "notes" in rules_text


def test_section_descriptions_use_accessible_body_text_token():
    """Section descriptions should inherit the readable body-text token on section cards."""
    base_tab_module.ctk.get_appearance_mode.return_value = "Light"
    surface_theme = BaseTab.get_active_surface_theme()
    label = MagicMock()
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.tab = MagicMock()
    dummy_tab._wraplength_labels = []

    base_tab_module.ctk.CTkLabel.reset_mock()
    base_tab_module.ctk.CTkLabel.return_value = label

    result = BaseTab.create_description(dummy_tab, "Readable copy")

    base_tab_module.ctk.CTkLabel.assert_called_once()
    assert (
        base_tab_module.ctk.CTkLabel.call_args.kwargs["text_color"]
        == surface_theme["text_primary"]
    )
    assert result is label
    assert dummy_tab._wraplength_labels == [label]


def test_helper_text_defaults_to_stronger_supporting_token():
    """Section-card helper copy should default to the stronger supporting-text token."""
    base_tab_module.ctk.get_appearance_mode.return_value = "Light"
    surface_theme = BaseTab.get_active_surface_theme()
    label = MagicMock()
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.tab = MagicMock()
    dummy_tab._wraplength_labels = []

    base_tab_module.ctk.CTkLabel.reset_mock()
    base_tab_module.ctk.CTkLabel.return_value = label

    result = BaseTab.create_helper_text(dummy_tab, "Helpful copy")

    base_tab_module.ctk.CTkLabel.assert_called_once()
    assert (
        base_tab_module.ctk.CTkLabel.call_args.kwargs["text_color"]
        == surface_theme["text_supporting"]
    )
    assert result is label
    assert dummy_tab._wraplength_labels == [label]


def test_section_sidebar_buttons_use_shared_surface_theme_tokens():
    """Sidebar anchor buttons should derive their chrome from the shared settings surface theme."""
    base_tab_module.ctk.get_appearance_mode.return_value = "Light"
    surface_theme = get_settings_surface_theme("Light")
    label = MagicMock()
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.tab = MagicMock()
    dummy_tab.scroll = MagicMock()
    dummy_tab.sidebar = MagicMock()
    dummy_tab._sections = []

    base_tab_module.ctk.CTkLabel.reset_mock()
    base_tab_module.ctk.CTkButton.reset_mock()
    base_tab_module.ctk.CTkLabel.return_value = label

    BaseTab.create_section_header(dummy_tab, "Section Title")

    assert base_tab_module.ctk.CTkButton.call_args.kwargs["hover_color"] == surface_theme["sidebar_button_hover"]
    assert base_tab_module.ctk.CTkButton.call_args.kwargs["text_color"] == surface_theme["text_secondary"]


def test_setup_layout_uses_shared_scrollbar_theme_tokens():
    """Scrollable chrome should use appearance-aware theme tokens instead of dark-only constants."""
    base_tab_module.ctk.get_appearance_mode.return_value = "Light"
    surface_theme = get_settings_surface_theme("Light")
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.tab = MagicMock()

    base_tab_module.ctk.CTkFrame.reset_mock()
    base_tab_module.ctk.CTkScrollableFrame.reset_mock()

    BaseTab.setup_layout(dummy_tab)

    scroll_calls = base_tab_module.ctk.CTkScrollableFrame.call_args_list
    assert scroll_calls[0].kwargs["scrollbar_button_color"] == surface_theme["scrollbar_button_color"]
    assert scroll_calls[0].kwargs["scrollbar_button_hover_color"] == surface_theme["scrollbar_button_hover_color"]
    assert scroll_calls[1].kwargs["scrollbar_button_color"] == surface_theme["scrollbar_button_color"]
    assert scroll_calls[1].kwargs["scrollbar_button_hover_color"] == surface_theme["scrollbar_button_hover_color"]


def test_scroll_resize_defers_wraplength_updates_via_next_idle_after():
    """The first resize event schedules an `after()` apply on the next idle moment, not synchronously.

    ``after(0, ...)`` is what we want: a visible wraplength update reaches
    the labels as soon as the Tk event loop is idle, with no perceptible
    delay during interactive window drag.  Anything longer would visibly
    lag the resize gesture without buying extra protection; coalescing
    beyond that is the responsibility of `_pending_wraplength_job` (already
    scheduled), `_wraplength_apply_in_progress` (re-entrance guard), and
    the `_last_applied_wraplength` cache (no-op short-circuit).
    """
    scheduled_callbacks = []
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.scroll = MagicMock()
    dummy_tab.scroll.after.side_effect = (
        lambda delay_ms, callback: scheduled_callbacks.append(callback) or "after#1"
    )
    dummy_tab.update_wraplength = MagicMock()
    dummy_tab._pending_wraplength = None
    dummy_tab._pending_wraplength_job = None
    dummy_tab._wraplength_apply_in_progress = False
    dummy_tab._last_applied_wraplength = None

    BaseTab._on_scroll_resize(dummy_tab, SimpleNamespace(width=260))

    dummy_tab.update_wraplength.assert_not_called()
    dummy_tab.scroll.after.assert_called_once()
    # Coalescing must be "next idle moment" only — no time-based debounce
    # that would perceptibly lag an interactive drag-resize.
    assert dummy_tab.scroll.after.call_args.args[0] == 0
    assert len(scheduled_callbacks) == 1

    scheduled_callbacks[0]()

    dummy_tab.update_wraplength.assert_called_once_with(228)
    assert dummy_tab._last_applied_wraplength == 228
    assert dummy_tab._pending_wraplength is None
    assert dummy_tab._pending_wraplength_job is None
    assert dummy_tab._wraplength_apply_in_progress is False


def test_scroll_resize_coalesces_pending_work_and_skips_redundant_wraplength():
    """Repeated resize events should collapse to the latest pending width without rescheduling churn."""
    scheduled_callbacks = []
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.scroll = MagicMock()
    dummy_tab.scroll.after.side_effect = (
        lambda delay_ms, callback: scheduled_callbacks.append(callback) or "after#1"
    )
    dummy_tab.update_wraplength = MagicMock()
    dummy_tab._pending_wraplength = None
    dummy_tab._pending_wraplength_job = None
    dummy_tab._wraplength_apply_in_progress = False
    dummy_tab._last_applied_wraplength = None

    BaseTab._on_scroll_resize(dummy_tab, SimpleNamespace(width=240))
    BaseTab._on_scroll_resize(dummy_tab, SimpleNamespace(width=320))

    dummy_tab.scroll.after.assert_called_once()
    scheduled_callbacks[0]()

    dummy_tab.update_wraplength.assert_called_once_with(288)

    dummy_tab.scroll.after.reset_mock()
    BaseTab._on_scroll_resize(dummy_tab, SimpleNamespace(width=320))

    dummy_tab.scroll.after.assert_not_called()
    dummy_tab.update_wraplength.assert_called_once_with(288)


def test_scroll_resize_ignores_resize_events_while_apply_is_in_flight():
    """Re-entrant resize events during `_apply_pending_wraplength` must NOT schedule additional work.

    Without this guard, the cascade of `<Configure>` events fired by each
    ``label.configure(wraplength=...)`` call would re-enter ``_on_scroll_resize``
    while we're still iterating labels, which (with the old per-call
    ``after_idle`` scheduling) would either pile up idle callbacks or, with
    the pending-job check, leave the *latest* captured width stranded in
    ``_pending_wraplength``.  The new behaviour: skip the schedule entirely
    while the apply is running and rely on the re-arm hook at the end of the
    apply.
    """
    scheduled_callbacks = []
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.scroll = MagicMock()
    dummy_tab.scroll.after.side_effect = (
        lambda delay_ms, callback: scheduled_callbacks.append(callback) or f"after#{len(scheduled_callbacks)+1}"
    )
    dummy_tab.update_wraplength = MagicMock()
    dummy_tab._pending_wraplength = 228
    dummy_tab._pending_wraplength_job = "after#already-scheduled"
    dummy_tab._wraplength_apply_in_progress = True  # simulate in-flight apply
    dummy_tab._last_applied_wraplength = None

    # Simulate two resize events arriving *during* a running apply.  Both
    # must be ignored by the scheduling logic -- the in-flight apply already
    # has the latest captured value.
    BaseTab._on_scroll_resize(dummy_tab, SimpleNamespace(width=300))
    BaseTab._on_scroll_resize(dummy_tab, SimpleNamespace(width=320))

    dummy_tab.scroll.after.assert_not_called()
    # The pending value picks up the latest resize event for the re-arm hook.
    assert dummy_tab._pending_wraplength == 320 - 32


def test_apply_pending_wraplength_rearms_when_configure_captures_newer_pending():
    """If the configure()-pass itself causes `_pending_wraplength` to be
    updated to a new widget width, we must schedule an additional apply so
    we converge without waiting on another resize event.
    """
    scheduled_callbacks = []
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.scroll = MagicMock()
    dummy_tab.scroll.after.side_effect = (
        lambda delay_ms, callback: scheduled_callbacks.append(callback) or "after#rearm"
    )

    # Mock update_wraplength so it can simulate the cascade: bumping the
    # pending width *during* its run (e.g., label re-flow propagating up to
    # a parent that fires another `<Configure>`).  Note: this fires the
    # cascade only on the *first* update_wraplength call so the second
    # apply converges cleanly (otherwise the side-effect would keep
    # re-priming `_pending_wraplength` and mask whether re-arm actually
    # converges the queue).
    initial_pending_width = 240 - 32  # 208

    update_calls = [0]

    def _fake_update_wraplength(width: int) -> None:
        update_calls[0] += 1
        if update_calls[0] == 1:
            # Capture the cascade on the first invoke only: pretend a parent
            # `<Configure>` fired during the apply, capturing a yet-newer
            # pending width so the re-arm hook kicks in.
            dummy_tab._pending_wraplength = 320 - 32  # 288

    dummy_tab.update_wraplength = MagicMock(side_effect=_fake_update_wraplength)
    dummy_tab._pending_wraplength = initial_pending_width
    dummy_tab._pending_wraplength_job = "after#original"
    dummy_tab._wraplength_apply_in_progress = False
    dummy_tab._last_applied_wraplength = None

    BaseTab._apply_pending_wraplength(dummy_tab)

    # The apply consumed the initial pending value and updated labels.
    dummy_tab.update_wraplength.assert_called_once_with(initial_pending_width)
    assert dummy_tab._last_applied_wraplength == initial_pending_width
    # The configure-pass captured a newer pending value, so the apply must
    # have re-armed itself exactly once.
    assert dummy_tab._pending_wraplength == 288
    assert dummy_tab.scroll.after.call_count == 1
    # The re-arm schedule is also `after(0, ...)` -- otherwise the
    # resize-to-resize round-trip would perceptibly lag during drag.
    assert dummy_tab.scroll.after.call_args.args[0] == 0
    assert dummy_tab._wraplength_apply_in_progress is False

    # Bound-method identity (`is`) is not stable across Python accesses to
    # `self.method`, so invoke the rescheduled callback and verify it
    # converges on the newer captured value -- this is the actual
    # behavioural guarantee the production code provides.
    dummy_tab.update_wraplength.reset_mock()
    scheduled_callbacks[0]()
    dummy_tab.update_wraplength.assert_called_once_with(288)
    assert dummy_tab._last_applied_wraplength == 288
    # The rescheduled apply consumed the captured value; nothing new was
    # captured, so `_pending_wraplength` is back to None and no further
    # re-arm is scheduled.
    assert dummy_tab._pending_wraplength is None
    assert dummy_tab.scroll.after.call_count == 1  # still the original re-arm


def test_apply_pending_wraplength_clears_in_progress_flag_on_early_exits():
    """The re-entrance guard must be cleared even when the apply short-circuits."""
    dummy_tab = object.__new__(_ConcreteBaseTab)
    dummy_tab.scroll = MagicMock()
    dummy_tab.update_wraplength = MagicMock()
    # Case 1: pending_wraplength is None.
    dummy_tab._pending_wraplength = None
    dummy_tab._pending_wraplength_job = "after#original"
    dummy_tab._wraplength_apply_in_progress = False
    dummy_tab._last_applied_wraplength = None
    BaseTab._apply_pending_wraplength(dummy_tab)
    assert dummy_tab._wraplength_apply_in_progress is False
    assert dummy_tab.update_wraplength.call_count == 0

    # Case 2: pending value matches last applied -- no work needed.
    dummy_tab._pending_wraplength = 100
    dummy_tab._last_applied_wraplength = 100
    dummy_tab._pending_wraplength_job = "after#original"
    dummy_tab._wraplength_apply_in_progress = False
    BaseTab._apply_pending_wraplength(dummy_tab)
    assert dummy_tab._wraplength_apply_in_progress is False
    assert dummy_tab.update_wraplength.call_count == 0


def test_wave2_tabs_use_section_surfaces_in_existing_order(monkeypatch):
    """Wave 2 tabs should promote each top-level anchor section into a section surface."""
    expected_sections = {
        AudioOutputTab: [
            "Playback Device",
            "Device Information",
            "Audio Normalization",
            "PulseAudio Sink Routing",
            "Microphone Passthrough",
        ],
        AppearanceTab: ["Appearance Mode", "Visible Buttons"],
        BehaviorTab: [
            "Behavior",
            "Text Transcription",
            "Transcription Refinement",
            "Audio Pre-processing",
            "Word Corrections",
        ],
        AbbreviationsTab: ["Abbreviations", "Usage Tips"],
        KeybindsTab: ["Keybinds"],
        SoundboardTab: ["Soundboard"],
    }

    for tab_class, section_titles in expected_sections.items():
        created_sections = []

        def _fake_setup_layout(self):
            self.scroll = MagicMock()
            self.sidebar = MagicMock()
            self.tab = MagicMock()
            self._wraplength_labels = []
            self._sections = []

        def _fake_create_section_surface(
            self,
            title,
            parent=None,
            description=None,
            register_sidebar=True,
        ):
            created_sections.append(title)
            return MagicMock(), MagicMock()

        monkeypatch.setattr(tab_class, "setup_layout", _fake_setup_layout)
        monkeypatch.setattr(tab_class, "create_section_surface", _fake_create_section_surface)

        tab_kwargs = {}
        if tab_class is KeybindsTab:
            tab_kwargs["parent_window"] = MagicMock()

        tab_class(MagicMock(), {}, audio_router=MagicMock(), **tab_kwargs)

        assert created_sections == section_titles


def test_wave2_tabs_drop_hardcoded_helper_and_status_text_colors():
    """Wave 2 tabs should use shared tokens/helpers instead of raw helper/status colors."""
    repo_root = Path(__file__).resolve().parents[1]
    target_files = [
        repo_root / "src" / "gui" / "settings_tabs" / "audio_output_tab.py",
        repo_root / "src" / "gui" / "settings_tabs" / "appearance_tab.py",
        repo_root / "src" / "gui" / "settings_tabs" / "behavior_tab.py",
        repo_root / "src" / "gui" / "settings_tabs" / "abbreviations_tab.py",
        repo_root / "src" / "gui" / "settings_tabs" / "keybinds_tab.py",
        repo_root / "src" / "gui" / "settings_tabs" / "soundboard_tab.py",
    ]
    hardcoded_text_colors = re.compile(
        r'text_color\s*=\s*"(?:gray|orange|green|red|blue|#e74c3c|#f39c12|#2ecc71)"'
    )

    for path in target_files:
        file_text = path.read_text(encoding="utf-8")
        assert hardcoded_text_colors.search(file_text) is None, path.name
        assert "\ufe0f" not in file_text, path.name
