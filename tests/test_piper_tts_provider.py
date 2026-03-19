"""
Tests for PiperTTSProvider.

Covers:
- Voice list completeness and structure
- get_default_voice
- _rate_to_length_scale conversions
- _volume_to_scale conversions
- _get_noise_scale / _get_noise_w_scale helpers
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


# ---------------------------------------------------------------------------
# status_callback
# ---------------------------------------------------------------------------

class TestStatusCallback:
    def test_set_status_callback_stores_callable(self, provider):
        cb = MagicMock()
        provider.set_status_callback(cb)
        assert provider._status_callback is cb

    def test_set_status_callback_accepts_none(self, provider):
        provider.set_status_callback(None)
        assert provider._status_callback is None

    def test_download_file_calls_callback(self, tmp_path):
        """_download_file should invoke the status_callback before downloading."""
        received = []

        def cb(msg):
            received.append(msg)

        dest = tmp_path / "model.onnx"
        fake_content = b"fake onnx data"

        with patch("src.tts.providers.piper_tts_provider.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read = MagicMock(return_value=b"")
            mock_open.return_value = mock_resp

            import shutil as _shutil
            with patch("src.tts.providers.piper_tts_provider.shutil.copyfileobj"):
                # Actually write something so rename succeeds
                tmp_file = dest.with_suffix(dest.suffix + ".tmp")
                tmp_file.write_bytes(fake_content)

                from src.tts.providers.piper_tts_provider import _download_file
                _download_file("https://example.com/model.onnx", dest, status_callback=cb)

        assert len(received) == 1
        assert "model.onnx" in received[0]

    def test_load_voice_calls_callback_on_first_load(self, tmp_path):
        """_load_voice should invoke the status_callback when loading a new model."""
        cb = MagicMock()
        provider = PiperTTSProvider(models_dir=tmp_path, status_callback=cb)

        fake_voice = MagicMock()
        with patch("src.tts.providers.piper_tts_provider._ensure_model", return_value=tmp_path / "x.onnx"):
            with patch("src.tts.providers.piper_tts_provider.PiperVoice.load", return_value=fake_voice):
                provider._load_voice("en_US-lessac-medium")

        cb.assert_called()
        messages = [call.args[0] for call in cb.call_args_list]
        assert any("Loading Piper model" in m for m in messages)

    def test_load_voice_no_callback_on_cached_voice(self, tmp_path):
        """_load_voice should NOT invoke the callback when the model is already cached."""
        cb = MagicMock()
        provider = PiperTTSProvider(models_dir=tmp_path, status_callback=cb)
        provider._loaded_models["en_US-lessac-medium"] = MagicMock()

        provider._load_voice("en_US-lessac-medium")

        cb.assert_not_called()


# ---------------------------------------------------------------------------
# Naturalness helpers: _get_noise_scale / _get_noise_w_scale
# ---------------------------------------------------------------------------

class TestNoiseScaleHelpers:
    """Tests for the noise_scale and noise_w_scale naturalness helpers."""

    def test_default_noise_scale_without_settings_manager(self, tmp_path):
        """Without a settings manager, noise_scale should fall back to 0.667."""
        p = PiperTTSProvider(settings_manager=None, models_dir=tmp_path)
        assert p._get_noise_scale() == pytest.approx(0.667)

    def test_default_noise_w_scale_without_settings_manager(self, tmp_path):
        """Without a settings manager, noise_w_scale should fall back to 0.8."""
        p = PiperTTSProvider(settings_manager=None, models_dir=tmp_path)
        assert p._get_noise_w_scale() == pytest.approx(0.8)

    def test_noise_scale_reads_from_settings_manager(self, tmp_path):
        """noise_scale should be read from the settings manager when present."""
        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: {
            "piper_noise_scale": 1.2,
            "piper_noise_w_scale": 0.5,
        }.get(key, default)
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_scale() == pytest.approx(1.2)

    def test_noise_w_scale_reads_from_settings_manager(self, tmp_path):
        """noise_w_scale should be read from the settings manager when present."""
        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: {
            "piper_noise_scale": 0.667,
            "piper_noise_w_scale": 0.5,
        }.get(key, default)
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_w_scale() == pytest.approx(0.5)

    def test_noise_scale_clamped_to_zero(self, tmp_path):
        """Negative noise_scale values should be clamped to 0.0."""
        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: {"piper_noise_scale": -1.0}.get(key, default)
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_scale() == pytest.approx(0.0)

    def test_noise_scale_clamped_to_max(self, tmp_path):
        """noise_scale values above 2.0 should be clamped to 2.0."""
        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: {"piper_noise_scale": 99.0}.get(key, default)
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_scale() == pytest.approx(2.0)

    def test_noise_w_scale_clamped_to_max(self, tmp_path):
        """noise_w_scale values above 2.0 should be clamped to 2.0."""
        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: {"piper_noise_w_scale": 5.0}.get(key, default)
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_w_scale() == pytest.approx(2.0)

    def test_invalid_noise_scale_falls_back_to_default(self, tmp_path):
        """A non-numeric noise_scale should fall back to the 0.667 default."""
        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: {"piper_noise_scale": "bad"}.get(key, default)
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_scale() == pytest.approx(0.667)

    def test_invalid_noise_w_scale_falls_back_to_default(self, tmp_path):
        """A non-numeric noise_w_scale (None) should fall back to the 0.8 default."""
        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: {"piper_noise_w_scale": None}.get(key, default)
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_w_scale() == pytest.approx(0.8)

    def test_noise_w_scale_missing_key_returns_default(self, tmp_path):
        """When piper_noise_w_scale is absent, get() should return the caller's default (0.8)."""
        sm = MagicMock()
        # Key is not in the dict at all, so the passed-in default is returned
        sm.get.side_effect = lambda key, default=None: default
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_w_scale() == pytest.approx(0.8)

    def test_noise_scale_missing_key_returns_default(self, tmp_path):
        """When piper_noise_scale is absent, get() should return the caller's default (0.667)."""
        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: default
        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)
        assert p._get_noise_scale() == pytest.approx(0.667)

    def test_synthesize_blocking_passes_noise_params(self, tmp_path):
        """_synthesize_blocking should forward noise_scale and noise_w_scale to SynthesisConfig."""
        import wave as _wave
        from unittest.mock import call as _call

        sm = MagicMock()
        sm.get.side_effect = lambda key, default=None: {
            "piper_noise_scale": 0.9,
            "piper_noise_w_scale": 0.6,
        }.get(key, default)

        p = PiperTTSProvider(settings_manager=sm, models_dir=tmp_path)

        # Create a minimal WAV buffer to return from synthesize_wav
        wav_buf = io.BytesIO()
        with _wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"\x00\x00")
        wav_bytes = wav_buf.getvalue()

        captured_cfg = []

        def fake_synthesize_wav(text, wav_file, syn_config=None):
            captured_cfg.append(syn_config)
            # Write the pre-built WAV frames into the file
            with _wave.open(io.BytesIO(wav_bytes), "rb") as src:
                wav_file.setnchannels(src.getnchannels())
                wav_file.setsampwidth(src.getsampwidth())
                wav_file.setframerate(src.getframerate())
                wav_file.writeframes(src.readframes(src.getnframes()))

        fake_voice = MagicMock()
        fake_voice.synthesize_wav.side_effect = fake_synthesize_wav
        p._loaded_models["en_US-lessac-medium"] = fake_voice

        p._synthesize_blocking("hello", "en_US-lessac-medium", 0, 100, None)

        assert len(captured_cfg) == 1
        cfg = captured_cfg[0]
        assert cfg.noise_scale == pytest.approx(0.9)
        assert cfg.noise_w_scale == pytest.approx(0.6)
