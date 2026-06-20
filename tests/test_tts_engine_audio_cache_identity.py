"""Regression tests for audio cache identity boundaries."""
import sys
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
