"""
Tests for CoquiTTSProvider.
Covers:
- Voice list completeness and structure
- get_default_voice
- _apply_volume helper
- _rate_to_speed helper
- _float_array_to_wav_bytes helper
- validate_voice
- clear_cache
- get_available_voices
- generate_speech (mocked Coqui TTS)
- _ensure_model_loaded
- _get_language
- _get_gpu_device
- sentence chunking and native XTTS speed handling
"""
import io
import sys
import wave
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Stub out TTS (Coqui) before it gets imported by the provider module so
# tests run without the heavy TTS wheel installed.
# ---------------------------------------------------------------------------
_tts_stub_module = types.ModuleType("TTS")
_tts_api_stub = types.ModuleType("TTS.api")

class _FakeTTS:
    """Minimal stub for TTS.api.TTS."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.synthesizer = MagicMock()
        self.synthesizer.output_sample_rate = 24000

    def to(self, device: str):
        self._device = device
        return self

    def tts(self, text: str, speaker: str, language: str):
        # Return a short silence
        return [0.0] * 24000


_tts_api_stub.TTS = _FakeTTS
_tts_stub_module.api = _tts_api_stub
sys.modules.setdefault("TTS", _tts_stub_module)
sys.modules.setdefault("TTS.api", _tts_api_stub)

# Now safe to import the provider
from src.tts.providers.coqui_tts_provider import (  # noqa: E402
    CoquiTTSProvider,
    _COQUI_VOICES,
    _VOICE_NAMES,
    _apply_volume,
    _float_array_to_wav_bytes,
    _COQUI_SAMPLE_RATE,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def provider() -> CoquiTTSProvider:
    """Create a CoquiTTSProvider with no settings manager."""
    return CoquiTTSProvider(settings_manager=None)


# ---------------------------------------------------------------------------
# Built-in voice list
# ---------------------------------------------------------------------------

class TestBuiltinVoices:
    def test_voices_list_has_15_entries(self):
        assert len(_COQUI_VOICES) == 15

    def test_all_voices_have_required_keys(self):
        required = {"name", "short_name", "gender", "locale", "language_code", "provider"}
        for v in _COQUI_VOICES:
            missing = required - v.keys()
            assert not missing, f"Voice {v.get('short_name')} missing keys: {missing}"

    def test_all_voices_have_coqui_provider(self):
        for v in _COQUI_VOICES:
            assert v["provider"] == "coqui", f"Expected provider='coqui' for {v['short_name']}"

    def test_voice_names_frozenset_matches_list(self):
        assert _VOICE_NAMES == frozenset(v["short_name"] for v in _COQUI_VOICES)

    def test_all_voices_are_english(self):
        for v in _COQUI_VOICES:
            assert v["language_code"] == "en"
            assert v["locale"] == "en-US"

    def test_first_voice_is_claribel_dervla(self):
        assert _COQUI_VOICES[0]["short_name"] == "Claribel Dervla"


# ---------------------------------------------------------------------------
# get_default_voice
# ---------------------------------------------------------------------------

class TestGetDefaultVoice:
    def test_returns_claribel_dervla(self, provider):
        assert provider.get_default_voice() == "Claribel Dervla"

    def test_default_voice_is_in_voice_names(self, provider):
        assert provider.get_default_voice() in _VOICE_NAMES


# ---------------------------------------------------------------------------
# _get_language
# ---------------------------------------------------------------------------

class TestGetLanguage:
    def test_default_language_is_en(self, provider):
        assert provider._get_language() == "en"

    def test_custom_language_from_settings(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            "fr" if key == "coqui_language" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_language() == "fr"

    def test_invalid_language_falls_back_to_en(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            "xx" if key == "coqui_language" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_language() == "en"


# ---------------------------------------------------------------------------
# Sampling stability settings (temperature / repetition penalty / splitting)
# ---------------------------------------------------------------------------

class TestSamplingSettings:
    def test_temperature_default(self, provider):
        assert provider._get_temperature() == pytest.approx(0.75)

    def test_temperature_from_settings(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            0.4 if key == "coqui_temperature" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_temperature() == pytest.approx(0.4)

    def test_temperature_clamped_high(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            5.0 if key == "coqui_temperature" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_temperature() == pytest.approx(1.0)

    def test_repetition_penalty_default(self, provider):
        assert provider._get_repetition_penalty() == pytest.approx(10.0)

    def test_repetition_penalty_from_settings(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            15.0 if key == "coqui_repetition_penalty" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_repetition_penalty() == pytest.approx(15.0)

    def test_repetition_penalty_clamped_low(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            0.5 if key == "coqui_repetition_penalty" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_repetition_penalty() == pytest.approx(1.0)

    def test_text_splitting_default_enabled(self, provider):
        """Text splitting is on by default when spaCy is available."""
        with patch("importlib.util.find_spec", return_value=types.SimpleNamespace()):
            assert provider._get_text_splitting_enabled() is True

    def test_text_splitting_disabled_from_settings(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            False if key == "coqui_enable_text_splitting" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_text_splitting_enabled() is False

    def test_text_splitting_falls_back_when_spacy_missing(self, provider):
        """Without spaCy, language-aware splitting must degrade, never crash.

        XTTS raises ImportError when ``enable_text_splitting=True`` is used
        without spaCy, so the provider must detect that and fall back to the
        built-in chunker instead of breaking synthesis.
        """
        with patch("importlib.util.find_spec", return_value=None):
            assert provider._get_text_splitting_enabled() is False

    def test_text_splitting_enabled_when_spacy_present(self, provider):
        """With spaCy available, language-aware splitting is on by default."""
        with patch(
            "importlib.util.find_spec",
            return_value=types.SimpleNamespace(),
        ):
            assert provider._get_text_splitting_enabled() is True

    def test_gpu_cleanup_interval_default(self, provider):
        assert provider._get_gpu_cleanup_interval() == 5

    def test_gpu_cleanup_interval_disabled(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            0 if key == "coqui_gpu_cleanup_interval" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_gpu_cleanup_interval() == 0


class TestGpuMemoryCleanup:
    def test_cleanup_runs_every_interval(self, provider):
        """empty_cache must run every `interval` syntheses, not each one."""
        provider._loaded_device = "cuda:0"
        with patch.object(provider, "_run_post_clear_memory_hygiene") as mock_hygiene:
            for _ in range(4):
                provider._maybe_cleanup_gpu_memory()
            mock_hygiene.assert_not_called()
            provider._maybe_cleanup_gpu_memory()  # 5th synthesis -> cleanup
        mock_hygiene.assert_called_once_with("cuda:0")

    def test_cleanup_disabled_when_interval_zero(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            0 if key == "coqui_gpu_cleanup_interval" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        with patch.object(p, "_run_post_clear_memory_hygiene") as mock_hygiene:
            for _ in range(20):
                p._maybe_cleanup_gpu_memory()
        mock_hygiene.assert_not_called()


# ---------------------------------------------------------------------------
# _get_gpu_device
# ---------------------------------------------------------------------------

class TestGetGpuDevice:
    def test_default_is_minus_two(self, provider):
        assert provider._get_gpu_device() == -2

    def test_custom_device_from_settings(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            0 if key == "coqui_gpu_device" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_gpu_device() == 0

    def test_device_clamped_to_minus_two_minimum(self):
        mock_sm = MagicMock()
        mock_sm.get.side_effect = lambda key, default=None: (
            -99 if key == "coqui_gpu_device" else default
        )
        p = CoquiTTSProvider(settings_manager=mock_sm)
        assert p._get_gpu_device() == -2


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

class TestApplyVolume:
    def test_full_volume_unchanged(self):
        arr = np.array([0.5, -0.5, 0.25], dtype=np.float32)
        result = _apply_volume(arr, 100)
        np.testing.assert_array_almost_equal(result, arr)

    def test_zero_volume_silences(self):
        arr = np.array([0.5, -0.5, 0.25], dtype=np.float32)
        result = _apply_volume(arr, 0)
        np.testing.assert_array_almost_equal(result, np.zeros_like(arr))

    def test_50_volume_halves(self):
        arr = np.array([0.8, -0.4], dtype=np.float32)
        result = _apply_volume(arr, 50)
        np.testing.assert_array_almost_equal(result, arr * 0.5)

    def test_volume_clamps_at_200(self):
        arr = np.array([0.5], dtype=np.float32)
        result = _apply_volume(arr, 300)
        np.testing.assert_array_almost_equal(result, arr * 2.0)


class TestRateToSpeed:
    def test_zero_rate_is_natural_tempo(self, provider):
        assert provider._rate_to_speed(0) == pytest.approx(1.0)

    def test_positive_rate_speeds_up(self, provider):
        assert provider._rate_to_speed(50) == pytest.approx(1.5)

    def test_negative_rate_slows_down(self, provider):
        assert provider._rate_to_speed(-50) == pytest.approx(0.5)

    def test_full_positive_rate_maps_to_max_speed(self, provider):
        assert provider._rate_to_speed(100) == pytest.approx(2.0)

    def test_full_negative_rate_maps_to_min_speed(self, provider):
        assert provider._rate_to_speed(-100) == pytest.approx(0.5)

    def test_rate_is_clamped_to_valid_range(self, provider):
        assert provider._rate_to_speed(200) == pytest.approx(2.0)
        assert provider._rate_to_speed(-200) == pytest.approx(0.5)


class TestFloatArrayToWavBytes:
    def test_returns_valid_wav(self):
        arr = np.zeros(100, dtype=np.float32)
        wav_bytes = _float_array_to_wav_bytes(arr, 24000)
        assert wav_bytes[:4] == b"RIFF"

    def test_wav_has_correct_sample_rate(self):
        arr = np.zeros(100, dtype=np.float32)
        wav_bytes = _float_array_to_wav_bytes(arr, 24000)
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getframerate() == 24000

    def test_clipping_does_not_raise(self):
        arr = np.array([2.0, -2.0, 1.5], dtype=np.float32)
        wav_bytes = _float_array_to_wav_bytes(arr, 24000)
        assert len(wav_bytes) > 0


# ---------------------------------------------------------------------------
# validate_voice
# ---------------------------------------------------------------------------

class TestValidateVoice:
    @pytest.mark.asyncio
    async def test_known_voice_is_valid(self, provider):
        assert await provider.validate_voice("Claribel Dervla") is True

    @pytest.mark.asyncio
    async def test_unknown_voice_is_invalid(self, provider):
        assert await provider.validate_voice("en-US-AriaNeural") is False

    @pytest.mark.asyncio
    async def test_empty_string_is_invalid(self, provider):
        assert await provider.validate_voice("") is False

    @pytest.mark.asyncio
    async def test_all_builtin_voices_valid(self, provider):
        for v in _COQUI_VOICES:
            assert await provider.validate_voice(v["short_name"]) is True


# ---------------------------------------------------------------------------
# get_available_voices
# ---------------------------------------------------------------------------

class TestGetAvailableVoices:
    @pytest.mark.asyncio
    async def test_returns_all_builtin_voices(self, provider):
        voices = await provider.get_available_voices()
        assert voices == _COQUI_VOICES

    @pytest.mark.asyncio
    async def test_voices_are_independent_copy(self, provider):
        voices = await provider.get_available_voices()
        voices.clear()
        voices2 = await provider.get_available_voices()
        assert len(voices2) == 15


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------

class TestClearCache:
    def test_clear_cache_resets_loaded_flag(self, provider):
        provider._model_loaded = True
        provider._tts = MagicMock()
        provider.clear_cache()
        assert provider._model_loaded is False
        assert provider._tts is None

    def test_clear_cache_runs_gc_after_unload(self, provider):
        provider._model_loaded = True
        provider._tts = MagicMock()

        with patch("src.tts.providers.coqui_tts_provider.gc.collect") as gc_collect:
            provider.clear_cache()

        gc_collect.assert_called_once_with()

    def test_clear_cache_empties_cuda_cache_for_cuda_loaded_model(self, provider):
        fake_torch = types.ModuleType("torch")
        fake_torch.cuda = types.SimpleNamespace(empty_cache=MagicMock())
        provider._model_loaded = True
        provider._tts = MagicMock()
        provider._loaded_device = "cuda:0"

        with (
            patch("src.tts.providers.coqui_tts_provider.gc.collect"),
            patch.dict(sys.modules, {"torch": fake_torch}),
        ):
            provider.clear_cache()

        fake_torch.cuda.empty_cache.assert_called_once_with()

    def test_clear_cache_waits_for_inflight_preload(self, provider):
        """clear_cache() should defer unload until an in-flight preload finishes."""
        import threading

        preload_started = threading.Event()
        allow_preload_finish = threading.Event()

        def fake_tts_ctor(_model_name: str):
            preload_started.set()
            assert allow_preload_finish.wait(timeout=1)
            return _FakeTTS("x")

        with (
            patch("src.tts.providers.coqui_tts_provider.os") as mock_os,
            patch.object(provider, "_get_gpu_device", return_value=-2),
            patch.object(provider, "_get_device_string", return_value="cpu"),
            patch("TTS.api.TTS", side_effect=fake_tts_ctor),
        ):
            mock_os.environ = {}

            preload_thread = threading.Thread(target=provider._ensure_model_loaded)
            preload_thread.start()
            assert preload_started.wait(timeout=1)

            provider.clear_cache()
            allow_preload_finish.set()
            preload_thread.join(timeout=2)

        assert preload_thread.is_alive() is False
        assert provider._model_loaded is False
        assert provider._tts is None


# ---------------------------------------------------------------------------
# _ensure_model_loaded
# ---------------------------------------------------------------------------

class TestEnsureModelLoaded:
    def test_calls_tts_constructor_with_correct_model(self, provider):
        """_ensure_model_loaded must instantiate TTS with the XTTS v2 model name."""
        with patch("src.tts.providers.coqui_tts_provider.os") as mock_os:
            mock_os.environ = {}
            fake_tts_instance = _FakeTTS(_COQUI_SAMPLE_RATE)  # reuse stub
            with patch("TTS.api.TTS", return_value=fake_tts_instance) as mock_tts_cls:
                provider._ensure_model_loaded()

        mock_tts_cls.assert_called_once_with("tts_models/multilingual/multi-dataset/xtts_v2")

    def test_model_loaded_only_once(self, provider):
        with patch("TTS.api.TTS") as mock_tts_cls:
            mock_tts_cls.return_value = _FakeTTS("x")
            provider._ensure_model_loaded()
            provider._ensure_model_loaded()  # second call should be no-op

        assert mock_tts_cls.call_count == 1

    def test_exception_does_not_crash(self, provider):
        with patch("TTS.api.TTS", side_effect=RuntimeError("no GPU")):
            provider._ensure_model_loaded()  # must not raise

        assert provider._model_loaded is False


# ---------------------------------------------------------------------------
# generate_speech (mocked Coqui TTS)
# ---------------------------------------------------------------------------

class TestGenerateSpeech:
    @pytest.mark.asyncio
    async def test_returns_wav_bytes(self, provider):
        fake_audio = [0.0] * 24000
        fake_tts = MagicMock()
        fake_tts.tts.return_value = fake_audio
        fake_tts.synthesizer.output_sample_rate = 24000

        provider._tts = fake_tts
        provider._model_loaded = True

        result = await provider.generate_speech("Hello world", "Claribel Dervla")
        assert result is not None
        assert result[:4] == b"RIFF"

    @pytest.mark.asyncio
    async def test_cancelled_by_stop_event(self, provider):
        import threading

        stop_event = threading.Event()
        stop_event.set()
        result = await provider.generate_speech(
            "Hello", "Claribel Dervla", stop_event=stop_event
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_stream_speech_yields_single_chunk(self, provider):
        fake_audio = [0.0] * 24000
        fake_tts = MagicMock()
        fake_tts.tts.return_value = fake_audio
        fake_tts.synthesizer.output_sample_rate = 24000

        provider._tts = fake_tts
        provider._model_loaded = True

        chunks = []
        async for chunk in provider.stream_speech("Hello world", "Claribel Dervla"):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0][:4] == b"RIFF"

    @pytest.mark.asyncio
    async def test_unknown_voice_falls_back_to_default(self, provider):
        """Synthesis with an unknown voice should still succeed (falls back)."""
        fake_tts = MagicMock()
        fake_tts.tts.return_value = [0.0] * 24000
        fake_tts.synthesizer.output_sample_rate = 24000

        provider._tts = fake_tts
        provider._model_loaded = True

        result = await provider.generate_speech("Test", "unknown-speaker-xyz")
        assert result is not None
        # Verify the default speaker was used
        call_kwargs = fake_tts.tts.call_args
        assert call_kwargs.kwargs.get("speaker") == "Claribel Dervla"

    @pytest.mark.asyncio
    async def test_synthesis_passes_native_speed(self, provider):
        """Rate should be applied via XTTS's native ``speed`` kwarg, not resampling."""
        fake_tts = MagicMock()
        fake_tts.tts.return_value = [0.0] * 24000
        fake_tts.synthesizer.output_sample_rate = 24000

        provider._tts = fake_tts
        provider._model_loaded = True

        await provider.generate_speech("Hello.", "Claribel Dervla", rate=50)

        assert fake_tts.tts.call_args.kwargs.get("speed") == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_synthesis_passes_stability_kwargs(self, provider):
        """Temperature and repetition penalty must reach XTTS."""
        fake_tts = MagicMock()
        fake_tts.tts.return_value = [0.0] * 24000
        fake_tts.synthesizer.output_sample_rate = 24000

        provider._tts = fake_tts
        provider._model_loaded = True

        await provider.generate_speech("Hello.", "Claribel Dervla")

        kwargs = fake_tts.tts.call_args.kwargs
        assert kwargs.get("temperature") == pytest.approx(0.75)
        assert kwargs.get("repetition_penalty") == pytest.approx(10.0)
        # Bool (True when spaCy is installed, False otherwise) — never a crash
        assert isinstance(kwargs.get("enable_text_splitting"), bool)

    def test_synthesize_blocking_chunks_sentences_and_stitches_pause(self, provider):
        fake_tts = MagicMock()
        fake_tts.tts.side_effect = [
            [0.0] * 10,
            [0.0] * 10,
        ]
        fake_tts.synthesizer.output_sample_rate = 24000

        provider._tts = fake_tts
        provider._model_loaded = True

        wav_bytes = provider._synthesize_blocking(
            "First sentence. Second sentence.",
            "Claribel Dervla",
            0,
            100,
            None,
        )

        assert wav_bytes is not None
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getnframes() > 20
        assert fake_tts.tts.call_count == 2
