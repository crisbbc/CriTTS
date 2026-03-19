"""
Piper TTS Provider Module
Provides offline, open-source neural text-to-speech synthesis using Piper TTS.
Voice models are downloaded on first use and cached locally.
"""
import asyncio
import io
import logging
import shutil
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.request import urlopen
from urllib.error import URLError

from piper import PiperVoice, SynthesisConfig

from . import TTSProvider

logger = logging.getLogger(__name__)

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
        """Return a cached (or freshly loaded) PiperVoice for *short_name*."""
        if short_name not in self._loaded_models:
            model_path = _ensure_model(short_name, self._models_dir, self._status_callback)
            logger.debug("Loading Piper model %s", model_path)
            if self._status_callback:
                self._status_callback(f"Loading Piper model: {short_name} …")
            self._loaded_models[short_name] = PiperVoice.load(str(model_path))
        return self._loaded_models[short_name]

    @staticmethod
    def _rate_to_length_scale(rate: int) -> float:
        """Convert edge-style rate (-100..100) to Piper length_scale.

        A higher length_scale produces slower speech; lower produces faster speech.
        rate=0  → length_scale=1.0  (normal)
        rate=100 → length_scale≈0.5  (2× faster)
        rate=-100 → length_scale=2.0 (2× slower)
        """
        rate = max(-100, min(100, rate))
        # The 0.1 floor prevents a length_scale of zero (or close to it), which
        # would cause either division-by-zero or an extremely fast, unintelligible
        # output from the ONNX inference engine.
        return 1.0 / max(0.1, 1.0 + rate / 100.0)

    @staticmethod
    def _volume_to_scale(volume: int) -> float:
        """Convert 0-100 integer volume to a 0.0-1.0 float scale."""
        return max(0.0, min(1.0, volume / 100.0))

    def _get_noise_scale(self) -> float:
        """Return the noise_scale setting (controls expressiveness/phoneme variability)."""
        if self._settings_manager is not None:
            val = self._settings_manager.get("piper_noise_scale", 0.667)
            try:
                return float(max(0.0, min(2.0, val)))
            except (TypeError, ValueError):
                pass
        return 0.667

    def _get_noise_w_scale(self) -> float:
        """Return the noise_w_scale setting (controls phoneme duration variability)."""
        if self._settings_manager is not None:
            val = self._settings_manager.get("piper_noise_w_scale", 0.8)
            try:
                return float(max(0.0, min(2.0, val)))
            except (TypeError, ValueError):
                pass
        return 0.8

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
            length_scale=self._rate_to_length_scale(rate),
            volume=self._volume_to_scale(volume),
            noise_scale=self._get_noise_scale(),
            noise_w_scale=self._get_noise_w_scale(),
        )

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            piper_voice.synthesize_wav(text, wav_file, syn_config=syn_cfg)

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
            length_scale=self._rate_to_length_scale(rate),
            volume=self._volume_to_scale(volume),
            noise_scale=self._get_noise_scale(),
            noise_w_scale=self._get_noise_w_scale(),
        )

        # synthesize() returns an iterable of AudioChunk (one per sentence)
        chunks = await loop.run_in_executor(
            None,
            lambda: list(piper_voice.synthesize(text, syn_config=syn_cfg)),
        )

        for chunk in chunks:
            if stop_event and stop_event.is_set():
                return
            wav_bytes = _make_wav_bytes(
                chunk.audio_int16_bytes,
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
