"""
Piper TTS Provider Module
Provides offline, open-source neural text-to-speech synthesis using Piper TTS.
Voice models are downloaded on first use and cached locally.
"""
import asyncio
import io
import json
import logging
import os
import shutil
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.request import urlopen
from urllib.error import URLError

from piper import PiperVoice, SynthesisConfig

from . import TTSProvider

logger = logging.getLogger(__name__)


def _configure_espeak_path() -> None:
    """Auto-detect and register the espeak-ng data directory bundled with piper-tts.

    On Windows the bundled espeak-ng data directory is not automatically
    registered by the C extension.  This function sets ``ESPEAK_DATA_PATH``
    once at module-import time so that every subsequent ``PiperVoice.load()``
    call finds the correct language data and produces correct accents.
    """
    if os.environ.get("ESPEAK_DATA_PATH"):
        logger.debug("ESPEAK_DATA_PATH already set: %s", os.environ["ESPEAK_DATA_PATH"])
        return

    candidates: List[Path] = []

    # Primary: piper-tts bundles espeak-ng-data alongside its own __init__.py
    try:
        import piper as _piper_pkg  # type: ignore[import]
        candidates.append(Path(_piper_pkg.__file__).parent / "espeak-ng-data")
    except Exception:
        pass

    # Secondary: piper_phonemize (separate package) also ships it
    try:
        import piper_phonemize  # type: ignore[import]
        candidates.append(Path(piper_phonemize.__file__).parent / "espeak-ng-data")
    except Exception:
        pass

    # Tertiary: scan all site-packages roots
    try:
        import site
        roots = site.getsitepackages() + [site.getusersitepackages()]
        for sp in roots:
            candidates.append(Path(sp) / "piper" / "espeak-ng-data")
            candidates.append(Path(sp) / "piper_phonemize" / "espeak-ng-data")
    except Exception:
        pass

    for candidate in candidates:
        if candidate.is_dir():
            os.environ["ESPEAK_DATA_PATH"] = str(candidate)
            logger.info("Set ESPEAK_DATA_PATH → %s", candidate)
            return

    logger.warning(
        "espeak-ng data directory not found; Piper phonemization may produce "
        "incorrect accents. Ensure piper-tts is installed correctly."
    )


_configure_espeak_path()

# Hugging Face URL template used by piper's own download_voices tool
_VOICE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    "/{lang_family}/{lang_code}/{voice_name}/{voice_quality}"
    "/{lang_code}-{voice_name}-{voice_quality}{extension}?download=true"
)

