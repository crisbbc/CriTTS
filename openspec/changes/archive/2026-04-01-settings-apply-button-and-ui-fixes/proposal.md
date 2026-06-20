## Why

The settings window forces users to close and reopen it after every save, breaking the workflow when iterating over multiple settings. Additionally, several layout bugs cause text to overflow or widgets to not expand properly when the window is resized.

## What Changes

- Add an **Apply** button to the settings window that saves settings to disk without closing the window
- Fix the validation order bug where in-memory settings are dirtied before validation runs (if validation fails and user cancels, stale values persist in memory)
- Bind the `<Configure>` event on the settings window so `wraplength` labels update dynamically as the window is resized
- Remove hardcoded `wraplength=550` from `create_description()` in `BaseTab` and everywhere it is used directly — replace with dynamic wraplength computed from actual scroll pane width
- Fix dropdown widgets (`device_dropdown` in `audio_output_tab.py`, `voice_dropdown` in `voice_tab.py`) that have a fixed `width` conflicting with `fill="x"` / `expand=True` pack options
- Bind `WM_DELETE_WINDOW` protocol so closing the window with the X button behaves the same as Cancel (no accidental dirty-state leak)

## Capabilities

### New Capabilities

- `settings-apply-button`: Apply button that persists settings to disk without dismissing the settings window; also fixes the pre-validation in-memory dirty state bug and the unbound WM_DELETE_WINDOW handler
- `settings-ui-resize`: Dynamic wraplength recalculation on window resize and removal of conflicting fixed widths on dropdown widgets so the settings UI scales correctly at any window size

### Modified Capabilities

## Impact

- `src/gui/settings_window.py` — adds Apply button, validate-before-set ordering, WM_DELETE_WINDOW binding
- `src/gui/settings_tabs/base_tab.py` — `create_description()` default `wraplength` changed to dynamic; `<Configure>` resize bind helper added
- `src/gui/settings_tabs/audio_output_tab.py` — remove fixed `width=500` from device dropdown
- `src/gui/settings_tabs/voice_tab.py` — remove fixed `width=400` from voice dropdown
- No new dependencies; no API/protocol changes; no breaking changes
