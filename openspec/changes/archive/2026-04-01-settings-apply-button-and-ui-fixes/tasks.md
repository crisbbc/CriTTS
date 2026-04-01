## 1. Refactor save logic into shared helper

- [x] 1.1 In `settings_window.py`, extract a private `_collect_and_save(close: bool)` method that (a) calls `tab.get_settings()` + `tab.validate()` for all tabs, (b) only mutates `SettingsManager` and calls `save_settings()` if validation passes, and (c) calls `self.window.destroy()` only when `close=True`
- [x] 1.2 Update the existing `_on_save()` to delegate to `_collect_and_save(close=True)`

## 2. Add Apply button

- [x] 2.1 In `settings_window.py` `_create_widgets()`, add an **Apply** button (green, same style as Save) packed to the right, between Save and Cancel in the button bar
- [x] 2.2 Wire Apply button to a new `_on_apply()` method that calls `_collect_and_save(close=False)`
- [x] 2.3 Bind `WM_DELETE_WINDOW` protocol on the window to `_on_cancel` so the X-button behaves identically to Cancel

## 3. Fix dynamic wraplength

- [x] 3.1 In `BaseTab.setup_layout()`, after creating the right-side `CTkScrollableFrame`, bind `<Configure>` on it to a new `_on_scroll_resize(event)` handler
- [x] 3.2 Implement `_on_scroll_resize(event)` in `BaseTab`: compute `new_wrap = max(100, event.width - 32)` and call `label.configure(wraplength=new_wrap)` for every label in `self._wraplength_labels`
- [x] 3.3 Change the default `wraplength=550` in `BaseTab.create_description()` to `wraplength=100` (a safe minimum) so the initial configure event replaces it immediately on first render

## 4. Fix expanding dropdowns

- [x] 4.1 In `audio_output_tab.py`, remove `width=500` from the `device_dropdown` widget constructor
- [x] 4.2 In `voice_tab.py`, remove `width=400` from the `voice_dropdown` widget constructor

## 5. Verification

- [ ] 5.1 Launch the app, open Settings — confirm Apply button is visible and saves without closing the window
- [ ] 5.2 Confirm that closing with the X-button does not save settings
- [ ] 5.3 Resize the settings window narrow and wide — confirm description labels reflow and dropdowns stretch
- [ ] 5.4 Trigger a validation error (e.g., blank required field) and click Apply — confirm the error dialog appears, window stays open, and no partial settings are written
- [x] 5.5 Run existing tests: `pytest tests/ -v` — confirm no regressions