# Curated list of popular Piper voices across multiple languages.
# short_name follows the pattern  {lang_code}-{voice_name}-{quality}
# and is also the model file stem (e.g. "en_US-lessac-medium.onnx").
_BUILTIN_VOICES: List[Dict[str, Any]] = [
    # English – United States
    {
        "name": "English (US) – Lessac (Medium)",
        "short_name": "en_US-lessac-medium",
        "gender": "Male",
        "locale": "en-US",
        "language_code": "en",
        "quality": "medium",
        "provider": "piper",
    },
    {
        "name": "English (US) – Ryan (High)",
        "short_name": "en_US-ryan-high",
        "gender": "Male",
        "locale": "en-US",
        "language_code": "en",
        "quality": "high",
        "provider": "piper",
    },
    {
        "name": "English (US) – Amy (Low)",
        "short_name": "en_US-amy-low",
        "gender": "Female",
        "locale": "en-US",
        "language_code": "en",
        "quality": "low",
        "provider": "piper",
    },
    {
        "name": "English (US) – Ljspeech (High)",
        "short_name": "en_US-ljspeech-high",
        "gender": "Female",
        "locale": "en-US",
        "language_code": "en",
        "quality": "high",
        "provider": "piper",
    },
    # English – Great Britain
    {
        "name": "English (GB) – Alan (Medium)",
        "short_name": "en_GB-alan-medium",
        "gender": "Male",
        "locale": "en-GB",
        "language_code": "en",
        "quality": "medium",
        "provider": "piper",
    },
    {
        "name": "English (GB) – Jenny Dioco (Medium)",
        "short_name": "en_GB-jenny_dioco-medium",
        "gender": "Female",
        "locale": "en-GB",
        "language_code": "en",
        "quality": "medium",
        "provider": "piper",
    },
    # German
    {
        "name": "German – Thorsten (Medium)",
        "short_name": "de_DE-thorsten-medium",
        "gender": "Male",
        "locale": "de-DE",
        "language_code": "de",
        "quality": "medium",
        "provider": "piper",
    },
    {
        "name": "German – Eva K (x-low)",
        "short_name": "de_DE-eva_k-x_low",
        "gender": "Female",
        "locale": "de-DE",
        "language_code": "de",
        "quality": "x_low",
        "provider": "piper",
    },
    # Spanish
    {
        "name": "Spanish (ES) – Carlfm (x-low)",
        "short_name": "es_ES-carlfm-x_low",
        "gender": "Male",
        "locale": "es-ES",
        "language_code": "es",
        "quality": "x_low",
        "provider": "piper",
    },
    {
        "name": "Spanish (MX) – Claude (High)",
        "short_name": "es_MX-claude-high",
        "gender": "Male",
        "locale": "es-MX",
        "language_code": "es",
        "quality": "high",
        "provider": "piper",
    },
    # French
    {
        "name": "French – Siwis (Medium)",
        "short_name": "fr_FR-siwis-medium",
        "gender": "Female",
        "locale": "fr-FR",
        "language_code": "fr",
        "quality": "medium",
        "provider": "piper",
    },
    # Italian
    {
        "name": "Italian – Riccardo (x-low)",
        "short_name": "it_IT-riccardo-x_low",
        "gender": "Male",
        "locale": "it-IT",
        "language_code": "it",
        "quality": "x_low",
        "provider": "piper",
    },
    # Portuguese
    {
        "name": "Portuguese (BR) – Faber (Medium)",
        "short_name": "pt_BR-faber-medium",
        "gender": "Male",
        "locale": "pt-BR",
        "language_code": "pt",
        "quality": "medium",
        "provider": "piper",
    },
    # Russian
    {
        "name": "Russian – Ruslan (Medium)",
        "short_name": "ru_RU-ruslan-medium",
        "gender": "Male",
        "locale": "ru-RU",
        "language_code": "ru",
        "quality": "medium",
        "provider": "piper",
    },
    # Dutch
    {
        "name": "Dutch – Mls (Medium)",
        "short_name": "nl_NL-mls-medium",
        "gender": "Female",
        "locale": "nl-NL",
        "language_code": "nl",
        "quality": "medium",
        "provider": "piper",
    },
    # Polish
    {
        "name": "Polish – Mls 6892 (Low)",
        "short_name": "pl_PL-mls_6892-low",
        "gender": "Female",
        "locale": "pl-PL",
        "language_code": "pl",
        "quality": "low",
        "provider": "piper",
    },
    # Ukrainian
    {
        "name": "Ukrainian – Lada (x-low)",
        "short_name": "uk_UA-lada-x_low",
        "gender": "Female",
        "locale": "uk-UA",
        "language_code": "uk",
        "quality": "x_low",
        "provider": "piper",
    },
    # Vietnamese
    {
        "name": "Vietnamese – Vivos (x-low)",
        "short_name": "vi_VN-vivos-x_low",
        "gender": "Female",
        "locale": "vi-VN",
        "language_code": "vi",
        "quality": "x_low",
        "provider": "piper",
    },
    # Turkish
    {
        "name": "Turkish – Dfki (Medium)",
        "short_name": "tr_TR-dfki-medium",
        "gender": "Male",
        "locale": "tr-TR",
        "language_code": "tr",
        "quality": "medium",
        "provider": "piper",
    },
    # Romanian
    {
        "name": "Romanian – Mihai (Medium)",
        "short_name": "ro_RO-mihai-medium",
        "gender": "Male",
        "locale": "ro-RO",
        "language_code": "ro",
        "quality": "medium",
        "provider": "piper",
    },
]

# Map short_name → voice metadata for O(1) lookup
_VOICE_MAP: Dict[str, Dict[str, Any]] = {v["short_name"]: v for v in _BUILTIN_VOICES}


def _build_model_url(short_name: str, extension: str) -> str:
    """Derive the HuggingFace download URL for a voice model file."""
    parts = short_name.split("-", 2)  # e.g. ["en_US", "lessac", "medium"]
    if len(parts) != 3:
        raise ValueError(f"Cannot parse voice short_name: {short_name!r}")
    lang_code, voice_name, voice_quality = parts
    lang_family = lang_code.split("_")[0]
    return _VOICE_URL.format(
        lang_family=lang_family,
        lang_code=lang_code,
        voice_name=voice_name,
        voice_quality=voice_quality,
        extension=extension,
    )


