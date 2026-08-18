"""Regression tests for audio cache identity boundaries."""
import sys
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.modules.setdefault("sounddevice", MagicMock())
sys.modules.setdefault("soundfile", MagicMock())
sys.modules.setdefault("pyloudnorm", MagicMock())
sys.modules.setdefault("keyboard", MagicMock())
sys.modules.setdefault("langid", MagicMock())

from src.tts.tts_engine import TTSEngine


def _make_engine(tmp_path, provider_name="edge"):
    current_provider = [provider_name]
    settings = MagicMock()

    def get_setting(key, default=None):
        values = {
            "tts_provider": current_provider[0],
            "audio_cache_enabled": True,
            "audio_cache_max_size_mb": 500,
            "audio_cache_path": str(tmp_path / "audio-cache"),
            "text_cache_size": 1000,
            "auto_language_detection": False,
        }
        return values.get(key, default)

    settings.get.side_effect = get_setting
    engine = TTSEngine(settings_manager=settings)
    engine.validate_voice = AsyncMock(return_value=True)
    engine.preprocess_text = AsyncMock(
        side_effect=lambda text, voice, provider_name=None: text.strip()
    )
    engine._phrase_tracker = MagicMock()
    engine._coqui_provider_instance = MagicMock()
    return engine, current_provider


@pytest.mark.asyncio
async def test_generate_speech_cache_isolated_by_provider(tmp_path):
    """The same text+voice should not reuse cached audio across different providers."""
    engine, current_provider = _make_engine(tmp_path)
    engine._edge_tts_provider.generate_speech = AsyncMock(return_value=b"edge-audio")
    engine._coqui_provider_instance.generate_speech = AsyncMock(return_value=b"coqui-audio")

    first_audio, first_error = await engine.generate_speech("Hello there", voice="shared-voice")
    current_provider[0] = "coqui"
    second_audio, second_error = await engine.generate_speech("Hello there", voice="shared-voice")

    try:
        assert first_error is None
        assert second_error is None
        assert first_audio == b"edge-audio"
        assert second_audio == b"coqui-audio"
        assert engine._edge_tts_provider.generate_speech.await_count == 1
        assert engine._coqui_provider_instance.generate_speech.await_count == 1
    finally:
        engine._audio_cache.shutdown()


@pytest.mark.asyncio
async def test_generate_speech_cache_isolated_by_voice(tmp_path):
    """The same text under different voices should remain cached separately."""
    engine, _ = _make_engine(tmp_path)
    engine._edge_tts_provider.generate_speech = AsyncMock(
        side_effect=[b"voice-a-audio", b"voice-b-audio"]
    )

    first_audio, first_error = await engine.generate_speech("Hello there", voice="voice-a")
    second_audio, second_error = await engine.generate_speech("Hello there", voice="voice-b")
    third_audio, third_error = await engine.generate_speech("Hello there", voice="voice-a")

    try:
        assert first_error is None
        assert second_error is None
        assert third_error is None
        assert first_audio == b"voice-a-audio"
        assert second_audio == b"voice-b-audio"
        assert third_audio == b"voice-a-audio"
        assert engine._edge_tts_provider.generate_speech.await_count == 2
    finally:
        engine._audio_cache.shutdown()


def test_audio_cache_fingerprint_tracks_coqui_stability_settings(tmp_path):
    """The cache fingerprint must change when Coqui sampling knobs change.

    Otherwise cached audio would silently be replayed under a different
    temperature/repetition penalty, undoing the staleness fix.
    """
    current = {
        "coqui_language": "en",
        "coqui_temperature": 0.75,
        "coqui_repetition_penalty": 10.0,
        "coqui_enable_text_splitting": True,
    }
    settings = MagicMock()

    def get_setting(key, default=None):
        values = {
            "tts_provider": "coqui",
            "audio_cache_enabled": True,
            "audio_cache_path": str(tmp_path / "audio-cache"),
        }
        values.update(current)
        return values.get(key, default)

    settings.get.side_effect = get_setting
    engine = TTSEngine(settings_manager=settings)

    try:
        base = engine._get_audio_cache_fingerprint("coqui")

        current["coqui_temperature"] = 0.4
        changed_temp = engine._get_audio_cache_fingerprint("coqui")
        assert base != changed_temp

        current["coqui_temperature"] = 0.75
        current["coqui_repetition_penalty"] = 15.0
        changed_rep = engine._get_audio_cache_fingerprint("coqui")
        assert base != changed_rep

        current["coqui_repetition_penalty"] = 10.0
        current["coqui_enable_text_splitting"] = False
        changed_split = engine._get_audio_cache_fingerprint("coqui")
        assert base != changed_split
    finally:
        engine._audio_cache.shutdown()


