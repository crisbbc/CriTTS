"""
Tests for TTSEngine.get_available_voices() cache invalidation.

Verifies that the voices cache is automatically busted whenever the active
TTS provider changes, so that switching between Edge TTS and Coqui TTS
always returns the new provider's voice list rather than stale cached data.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys

# Mock heavy GUI / audio dependencies that are not needed for engine tests
sys.modules.setdefault("sounddevice", MagicMock())
sys.modules.setdefault("soundfile", MagicMock())
sys.modules.setdefault("pyloudnorm", MagicMock())
sys.modules.setdefault("keyboard", MagicMock())
sys.modules.setdefault("langid", MagicMock())

from src.tts.tts_engine import TTSEngine
from src.tts.audio_cache import AudioCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(provider: str = "edge") -> TTSEngine:
    """Create a TTSEngine backed by a mock SettingsManager."""
    mgr = MagicMock()
    mgr.get.side_effect = lambda key, default=None: (
        provider if key == "tts_provider" else default
    )
    return TTSEngine(settings_manager=mgr)


_EDGE_VOICES = [{"name": "Aria", "short_name": "en-US-AriaNeural", "provider": "edge_tts"}]
_COQUI_VOICES = [{"name": "Claribel Dervla", "short_name": "Claribel Dervla", "provider": "coqui"}]
_PIPER_VOICES = [{"name": "Lessac", "short_name": "en_US-lessac-medium", "provider": "piper"}]


# ---------------------------------------------------------------------------
# Cache respects provider identity
# ---------------------------------------------------------------------------

class TestGetAvailableVoicesCacheInvalidation:

    @pytest.mark.asyncio
    async def test_provider_override_fetches_requested_provider_without_cache_pollution(self):
        """provider_override fetches the requested provider and leaves active-provider cache untouched."""
        engine = _make_engine("edge")
        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))
        piper_fetch = AsyncMock(return_value=list(_PIPER_VOICES))

        with (
            patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch),
            patch.object(engine._piper_tts_provider, "get_available_voices", new=piper_fetch),
        ):
            # Override fetch should return Coqui voices even when settings provider is Edge.
            override_voices = await engine.get_available_voices(provider_override="coqui")
            assert any(v["provider"] == "coqui" for v in override_voices)
            assert engine._coqui_provider_instance is None
            assert edge_fetch.call_count == 0
            assert piper_fetch.call_count == 0

            # Piper override should also work without affecting the active provider cache.
            piper_override_voices = await engine.get_available_voices(provider_override="piper")
            assert any(v["provider"] == "piper" for v in piper_override_voices)
            assert piper_fetch.call_count == 1

            # Regular fetch still resolves and caches using the active settings provider.
            active_voices = await engine.get_available_voices()
            assert any(v["provider"] == "edge_tts" for v in active_voices)
            assert edge_fetch.call_count == 1
            assert engine._cached_provider == "edge"

    @pytest.mark.asyncio
    async def test_cache_hit_same_provider(self):
        """Second call with the same provider returns cached result (no provider fetch)."""
        engine = _make_engine("edge")
        with patch.object(
            engine._edge_tts_provider, "get_available_voices",
            new=AsyncMock(return_value=list(_EDGE_VOICES))
        ) as mock_fetch:
            await engine.get_available_voices()
            await engine.get_available_voices()

        assert mock_fetch.call_count == 1, "Should only fetch once when provider is unchanged"

    @pytest.mark.asyncio
    async def test_cache_bust_on_provider_switch(self):
        """Switching the provider invalidates the cache and fetches from the new provider."""
        # Start as Edge TTS
        mgr = MagicMock()
        current_provider = ["edge"]
        mgr.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else default
        )
        engine = TTSEngine(settings_manager=mgr)

        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))

        with (
            patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch),
        ):
            # First call – Edge TTS
            voices_edge = await engine.get_available_voices()
            assert any(v["provider"] == "edge_tts" for v in voices_edge)
            assert edge_fetch.call_count == 1

            # Switch provider to Coqui (simulates settings change)
            current_provider[0] = "coqui"

            # Second call – should bypass the Edge TTS cache and fetch Coqui voices
            voices_coqui = await engine.get_available_voices()
            assert any(v["provider"] == "coqui" for v in voices_coqui)
            assert edge_fetch.call_count == 1, "Edge TTS should not be fetched again"
            assert engine._coqui_provider_instance is None

    @pytest.mark.asyncio
    async def test_switching_back_refetches_edge(self):
        """Switching back from Coqui to Edge TTS also busts the cache."""
        mgr = MagicMock()
        current_provider = ["coqui"]
        mgr.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else default
        )
        engine = TTSEngine(settings_manager=mgr)

        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))
        coqui_fetch = AsyncMock(return_value=list(_COQUI_VOICES))

        with (
            patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch),
            patch.object(engine._coqui_tts_provider, "get_available_voices", new=coqui_fetch),
        ):
            await engine.get_available_voices()  # Coqui cached
            current_provider[0] = "edge"
            voices = await engine.get_available_voices()  # Should re-fetch Edge

        assert any(v["provider"] == "edge_tts" for v in voices)
        assert edge_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_bust_on_switch_to_piper(self):
        """Switching from Edge TTS to Piper invalidates the cache and fetches Piper voices."""
        mgr = MagicMock()
        current_provider = ["edge"]
        mgr.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else default
        )
        engine = TTSEngine(settings_manager=mgr)

        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))
        piper_fetch = AsyncMock(return_value=list(_PIPER_VOICES))

        with (
            patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch),
            patch.object(engine._piper_tts_provider, "get_available_voices", new=piper_fetch),
        ):
            voices_edge = await engine.get_available_voices()
            assert any(v["provider"] == "edge_tts" for v in voices_edge)

            current_provider[0] = "piper"
            voices_piper = await engine.get_available_voices()

        assert any(v["provider"] == "piper" for v in voices_piper)
        assert edge_fetch.call_count == 1
        assert piper_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_clear_voices_cache_resets_provider_tracking(self):
        """clear_voices_cache() resets _cached_provider so next call always refetches."""
        engine = _make_engine("edge")
        edge_fetch = AsyncMock(return_value=list(_EDGE_VOICES))

        with patch.object(engine._edge_tts_provider, "get_available_voices", new=edge_fetch):
            await engine.get_available_voices()  # Populates cache
            engine.clear_voices_cache()           # Should also reset _cached_provider
            await engine.get_available_voices()   # Must refetch

        assert edge_fetch.call_count == 2
        assert engine._cached_provider == "edge"

    def test_clear_voices_cache_clears_all_provider_caches(self):
        """clear_voices_cache() clears Edge, Coqui, and Piper provider caches."""
        engine = _make_engine("edge")

        with (
            patch.object(engine._edge_tts_provider, "clear_cache") as edge_clear,
            patch.object(engine._coqui_tts_provider, "clear_cache") as coqui_clear,
            patch.object(engine._piper_tts_provider, "clear_cache") as piper_clear,
        ):
            engine.clear_voices_cache()

        edge_clear.assert_called_once_with()
        coqui_clear.assert_called_once_with()
        piper_clear.assert_called_once_with()


class TestLazyOfflineProviders:
    def test_init_does_not_create_offline_providers(self):
        """TTSEngine startup should not eagerly construct Coqui or Piper providers."""
        with (
            patch.object(TTSEngine, "_create_coqui_provider") as create_coqui,
            patch.object(TTSEngine, "_create_piper_provider") as create_piper,
        ):
            _make_engine("edge")

        create_coqui.assert_not_called()
        create_piper.assert_not_called()

    @pytest.mark.asyncio
    async def test_provider_override_lazily_creates_requested_offline_provider(self):
        """provider_override should create the requested offline provider on demand."""
        engine = _make_engine("edge")
        piper_provider = MagicMock()
        piper_provider.get_available_voices = AsyncMock(return_value=list(_PIPER_VOICES))

        with (
            patch.object(engine, "_create_coqui_provider") as create_coqui,
            patch.object(engine, "_create_piper_provider", return_value=piper_provider) as create_piper,
        ):
            voices = await engine.get_available_voices(provider_override="piper")

        assert any(v["provider"] == "piper" for v in voices)
        create_coqui.assert_not_called()
        create_piper.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_provider_override_coqui_voice_list_stays_metadata_only_pre_synthesis(self):
        """Coqui preview voice fetches should not import the heavyweight provider module."""
        engine = _make_engine("edge")

        with patch("src.tts.tts_engine.import_module", side_effect=AssertionError("heavy provider import")):
            voices = await engine.get_available_voices(provider_override="coqui")

        assert any(v["provider"] == "coqui" for v in voices)
        assert engine._coqui_provider_instance is None

    @pytest.mark.asyncio
    async def test_active_coqui_voice_list_stays_metadata_only_pre_synthesis(self):
        """Active-provider Coqui voice fetches should not import the heavyweight provider module."""
        engine = _make_engine("coqui")

        with patch("src.tts.tts_engine.import_module", side_effect=AssertionError("heavy provider import")):
            voices = await engine.get_available_voices()

        assert any(v["provider"] == "coqui" for v in voices)
        assert engine._coqui_provider_instance is None

    def test_set_coqui_status_callback_waits_for_lazy_provider_creation(self):
        """Registering Coqui status feedback should not eagerly construct the provider."""
        engine = _make_engine("edge")
        callback = MagicMock()
        coqui_provider = MagicMock()

        with patch.object(engine, "_create_coqui_provider", return_value=coqui_provider) as create_coqui:
            engine.set_coqui_status_callback(callback)
            create_coqui.assert_not_called()

            provider = engine._get_provider_by_name("coqui")

        assert provider is coqui_provider
        create_coqui.assert_called_once_with()
        coqui_provider.set_status_callback.assert_called_once_with(callback)


class TestCommittedProviderLifecycle:
    def test_committed_switch_away_from_coqui_clears_inactive_model_state(self):
        """Committed provider changes should release inactive Coqui state."""
        mgr = MagicMock()
        current_provider = ["coqui"]
        mgr.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else default
        )
        engine = TTSEngine(settings_manager=mgr)

        with patch.object(engine._coqui_tts_provider, "clear_cache") as coqui_clear:
            engine.handle_committed_provider_change()
            coqui_clear.assert_not_called()

            current_provider[0] = "edge"
            engine.handle_committed_provider_change()

        coqui_clear.assert_called_once_with()


class TestAudioCacheIsolation:
    def test_audio_cache_isolates_entries_by_provider_and_voice(self, tmp_path):
        """Same text must remain distinct across providers and voices."""
        cache = AudioCache(cache_dir=tmp_path, enabled=True)

        try:
            assert cache.store(
                b"edge-audio",
                "Hello there",
                "SharedVoice",
                provider="edge",
            )
            assert cache.store(
                b"coqui-audio",
                "Hello there",
                "SharedVoice",
                provider="coqui",
            )
            assert cache.store(
                b"other-voice-audio",
                "Hello there",
                "OtherVoice",
                provider="edge",
            )

            assert cache.lookup("Hello there", "SharedVoice", provider="edge") == b"edge-audio"
            assert cache.lookup("Hello there", "SharedVoice", provider="coqui") == b"coqui-audio"
            assert cache.lookup("Hello there", "OtherVoice", provider="edge") == b"other-voice-audio"
            assert cache.get_statistics()["entries"] == 3
        finally:
            cache.shutdown()

    def test_audio_cache_isolates_entries_by_settings_fingerprint(self, tmp_path):
        """Same text/voice under different synthesis settings must not collide.

        Changing a synthesis-affecting setting (Coqui language, Piper noise
        scales, EQ/normalization/profile) must be a cache miss — otherwise the
        app silently replays audio recorded under a different configuration.
        """
        fp_default = "lang=en|eq=1|norm=1:Peak|prof=balanced"
        fp_spanish = "lang=es|eq=1|norm=1:Peak|prof=balanced"
        fp_different = "lang=de|eq=1|norm=1:Peak|prof=balanced"
        cache = AudioCache(cache_dir=tmp_path, enabled=True)

        try:
            assert cache.store(
                b"en-audio",
                "Hello there",
                "SharedVoice",
                provider="coqui",
                settings_fingerprint=fp_default,
            )
            assert cache.store(
                b"es-audio",
                "Hello there",
                "SharedVoice",
                provider="coqui",
                settings_fingerprint=fp_spanish,
            )

            assert cache.lookup(
                "Hello there", "SharedVoice", provider="coqui",
                settings_fingerprint=fp_default,
            ) == b"en-audio"
            assert cache.lookup(
                "Hello there", "SharedVoice", provider="coqui",
                settings_fingerprint=fp_spanish,
            ) == b"es-audio"
            # A fingerprint change must miss, never return stale audio
            assert cache.lookup(
                "Hello there", "SharedVoice", provider="coqui",
                settings_fingerprint=fp_different,
            ) is None
            # Entries written without a fingerprint are also isolated from them
            assert cache.store(
                b"legacy-style-audio",
                "Hello there",
                "SharedVoice",
                provider="coqui",
            )
            assert cache.lookup(
                "Hello there", "SharedVoice", provider="coqui",
            ) == b"legacy-style-audio"
            assert cache.get_statistics()["entries"] == 3
        finally:
            cache.shutdown()

    def test_schema_version_mismatch_invalidates_legacy_cache_entries(self, tmp_path):
        """Legacy cache files should be invalidated when the cache-key schema changes."""
        legacy_key = "legacy-providerless-entry"
        (tmp_path / f"{legacy_key}.mp3").write_bytes(b"legacy-audio")
        (tmp_path / "cache_index.json").write_text(
            json.dumps(
                {
                    "version": AudioCache.CACHE_VERSION - 1,
                    "entries": {
                        legacy_key: {
                            "text": "Hello there",
                            "voice": "SharedVoice",
                            "rate": 0,
                            "volume": 100,
                            "pitch": 0,
                            "size_bytes": 12,
                            "created": 1,
                            "last_access": 1,
                            "access_count": 0,
                            "generation_time": 0,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        cache = AudioCache(cache_dir=tmp_path, enabled=True)

        try:
            assert cache.get_statistics()["entries"] == 0
            assert not (tmp_path / f"{legacy_key}.mp3").exists()
        finally:
            cache.shutdown()


class TestGenerateSpeechCacheIsolation:
    @pytest.mark.asyncio
    async def test_generate_speech_cache_isolated_by_provider(self, tmp_path):
        """Switching providers must not reuse cached audio generated by another provider."""
        current_provider = ["edge"]
        settings = {
            "audio_cache_enabled": True,
            "audio_cache_max_size_mb": 500,
            "audio_cache_path": str(tmp_path),
            "tts_provider": current_provider[0],
        }
        manager = MagicMock()
        manager.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else settings.get(key, default)
        )
        engine = TTSEngine(settings_manager=manager)

        edge_provider = engine._edge_tts_provider
        edge_provider.generate_speech = AsyncMock(return_value=b"edge-audio")
        edge_provider.get_default_voice = MagicMock(return_value="SharedVoice")

        coqui_provider = MagicMock()
        coqui_provider.generate_speech = AsyncMock(return_value=b"coqui-audio")
        coqui_provider.get_default_voice.return_value = "SharedVoice"
        engine._coqui_provider_instance = coqui_provider

        engine.validate_voice = AsyncMock(return_value=True)
        engine.preprocess_text = AsyncMock(
            side_effect=lambda text, voice, provider_name=None: text
        )

        try:
            edge_audio, edge_error = await engine.generate_speech("Hello there", "SharedVoice")
            assert edge_error is None
            assert edge_audio == b"edge-audio"

            current_provider[0] = "coqui"
            coqui_audio, coqui_error = await engine.generate_speech("Hello there", "SharedVoice")
            assert coqui_error is None
            assert coqui_audio == b"coqui-audio"

            current_provider[0] = "edge"
            cached_edge_audio, cached_edge_error = await engine.generate_speech("Hello there", "SharedVoice")
            assert cached_edge_error is None
            assert cached_edge_audio == b"edge-audio"
        finally:
            if engine._audio_cache is not None:
                engine._audio_cache.shutdown()
            if engine._phrase_tracker is not None:
                engine._phrase_tracker.shutdown()

        assert edge_provider.generate_speech.await_count == 1
        assert coqui_provider.generate_speech.await_count == 1


class TestGenerateSpeechMidCallProviderChange:
    """Regression tests: provider snapshoted once per generate_speech() call.

    If ``tts_provider`` changes during preprocessing the audio must still be
    generated by—and cached under—the provider that was active when the call
    started (provider A), not the provider that is active after preprocessing
    completes (provider B).
    """

    @pytest.mark.asyncio
    async def test_mid_call_provider_flip_uses_snapshot_provider(self, tmp_path):
        """Provider-A audio must not be cached under Provider-B's cache key.

        Scenario
        --------
        1. ``tts_provider`` is ``"edge"`` when ``generate_speech()`` starts.
        2. During ``preprocess_text()`` the setting flips to ``"coqui"``.
        3. The first call must:
           - use the edge provider for generation (provider A),
           - store the result under the edge cache key.
        4. The second call with ``tts_provider="coqui"`` must NOT find a cache
           hit (edge audio must not be replayed as coqui audio) and must invoke
           the coqui provider.
        """
        current_provider = ["edge"]
        settings = {
            "audio_cache_enabled": True,
            "audio_cache_max_size_mb": 500,
            "audio_cache_path": str(tmp_path),
        }
        manager = MagicMock()
        manager.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else settings.get(key, default)
        )
        engine = TTSEngine(settings_manager=manager)

        edge_provider = engine._edge_tts_provider
        edge_provider.generate_speech = AsyncMock(return_value=b"edge-audio")
        edge_provider.get_default_voice = MagicMock(return_value="SharedVoice")

        coqui_provider = MagicMock()
        coqui_provider.generate_speech = AsyncMock(return_value=b"coqui-audio")
        coqui_provider.get_default_voice.return_value = "SharedVoice"
        engine._coqui_provider_instance = coqui_provider

        engine.validate_voice = AsyncMock(return_value=True)

        def _preprocess_and_flip(text, voice, provider_name=None):
            # Simulate the race: flip the provider setting mid-call, after
            # the provider snapshot has already been taken.
            current_provider[0] = "coqui"
            return text

        engine.preprocess_text = AsyncMock(side_effect=_preprocess_and_flip)

        try:
            # Call 1: starts as "edge", flips to "coqui" during preprocess_text.
            # Must use edge provider and cache under "edge" key.
            audio1, err1 = await engine.generate_speech("Hello there", "SharedVoice")
            assert err1 is None
            assert audio1 == b"edge-audio", (
                "First call must return provider-A (edge) audio even after mid-call flip"
            )
            assert edge_provider.generate_speech.await_count == 1
            assert coqui_provider.generate_speech.await_count == 0, (
                "Coqui must NOT be invoked during a call that started as edge"
            )

            # After the flip current_provider is now "coqui".
            # Call 2: starts and stays as "coqui"; should NOT hit the edge cache
            # entry and must invoke the coqui provider.
            # Reset preprocess_text to a no-op (no more flips).
            engine.preprocess_text = AsyncMock(
                side_effect=lambda text, voice, provider_name=None: text
            )

            audio2, err2 = await engine.generate_speech("Hello there", "SharedVoice")
            assert err2 is None
            assert audio2 == b"coqui-audio", (
                "Second call under coqui must not reuse the edge cache entry"
            )
            assert coqui_provider.generate_speech.await_count == 1, (
                "Coqui provider must be invoked for the coqui call"
            )
            # Edge should still only have been called once (no spurious re-call).
            assert edge_provider.generate_speech.await_count == 1
        finally:
            if engine._audio_cache is not None:
                engine._audio_cache.shutdown()
            if engine._phrase_tracker is not None:
                engine._phrase_tracker.shutdown()


class TestProviderStableValidationAndPreprocessing:
    @pytest.mark.asyncio
    async def test_validate_voice_cache_is_scoped_by_provider(self):
        current_provider = ["edge"]
        manager = MagicMock()
        manager.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else default
        )
        engine = TTSEngine(settings_manager=manager)

        engine.get_available_voices = AsyncMock(
            side_effect=lambda provider_override=None: (
                [{"short_name": "SharedVoice"}]
                if provider_override == "edge"
                else []
            )
        )

        assert await engine.validate_voice("SharedVoice", provider_name="edge") is True
        assert await engine.validate_voice("SharedVoice", provider_name="coqui") is False

    @pytest.mark.asyncio
    async def test_generate_speech_passes_snapshot_provider_to_validation_and_preprocessing(
        self, tmp_path
    ):
        current_provider = ["edge"]
        settings = {
            "audio_cache_enabled": True,
            "audio_cache_max_size_mb": 500,
            "audio_cache_path": str(tmp_path),
        }
        manager = MagicMock()
        manager.get.side_effect = lambda key, default=None: (
            current_provider[0] if key == "tts_provider" else settings.get(key, default)
        )
        engine = TTSEngine(settings_manager=manager)

        edge_provider = engine._edge_tts_provider
        edge_provider.generate_speech = AsyncMock(return_value=b"edge-audio")
        edge_provider.get_default_voice = MagicMock(return_value="SharedVoice")

        async def _validate(voice, provider_name=None):
            return provider_name == "edge"

        async def _preprocess(text, voice, provider_name=None):
            current_provider[0] = "coqui"
            return text if provider_name == "edge" else f"wrong:{text}"

        engine.validate_voice = AsyncMock(side_effect=_validate)
        engine.preprocess_text = AsyncMock(side_effect=_preprocess)

        try:
            audio, error = await engine.generate_speech("Hello there", "SharedVoice")
        finally:
            if engine._audio_cache is not None:
                engine._audio_cache.shutdown()
            if engine._phrase_tracker is not None:
                engine._phrase_tracker.shutdown()

        assert error is None
        assert audio == b"edge-audio"
        edge_provider.generate_speech.assert_awaited_once_with(
            "Hello there", "SharedVoice", 0, 100, 0, None
        )
        assert engine.validate_voice.await_args_list[0].kwargs == {"provider_name": "edge"}
        assert engine.preprocess_text.await_args.kwargs == {"provider_name": "edge"}


# ---------------------------------------------------------------------------
# A mocked audio_cache_path must never become a real on-disk directory
# ---------------------------------------------------------------------------

def test_coerce_cache_path_rejects_mock_values():
    """Only str/Path values are valid cache paths; mocks fall back to default."""
    from pathlib import Path

    assert TTSEngine._coerce_cache_path(MagicMock()) is None
    # `Path(MagicMock())` -> 'MagicMock/mock.get()/…' which AudioCache would mkdir
    assert TTSEngine._coerce_cache_path(MagicMock().get("audio_cache_path")) is None
    assert TTSEngine._coerce_cache_path(None) is None
    assert TTSEngine._coerce_cache_path(123) is None
    # bytes are not a valid Path in Python 3.14, so they must be rejected too
    assert TTSEngine._coerce_cache_path(b"/tmp/audio-cache") is None
    assert TTSEngine._coerce_cache_path("/tmp/audio-cache") == Path("/tmp/audio-cache")
    real_path = Path("/tmp/audio-cache")
    assert TTSEngine._coerce_cache_path(real_path) == real_path


def test_mock_audio_cache_path_falls_back_to_default_cache_dir():
    """A mocked audio_cache_path must not be turned into a MagicMock directory.

    Regression: TTSEngine passed ``Path(settings.get("audio_cache_path"))``
    straight to AudioCache, and ``pathlib.Path`` converts a MagicMock into a
    relative ``MagicMock/mock.get()/…`` path that AudioCache then created on
    disk in the working directory.
    """
    manager = MagicMock()

    def get(key, default=None):
        values = {
            "audio_cache_enabled": True,
            "audio_cache_max_size_mb": 500,
            "text_cache_size": 1000,
        }
        if key == "audio_cache_path":
            return MagicMock()  # simulate an unconfigured mock settings manager
        return values.get(key, default)

    manager.get.side_effect = get
    engine = TTSEngine(settings_manager=manager)
    try:
        assert "MagicMock" not in str(engine._audio_cache.cache_dir)
    finally:
        if engine._audio_cache is not None:
            engine._audio_cache.shutdown()
        if engine._phrase_tracker is not None:
            engine._phrase_tracker.shutdown()
