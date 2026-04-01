## 1. TTSEngine — provider override support

- [x] 1.1 Add optional `provider_override: str | None = None` parameter to `TTSEngine.get_available_voices()`
- [x] 1.2 When `provider_override` is set, route to the matching provider directly and skip the cache (do not write the result to cache either, to avoid poisoning runtime voice lookups with an unsaved provider)

## 2. VoiceTab — live reload on provider change

- [x] 2.1 Add `provider_override: str | None = None` parameter to `VoiceTab._load_voices()` and forward it to `TTSEngine.get_available_voices()`
- [x] 2.2 Replace the no-op `update_provider_sliders` method with `reload_for_provider(provider_key: str)` that sets the voice dropdown to a "Loading…" placeholder and then calls `_load_voices(provider_override=provider_key)` on the background thread

## 3. SettingsWindow — update callback wiring

- [x] 3.1 Update `SettingsWindow` to wire `TTSProviderTab.set_voice_tab_callback(voice_tab_obj.reload_for_provider)` instead of `voice_tab_obj.update_provider_sliders`

## 4. TTSProviderTab — remove stale instructional note

- [x] 4.1 Remove or revise the `CTkLabel` note in `TTSProviderTab` that instructs users to "save and reopen Settings to see the updated voice list"

## 5. Tests

- [x] 5.1 Add a unit test verifying that `TTSEngine.get_available_voices(provider_override="piper")` returns Piper voices regardless of the value stored in `settings_manager`
- [x] 5.2 Add a unit test verifying that calling `reload_for_provider` on `VoiceTab` triggers `_load_voices` with the correct `provider_override` argument
