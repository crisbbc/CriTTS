"""
Coqui TTS Provider Module
Provides high-quality offline text-to-speech synthesis using Coqui XTTS v2.
The model is downloaded automatically from Hugging Face on first use.
"""
import asyncio
import gc
import importlib.util
import io
import logging
import os
import re
import threading
import wave
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from . import TTSProvider
from .coqui_metadata import COQUI_VOICES as _COQUI_VOICES, VOICE_NAMES as _VOICE_NAMES, XTTS_LANGUAGES as _XTTS_LANGUAGES

# Patch missing isin_mps_friendly for transformers >= 4.46 before TTS imports it
try:
    import transformers.pytorch_utils as _tpu
    if not hasattr(_tpu, "isin_mps_friendly"):
        import torch as _torch
        _tpu.isin_mps_friendly = _torch.isin
except Exception:
    pass

logger = logging.getLogger(__name__)

# XTTS v2 outputs 24 kHz audio
_COQUI_SAMPLE_RATE = 24000

_COQUI_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
# Native XTTS ``speed`` bounds. Native speed scaling stretches/compresses the
# latents *before* vocoding, which preserves intonation far better than
# resampling the finished waveform. Keeping the range modest avoids the
# intelligibility collapse XTTS exhibits at extreme speeds.
_COQUI_MIN_SPEED = 0.5
_COQUI_MAX_SPEED = 2.0
_COQUI_CHUNK_PAUSE_SECS = 0.12

# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _float_array_to_wav_bytes(
    audio_array: "np.ndarray",
    sample_rate: int,
) -> bytes:
    """Convert a float32 numpy array to 16-bit WAV bytes."""
    audio_clipped = np.clip(audio_array, -1.0, 1.0)
    audio_int16 = (audio_clipped * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


def _apply_volume(audio_array: "np.ndarray", volume: int) -> "np.ndarray":
    """Scale audio amplitude by volume (0–100, 100 = unity)."""
    scale = max(0.0, min(2.0, volume / 100.0))
    return audio_array * scale


def _split_into_synthesis_chunks(text: str, max_chars: int = 260) -> List[str]:
    """Split long text into sentence-friendly chunks for XTTS stability."""
    sentences = [
        chunk.strip()
        for chunk in re.split(r'(?<=[.!?…])\s+', text.strip())
        if chunk.strip()
    ]
    if not sentences:
        return []

    chunks: List[str] = []
    for sentence in sentences:
        if len(sentence) > max_chars:
            parts = [part.strip() for part in re.split(r'(?<=[,:;])\s+', sentence) if part.strip()]
        else:
            parts = [sentence]

        for part in parts:
            if len(part) <= max_chars:
                chunks.append(part)
                continue

            words = part.split()
            current = ""
            for word in words:
                if not current:
                    current = word
                elif len(current) + 1 + len(word) <= max_chars:
                    current = f"{current} {word}"
                else:
                    chunks.append(current)
                    current = word
            if current:
                chunks.append(current)
    return chunks


# ---------------------------------------------------------------------------
# CoquiTTSProvider
# ---------------------------------------------------------------------------

class CoquiTTSProvider(TTSProvider):
    """High-quality offline TTS provider backed by Coqui XTTS v2."""

    def __init__(
        self,
        settings_manager=None,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        self._settings_manager = settings_manager
        self._status_callback: Optional[Callable[[str], None]] = status_callback
        self._tts = None
        self._model_loaded = False
        self._loaded_device: Optional[str] = None
        self._lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._active_operations = 0
        self._pending_cache_clear = False
        self._synthesis_count = 0  # Syntheses since last GPU memory cleanup

    def _begin_model_operation(self) -> None:
        """Mark a model-resident operation as in flight."""
        with self._lifecycle_lock:
            self._active_operations += 1

    def _end_model_operation(self) -> None:
        """Finish an in-flight model operation and apply deferred clears."""
        should_clear = False
        with self._lifecycle_lock:
            self._active_operations = max(0, self._active_operations - 1)
            if self._active_operations == 0 and self._pending_cache_clear:
                self._pending_cache_clear = False
                should_clear = True

        if should_clear:
            self._clear_cache_now()

    def _clear_cache_now(self) -> None:
        """Unload the XTTS model immediately."""
        loaded_device: Optional[str] = None
        with self._lock:
            loaded_device = self._loaded_device
            self._model_loaded = False
            self._tts = None
            self._loaded_device = None

        self._run_post_clear_memory_hygiene(loaded_device)

    def _run_post_clear_memory_hygiene(self, loaded_device: Optional[str]) -> None:
        """Best-effort post-unload memory cleanup."""
        gc.collect()

        if not isinstance(loaded_device, str) or not loaded_device.startswith("cuda"):
            return

        try:
            import torch  # noqa: PLC0415

            empty_cache = getattr(getattr(torch, "cuda", None), "empty_cache", None)
            if callable(empty_cache):
                empty_cache()
        except Exception:
            logger.debug("Coqui TTS: torch.cuda.empty_cache() unavailable during cache clear.", exc_info=True)

    # ------------------------------------------------------------------
    # Status callback
    # ------------------------------------------------------------------

    def set_status_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Register a callback for status messages (model loading/downloading)."""
        self._status_callback = callback

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def _get_gpu_device(self) -> int:
        """Return configured GPU device index.

        -2 = Auto (pick first available CUDA GPU)
        0+ = specific CUDA device index
        """
        if self._settings_manager is not None:
            val = self._settings_manager.get("coqui_gpu_device", -2)
            try:
                return max(-2, int(val))
            except (TypeError, ValueError):
                pass
        return -2

    def _get_language(self) -> str:
        """Return the configured XTTS language code (default: 'en')."""
        if self._settings_manager is not None:
            val = self._settings_manager.get("coqui_language", "en")
            if isinstance(val, str) and val in _XTTS_LANGUAGES:
                return val
        return "en"

    def _get_temperature(self) -> float:
        """Return the XTTS sampling temperature (default: 0.75).

        Lower values make the autoregressive decoder more deterministic, which
        reduces the "uhhh"/loop artifacts XTTS is prone to on long sessions.
        """
        if self._settings_manager is not None:
            val = self._settings_manager.get("coqui_temperature", 0.75)
            try:
                return float(max(0.0, min(1.0, val)))
            except (TypeError, ValueError):
                pass
        return 0.75

    def _get_repetition_penalty(self) -> float:
        """Return the XTTS repetition penalty (default: 10.0).

        Higher values punish the decoder for repeating tokens, curbing the
        repetition spirals that make output sound broken after long use.
        """
        if self._settings_manager is not None:
            val = self._settings_manager.get("coqui_repetition_penalty", 10.0)
            try:
                return float(max(1.0, min(20.0, val)))
            except (TypeError, ValueError):
                pass
        return 10.0

    def _get_text_splitting_enabled(self) -> bool:
        """Return whether XTTS language-aware sentence splitting is enabled.

        When enabled, XTTS splits each input chunk on sentence boundaries using
        per-language punctuation rules before synthesis, which keeps long or
        unpunctuated text stable instead of letting the decoder run away.

        XTTS raises ``ImportError`` when ``enable_text_splitting=True`` is used
        without spaCy (it only needs spaCy for sentences at/above the language's
        character limit, but the import is unconditional on that path; Japanese
        also needs the ``spacy[ja]`` extra for SudachiPy).  If spaCy is unavailable
        we silently fall back to the built-in chunker instead of crashing
        synthesis.  ``importlib.util.find_spec`` is used (not ``import``) so this
        check is cheap and has no side effects.
        """
        if self._settings_manager is not None:
            val = self._settings_manager.get("coqui_enable_text_splitting", True)
            if not isinstance(val, bool):
                val = True
        else:
            val = True

        if not val:
            return False

        if importlib.util.find_spec("spacy") is None:
            logger.warning(
                "Coqui TTS: language-aware text splitting requires spaCy "
                "(pip install \"spacy[ja]\"); falling back to the built-in chunker."
            )
            return False
        return True

    def _get_gpu_cleanup_interval(self) -> int:
        """Return how many syntheses between CUDA memory cleanups (0 = disabled)."""
        if self._settings_manager is not None:
            val = self._settings_manager.get("coqui_gpu_cleanup_interval", 5)
            try:
                return max(0, int(val))
            except (TypeError, ValueError):
                pass
        return 5

    def _get_device_string(self, gpu_device: int) -> str:
        """Convert a gpu_device index to a PyTorch device string.

        -2 → "cuda" (auto) or "cpu"
        0  → "cuda:0"
        1  → "cuda:1"
        …
        """
        try:
            import torch

            if gpu_device == -2:
                if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                    return "cuda"
                return "cpu"

            if gpu_device >= 0:
                if torch.cuda.is_available() and gpu_device < torch.cuda.device_count():
                    return f"cuda:{gpu_device}"
                logger.warning(
                    "Coqui TTS: CUDA device %d requested but not available — falling back to CPU",
                    gpu_device,
                )
                return "cpu"
        except Exception:
            pass
        return "cpu"

    @staticmethod
    def _rate_to_speed(rate: int) -> float:
        """Convert edge-style rate (-100..100) to a native XTTS ``speed``.

        XTTS applies ``speed`` by interpolating the duration latents *before*
        vocoding, so pauses and intonation scale naturally. Resampling the
        finished waveform (the previous approach) time-stretched everything
        uniformly, flattening prosody and smearing transients.

        rate=0   → 1.0 (natural tempo)
        rate=100 → 2.0 (2× faster)
        rate=-100 → 0.5 (2× slower)
        """
        rate = max(-100, min(100, rate))
        speed = 1.0 + rate / 100.0
        return max(_COQUI_MIN_SPEED, min(_COQUI_MAX_SPEED, speed))

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Thread-safe model load with double-checked locking."""
        if self._model_loaded:
            return

        self._begin_model_operation()
        try:
            if self._model_loaded:
                return

            with self._lock:
                if self._model_loaded:
                    return

                try:
                    # Agree to XTTS v2 terms of service automatically
                    os.environ["COQUI_TOS_AGREED"] = "1"

                    if self._status_callback:
                        self._status_callback("🔄  Coqui TTS: loading XTTS v2 model…")

                    gpu_device = self._get_gpu_device()
                    device_str = self._get_device_string(gpu_device)

                    logger.info("Coqui TTS: loading model on device '%s'", device_str)

                    from TTS.api import TTS  # noqa: PLC0415

                    if self._status_callback:
                        self._status_callback("⬇️  Coqui TTS: downloading/verifying model files…")

                    self._tts = TTS(_COQUI_MODEL).to(device_str)
                    self._model_loaded = True
                    self._loaded_device = device_str

                    logger.info("Coqui TTS: model ready on '%s'.", device_str)
                    if self._status_callback:
                        self._status_callback("✅  Coqui TTS model ready")

                except Exception as exc:
                    logger.warning("Coqui TTS: could not load model: %s", exc)
                    if self._status_callback:
                        self._status_callback(f"❌  Coqui TTS: failed to load model — {exc}")
        finally:
            self._end_model_operation()

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _synthesize_blocking(
        self,
        text: str,
        voice: str,
        rate: int,
        volume: int,
        stop_event,
    ) -> Optional[bytes]:
        """CPU/GPU-bound synthesis — must be run in an executor."""
        if stop_event and stop_event.is_set():
            return None

        self._begin_model_operation()
        try:
            self._ensure_model_loaded()

            if self._tts is None:
                raise RuntimeError(
                    "Coqui TTS model failed to load. "
                    "Check the status bar for details and ensure you have an internet connection for the first-time download (~1.8 GB)."
                )

            if stop_event and stop_event.is_set():
                return None

            # Prevent XTTS continuation/hallucination artefacts
            tts_text = text.rstrip()
            if tts_text and tts_text[-1] not in ".!?…":
                tts_text += "."

            speaker = voice if voice in _VOICE_NAMES else self.get_default_voice()
            language = self._get_language()
            speed = self._rate_to_speed(rate)
            temperature = self._get_temperature()
            repetition_penalty = self._get_repetition_penalty()
            enable_text_splitting = self._get_text_splitting_enabled()

            logger.debug(
                "Coqui synthesis: speaker=%s language=%s speed=%.2f temperature=%.2f "
                "repetition_penalty=%.1f text_splitting=%s",
                speaker, language, speed, temperature, repetition_penalty, enable_text_splitting,
            )

            def _synthesize_text_chunk(chunk_text: str):
                kwargs = dict(
                    text=chunk_text,
                    speaker=speaker,
                    language=language,
                    speed=speed,
                    temperature=temperature,
                    repetition_penalty=repetition_penalty,
                    enable_text_splitting=enable_text_splitting,
                )
                try:
                    import torch  # noqa: PLC0415

                    with torch.inference_mode():
                        return self._tts.tts(**kwargs)
                except ImportError:
                    return self._tts.tts(**kwargs)

            if stop_event and stop_event.is_set():
                return None

            # Detect actual sample rate from model if available
            try:
                sample_rate = self._tts.synthesizer.output_sample_rate
            except AttributeError:
                sample_rate = _COQUI_SAMPLE_RATE

            chunk_arrays: List[np.ndarray] = []
            silence_samples = max(1, int(sample_rate * _COQUI_CHUNK_PAUSE_SECS))
            pause = np.zeros(silence_samples, dtype=np.float32)

            for index, text_chunk in enumerate(_split_into_synthesis_chunks(tts_text) or [tts_text]):
                if stop_event and stop_event.is_set():
                    return None

                audio_list = _synthesize_text_chunk(text_chunk)
                chunk_audio = np.array(audio_list, dtype=np.float32)
                if chunk_audio.size == 0:
                    continue

                if index > 0:
                    chunk_arrays.append(pause)
                chunk_arrays.append(chunk_audio)

            if not chunk_arrays:
                raise RuntimeError("Coqui TTS produced no audio.")

            audio_array = np.concatenate(chunk_arrays)
            audio_array = _apply_volume(audio_array, volume)

            return _float_array_to_wav_bytes(audio_array, sample_rate)
        finally:
            self._end_model_operation()
            self._maybe_cleanup_gpu_memory()

    def _maybe_cleanup_gpu_memory(self) -> None:
        """Periodically release cached CUDA memory to counter long-session drift.

        XTTS holds a large long-lived model; over hours of use the PyTorch
        caching allocator can fragment VRAM and memory pressure can degrade
        inference.  Every ``coqui_gpu_cleanup_interval`` syntheses (0 = never)
        we run gc() and ``torch.cuda.empty_cache()`` — a few ms on GPU, a
        no-op beyond gc on CPU.
        """
        interval = self._get_gpu_cleanup_interval()
        if interval <= 0:
            return
        with self._lifecycle_lock:
            self._synthesis_count += 1
            if self._synthesis_count % interval != 0:
                return
            loaded_device = self._loaded_device
        self._run_post_clear_memory_hygiene(loaded_device)

    # ------------------------------------------------------------------
    # TTSProvider interface
    # ------------------------------------------------------------------

    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Return the built-in list of XTTS v2 speakers."""
        return list(_COQUI_VOICES)

    async def generate_speech(
        self,
        text: str,
        voice: str,
        rate: int = 0,
        volume: int = 100,
        pitch: int = 0,
        stop_event=None,
    ) -> Optional[bytes]:
        """Generate speech and return WAV bytes.

        Args:
            text: Text to synthesize.
            voice: XTTS v2 speaker name (e.g. "Claribel Dervla").
            rate: Speech rate adjustment (-100 to 100, 0 is normal).
            volume: Volume level (0 to 100, 100 is normal).
            pitch: Not supported by XTTS; accepted for interface compatibility.
            stop_event: Optional threading.Event to signal cancellation.

        Returns:
            WAV audio bytes, or None if generation was cancelled.
        """
        if stop_event and stop_event.is_set():
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._synthesize_blocking,
            text,
            voice,
            rate,
            volume,
            stop_event,
        )

    async def stream_speech(
        self,
        text: str,
        voice: str,
        rate: int = 0,
        volume: int = 100,
        pitch: int = 0,
        stop_event=None,
    ):
        """Yield the full audio as a single chunk (XTTS does not stream natively)."""
        audio = await self.generate_speech(text, voice, rate, volume, pitch, stop_event)
        if audio is not None:
            yield audio

    async def validate_voice(self, voice: str) -> bool:
        """Return True if *voice* is a known XTTS v2 speaker name."""
        return voice in _VOICE_NAMES

    def get_default_voice(self) -> str:
        """Return the default XTTS v2 speaker."""
        return "Claribel Dervla"

    def clear_cache(self) -> None:
        """Unload the model from memory."""
        with self._lifecycle_lock:
            if self._active_operations > 0:
                self._pending_cache_clear = True
                return

        self._clear_cache_now()
