## Context

CriTTS supports two TTS providers: Edge TTS (online) and Piper TTS (offline). The active provider is selected in the TTS Provider settings tab and stored in `settings_manager` under `tts_provider`. When the user changes provider in the UI (before saving), the settings manager still holds the old value. The Voice tab's voice list was only loaded once at settings window creation time (`_load_voices` in `__init__`), so it always shows voices for the provider that was active when the window opened.

`TTSEngine.get_available_voices()` fetches from whichever provider `settings_manager.get("tts_provider")` currently resolves to. Because the UI change hasn't been saved yet, the engine still returns voices for the old provider. The `update_provider_sliders` callback wired from `TTSProviderTab` → `VoiceTab` is currently a no-op.

## Goals / Non-Goals

**Goals:**
- When the provider dropdown in the TTS Provider tab changes, immediately reload the voice list in the Voice tab for the newly selected provider.
- After reload, auto-select a valid default voice for the new provider so `get_settings()` returns a valid `voice` value without the user needing to manually pick one.
- Remove the "save and reopen Settings" instructional note from the TTS Provider tab, since it is no longer necessary.

**Non-Goals:**
- Persisting a per-provider last-used voice across settings sessions (that is a separate enhancement).
- Changing how voices are fetched from the providers themselves.
- Modifying the cache invalidation logic in `TTSEngine`.

## Decisions

### 1. Pass provider key directly to the reload path rather than mutating settings prematurely

**Decision:** Add an optional `provider_override: str | None` parameter to `TTSEngine.get_available_voices()`. When set, it bypasses `settings_manager.get("tts_provider")` and routes to the specified provider's `get_available_voices()` directly (without polluting the cache with an unsaved provider key).

**Alternatives considered:**
- *Temporarily write the new provider to settings_manager then restore it* — fragile, causes race conditions if the user is speaking.
- *Duplicate the provider-fetch logic in VoiceTab* — violates single-responsibility; VoiceTab doesn't own provider routing.

### 2. Extend `update_provider_sliders` to trigger voice reload

**Decision:** Rename / replace the no-op `update_provider_sliders` in `VoiceTab` with a `reload_for_provider(provider_key: str)` method that:
1. Clears the current voice list (sets dropdown to loading state).
2. Kicks off `_load_voices(provider_override=provider_key)` on a background thread.
3. On completion, calls `_apply_voices_ui(voices)` which already handles choosing the best matching voice.

`SettingsWindow` wires `TTSProviderTab.set_voice_tab_callback(voice_tab.reload_for_provider)` instead of `update_provider_sliders`.

**Alternatives considered:**
- *Load voices for all providers at startup* — unnecessary latency, especially for Piper which may download models.

### 3. Auto-select the provider's first valid voice after reload

**Decision:** After a provider-triggered reload, `_apply_voices_ui` already falls back to `friendly_names[0]` if the saved voice isn't found in the new list. No additional logic is needed — this existing fallback produces the correct behavior because the saved voice (from the old provider) won't be in the new list.

## Risks / Trade-offs

- **Async timing** — Provider switch fires the reload, but if the user saves immediately before the thread completes, `get_settings()` may still return the old voice. Mitigation: show a brief "Loading…" placeholder in the dropdown to signal that the list is updating; accept this minor edge-case.
- **Cache bypass** — Passing `provider_override` skips the cache. If the user rapidly toggles back and forth, extra fetches occur. Mitigation: acceptable for a settings screen interaction; keep existing cache intact for runtime use.

## Migration Plan

1. Add `provider_override` param to `TTSEngine.get_available_voices`.
2. Update `VoiceTab._load_voices` to forward optional `provider_override`.
3. Replace no-op `update_provider_sliders` with `reload_for_provider`.
4. Update `SettingsWindow` wiring.
5. Remove/revise the stale informational note in `TTSProviderTab`.
6. Add/update unit tests.

No data migration needed. Rollback: revert the above files; existing settings are unaffected.

## Open Questions

- None.
