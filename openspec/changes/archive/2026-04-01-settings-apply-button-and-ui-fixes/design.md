## Context

`SettingsWindow` currently has four buttons: Reset, Refresh, Cancel, Save. Save collects all tab settings into the in-memory `SettingsManager`, validates, then writes to disk and **closes the window**. Users who want to tweak multiple settings across several tabs must reopen the window after every save, which is disruptive.

Two secondary issues compound the UX problem:
1. Settings are written into the in-memory `SettingsManager` before validation runs. A failed validation leaves stale values in memory until the next window open.
2. The window's X-button uses Tkinter's default destroy (no `WM_DELETE_WINDOW` binding), so it bypasses the cancel flow.

On the layout side, description labels have a hardcoded `wraplength=550` and the resize handler is stubbed out but never bound. Several dropdown widgets declare a fixed pixel `width` alongside `fill="x"` / `expand=True`, so the fixed width wins and they never stretch.

## Goals / Non-Goals

**Goals:**
- Add an **Apply** button that saves to disk without closing the window
- Validate settings **before** writing them into in-memory `SettingsManager`
- Bind `WM_DELETE_WINDOW` to the cancel handler
- Implement dynamic `wraplength` on all description labels — recalculated when the scroll pane resizes
- Remove conflicting fixed `width` from dropdown widgets that already use `fill="x"` / `expand=True`

**Non-Goals:**
- Redesigning the tab layout or adding new settings
- Per-tab apply (all tabs are collected atomically, same as Save)
- Undo/redo history for settings changes
- Live preview of changes before Apply

## Decisions

### D1 — Apply = collect + validate + write, window stays open

**Decision**: Apply follows the same collect/validate/write path as Save, but omits `window.destroy()`.

**Alternatives considered**:
- *Auto-save on field change*: too noisy for users still mid-edit; would require change-tracking on every widget.
- *Separate "dirty flag" badge on Apply*: adds visual complexity not justified by scope.

**Rationale**: Mirrors the pattern users already understand from other desktop apps (e.g., Preferences in JetBrains IDEs).

### D2 — Validate before mutating in-memory state

**Decision**: In `_on_save()` / new `_on_apply()`, call `tab.get_settings()` and `tab.validate()` first. Only if validation passes, write values into `SettingsManager` and call `save_settings()`.

**Alternatives considered**:
- *Keep current order, reset memory on cancel*: requires a deep-copy snapshot of all settings on window open and a restore path — more code, more risk.

**Rationale**: The validate-first order is simpler and eliminates the latent dirty-state bug with zero extra state management.

### D3 — Dynamic wraplength via `<Configure>` on the scroll pane

**Decision**: In `BaseTab.setup_layout()`, after creating the right-side `CTkScrollableFrame`, bind `<Configure>` on it. The handler updates `wraplength` on all labels registered in `self._wraplength_labels` to `event.width - 32` (subtracting padding).

**Alternatives considered**:
- *Bind on the top-level window*: window width ≠ scroll pane inner width; requires extra math per tab.
- *CSS `wrapLength` via `place()`*: not supported in Tkinter/CTk.

**Rationale**: Binding directly on the scroll pane gives exact inner width without coordinate translation. The `_wraplength_labels` list already exists in `BaseTab` — only the binding was missing.

### D4 — Remove fixed `width` from expanding dropdowns

**Decision**: Remove `width=500` / `width=400` from dropdowns that already use `fill="x"` / `expand=True`. CTk dropdowns default to 140px when no width is set; with `fill="x"` they will stretch to the container.

**Alternatives considered**:
- *Set a minimum-width via `minsize()`*: not needed; CTk dropdowns render fine at default width.

**Rationale**: The simplest fix — one attribute removal per widget.

## Risks / Trade-offs

- [Apply button UX]: Users who expect Apply to be a "preview" could be surprised it writes to disk immediately. → Mitigation: button label is "Apply" (not "Preview"); tooltip or docs can clarify if needed.
- [Validate-first refactor]: Two call sites must change (`_on_save` and the new `_on_apply`). A shared private method `_collect_and_save(close: bool)` avoids duplication and keeps the validation order consistent. → Mitigation: implement the shared helper first, then wire both buttons to it.
- [wraplength binding frequency]: `<Configure>` fires on every pixel of resize, updating potentially many labels. → Mitigation: labels are CTkLabel `configure()` calls — no layout recalculation triggered, so cost is negligible.

## Migration Plan

No data migration required. The settings file format (`~/.critts/config.json`) is unchanged. The change is purely additive (new button) plus internal fixes. Existing saved settings remain valid.

Rollback: revert the changed files; no schema or data changes to undo.

## Open Questions

- None at this time.