def _download_file(
    url: str,
    dest: Path,
    status_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Download *url* to *dest*, replacing any partial file on failure."""
    logger.info("Downloading %s …", url)
    if status_callback:
        status_callback(f"Downloading Piper model: {dest.name} …")
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with urlopen(url, timeout=120) as resp, open(tmp, "wb") as fh:
            shutil.copyfileobj(resp, fh)
        tmp.replace(dest)
        logger.info("Saved to %s", dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _ensure_model(
    short_name: str,
    models_dir: Path,
    status_callback: Optional[Callable[[str], None]] = None,
) -> Path:
    """Return path to the .onnx model, downloading it if necessary."""
    onnx_path = models_dir / f"{short_name}.onnx"
    json_path = models_dir / f"{short_name}.onnx.json"

    if not onnx_path.exists() or onnx_path.stat().st_size == 0:
        _download_file(_build_model_url(short_name, ".onnx"), onnx_path, status_callback)

    if not json_path.exists() or json_path.stat().st_size == 0:
        _download_file(_build_model_url(short_name, ".onnx.json"), json_path, status_callback)

    return onnx_path


def _make_wav_bytes(
    audio_bytes: bytes,
    sample_rate: int,
    sample_width: int = 2,
    channels: int = 1,
) -> bytes:
    """Wrap raw 16-bit PCM *audio_bytes* in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_bytes)
    return buf.getvalue()


def _make_silence_bytes(silence_secs: float, sample_rate: int, sample_width: int = 2, channels: int = 1) -> bytes:
    """Return silent PCM bytes for the given duration."""
    num_samples = max(0, int(sample_rate * silence_secs))
    return b"\x00" * (num_samples * sample_width * channels)


def _read_voice_config(short_name: str, models_dir: Path) -> Dict[str, Any]:
    """Read a voice model's JSON config and return its ``inference`` block.

    Piper ships each model with an ``.onnx.json`` sidecar that contains the
    recommended inference hyper-parameters (``noise_scale``, ``noise_w``,
    ``length_scale``) tuned specifically for that voice.  Using these instead
    of generic global defaults produces natural, accent-correct speech.

    Returns an empty dict if the file is missing, unreadable, or malformed so
    callers can fall back gracefully.
    """
    json_path = models_dir / f"{short_name}.onnx.json"
    if not json_path.is_file():
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        inference = data.get("inference", {})
        # Validate expected numeric fields; discard any that are non-numeric
        result: Dict[str, Any] = {}
        for key in ("noise_scale", "noise_w", "length_scale"):
            val = inference.get(key)
            if isinstance(val, (int, float)):
                result[key] = float(val)
        return result
    except Exception as exc:
        logger.debug("Could not read voice config for %s: %s", short_name, exc)
        return {}


