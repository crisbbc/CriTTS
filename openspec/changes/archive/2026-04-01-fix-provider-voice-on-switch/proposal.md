## Why

When the user switches TTS providers in Settings → TTS Provider, the Voice tab's voice list and selected voice are not refreshed to reflect the new provider. The previously-selected voice (which belongs to the old provider) remains in the dropdown, so the saved `voice` setting is invalid for the newly-chosen provider. The selection is only corrected after the user triggers a speak action, which falls back to a valid default at runtime — making the switch feel broken until then.

## What Changes

- When the provider selection changes in the TTS Provider tab, the Voice tab immediately reloads its voice list for the new provider.
- After the reload completes, the selected voice is automatically updated to a valid voice for the new provider (falling back to the provider's default if no prior selection exists for it).
- The informational note in the TTS Provider tab instructing users to "save and reopen Settings" to see the updated voice list is removed or revised, since the list now updates live.

## Capabilities

### New Capabilities
- `voice-auto-select-on-provider-switch`: Automatically reload the voice list and select a valid default voice in the Voice tab whenever the active TTS provider is changed, without requiring a save-and-reopen cycle.

### Modified Capabilities

## Impact

- `src/gui/settings_tabs/voice_tab.py` — `update_provider_sliders` / new `reload_for_provider` method; `_load_voices` needs to accept an optional provider override.
- `src/gui/settings_tabs/tts_provider_tab.py` — stale informational note about reopening Settings updated.
- `src/gui/settings_window.py` — callback wiring may need updating to pass the new reload method.
- `src/tts/tts_engine.py` — `get_available_voices` already accepts a provider argument; no changes expected.
