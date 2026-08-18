"""
TTS Engine Module
Manages text-to-speech generation, supporting multiple providers.
"""
import asyncio
import threading
from collections import OrderedDict
from importlib import import_module
from typing import List, Dict, Optional, Tuple
import time
import logging
import re
from pathlib import Path

from .providers.edge_tts_provider import EdgeTTSProvider
from .providers.coqui_metadata import get_coqui_voice_metadata
from .audio_cache import AudioCache, PhraseTracker
from ..config.settings_manager import SettingsManager

# Import the new language detector module
from ..utils.language_detector import LanguageDetector, detect_language, get_detector

logger = logging.getLogger(__name__)




class TTSEngine:
    """Manages text-to-speech generation using the configured TTS provider."""

    # Class-level constants for number-to-word conversion (avoids recreating on every call)
    _NUMBER_WORDS = {
        'en': ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
               'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
               'seventeen', 'eighteen', 'nineteen', 'twenty'],
        'es': ['cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve',
               'diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis',
               'diecisiete', 'dieciocho', 'diecinueve', 'veinte'],
        'fr': ['zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf',
               'dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize',
               'dix-sept', 'dix-huit', 'dix-neuf', 'vingt'],
        'de': ['null', 'eins', 'zwei', 'drei', 'vier', 'fünf', 'sechs', 'sieben', 'acht', 'neun',
               'zehn', 'elf', 'zwölf', 'dreizehn', 'vierzehn', 'fünfzehn', 'sechzehn',
               'siebzehn', 'achtzehn', 'neunzehn', 'zwanzig'],
        'it': ['zero', 'uno', 'due', 'tre', 'quattro', 'cinque', 'sei', 'sette', 'otto', 'nove',
               'dieci', 'undici', 'dodici', 'tredici', 'quattordici', 'quindici', 'sedici',
               'diciassette', 'diciotto', 'diciannove', 'venti'],
        'pt': ['zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove',
               'dez', 'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezesseis',
               'dezessete', 'dezoito', 'dezenove', 'vinte'],
        'ru': ['ноль', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять',
               'десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать', 'шестнадцать',
               'семнадцать', 'восемнадцать', 'девятнадцать', 'двадцать'],
        'zh': ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九',
               '十', '十一', '十二', '十三', '十四', '十五', '十六',
               '十七', '十八', '十九', '二十'],
        'ja': ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九',
               '十', '十一', '十二', '十三', '十四', '十五', '十六',
               '十七', '十八', '十九', '二十'],
        'ko': ['영', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구',
               '십', '십일', '십이', '십삼', '십사', '십오', '십육',
               '십칠', '십팔', '십구', '이십'],
    }

    _TENS_WORDS = {
        'en': ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'],
        'es': ['', '', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa'],
        'fr': ['', '', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante', 'soixante', 'quatre-vingt', 'quatre-vingt'],
        'de': ['', '', 'zwanzig', 'dreißig', 'vierzig', 'fünfzig', 'sechzig', 'siebzig', 'achtzig', 'neunzig'],
        'it': ['', '', 'venti', 'trenta', 'quaranta', 'cinquanta', 'sessanta', 'settanta', 'ottanta', 'novanta'],
        'pt': ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa'],
        'ru': ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто'],
        'zh': ['', '', '二十', '三十', '四十', '五十', '六十', '七十', '八十', '九十'],
        'ja': ['', '', '二十', '三十', '四十', '五十', '六十', '七十', '八十', '九十'],
        'ko': ['', '', '이십', '삼십', '사십', '오십', '육십', '칠십', '팔십', '구십'],
    }

    _HUNDREDS_WORDS = {
        'en': ['', 'one hundred', 'two hundred', 'three hundred', 'four hundred', 'five hundred', 'six hundred', 'seven hundred', 'eight hundred', 'nine hundred'],
        'es': ['', 'cien', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos', 'novecientos'],
        'fr': ['', 'cent', 'deux cents', 'trois cents', 'quatre cents', 'cinq cents', 'six cents', 'sept cents', 'huit cents', 'neuf cents'],
        'de': ['', 'einhundert', 'zweihundert', 'dreihundert', 'vierhundert', 'fünfhundert', 'sechshundert', 'siebenhundert', 'achthundert', 'neunhundert'],
        'it': ['', 'cento', 'duecento', 'trecento', 'quattrocento', 'cinquecento', 'seicento', 'settecento', 'ottocento', 'novecento'],
        'pt': ['', 'cem', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos'],
        'ru': ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот'],
        'zh': ['', '一百', '二百', '三百', '四百', '五百', '六百', '七百', '八百', '九百'],
        'ja': ['', '百', '二百', '三百', '四百', '五百', '六百', '七百', '八百', '九百'],
        'ko': ['', '백', '이백', '삼백', '사백', '오백', '육백', '칠백', '팔백', '구백'],
    }

    # Regex patterns used by _clean_symbols (compiled once at class level)
    _URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')
    _MARKDOWN_BOLD_ITALIC = re.compile(r'\*{1,3}(.+?)\*{1,3}', re.DOTALL)
    _MARKDOWN_UNDERLINE = re.compile(r'_{1,2}(.+?)_{1,2}', re.DOTALL)
    _MARKDOWN_STRIKE = re.compile(r'~~(.+?)~~', re.DOTALL)
    _MARKDOWN_CODE = re.compile(r'`{1,3}[^`]*`{1,3}')
    _MARKDOWN_BLOCK_QUOTE = re.compile(r'^\s*>\s?', re.MULTILINE)
    _EMOJI_PATTERN = re.compile(
        u'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F'
        u'\U00010000-\U0010FFFF\u2600-\u26FF\u2700-\u27BF]+',
        re.UNICODE
    )
    _REPEATED_PUNCT = re.compile(r'([!?]){2,}')
    _PIPER_VOICE_LANGUAGE = re.compile(r'^([A-Za-z]{2,3})(?:[_-][A-Za-z]{2,4})?[-_]')
    _CURRENCY_SYMBOLS = '$€£¥₹₽₩¢₿'
    _PERCENT_SYMBOLS = '%‰'

    def __init__(self, settings_manager: Optional['SettingsManager'] = None):
        """Initialize the TTS engine.
        
        Args:
            settings_manager: Optional SettingsManager instance. If provided, it will be used
                            for all settings access instead of creating new instances.
        """
        self._settings_manager = settings_manager
        self._voices_cache: Optional[List[Dict]] = None
        self._cache_timestamp: float = 0
        self._cache_duration: float = 300  # Cache voices for 5 minutes
        self._cached_provider: str = ""  # Track which provider the cache belongs to
        self._voice_cache: OrderedDict = OrderedDict()  # Cache for voice validation (LRU)
        self._voice_cache_lock = threading.Lock()  # Lock for thread-safe voice cache access
        self._text_cache: OrderedDict = OrderedDict()  # Cache for text processing (LRU)
        self._text_cache_lock = threading.Lock()  # Lock for thread-safe text cache access
        self._provider_init_lock = threading.Lock()
        self._coqui_status_callback = None
        self._committed_provider_name = self._get_active_provider_name()
        
        # Initialize always-lightweight provider eagerly; keep heavyweight offline providers lazy.
        self._edge_tts_provider = EdgeTTSProvider(settings_manager=self._settings_manager)
        self._coqui_provider_instance = None
        self._piper_provider_instance = None
        
        # Initialize audio cache and phrase tracker
        self._audio_cache: Optional[AudioCache] = None
        self._phrase_tracker: Optional[PhraseTracker] = None
        self._cache_settings_loaded = False
        
        # Load cache settings
        self._load_cache_settings()
    
    def _get_settings(self) -> 'SettingsManager':
        """Get the settings manager instance, using injected one or creating new as fallback."""
        if self._settings_manager is not None:
            return self._settings_manager
        return SettingsManager()

    @staticmethod
    def _coerce_cache_path(value) -> Optional[Path]:
        """Return ``value`` as a real cache path, or ``None`` when it isn't one.

        ``audio_cache_path`` is read from the settings manager, which in tests
        may be a MagicMock whose ``get()`` returns another mock.  ``pathlib.Path``
        converts such mocks into a relative ``MagicMock/mock.get()/…`` path, and
        AudioCache would then create that directory on disk.  Only genuine
        ``str``/``Path`` values are valid cache locations; anything else falls
        back to the default.
        """
        if isinstance(value, (str, Path)):
            return Path(value)
        return None
    
    def reload_cache_settings(self):
        """
        Reload cache-related settings from the settings manager.
        
        This method should be called after settings are changed to update
        cache behavior without requiring a restart.
        """
        try:
            settings = self._get_settings()
            
            # Get cache settings
            cache_enabled = settings.get("audio_cache_enabled", True)
            max_size_mb = settings.get("audio_cache_max_size_mb", 500)
            cache_path = self._coerce_cache_path(settings.get("audio_cache_path"))
            
            # Update audio cache settings if cache exists
            if self._audio_cache:
                self._audio_cache.enabled = cache_enabled
                self._audio_cache.max_size_mb = max_size_mb
                # If cache path changed, we'd need to reinitialize - log a warning
                current_cache_dir = str(self._audio_cache.cache_dir) if self._audio_cache.cache_dir else None
                new_cache_path = str(cache_path) if cache_path is not None else None
                if current_cache_dir != new_cache_path:
                    logger.warning("Cache path change requires restart to take effect")
            
            # Update text cache size from settings
            self._max_cache_size = settings.get("text_cache_size", 1000)
            
            logger.info(f"Cache settings reloaded: enabled={cache_enabled}, max_size={max_size_mb}MB, text_cache_size={self._max_cache_size}")
            
        except Exception as e:
            logger.warning(f"Failed to reload cache settings: {e}")
    
    def _load_cache_settings(self):
        """Load cache settings from settings manager."""
        try:
            settings = self._get_settings()
            
            # Get cache settings
            cache_enabled = settings.get("audio_cache_enabled", True)
            max_size_mb = settings.get("audio_cache_max_size_mb", 500)
            cache_path = self._coerce_cache_path(settings.get("audio_cache_path"))
            
            # Initialize audio cache
            self._audio_cache = AudioCache(
                cache_dir=cache_path,
                max_size_mb=max_size_mb,
                enabled=cache_enabled
            )
            
            # Initialize phrase tracker
            self._phrase_tracker = PhraseTracker()
            
            # Update text cache size from settings
            self._max_cache_size = settings.get("text_cache_size", 1000)
            
            self._cache_settings_loaded = True
            logger.info(f"Audio cache initialized: enabled={cache_enabled}, max_size={max_size_mb}MB")
            
        except Exception as e:
            logger.warning(f"Failed to load cache settings: {e}")
            # Use defaults
            self._audio_cache = AudioCache(enabled=True)
            self._phrase_tracker = PhraseTracker()
            self._max_cache_size = 1000
    
    def get_audio_cache_statistics(self) -> Dict:
        """Get audio cache statistics."""
        if self._audio_cache:
            return self._audio_cache.get_statistics()
        return {"enabled": False, "entries": 0, "size_mb": 0}
    
    def clear_audio_cache(self) -> bool:
        """Clear the audio cache."""
        if self._audio_cache:
            return self._audio_cache.clear()
        return False
    
    def get_common_phrases(self, min_uses: int = 3, limit: int = 20) -> list:
        """Get commonly used phrases for pre-generation."""
        if self._phrase_tracker:
            return self._phrase_tracker.get_common_phrases(min_uses, limit)
        return []
    
    async def pregenerate_common_phrases(self, progress_callback=None, stop_event=None) -> int:
        """
        Pre-generate audio for common phrases.
        
        Args:
            progress_callback: Optional callback for progress updates
            stop_event: Optional event to signal cancellation (checked between
                phrases and passed into each generate_speech call)
            
        Returns:
            Number of phrases pre-generated
        """
        if not self._phrase_tracker or not self._audio_cache:
            return 0
        
        settings = self._get_settings()
        min_uses = settings.get("pregenerate_min_uses", 3)
        max_phrases = settings.get("pregenerate_max_phrases", 20)
        
        phrases = self._phrase_tracker.get_common_phrases(min_uses, max_phrases)
        generated = 0
        
        provider_name = self._get_active_provider_name()
        fingerprint = self._get_audio_cache_fingerprint(provider_name)

        for text, voice, count in phrases:
            if stop_event is not None and stop_event.is_set():
                break

            # Resolve the exact voice and preprocessed text that
            # generate_speech() will use, so this pre-check matches the runtime
            # cache key.  Looking up the raw text always missed — generate_speech
            # caches under the *preprocessed* text — so already-cached phrases
            # were re-invoked (and re-counted) on every run.
            actual_voice, voice_error = await self._resolve_synthesis_voice(
                text, voice, provider_name
            )
            if voice_error:
                continue

            processed_text = await self.preprocess_text(
                text, actual_voice, provider_name=provider_name,
            )

            if self._audio_cache.lookup(
                processed_text,
                actual_voice,
                0,
                100,
                0,
                provider=provider_name,
                settings_fingerprint=fingerprint,
            ):
                continue
            
            # Generate and cache (generate_speech derives the identical key)
            try:
                audio_data, error = await self.generate_speech(
                    text, actual_voice, stop_event=stop_event
                )
                if audio_data and not error:
                    generated += 1
                    if progress_callback:
                        progress_callback(generated, len(phrases))
            except Exception as e:
                logger.debug(f"Failed to pre-generate phrase: {e}")
        
        return generated
    
    def _get_active_provider_name(self) -> str:
        """Return the configured TTS provider name ('edge', 'piper', or 'coqui')."""
        if self._settings_manager:
            return self._settings_manager.get("tts_provider", "edge")
        return "edge"

    def _get_audio_cache_fingerprint(self, provider_name: str) -> str:
        """Return a stable fingerprint of settings that affect cached audio content.

        The disk audio cache is keyed on (provider, processed text, voice, rate,
        volume, pitch).  Any other setting that changes the synthesized waveform
        (Coqui language, Piper noise/silence knobs, playback EQ/normalization/
        profile) would otherwise silently replay audio recorded under a different
        configuration — which sounds "stale" after the user tweaks a knob.  All
        of them are folded into the fingerprint so a config change becomes a
        cache miss.  Playback processing is re-applied at play time, but is
        included anyway so the cache contract is simply "audio valid for exactly
        these settings".
        """
        settings = self._get_settings()

        def _get(key: str, default):
            try:
                return settings.get(key, default)
            except Exception:
                return default

        parts = []
        if provider_name == "coqui":
            parts.append(f"lang={_get('coqui_language', 'en')}")
            parts.append(f"temp={_get('coqui_temperature', 0.75)}")
            parts.append(f"rep={_get('coqui_repetition_penalty', 10.0)}")
            parts.append(f"split={int(bool(_get('coqui_enable_text_splitting', True)))}")
        elif provider_name == "piper":
            parts.append(f"ns={_get('piper_noise_scale', None)}")
            parts.append(f"nw={_get('piper_noise_w_scale', None)}")
            parts.append(f"sil={_get('piper_sentence_silence', None)}")

        parts.append(f"eq={int(bool(_get('enable_clarity_eq', True)))}")
        parts.append(
            f"norm={int(bool(_get('enable_normalization', True)))}:"
            f"{_get('normalization_type', 'Peak')}"
        )
        parts.append(f"prof={_get('processing_profile', 'balanced')}")
        return "|".join(parts)

    def _create_coqui_provider(self):
        """Create the Coqui provider on first real use."""
        provider_module = import_module("src.tts.providers.coqui_tts_provider")
        provider = provider_module.CoquiTTSProvider(settings_manager=self._settings_manager)
        if self._coqui_status_callback is not None:
            provider.set_status_callback(self._coqui_status_callback)
        return provider

    def _create_piper_provider(self):
        """Create the Piper provider on first real use."""
        provider_module = import_module("src.tts.providers.piper_tts_provider")
        return provider_module.PiperTTSProvider(settings_manager=self._settings_manager)

    @property
    def _coqui_tts_provider(self):
        """Lazily create the Coqui provider."""
        if self._coqui_provider_instance is None:
            with self._provider_init_lock:
                if self._coqui_provider_instance is None:
                    self._coqui_provider_instance = self._create_coqui_provider()
                    if self._coqui_status_callback is not None:
                        self._coqui_provider_instance.set_status_callback(self._coqui_status_callback)
        return self._coqui_provider_instance

    @property
    def _piper_tts_provider(self):
        """Lazily create the Piper provider."""
        if self._piper_provider_instance is None:
            with self._provider_init_lock:
                if self._piper_provider_instance is None:
                    self._piper_provider_instance = self._create_piper_provider()
        return self._piper_provider_instance

    def _get_provider_by_name(self, provider_name: str):
        """Return the provider instance for a provider key."""
        if provider_name == "coqui":
            return self._coqui_tts_provider
        if provider_name == "piper":
            return self._piper_tts_provider
        return self._edge_tts_provider

    def _get_voice_metadata(self, provider_name: str) -> Optional[List[Dict]]:
        """Return lightweight provider voice metadata when runtime import is unnecessary."""
        if provider_name == "coqui":
            return get_coqui_voice_metadata()
        return None

    async def get_available_voices(self, provider_override: Optional[str] = None) -> List[Dict]:
        """
        Get list of available voices from the current provider.

        Args:
            provider_override: Optional provider key ("edge", "piper", or "coqui") used
                for transient UI reloads before settings are saved.
        
        Returns:
            List of voice dictionaries with 'name', 'id', 'provider', and provider-specific metadata.
        """
        if provider_override is not None:
            try:
                metadata_voices = self._get_voice_metadata(provider_override)
                if metadata_voices is not None:
                    metadata_voices.sort(key=lambda x: x.get('name', ''))
                    return metadata_voices

                provider = self._get_provider_by_name(provider_override)
                voices = await provider.get_available_voices()
                voices.sort(key=lambda x: x.get('name', ''))
                # Do not update shared cache for override fetches because the selection
                # may be unsaved and should not affect runtime provider caching.
                return voices
            except Exception as e:
                logger.error(f"Error getting voices from provider override '{provider_override}': {e}")
                return []

        active_provider = self._get_active_provider_name()

        # Return cached voices only when they are still fresh AND belong to the active provider.
        # If the provider has changed since the cache was populated we must refetch, otherwise
        # the Voice tab would display the previous provider's voices.
        if (
            self._voices_cache is not None
            and self._cached_provider == active_provider
            and time.time() - self._cache_timestamp < self._cache_duration
        ):
            return self._voices_cache
        
        try:
            metadata_voices = self._get_voice_metadata(active_provider)
            if metadata_voices is not None:
                metadata_voices.sort(key=lambda x: x.get('name', ''))
                self._voices_cache = metadata_voices
                self._cache_timestamp = time.time()
                self._cached_provider = active_provider
                return metadata_voices

            # Get current provider
            provider = self._get_current_provider()
            
            # Get voices from provider
            voices = await provider.get_available_voices()
            
            # Sort voices for better UX
            voices.sort(key=lambda x: x.get('name', ''))
            
            # Populate cache together with the provider it belongs to
            self._voices_cache = voices
            self._cache_timestamp = time.time()
            self._cached_provider = active_provider
            
            return voices
            
        except Exception as e:
            logger.error(f"Error getting voices from provider: {e}")
            return []
    
    def _get_current_provider(self):
        """Get the currently active TTS provider based on settings."""
        return self._get_provider_by_name(self._get_active_provider_name())

    def set_coqui_status_callback(self, callback) -> None:
        """Register a status callback on the Coqui TTS provider.

        The callback is called (from a background thread) with a human-readable
        string whenever the Coqui model is being downloaded or loaded for
        the first time.  Pass *None* to remove the callback.
        """
        self._coqui_status_callback = callback
        if self._coqui_provider_instance is not None:
            self._coqui_provider_instance.set_status_callback(callback)

    def preload_coqui_model_async(self) -> None:
        """Trigger Coqui model preloading in a daemon background thread.

        Safe to call multiple times — does nothing if the model is already loaded.
        Status updates are forwarded via the registered Coqui status callback.
        """
        import threading
        t = threading.Thread(
            target=self._coqui_tts_provider._ensure_model_loaded,
            daemon=True,
            name="coqui-preload",
        )
        t.start()

    def handle_committed_provider_change(self) -> None:
        """Apply the small offline-provider unload policy after settings are saved."""
        active_provider = self._get_active_provider_name()
        previous_provider = self._committed_provider_name
        self._committed_provider_name = active_provider

        if previous_provider == active_provider:
            return

        if previous_provider == "coqui" and self._coqui_provider_instance is not None:
            try:
                self._coqui_provider_instance.clear_cache()
            except Exception as e:
                logger.warning(f"Failed to clear inactive Coqui TTS cache: {e}")
    
    def clear_voices_cache(self):
        """Clear the voices cache to force refresh on next call."""
        self._voices_cache = None
        self._cached_provider = ""
        with self._voice_cache_lock:
            self._voice_cache.clear()
        
        # Clear provider caches
        try:
            self._edge_tts_provider.clear_cache()
        except Exception as e:
            logger.warning(f"Failed to clear Edge TTS cache: {e}")

        if self._coqui_provider_instance is not None:
            try:
                self._coqui_provider_instance.clear_cache()
            except Exception as e:
                logger.warning(f"Failed to clear Coqui TTS cache: {e}")

        if self._piper_provider_instance is not None:
            try:
                self._piper_provider_instance.clear_cache()
            except Exception as e:
                logger.warning(f"Failed to clear Piper TTS cache: {e}")
    
    async def generate_speech_batch(self, texts: List[str], **kwargs) -> List[Tuple[Optional[bytes], Optional[str]]]:
        """
        Generate speech for multiple texts efficiently.
        
        Args:
            texts: List of texts to convert to speech
            **kwargs: Same parameters as generate_speech
            
        Returns:
            List of tuples (audio_data, error_message) for each text
        """
        if not texts:
            return []
        
        # Process texts concurrently for better performance
        tasks = [self.generate_speech(text, **kwargs) for text in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append((None, f"Error processing text {i+1}: {str(result)}"))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def get_optimal_voice_for_text(self, text: str) -> Optional[str]:
        """
        Suggest the most appropriate voice for the given text based on language detection.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Suggested voice ID or None if no match found
        """
        if not text:
            return None
        
        # Language-based voice selection is supported when a voices cache is available
        if self._voices_cache:
            return self._detect_language_voice(text)
        
        return None
    
    async def validate_voice(
        self,
        voice_short_name: str,
        provider_name: Optional[str] = None,
    ) -> bool:
        """
        Return True if the given voice short_name exists in the available voices.
        Can be called before TTS generation to prevent errors.
        """
        provider_cache_key = provider_name or self._get_active_provider_name()
        cache_key = (provider_cache_key, voice_short_name)

        # Thread-safe cache lookup
        with self._voice_cache_lock:
            if cache_key in self._voice_cache:
                self._voice_cache.move_to_end(cache_key)
                return self._voice_cache[cache_key]

        voices = await self.get_available_voices(provider_override=provider_name)
        short_names = {v.get("short_name") for v in voices if v.get("short_name")}
        is_valid = voice_short_name in short_names

        # Thread-safe cache update with efficient batch eviction when full
        with self._voice_cache_lock:
            if len(self._voice_cache) >= self._max_cache_size:
                # Remove 10% of entries (minimum 1) for better performance
                # than single-entry eviction on every insert
                entries_to_remove = max(1, self._max_cache_size // 10)
                for _ in range(entries_to_remove):
                    if self._voice_cache:
                        oldest_key = next(iter(self._voice_cache))
                        del self._voice_cache[oldest_key]

            self._voice_cache[cache_key] = is_valid
        return is_valid
    
    async def preprocess_text(
        self,
        text: str,
        voice: Optional[str] = None,
        provider_name: Optional[str] = None,
    ) -> str:
        """
        Preprocess text for better TTS quality and speed.
        
        Args:
            text: Input text to preprocess
            voice: Voice ID to determine language for number formatting.
                   If None, falls back to settings voice.
            provider_name: Optional provider key to keep preprocessing stable for
                    a single request even if settings change mid-call.
            
        Returns:
            Preprocessed text optimized for TTS
        """
        active_provider_name = provider_name or self._get_active_provider_name()
        language = self._get_current_voice_language(voice, active_provider_name)

        # Use cached preprocessing for repeated text.
        # Include provider/language so multilingual offline settings do not reuse
        # stale English-biased preprocessing from a previous voice/configuration.
        cache_key = (text.strip(), voice or "default", active_provider_name, language)
        
        # Thread-safe cache lookup
        with self._text_cache_lock:
            if cache_key in self._text_cache:
                self._text_cache.move_to_end(cache_key)
                return self._text_cache[cache_key]
        
        # Text preprocessing for better TTS quality
        processed_text = text.replace('\r\n', '\n').replace('\r', '\n').strip()

        # Strip symbols/URLs/emojis/markdown that TTS handles poorly
        processed_text = self._clean_symbols(processed_text)

        # Handle language-aware number formatting
        processed_text = self._format_numbers(processed_text, voice)

        # Add provider-aware pauses after preserving paragraph breaks
        processed_text = self._add_natural_pauses(processed_text, active_provider_name)
        
        # Note: No hard truncation - edge_tts handles long inputs without a documented
        # 2000-character limit. If issues arise, consider chunking instead.
        
        # Thread-safe cache update with size limit
        with self._text_cache_lock:
            if len(self._text_cache) >= self._max_cache_size:
                oldest_key = next(iter(self._text_cache))
                del self._text_cache[oldest_key]
            self._text_cache[cache_key] = processed_text
        
        return processed_text
    
    @staticmethod
    def _clean_symbols(text: str) -> str:
        """Remove or replace symbols that TTS engines struggle to pronounce clearly.

        Handles URLs, markdown formatting, emojis, and common symbol substitutions
        so the synthesised speech doesn't contain garbled character strings.
        """
        # Replace URLs with the spoken word "link"
        text = TTSEngine._URL_PATTERN.sub('link', text)

        # Strip markdown formatting but preserve the inner text
        text = TTSEngine._MARKDOWN_BOLD_ITALIC.sub(r'\1', text)
        text = TTSEngine._MARKDOWN_UNDERLINE.sub(r'\1', text)
        text = TTSEngine._MARKDOWN_STRIKE.sub(r'\1', text)
        text = TTSEngine._MARKDOWN_CODE.sub('', text)
        text = TTSEngine._MARKDOWN_BLOCK_QUOTE.sub('', text)

        # Strip emojis (they produce garbled output or unicode names in most TTS models)
        text = TTSEngine._EMOJI_PATTERN.sub('', text)

        # Replace common symbols with natural spoken equivalents
        text = text.replace(' & ', ' and ')
        text = re.sub(r'&', ' and ', text)
        text = re.sub(r'\bw/o\b', 'without', text)
        text = re.sub(r'\bw/\b', 'with', text)

        # Reduce runs of repeated punctuation to a single mark (e.g. "!!!!" → "!")
        text = TTSEngine._REPEATED_PUNCT.sub(r'\1', text)

        # Normalise whitespace
        text = re.sub(r' {2,}', ' ', text).strip()
        return text

    def _format_numbers(self, text: str, voice: Optional[str] = None) -> str:
        """Format standalone whole numbers for better TTS pronunciation.

        Only plain, standalone integers (0-999) are rewritten to words.
        Decimals, currency amounts, thousands-separated figures, times,
        fractions, dates, percentages, and standalone years or larger numbers
        are left untouched so the provider can read them with proper context.
        
        Args:
            text: Text containing numbers to format
            voice: Voice ID to determine language. If None, falls back to settings voice.
            
        Returns:
            Text with standalone small numbers converted to words
        """
        # Get the current voice to determine language
        current_voice = self._get_current_voice_language(voice)

        # Get number words for current language (default to English)
        words = self._NUMBER_WORDS.get(current_voice, self._NUMBER_WORDS['en'])

        def part_of_larger_number(match) -> bool:
            """True when a digit run belongs to a bigger numeric token."""
            start, end = match.start(), match.end()
            prev = text[start - 1] if start > 0 else ''
            nxt = text[end] if end < len(text) else ''

            # Currency attaches before the number ($5.99); % and ‰ attach after (50%).
            if prev and prev in self._CURRENCY_SYMBOLS:
                return True
            if nxt and nxt in self._PERCENT_SYMBOLS:
                return True

            # A separator only links two halves of a number when a digit sits on
            # the other side (3.14, 1,234, 12:30, 3/4, 555-1234, 2026-08-17).
            for separator in '.,:/':
                if prev == separator and start > 1 and text[start - 2].isdigit():
                    return True
                if nxt == separator and end + 1 < len(text) and text[end + 1].isdigit():
                    return True

            for dash in '-–—':
                if prev == dash and start > 1 and text[start - 2].isdigit():
                    return True
                if nxt == dash and end + 1 < len(text) and text[end + 1].isdigit():
                    return True

            return False

        def number_to_words(match):
            num = int(match.group())

            if part_of_larger_number(match) or num >= 1000:
                return match.group()

            if 0 <= num <= 20:
                return words[num]
            if 21 <= num <= 99:
                return self._convert_tens_to_words(num, words, current_voice)
            return self._convert_hundreds_to_words(num, words, current_voice)
        
        # Replace standalone whole numbers with words
        text = re.sub(r'\b\d+\b', number_to_words, text)
        
        return text
    
    def _convert_tens_to_words(self, num: int, words: list, language: str) -> str:
        """Convert numbers 21-99 to words."""
        if num <= 20:
            return words[num]

        tens = num // 10
        ones = num % 10

        tens_list = self._TENS_WORDS.get(language, self._TENS_WORDS['en'])
        
        if ones == 0:
            return tens_list[tens]
        elif language == 'en' and tens == 2:
            return f"twenty-{words[ones]}"
        elif language == 'fr' and tens in [7, 9]:
            # French special case for 70-79 and 90-99
            base = 60 if tens == 7 else 80
            return f"{tens_list[base//10]}-{words[num - base]}"
        elif language == 'de' and ones != 0:
            # German special case: ones come first
            return f"{words[ones]}und{tens_list[tens]}"
        else:
            return f"{tens_list[tens]}-{words[ones]}"
    
    def _convert_hundreds_to_words(self, num: int, words: list, language: str) -> str:
        """Convert numbers 100-999 to words."""
        hundreds = num // 100
        remainder = num % 100

        hundreds_list = self._HUNDREDS_WORDS.get(language, self._HUNDREDS_WORDS['en'])
        
        result = hundreds_list[hundreds]
        if remainder > 0:
            if language in ['en', 'fr', 'de', 'it', 'pt']:
                result += f" {self._convert_tens_to_words(remainder, words, language)}"
            else:
                result += self._convert_tens_to_words(remainder, words, language)
        
        return result
    
    @staticmethod
    def _normalize_language_code(language_code: Optional[str]) -> str:
        """Normalize locale-like codes to the base number-formatting language."""
        if not isinstance(language_code, str) or not language_code.strip():
            return 'en'

        normalized = language_code.strip().lower().replace('_', '-')
        if normalized.startswith('zh-'):
            return 'zh'
        return normalized.split('-', 1)[0]

    def _get_current_voice_language(
        self,
        voice: Optional[str] = None,
        provider_name: Optional[str] = None,
    ) -> str:
        """Get the language code from a voice ID.
        
        Args:
            voice: Voice ID to extract language from. If None, falls back to settings voice.
            
        Returns:
            Language code (e.g., 'en', 'es', 'fr')
        """
        current_voice = voice
        provider_name = provider_name or self._get_active_provider_name()
        if current_voice is None:
            try:
                settings_manager = self._get_settings()
                current_voice = settings_manager.get("voice", "en-US-AriaNeural")
            except Exception:
                current_voice = "en-US-AriaNeural"

        if provider_name == "coqui":
            try:
                settings_manager = self._get_settings()
                return self._normalize_language_code(settings_manager.get("coqui_language", "en"))
            except Exception:
                return 'en'

        if provider_name == "piper":
            match = self._PIPER_VOICE_LANGUAGE.match(current_voice)
            if match:
                return self._normalize_language_code(match.group(1))
            return 'en'

        if '-' in current_voice:
            return self._normalize_language_code(current_voice.split('-', 1)[0])

        return 'en'

    def _add_natural_pauses(self, text: str, provider_name: str = "edge") -> str:
        """
        Add natural pauses to improve speech flow.
        
        Note: edge-tts does not reliably support inline SSML tags in the text stream.
        The tags get spoken as plain text instead of being interpreted.
        This method now only handles text normalization without SSML injection.
        """
        paragraphs = re.split(r'\n\s*\n+', text.strip())
        processed_paragraphs = []

        for paragraph in paragraphs:
            chunk = re.sub(r'\s*\n\s*', ' ', paragraph.strip())
            if not chunk:
                continue

            chunk = re.sub(r'\s*[—–]+\s*', ', ', chunk)
            chunk = re.sub(r'\s*:\s*', ': ', chunk)
            chunk = re.sub(r'\s*;\s*', '; ', chunk)
            chunk = re.sub(r'\s*,\s*', ', ', chunk)
            chunk = re.sub(r'\s+([,;:.!?…])', r'\1', chunk)
            chunk = re.sub(r'([.!?…])([^\s])', r'\1 \2', chunk)
            chunk = re.sub(r'([:;,])([^\s])', r'\1 \2', chunk)
            chunk = re.sub(r' {2,}', ' ', chunk).strip()

            if provider_name in {"piper", "coqui"} and chunk[-1] not in '.!?…':
                chunk += '.'

            processed_paragraphs.append(chunk)

        return '\n\n'.join(processed_paragraphs)
    
    async def speak(
        self, 
        text: str, 
        voice: str = "en-US-AriaNeural",
        rate: int = 0,
        volume: int = 100,
        pitch: int = 0,
        stop_event: Optional[threading.Event] = None,
        auto_select_voice: bool = False
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate speech from text using the current provider.
        This is a wrapper around generate_speech for backward compatibility.
        
        Args:
            text: Text to convert to speech
            voice: Voice ID (provider-specific)
            rate: Speech rate (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)
            stop_event: Optional event to signal cancellation
            auto_select_voice: If True, automatically select best voice for text language
            
        Returns:
            Tuple of (audio_data, error_message). 
            audio_data is None if error occurred.
        """
        return await self.generate_speech(text, voice, rate, volume, pitch, stop_event, auto_select_voice)

    async def _resolve_synthesis_voice(
        self,
        text: str,
        voice: str,
        provider_name: str,
        auto_select_voice: bool = False,
    ) -> Tuple[str, Optional[str]]:
        """Resolve the voice that will actually synthesize *text*.

        Applies the full resolution pipeline used before generation: optional
        language-based auto-selection, language auto-detection with custom-voice
        mapping, and provider validation with fallback to the provider default.
        Shared by ``generate_speech()`` and ``pregenerate_common_phrases()`` so
        both derive identical voice + cache keys.

        Returns:
            ``(actual_voice, error)``; ``error`` is ``None`` when the voice
            resolved successfully.
        """
        actual_voice = voice

        if auto_select_voice:
            suggested_voice = self.get_optimal_voice_for_text(text)
            if suggested_voice and suggested_voice != voice:
                actual_voice = suggested_voice
                logger.info("Auto-selected voice '%s' for text language", actual_voice)

        # Check settings for auto language detection (only for Edge TTS)
        auto_language = False
        try:
            settings_manager = self._get_settings()
            auto_language = settings_manager.get("auto_language_detection", False)
            # Only apply auto language detection for Edge TTS
            if auto_language:
                detected_voice = self._detect_language_voice(text)
                if detected_voice and detected_voice != actual_voice:
                    # Check if user has a custom voice mapping for this language
                    custom_voice = self._get_custom_language_voice(text, detected_voice)
                    if custom_voice:
                        actual_voice = custom_voice
                        logger.info("Using custom language voice '%s' for text", actual_voice)
                    else:
                        actual_voice = detected_voice
                        logger.info("Auto-detected language voice '%s' for text", actual_voice)
        except Exception:
            pass

        # Validate voice before generation (cached); fall back to provider default if mismatched
        if not await self.validate_voice(actual_voice, provider_name=provider_name):
            provider = self._get_provider_by_name(provider_name)
            fallback = provider.get_default_voice()
            if fallback and await self.validate_voice(fallback, provider_name=provider_name):
                logger.info(
                    "Voice '%s' is not valid for the current provider; "
                    "falling back to '%s'", actual_voice, fallback
                )
                invalid_voice = actual_voice
                actual_voice = fallback
                # Invalidate the validation cache entry for the incompatible voice
                # so it is re-checked if the provider changes later.
                with self._voice_cache_lock:
                    self._voice_cache.pop((provider_name, invalid_voice), None)
            else:
                return actual_voice, (
                    f"Voice '{actual_voice}' is not available with the current TTS provider. "
                    "Please select a compatible voice in Settings."
                )

        return actual_voice, None

    async def generate_speech(
        self, 
        text: str, 
        voice: str = "en-US-AriaNeural",
        rate: int = 0,
        volume: int = 100,
        pitch: int = 0,
        stop_event: Optional[threading.Event] = None,
        auto_select_voice: bool = False,
        use_cache: bool = True,
        provider_override: Optional[str] = None,
    ) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Generate speech from text using the current provider.
        
        Args:
            text: Text to convert to speech
            voice: Voice ID (provider-specific)
            rate: Speech rate (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)
            stop_event: Optional event to signal cancellation
            auto_select_voice: If True, automatically select best voice for text language
            use_cache: If True, check cache before generating (default: True)
            provider_override: Optional provider key for transient UI previews that
                should use an unsaved provider selection without mutating settings.
            
        Returns:
            Tuple of (audio_data, error_message). 
            audio_data is None if error occurred.
            If cancelled via stop_event, returns (None, "Cancelled").
        """
        start_time = time.time()
        
        # Check if stop was already requested before starting
        if stop_event and stop_event.is_set():
            return None, "Cancelled"
        
        if not text or not text.strip():
            return None, "Text is empty"
        
        # Validate and clamp parameters to valid ranges
        rate = max(-100, min(100, rate))
        volume = max(0, min(100, volume))
        pitch = max(-100, min(100, pitch))

        # Snapshot provider name once so that every step of this request
        # (provider selection, cache lookup, and cache store) uses the same
        # provider identity even if settings change mid-call.
        provider_name = provider_override or self._get_active_provider_name()
        provider = self._get_provider_by_name(provider_name)

        # Snapshot the synthesis-affecting settings fingerprint so the cache
        # entry is tagged with exactly the configuration that produced the audio.
        settings_fingerprint = self._get_audio_cache_fingerprint(provider_name)

        # Auto-select voice if requested and provider supports it
        # Resolve the voice that will actually synthesize the text (auto
        # language detection, validation, provider-default fallback).
        actual_voice, voice_error = await self._resolve_synthesis_voice(
            text, voice, provider_name, auto_select_voice=auto_select_voice
        )
        if voice_error:
            return None, voice_error
        
        # Preprocess text for better quality and speed, passing actual_voice for language-aware number formatting
        processed_text = await self.preprocess_text(
            text,
            actual_voice,
            provider_name=provider_name,
        )

        # Check audio cache first
        if use_cache and self._audio_cache:
            cached_audio = self._audio_cache.lookup(
                processed_text,
                actual_voice,
                rate,
                volume,
                pitch,
                provider=provider_name,
                settings_fingerprint=settings_fingerprint,
            )
            if cached_audio:
                logger.debug(f"Cache hit for text ({len(cached_audio)} bytes)")
                return cached_audio, None
        
        # Log parameters being used for generation
        logger.debug(f"Generating speech with params: rate={rate}, volume={volume}, pitch={pitch}, voice={actual_voice}")
        
        try:
            # Create an async wrapper to check stop_event during generation
            async def generate_with_stop_check():
                """Generate speech, checking stop_event periodically."""
                return await provider.generate_speech(
                    processed_text, actual_voice, rate, volume, pitch, stop_event
                )
            
            # If no stop_event, just await directly
            if stop_event is None:
                audio_data = await generate_with_stop_check()
            else:
                # Run generation in a task and wait on either completion or stop_event
                generate_task = asyncio.create_task(generate_with_stop_check())
                
                # Create an async waiter for the stop_event
                async def stop_event_waiter():
                    """Wait for stop_event to be set."""
                    while not stop_event.is_set():
                        await asyncio.sleep(0.05)  # Check every 50ms
                    return "stopped"
                
                waiter_task = asyncio.create_task(stop_event_waiter())
                
                try:
                    # Wait for either generation to complete or stop_event to fire
                    done, pending = await asyncio.wait(
                        {generate_task, waiter_task},
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Cancel any pending tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    
                    # Check if stop_event fired
                    if stop_event.is_set():
                        logger.debug("TTS generation cancelled by stop_event")
                        return None, "Cancelled"
                    
                    # Get the result from the completed generation task
                    audio_data = generate_task.result()
                    
                except asyncio.CancelledError:
                    logger.debug("TTS generation cancelled")
                    return None, "Cancelled"
            
            # Check if generation returned None (cancelled in provider)
            if audio_data is None:
                return None, "Cancelled"
            
            # Calculate generation time
            duration = time.time() - start_time
            
            # Store in cache if enabled
            if use_cache and self._audio_cache and audio_data:
                self._audio_cache.store(
                    audio_data, 
                    processed_text, 
                    actual_voice, 
                    rate, 
                    volume, 
                    pitch,
                    provider=provider_name,
                    generation_time=duration,
                    settings_fingerprint=settings_fingerprint,
                )
            
            # Track phrase usage for pre-generation
            if self._phrase_tracker and audio_data:
                self._phrase_tracker.track_usage(text, actual_voice)
            
            # Log performance metrics
            logger.debug(f"TTS generation completed in {duration:.2f}s for {len(text)} chars")
            
            return audio_data, None
            
        except Exception as e:
            error_msg = str(e)
            return None, f"TTS generation error: {error_msg}"
    
    async def stream_speech(
        self, 
        text: str, 
        voice: str = "en-US-AriaNeural",
        rate: int = 0,
        volume: int = 100,
        pitch: int = 0,
        stop_event: Optional[threading.Event] = None,
        max_retries: int = 2
    ):
        """
        Stream speech from text, yielding audio chunks as they arrive.
        
        This enables low-latency playback where audio starts playing before the entire
        TTS generation is complete. Ideal for longer text where waiting for full
        generation would cause noticeable delay.
        
        Args:
            text: Text to convert to speech
            voice: Voice ID (provider-specific)
            rate: Speech rate (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)
            stop_event: Optional event to signal cancellation
            max_retries: Maximum number of retry attempts for transient failures (default: 2)
            
        Yields:
            Audio bytes chunks in MP3 format
        """
        if not text or not text.strip():
            return
        
        # Validate and clamp parameters to valid ranges
        rate = max(-100, min(100, rate))
        volume = max(0, min(100, volume))
        pitch = max(-100, min(100, pitch))
        
        # Get current provider
        provider = self._get_current_provider()
        
        # Handle auto language detection
        actual_voice = voice
        auto_language = False
        try:
            settings_manager = self._get_settings()
            auto_language = settings_manager.get("auto_language_detection", False)
            if auto_language:
                detected_voice = self._detect_language_voice(text)
                if detected_voice:
                    # Check if user has a custom voice mapping for this language
                    custom_voice = self._get_custom_language_voice(text, detected_voice)
                    actual_voice = custom_voice if custom_voice else detected_voice
        except Exception:
            pass
        
        # Validate voice before streaming
        if not await self.validate_voice(actual_voice):
            logger.error("Invalid voice for streaming: %s", actual_voice)
            return
        
        # Preprocess text, passing actual_voice for language-aware number formatting
        processed_text = await self.preprocess_text(text, actual_voice)
        
        # Track phrase usage
        if self._phrase_tracker:
            self._phrase_tracker.track_usage(text, actual_voice)
        
        logger.debug("Streaming speech with voice=%s, rate=%d, volume=%d, pitch=%d", actual_voice, rate, volume, pitch)
        
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # Stream speech using the provider
                async for chunk in provider.stream_speech(processed_text, actual_voice, rate, volume, pitch, stop_event):
                    yield chunk
                return  # Success, exit retry loop
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # Check if error is retryable (network/timeout issues)
                is_retryable = any(keyword in error_str for keyword in [
                    'timeout', 'connection', 'network', 'reset', 'unreachable', 'temporarily'
                ])
                
                if is_retryable and attempt < max_retries and (stop_event is None or not stop_event.is_set()):
                    logger.warning("Stream attempt %d failed (retryable error: %s), retrying...", attempt + 1, e)
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff: 0.5s, 1s, etc.
                    continue
                else:
                    # Non-retryable error or max retries exceeded
                    logger.error("Error streaming speech: %s", e)
                    raise



    
    def get_voice_by_locale(self, locale: str) -> List[Dict]:
        """
        Get voices filtered by locale (e.g., 'en-US', 'es-ES').
        
        Args:
            locale: Locale code to filter by
            
        Returns:
            List of voice dictionaries matching the locale.
        """
        if self._voices_cache is None:
            # Can't filter without cache, return empty
            return []
        
        locale_lower = locale.lower()
        return [
            voice for voice in self._voices_cache 
            if voice.get('locale', '').lower().startswith(locale_lower)
        ]
    
    def search_voices(self, query: str) -> List[Dict]:
        """
        Search voices by name or locale.
        
        Args:
            query: Search string
            
        Returns:
            List of matching voice dictionaries.
        """
        if self._voices_cache is None:
            return []
        
        query_lower = query.lower()
        return [
            voice for voice in self._voices_cache
            if query_lower in voice.get('name', '').lower() 
            or query_lower in voice.get('short_name', '').lower()
            or query_lower in voice.get('locale', '').lower()
        ]
    
    def get_voices_by_gender(self, gender: str) -> List[Dict]:
        """
        Get voices filtered by gender.
        
        Args:
            gender: Gender to filter by ("Male", "Female", or "All")
            
        Returns:
            List of voice dictionaries matching the gender.
        """
        if self._voices_cache is None:
            return []
        
        if gender == "All" or not gender:
            return self._voices_cache.copy()
        
        gender_lower = gender.lower()
        return [
            voice for voice in self._voices_cache
            if voice.get('gender', '').lower() == gender_lower
        ]
    
    def get_unique_locales(self) -> List[str]:
        """
        Get list of unique locale codes from available voices.
        
        Returns:
            List of unique locale codes (e.g., ['en-US', 'es-ES', 'fr-FR']).
        """
        if self._voices_cache is None:
            return []
        
        locales = set()
        for voice in self._voices_cache:
            locale = voice.get('locale', '')
            if locale:
                locales.add(locale)
        
        return sorted(list(locales))
    
    def get_unique_languages(self) -> List[str]:
        """
        Get list of unique language codes extracted from locales.
        
        Returns:
            List of unique language codes (e.g., ['en', 'es', 'fr']).
        """
        locales = self.get_unique_locales()
        languages = set()
        
        for locale in locales:
            # Extract language code from locale (e.g., 'en' from 'en-US')
            if '-' in locale:
                lang = locale.split('-')[0]
                languages.add(lang)
        
        return sorted(list(languages))
    
    def get_voices_count(self) -> int:
        """
        Get the count of available voices without returning full list.
        
        Returns:
            Number of available voices.
        """
        if self._voices_cache is None:
            return 0
        return len(self._voices_cache)
    
    def get_voice_info(self, voice_short_name: str) -> Optional[Dict]:
        """
        Get detailed information about a specific voice.
        
        Args:
            voice_short_name: The short name of the voice to get info for
            
        Returns:
            Dictionary with voice details or None if not found
        """
        if self._voices_cache is None:
            return None
        
        for voice in self._voices_cache:
            if voice.get('short_name') == voice_short_name:
                return {
                    'name': voice.get('name', ''),
                    'short_name': voice.get('short_name', ''),
                    'gender': voice.get('gender', ''),
                    'locale': voice.get('locale', ''),
                    'language': voice.get('locale', '').split('-')[0] if '-' in voice.get('locale', '') else voice.get('locale', '')
                }
        
        return None
    
    def format_voice_display(self, voice_short_name: str) -> str:
        """
        Format voice information for display purposes.
        
        Args:
            voice_short_name: The short name of the voice
            
        Returns:
            Formatted string for display (e.g., "Aria (en-US, Female)")
        """
        voice_info = self.get_voice_info(voice_short_name)
        if not voice_info:
            return voice_short_name
        
        # Extract voice name without locale suffix
        voice_name = voice_info['name']
        if '(' in voice_name:
            voice_name = voice_name.split('(')[0].strip()
        
        return f"{voice_name} ({voice_info['locale']}, {voice_info['gender']})"
    
    def get_actual_voice_for_generation(self, text: str, voice: str, auto_select_voice: bool = False) -> str:
        """
        Get the actual voice that would be used for TTS generation.
        This method can be called before generate_speech to know which voice will be used.
        
        Args:
            text: Text to analyze for language detection
            voice: Original voice selection
            auto_select_voice: Whether to auto-select based on text language
            
        Returns:
            The actual voice ID that would be used
        """
        actual_voice = voice
        
        if auto_select_voice:
            suggested_voice = self.get_optimal_voice_for_text(text)
            if suggested_voice and suggested_voice != voice:
                actual_voice = suggested_voice
        
        return actual_voice
    
    def _calculate_language_scores(self, text: str) -> Dict[str, float]:
        """
        Calculate weighted language detection scores for the given text.
        
        Uses a weighted scoring system that counts ALL matches across the entire text
        instead of stopping at the first match, making it more reliable for long phrases.
        
        This is used as a fallback when langdetect is unavailable or unreliable.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dictionary mapping language codes to confidence scores
        """
        scores = {
            'en': 0.0, 'es': 0.0, 'fr': 0.0, 'de': 0.0, 'pt': 0.0, 'it': 0.0,
            'zh': 0.0, 'ja': 0.0, 'ko': 0.0, 'ru': 0.0, 'ar': 0.0, 'hi': 0.0
        }
        
        if not text or not text.strip():
            return scores
        
        text_lower = text.lower()
        
        # Calculate the length of letters-only text for minimum length guard
        # Also perform single-pass script detection for non-Latin scripts
        letters_only_length = 0
        
        for char in text:
            # Script-based detection (high weight - very reliable) - single pass
            code = ord(char)
            
            # Chinese characters (Simplified and Traditional)
            if 0x4e00 <= code <= 0x9fff or 0x3400 <= code <= 0x4dbf or 0xf900 <= code <= 0xfaff:
                scores['zh'] += 5
                letters_only_length += 1
            # Japanese Hiragana
            elif 0x3040 <= code <= 0x309f:
                scores['ja'] += 5
                letters_only_length += 1
            # Japanese Katakana
            elif 0x30a0 <= code <= 0x30ff:
                scores['ja'] += 5
                letters_only_length += 1
            # Korean Hangul
            elif 0xac00 <= code <= 0xd7af or 0x1100 <= code <= 0x11ff or 0x3130 <= code <= 0x318f:
                scores['ko'] += 5
                letters_only_length += 1
            # Cyrillic (Russian and related)
            elif 0x0400 <= code <= 0x04ff or 0x0500 <= code <= 0x052f:
                scores['ru'] += 5
                letters_only_length += 1
            # Arabic
            elif 0x0600 <= code <= 0x06ff or 0x0750 <= code <= 0x077f:
                scores['ar'] += 5
                letters_only_length += 1
            # Devanagari (Hindi)
            elif 0x0900 <= code <= 0x097f:
                scores['hi'] += 5
                letters_only_length += 1
            # Latin script letters (including extended Latin for accented characters)
            elif char.isalpha():
                letters_only_length += 1
        
        # Character-based indicators for Latin script languages (weight = 3)
        # Single pass through lowercase text for diacritic detection
        for char in text_lower:
            if char in 'äöü':
                scores['de'] += 3
            elif char == 'ß':
                scores['de'] += 3
            elif char in 'âêîôûëïÿ':  # French-specific diacritics
                scores['fr'] += 3
            elif char in 'æœ':
                scores['fr'] += 3
            elif char in 'ãõ':  # Portuguese-specific
                scores['pt'] += 3
            elif char == 'ñ':  # Spanish-specific
                scores['es'] += 3
            elif char == 'ç':  # Shared between French and Portuguese
                scores['fr'] += 1.5
                scores['pt'] += 1.5
            elif char in 'àèìòù':  # Grave accent - Italian and French
                scores['it'] += 1
                scores['fr'] += 1
            elif char in 'áéíóú':  # Acute accent - Spanish and Portuguese
                scores['es'] += 1
                scores['pt'] += 1
        
        # Word-based indicators (weight = 1 per word match)
        # Only apply word-based scoring if text has enough letters (minimum length guard)
        if letters_only_length >= 8:
            # Pruned English word list - only unambiguously English words
            # Removed: 'a', 'in', 'is', 'it', 'or', 'an', 'be', 'on', 'as', 'by' (ambiguous short words)
            language_words = {
                'en': ['the', 'and', 'this', 'that', 'with', 'have', 'from', 'were', 'been', 
                       'would', 'their', 'there', 'which', 'what', 'when', 'will', 'your', 
                       'they', 'you', 'she', 'him', 'his', 'her', 'our', 'how', 'who'],
                'es': ['hola', 'señores', 'buenos', 'dias', 'tardes', 'noches', 'como', 'esta', 'estas', 'bien', 
                       'gracias', 'por', 'favor', 'qué', 'muy', 'tengo', 'quiero', 'hacer', 'tiempo', 'hoy', 'mañana'],
                'fr': ['bonjour', 'bonsoir', 'merci', 'dans', 'par', 'pour', 'sur', 'avec', 'sans', 'plus', 'moins',
                       'bien', 'tout', 'tous', 'cette', 'sont', 'être', 'avoir', 'fait', 'faire', 'comme', 'votre'],
                'de': ['der', 'die', 'das', 'und', 'den', 'von', 'zu', 'mit', 'sich', 'des', 'auf', 'für', 'ist', 
                       'im', 'dem', 'nicht', 'ein', 'eine', 'hallo', 'guten', 'tag', 'abend', 'ich', 'bin', 'du', 
                       'wir', 'ihr', 'sie', 'sind', 'haben', 'werden', 'kann', 'muss', 'soll'],
                'it': ['il', 'la', 'lo', 'le', 'gli', 'ciao', 'buongiorno', 'buonasera', 'grazie', 'prego', 
                       'come', 'stai', 'bene', 'questo', 'quello', 'sono', 'essere', 'avere', 'fare', 'andare'],
                'pt': ['não', 'uma', 'para', 'com', 'seu', 'mais', 'dos', 'são', 'como', 'mas', 'foi', 'ele', 
                       'nas', 'tem', 'à', 'seus', 'pelo', 'ola', 'bom', 'dia', 'tarde', 'noite', 'você', 'isso']
            }
            
            # Count word matches for each language
            for lang, words in language_words.items():
                for word in words:
                    # Count all occurrences of the word in the text
                    pattern = r'\b' + re.escape(word) + r'\b'
                    matches = len(re.findall(pattern, text_lower))
                    scores[lang] += matches * 1.0
        
        return scores
    
    def _detect_language_voice(self, text: str, min_length: int = 3) -> Optional[str]:
        """
        Detect language from text and return appropriate voice.
        
        Uses the new LanguageDetector module with multi-tier detection:
        1. Script-based detection for non-Latin scripts
        2. langid for fast, accurate detection
        3. Heuristic scoring as fallback
        
        Args:
            text: Input text to analyze
            min_length: Minimum text length (stripped) for detection. Default 5.
            
        Returns:
            Voice short name (e.g., 'en-US-AriaNeural') or None if text too short
        """
        if not text or not text.strip():
            return None
        
        # Minimum text length guard - very short texts are unreliable to detect
        if len(text.strip()) < min_length:
            logger.debug(f"Text too short ({len(text.strip())} chars) for reliable language detection, skipping")
            return None
        
        # Voice mapping for each language
        voice_mapping = {
            'en': "en-US-AriaNeural",
            'es': "es-ES-ElviraNeural",
            'fr': "fr-FR-DeniseNeural",
            'de': "de-DE-KatjaNeural",
            'it': "it-IT-ElsaNeural",
            'pt': "pt-BR-FranciscaNeural",
            'zh': "zh-CN-XiaoxiaoNeural",
            'ja': "ja-JP-NanamiNeural",
            'ko': "ko-KR-SunHiNeural",
            'ru': "ru-RU-SvetlanaNeural",
            'ar': "ar-SA-ZariyahNeural",
            'hi': "hi-IN-SwaraNeural"
        }
        
        # Use the refactored _detect_language_from_text
        detected_lang = self._detect_language_from_text(text)
        
        if detected_lang:
            return voice_mapping.get(detected_lang, "en-US-AriaNeural")
        
        # Default to English if detection failed
        return "en-US-AriaNeural"
    
    def _get_custom_language_voice(self, text: str, detected_voice: str) -> Optional[str]:
        """Get custom voice mapping for the detected language."""
        try:
            settings_manager = self._get_settings()
            language_mappings = settings_manager.get("language_voice_mappings", {})
            
            if not language_mappings:
                return None
            
            # Detect language from text
            language = self._detect_language_from_text(text)
            if not language:
                return None
            
            # Check if user has a custom voice for this language
            custom_voice = language_mappings.get(language)
            if custom_voice and custom_voice != detected_voice:
                # Validate the custom voice exists
                if self._validate_voice_exists(custom_voice):
                    return custom_voice
            
        except Exception:
            pass
        
        return None
    
    # Supported language codes for the new language detector
    _SUPPORTED_LANGUAGES = LanguageDetector.SUPPORTED_LANGUAGES
    
    def _detect_language_from_text(self, text: str) -> Optional[str]:
        """
        Detect language code from text using the new LanguageDetector module.
        
        Uses a robust multi-tier approach:
        1. Script-based detection for non-Latin scripts (CJK, Cyrillic, Arabic, etc.)
        2. langid for fast, accurate detection on remaining text
        3. Heuristic scoring as fallback for edge cases
        
        Args:
            text: Input text to analyze
            
        Returns:
            Language code (e.g., 'en', 'es', 'fr') or None if detection fails
        """
        if not text or not text.strip():
            return None
        
        # Use the new language detector
        try:
            result = detect_language(text)
            
            if result and result.language:
                logger.debug(f"Language detected: {result.language} (confidence: {result.confidence:.2f}, method: {result.method})")
                return result.language
        except Exception as e:
            logger.debug(f"Language detection failed: {e}")
        
        return None
    
    def _validate_voice_exists(self, voice_short_name: str) -> bool:
        """Check if a voice exists in the available voices."""
        try:
            # Use cached validation if available
            if voice_short_name in self._voice_cache:
                return self._voice_cache[voice_short_name]
            
            # Validate against available voices
            if self._voices_cache:
                short_names = {v.get("short_name") for v in self._voices_cache if v.get("short_name")}
                is_valid = voice_short_name in short_names
                self._voice_cache[voice_short_name] = is_valid
                return is_valid
            
            # If no cache available, return True optimistically
            # The voices cache is populated before any generation call in normal flow,
            # and the provider will fail gracefully if the voice is invalid
            return True
                
        except Exception:
            return False
    
    def shutdown(self):
        """
        Shutdown the TTS engine and persist all cached data.
        
        This provides a clean shutdown by:
        - Persisting the audio cache index
        - Persisting phrase tracker stats
        """
        # Shutdown audio cache
        if self._audio_cache is not None:
            self._audio_cache.shutdown()
        
        # Shutdown phrase tracker
        if self._phrase_tracker is not None:
            self._phrase_tracker.shutdown()
        
        logger.info("TTS engine shutdown complete")