class PiperTTSProvider(TTSProvider):
    """Offline neural TTS provider backed by Piper."""

    # Default model storage directory
    _DEFAULT_MODELS_DIR = Path.home() / ".critts" / "piper_voices"

    def __init__(self, settings_manager=None, models_dir: Optional[Path] = None,
                 status_callback: Optional[Callable[[str], None]] = None):
        self._settings_manager = settings_manager
        self._models_dir: Path = models_dir or self._DEFAULT_MODELS_DIR
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._status_callback: Optional[Callable[[str], None]] = status_callback
        # In-memory cache of loaded PiperVoice objects
        self._loaded_models: Dict[str, PiperVoice] = {}
        # Cache of per-voice inference config read from each model's .onnx.json
        self._voice_configs: Dict[str, Dict[str, Any]] = {}

    def set_status_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Register a callback that receives human-readable status messages.

        The callback is invoked (synchronously, from a background thread) when a
        model file is being downloaded or loaded for the first time so that the
        caller can surface progress information to the user.
        """
        self._status_callback = callback

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_voice(self, short_name: str) -> PiperVoice:
        """Return a cached (or freshly loaded) PiperVoice for *short_name*.

        Also populates ``self._voice_configs[short_name]`` from the model's
        ``.onnx.json`` sidecar so that per-voice inference parameters are
        available before the first synthesis call.
        """
        if short_name not in self._loaded_models:
            model_path = _ensure_model(short_name, self._models_dir, self._status_callback)
            logger.debug("Loading Piper model %s", model_path)
            if self._status_callback:
                self._status_callback(f"Loading Piper model: {short_name} …")
            self._loaded_models[short_name] = PiperVoice.load(str(model_path))
            # Read and cache the model's own recommended inference parameters
            cfg = _read_voice_config(short_name, self._models_dir)
            self._voice_configs[short_name] = cfg
            if cfg:
                logger.debug(
                    "Voice %s inference config: noise_scale=%.3f noise_w=%.3f length_scale=%.3f",
                    short_name,
                    cfg.get("noise_scale", 0.667),
                    cfg.get("noise_w", 0.8),
                    cfg.get("length_scale", 1.0),
                )
        return self._loaded_models[short_name]

    @staticmethod
    def _rate_to_length_scale(rate: int, base_length_scale: float = 1.0) -> float:
        """Convert edge-style rate (-100..100) to Piper length_scale.

        The adjustment is applied *relative* to *base_length_scale*, which is
        the value recommended by the voice model's own JSON config.  This
        ensures that rate=0 always means "the voice's natural tempo" rather
        than a generic 1.0 that may not match the model's training tempo.

        rate=0   → base_length_scale       (natural tempo for this voice)
        rate=100 → base_length_scale × 0.5  (2× faster)
        rate=-100 → base_length_scale × 2.0 (2× slower)
        """
        rate = max(-100, min(100, rate))
        # The 0.1 floor prevents a length_scale of zero (or close to it), which
        # would cause either division-by-zero or an extremely fast, unintelligible
        # output from the ONNX inference engine.
        speed_multiplier = 1.0 / max(0.1, 1.0 + rate / 100.0)
        return base_length_scale * speed_multiplier

    @staticmethod
    def _volume_to_scale(volume: int) -> float:
        """Convert 0-100 integer volume to a 0.0-1.0 float scale."""
        return max(0.0, min(1.0, volume / 100.0))

    def _get_noise_scale(self, voice: str) -> float:
        """Return the noise_scale to use for *voice*.

        Priority (highest → lowest):
        1. Explicit user override stored as ``piper_noise_scale`` in settings
           (only honoured when the user has actually customised the key, i.e.
           the stored value differs from the sentinel ``None``).
        2. Value recommended by the voice model's own ``.onnx.json`` config.
        3. Hard-coded Piper default (0.667).
        """
        _SENTINEL = None
        if self._settings_manager is not None:
            val = self._settings_manager.get("piper_noise_scale", _SENTINEL)
            if val is not _SENTINEL:
                try:
                    return float(max(0.0, min(2.0, val)))
                except (TypeError, ValueError):
                    pass
        # Use per-voice recommended value if available
        cfg = self._voice_configs.get(voice, {})
        if "noise_scale" in cfg:
            return cfg["noise_scale"]
        return 0.667

    def _get_noise_w_scale(self, voice: str) -> float:
        """Return the noise_w (phoneme duration variability) scale for *voice*.

        Same priority order as :meth:`_get_noise_scale`.
        """
        _SENTINEL = None
        if self._settings_manager is not None:
            val = self._settings_manager.get("piper_noise_w_scale", _SENTINEL)
            if val is not _SENTINEL:
                try:
                    return float(max(0.0, min(2.0, val)))
                except (TypeError, ValueError):
                    pass
        cfg = self._voice_configs.get(voice, {})
        if "noise_w" in cfg:
            return cfg["noise_w"]
        return 0.8

    def _get_length_scale_base(self, voice: str) -> float:
        """Return the natural tempo baseline (length_scale) for *voice*.

        Falls back to 1.0 if the model JSON does not specify one.
        """
        return self._voice_configs.get(voice, {}).get("length_scale", 1.0)

    def _get_sentence_silence(self) -> float:
        """Return silence duration (seconds) to insert between sentences.

        Reads ``piper_sentence_silence`` from settings; falls back to 0.2 s.
        Clamped to [0.0, 2.0] to avoid degenerate values.
        """
        _DEFAULT = 0.2
        if self._settings_manager is not None:
            val = self._settings_manager.get("piper_sentence_silence", None)
            if val is not None:
                try:
                    return float(max(0.0, min(2.0, val)))
                except (TypeError, ValueError):
                    pass
        return _DEFAULT

    # ------------------------------------------------------------------
    # TTSProvider interface
    # ------------------------------------------------------------------

    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Return the built-in list of available Piper voices."""
        return list(_BUILTIN_VOICES)

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
            text: Text to synthesize (already preprocessed by TTS engine).
            voice: Voice short name (e.g. "en_US-lessac-medium").
            rate: Speech rate adjustment (-100 to 100, 0 is normal).
            volume: Volume level (0 to 100, 100 is normal).
            pitch: Pitch adjustment (not supported by Piper; accepted but ignored).
            stop_event: Optional threading.Event to signal cancellation.

        Returns:
            WAV audio bytes, or None if generation was cancelled.
        """
        if stop_event and stop_event.is_set():
            return None

        loop = asyncio.get_event_loop()
        try:
            audio_bytes = await loop.run_in_executor(
                None,
                self._synthesize_blocking,
                text,
                voice,
                rate,
                volume,
                stop_event,
            )
        except URLError as exc:
            logger.error("Failed to download Piper voice model: %s", exc)
            raise RuntimeError(
                f"Could not download voice model '{voice}'. "
                "Please check your internet connection."
            ) from exc

        return audio_bytes

    def _synthesize_blocking(
        self,
        text: str,
        voice: str,
        rate: int,
        volume: int,
        stop_event,
    ) -> Optional[bytes]:
        """CPU-bound synthesis – run in executor to avoid blocking the event loop."""
        if stop_event and stop_event.is_set():
            return None

        piper_voice = self._load_voice(voice)
        syn_cfg = SynthesisConfig(
            length_scale=self._rate_to_length_scale(rate, self._get_length_scale_base(voice)),
            volume=self._volume_to_scale(volume),
            noise_scale=self._get_noise_scale(voice),
            noise_w_scale=self._get_noise_w_scale(voice),
        )
        silence_secs = self._get_sentence_silence()

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            first_chunk = True
            for chunk in piper_voice.synthesize(text, syn_config=syn_cfg):
                if stop_event and stop_event.is_set():
                    return None

                if first_chunk:
                    wav_file.setframerate(chunk.sample_rate)
                    wav_file.setsampwidth(chunk.sample_width)
                    wav_file.setnchannels(chunk.sample_channels)
                    first_chunk = False
                elif silence_secs > 0:
                    wav_file.writeframes(
                        _make_silence_bytes(silence_secs, chunk.sample_rate, chunk.sample_width, chunk.sample_channels)
                    )

                wav_file.writeframes(chunk.audio_int16_bytes)

        if stop_event and stop_event.is_set():
            return None

        return buf.getvalue()

    async def stream_speech(
        self,
        text: str,
        voice: str,
        rate: int = 0,
        volume: int = 100,
        pitch: int = 0,
        stop_event=None,
    ):
        """Stream speech sentence-by-sentence, yielding WAV-wrapped chunks.

        Each yielded chunk is a self-contained WAV byte-string for one sentence.
        This gives low-latency playback for long texts.
        """
        if stop_event and stop_event.is_set():
            return

        loop = asyncio.get_event_loop()
        piper_voice = await loop.run_in_executor(None, self._load_voice, voice)
        syn_cfg = SynthesisConfig(
            length_scale=self._rate_to_length_scale(rate, self._get_length_scale_base(voice)),
            volume=self._volume_to_scale(volume),
            noise_scale=self._get_noise_scale(voice),
            noise_w_scale=self._get_noise_w_scale(voice),
        )

        # synthesize() returns an iterable of AudioChunk (one per sentence)
        chunks = await loop.run_in_executor(
            None,
            lambda: list(piper_voice.synthesize(text, syn_config=syn_cfg)),
        )

        silence_secs = self._get_sentence_silence()
        for chunk in chunks:
            if stop_event and stop_event.is_set():
                return
            # Append sentence silence so playback has a natural pause after each sentence
            trailing_silence = (
                _make_silence_bytes(silence_secs, chunk.sample_rate, chunk.sample_width, chunk.sample_channels)
                if silence_secs > 0
                else b""
            )
            wav_bytes = _make_wav_bytes(
                chunk.audio_int16_bytes + trailing_silence,
                chunk.sample_rate,
                sample_width=chunk.sample_width,
                channels=chunk.sample_channels,
            )
            yield wav_bytes

    async def validate_voice(self, voice: str) -> bool:
        """Return True if *voice* is in the built-in voice list."""
        return voice in _VOICE_MAP

    def get_default_voice(self) -> str:
        """Return the default Piper voice."""
        return "en_US-lessac-medium"

    def clear_cache(self) -> None:
        """Unload all cached voice models from memory."""
        self._loaded_models.clear()
        self._voice_configs.clear()