@pytest.mark.asyncio
async def test_pregenerate_skips_phrases_cached_under_processed_text(tmp_path):
    """Pregeneration must key its pre-check by processed text like generate_speech.

    Regression: the pre-check looked up the raw text while generate_speech()
    caches under the *preprocessed* text, so every pregen run re-invoked
    synthesis for already-cached phrases and over-counted them as generated.
    """
    engine, _ = _make_engine(tmp_path)
    # Preprocessing transforms text, as in production
    engine.preprocess_text = AsyncMock(
        side_effect=lambda text, voice, provider_name=None: f"[{text.strip()}]"
    )
    edge_provider = engine._edge_tts_provider
    edge_provider.generate_speech = AsyncMock(return_value=b"edge-audio")
    edge_provider.get_default_voice = MagicMock(return_value="SharedVoice")

    phrases = [("hello", "SharedVoice", 5), ("world", "SharedVoice", 3)]
    engine._phrase_tracker.get_common_phrases.return_value = phrases

    try:
        first_count = await engine.pregenerate_common_phrases()
        second_count = await engine.pregenerate_common_phrases()

        assert first_count == 2
        # Second run: everything is already cached under the processed key
        assert second_count == 0
        assert edge_provider.generate_speech.await_count == 2
        # Runtime lookup uses the same processed key and must hit the pregen entry
        cached, err = await engine.generate_speech("hello", "SharedVoice")
        assert err is None
        assert cached == b"edge-audio"
        assert edge_provider.generate_speech.await_count == 2
    finally:
        engine._audio_cache.shutdown()


@pytest.mark.asyncio
async def test_generate_speech_cache_isolated_by_synthesis_settings(tmp_path):
    """Changing a synthesis-affecting setting must regenerate, not replay stale audio.

    The same text/voice/provider with a different ``coqui_language`` must miss
    the cache and invoke the provider again; reverting to a previously used
    language must hit the matching entry.
    """
    current_language = ["en"]
    settings = MagicMock()

    def get_setting(key, default=None):
        values = {
            "tts_provider": "coqui",
            "audio_cache_enabled": True,
            "audio_cache_max_size_mb": 500,
            "audio_cache_path": str(tmp_path / "audio-cache"),
            "text_cache_size": 1000,
            "auto_language_detection": False,
            "coqui_language": current_language[0],
        }
        return values.get(key, default)

    settings.get.side_effect = get_setting
    engine = TTSEngine(settings_manager=settings)
    engine.validate_voice = AsyncMock(return_value=True)
    engine.preprocess_text = AsyncMock(
        side_effect=lambda text, voice, provider_name=None: text.strip()
    )
    engine._phrase_tracker = MagicMock()

    coqui_provider = MagicMock()
    coqui_provider.generate_speech = AsyncMock(side_effect=[b"en-audio", b"es-audio"])
    coqui_provider.get_default_voice.return_value = "Claribel Dervla"
    engine._coqui_provider_instance = coqui_provider

    try:
        first_audio, first_error = await engine.generate_speech(
            "Hello there", voice="Claribel Dervla"
        )
        current_language[0] = "es"
        second_audio, second_error = await engine.generate_speech(
            "Hello there", voice="Claribel Dervla"
        )
        # Same language again -> cache hit, no regeneration
        third_audio, third_error = await engine.generate_speech(
            "Hello there", voice="Claribel Dervla"
        )

        assert first_error is None
        assert second_error is None
        assert third_error is None
        assert first_audio == b"en-audio"
        assert second_audio == b"es-audio"
        assert third_audio == b"es-audio"
        assert coqui_provider.generate_speech.await_count == 2
    finally:
        engine._audio_cache.shutdown()


@pytest.mark.asyncio
async def test_pregenerate_stops_early_when_stop_event_set(tmp_path):
    """A set stop event must halt pre-generation between phrases."""
    engine, _ = _make_engine(tmp_path)
    engine.preprocess_text = AsyncMock(
        side_effect=lambda text, voice, provider_name=None: f"[{text.strip()}]"
    )
    edge_provider = engine._edge_tts_provider
    edge_provider.generate_speech = AsyncMock(return_value=b"edge-audio")
    edge_provider.get_default_voice = MagicMock(return_value="SharedVoice")

    phrases = [
        ("hello", "SharedVoice", 5),
        ("world", "SharedVoice", 3),
        ("again", "SharedVoice", 4),
    ]
    engine._phrase_tracker.get_common_phrases.return_value = phrases

    stop_event = threading.Event()

    # Signal stop from the progress callback, which fires *after* each phrase
    # completes — the loop must then break before the next phrase, and the stop
    # event must be forwarded into generate_speech for in-flight cancellation.
    def progress(generated: int, total: int):
        if generated == 1:
            stop_event.set()

    try:
        count = await engine.pregenerate_common_phrases(
            progress_callback=progress, stop_event=stop_event
        )

        assert count == 1
        assert edge_provider.generate_speech.await_count == 1
        # generate_speech forwards stop_event positionally to the provider
        assert edge_provider.generate_speech.await_args.args[-1] is stop_event
    finally:
        engine._audio_cache.shutdown()
