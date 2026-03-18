"""
Tests for PiperTTSProvider.

Covers:
- Voice list completeness and structure
- get_default_voice
- _rate_to_length_scale conversions
- _volume_to_scale conversions
- validate_voice (sync logic)
- clear_cache
- _build_model_url correctness
"""
import io
import wave
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

from src.tts.providers.piper_tts_provider import (
    PiperTTSProvider,
    _BUILTIN_VOICES,
    _VOICE_MAP,
    _build_model_url,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def provider(tmp_path) -> PiperTTSProvider:
    """Create a PiperTTSProvider backed by a temporary model directory."""
    return PiperTTSProvider(settings_manager=None, models_dir=tmp_path)


# ---------------------------------------------------------------------------
# Built-in voice list
# ---------------------------------------------------------------------------

class TestBuiltinVoices:
    def test_voices_list_is_non_empty(self):
        assert len(_BUILTIN_VOICES) > 0

    def test_all_voices_have_required_keys(self):
        required = {"name", "short_name", "gender", "locale", "language_code", "quality", "provider"}
        for v in _BUILTIN_VOICES:
            missing = required - v.keys()
            assert not missing, f"Voice {v.get('short_name')} missing keys: {missing}"

    def test_all_voices_have_piper_provider(self):
        for v in _BUILTIN_VOICES:
            assert v["provider"] == "piper", f"Expected provider='piper' for {v['short_name']}"

    def test_voice_map_matches_builtin_list(self):
        assert set(_VOICE_MAP.keys()) == {v["short_name"] for v in _BUILTIN_VOICES}


# ---------------------------------------------------------------------------
# Model URL construction
# ---------------------------------------------------------------------------

class TestBuildModelUrl:
    def test_onnx_url(self):
        url = _build_model_url("en_US-lessac-medium", ".onnx")
        assert "en_US-lessac-medium.onnx" in url
        assert url.startswith("https://")

    def test_json_url(self):
        url = _build_model_url("en_US-lessac-medium", ".onnx.json")
        assert "en_US-lessac-medium.onnx.json" in url

    def test_url_contains_correct_path_segments(self):
        url = _build_model_url("de_DE-thorsten-medium", ".onnx")
        assert "/de/" in url
        assert "/de_DE/" in url
        assert "/thorsten/" in url
        assert "/medium/" in url

    def test_invalid_short_name_raises(self):
        with pytest.raises(ValueError):
            _build_model_url("badname", ".onnx")


# ---------------------------------------------------------------------------
# Prosody helpers
# ---------------------------------------------------------------------------

class TestRateToLengthScale:
    def test_zero_rate_is_normal(self):
        assert PiperTTSProvider._rate_to_length_scale(0) == pytest.approx(1.0)

    def test_positive_rate_is_faster(self):
        fast = PiperTTSProvider._rate_to_length_scale(100)
        assert fast < 1.0

    def test_negative_rate_is_slower(self):
        slow = PiperTTSProvider._rate_to_length_scale(-100)
        assert slow > 1.0

    def test_rate_clamped_above(self):
        # Values above 100 should be treated as 100
        assert PiperTTSProvider._rate_to_length_scale(200) == PiperTTSProvider._rate_to_length_scale(100)

    def test_rate_clamped_below(self):
        assert PiperTTSProvider._rate_to_length_scale(-200) == PiperTTSProvider._rate_to_length_scale(-100)

    def test_never_zero_or_negative(self):
        for rate in [-100, -50, 0, 50, 100]:
            assert PiperTTSProvider._rate_to_length_scale(rate) > 0


class TestVolumeToScale:
    def test_100_maps_to_1(self):
        assert PiperTTSProvider._volume_to_scale(100) == pytest.approx(1.0)

    def test_0_maps_to_0(self):
        assert PiperTTSProvider._volume_to_scale(0) == pytest.approx(0.0)

    def test_50_maps_to_half(self):
        assert PiperTTSProvider._volume_to_scale(50) == pytest.approx(0.5)

    def test_clamped_above(self):
        assert PiperTTSProvider._volume_to_scale(200) == pytest.approx(1.0)

    def test_clamped_below(self):
        assert PiperTTSProvider._volume_to_scale(-10) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# validate_voice
# ---------------------------------------------------------------------------

class TestValidateVoice:
    @pytest.mark.asyncio
    async def test_known_voice_is_valid(self, provider):
        assert await provider.validate_voice("en_US-lessac-medium") is True

    @pytest.mark.asyncio
    async def test_unknown_voice_is_invalid(self, provider):
        assert await provider.validate_voice("en-US-AriaNeural") is False

    @pytest.mark.asyncio
    async def test_empty_string_is_invalid(self, provider):
        assert await provider.validate_voice("") is False


# ---------------------------------------------------------------------------
# get_default_voice
# ---------------------------------------------------------------------------

class TestGetDefaultVoice:
    def test_returns_a_string(self, provider):
        assert isinstance(provider.get_default_voice(), str)

    def test_default_voice_is_in_voice_map(self, provider):
        assert provider.get_default_voice() in _VOICE_MAP


# ---------------------------------------------------------------------------
# get_available_voices
# ---------------------------------------------------------------------------

class TestGetAvailableVoices:
    @pytest.mark.asyncio
    async def test_returns_all_builtin_voices(self, provider):
        voices = await provider.get_available_voices()
        assert voices == _BUILTIN_VOICES

    @pytest.mark.asyncio
    async def test_voices_are_independent_copy(self, provider):
        voices = await provider.get_available_voices()
        voices.clear()
        # Calling again should still return the full list
        voices2 = await provider.get_available_voices()
        assert len(voices2) > 0


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------

class TestClearCache:
    def test_clear_cache_empties_loaded_models(self, provider):
        provider._loaded_models["fake"] = MagicMock()
        provider.clear_cache()
        assert provider._loaded_models == {}


# ---------------------------------------------------------------------------
# generate_speech (mocked synthesis)
# ---------------------------------------------------------------------------

def _make_minimal_wav(sample_rate: int = 22050) -> bytes:
    """Create a minimal valid WAV file with one sample of silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00")
    return buf.getvalue()


class TestGenerateSpeech:
    @pytest.mark.asyncio
    async def test_returns_wav_bytes(self, provider):
        wav_output = _make_minimal_wav()

        with patch.object(provider, "_synthesize_blocking", return_value=wav_output):
            result = await provider.generate_speech("Hello world", "en_US-lessac-medium")

        assert result == wav_output

    @pytest.mark.asyncio
    async def test_returns_none_when_stop_event_set(self, provider):
        import threading
        stop = threading.Event()
        stop.set()

        result = await provider.generate_speech("Hello", "en_US-lessac-medium", stop_event=stop)
        assert result is None
