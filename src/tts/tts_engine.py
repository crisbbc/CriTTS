"""
TTS Engine Module
Async wrapper around edge_tts library for text-to-speech generation.
"""
import edge_tts
import asyncio
import threading
from typing import List, Dict, Optional, Tuple
import time
import logging
import re
from functools import lru_cache
import concurrent.futures
from pathlib import Path

from .providers.edge_tts_provider import EdgeTTSProvider
from .audio_cache import AudioCache, PhraseTracker
from ..config.settings_manager import SettingsManager

logger = logging.getLogger(__name__)




class TTSEngine:
    """Manages text-to-speech generation using edge_tts."""
    
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
        self._voice_cache = {}  # Cache for voice validation
        self._text_cache = {}  # Cache for text processing
        self._text_processing_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        
        # Initialize providers - pass settings_manager to avoid per-call SettingsManager instantiation
        self._edge_tts_provider = EdgeTTSProvider(settings_manager=self._settings_manager)
        
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
            cache_path = settings.get("audio_cache_path")
            
            # Update audio cache settings if cache exists
            if self._audio_cache:
                self._audio_cache.enabled = cache_enabled
                self._audio_cache.max_size_mb = max_size_mb
                # If cache path changed, we'd need to reinitialize - log a warning
                current_cache_dir = str(self._audio_cache.cache_dir) if self._audio_cache.cache_dir else None
                new_cache_path = str(Path(cache_path)) if cache_path else None
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
            cache_path = settings.get("audio_cache_path")
            
            # Initialize audio cache
            self._audio_cache = AudioCache(
                cache_dir=Path(cache_path) if cache_path else None,
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
    
    async def pregenerate_common_phrases(self, progress_callback=None) -> int:
        """
        Pre-generate audio for common phrases.
        
        Args:
            progress_callback: Optional callback for progress updates
            
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
        
        for text, voice, count in phrases:
            # Check if already cached
            if self._audio_cache.lookup(text, voice, 0, 100, 0):
                continue
            
            # Generate and cache
            try:
                audio_data, error = await self.generate_speech(text, voice)
                if audio_data and not error:
                    generated += 1
                    if progress_callback:
                        progress_callback(generated, len(phrases))
            except Exception as e:
                logger.debug(f"Failed to pre-generate phrase: {e}")
        
        return generated
    
    async def get_available_voices(self) -> List[Dict]:
        """
        Get list of available voices from the current provider.
        
        Returns:
            List of voice dictionaries with 'name', 'id', 'provider', and provider-specific metadata.
        """
        # Return cached voices if still fresh
        if self._voices_cache is not None:
            current_time = time.time()
            if current_time - self._cache_timestamp < self._cache_duration:
                return self._voices_cache
        
        try:
            # Get current provider
            provider = self._get_current_provider()
            
            # Get voices from provider
            voices = await provider.get_available_voices()
            
            # Sort voices for better UX
            voices.sort(key=lambda x: x.get('name', ''))
            
            # Populate cache for downstream helpers and language detection
            self._voices_cache = voices
            self._cache_timestamp = time.time()
            
            return voices
            
        except Exception as e:
            logger.error(f"Error getting voices from provider: {e}")
            return []
    
    def _get_current_provider(self):
        """Get the currently active TTS provider."""
        return self._edge_tts_provider
    
    def clear_voices_cache(self):
        """Clear the voices cache to force refresh on next call."""
        self._voices_cache = None
        self._voice_cache.clear()
        
        # Clear provider caches
        try:
            self._edge_tts_provider.clear_cache()
        except Exception as e:
            logger.warning(f"Failed to clear Edge TTS cache: {e}")
    
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
        
        # Get current provider
        provider = self._get_current_provider()
        
        # For Edge TTS, use existing language detection logic
        if hasattr(provider, '_voice_cache') or str(type(provider)) == "<class 'src.tts.providers.edge_tts_provider.EdgeTTSProvider'>":
            return self._get_edge_tts_optimal_voice(text)
        
        # Only Edge TTS supports language-based selection
        return None
    
    def _get_edge_tts_optimal_voice(self, text: str) -> Optional[str]:
        """Get optimal Edge TTS voice based on language detection."""
        if not self._voices_cache:
            return None
        
        # Use the robust weighted-scoring language detection method
        return self._detect_language_voice(text)
    
    async def validate_voice(self, voice_short_name: str) -> bool:
        """
        Return True if the given voice short_name exists in the available voices.
        Can be called before TTS generation to prevent errors.
        """
        # Use cache for faster validation
        if voice_short_name in self._voice_cache:
            return self._voice_cache[voice_short_name]
        
        voices = await self.get_available_voices()
        short_names = {v.get("short_name") for v in voices if v.get("short_name")}
        is_valid = voice_short_name in short_names
        
        # Update cache with size limit
        if len(self._voice_cache) >= self._max_cache_size:
            # Remove oldest entry
            oldest_key = next(iter(self._voice_cache))
            del self._voice_cache[oldest_key]
        
        self._voice_cache[voice_short_name] = is_valid
        return is_valid
    
    async def preprocess_text(self, text: str) -> str:
        """
        Preprocess text for better TTS quality and speed.
        
        Args:
            text: Input text to preprocess
            
        Returns:
            Preprocessed text optimized for TTS
        """
        # Use cached preprocessing for repeated text
        # Use full stripped text as cache key to avoid collisions
        cache_key = text.strip()
        if cache_key in self._text_cache:
            return self._text_cache[cache_key]
        
        # Text preprocessing for better TTS quality
        processed_text = text
        
        # Remove excessive whitespace and normalize
        processed_text = re.sub(r'\s+', ' ', processed_text).strip()
        
        # Handle common abbreviations and numbers
        processed_text = self._expand_common_abbreviations(processed_text)
        processed_text = self._format_numbers(processed_text)
        
        # Add slight pauses for better natural flow
        processed_text = self._add_natural_pauses(processed_text)
        
        # Note: No hard truncation - edge_tts handles long inputs without a documented
        # 2000-character limit. If issues arise, consider chunking instead.
        
        # Update cache with size limit
        if len(self._text_cache) >= self._max_cache_size:
            oldest_key = next(iter(self._text_cache))
            del self._text_cache[oldest_key]
        
        self._text_cache[cache_key] = processed_text
        return processed_text
    
    def _expand_common_abbreviations(self, text: str) -> str:
        """Expand common abbreviations for better pronunciation."""
        abbreviations = {
            'mr.': 'mister',
            'mrs.': 'missus',
            'ms.': 'miss',
            'dr.': 'doctor',
            'vs.': 'versus',
            'etc.': 'et cetera',
            'i.e.': 'that is',
            'e.g.': 'for example',
            'u.s.': 'united states',
            'u.k.': 'united kingdom',
            'a.m.': 'am',
            'p.m.': 'pm',
            'ft.': 'foot',
            'in.': 'inch',
            'oz.': 'ounce',
            'lb.': 'pound',
        }
        
        for abbr, full in abbreviations.items():
            text = text.replace(abbr, full)
        
        return text
    
    def _format_numbers(self, text: str) -> str:
        """Format numbers for better TTS pronunciation with language-aware conversion."""
        # Get the current voice to determine language
        current_voice = self._get_current_voice_language()
        
        # Language-specific number words
        number_words = {
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
        
        # Get number words for current language (default to English)
        words = number_words.get(current_voice, number_words['en'])
        
        def number_to_words(match):
            num = int(match.group())
            if 0 <= num <= 20:
                return words[num]
            elif 21 <= num <= 99:
                return self._convert_tens_to_words(num, words, current_voice)
            elif 100 <= num <= 999:
                return self._convert_hundreds_to_words(num, words, current_voice)
            elif 1000 <= num <= 999999:
                return self._convert_thousands_to_words(num, words, current_voice)
            else:
                return str(num)
        
        # Replace numbers with words (extended range)
        text = re.sub(r'\b\d+\b', number_to_words, text)
        
        return text
    
    def _convert_tens_to_words(self, num: int, words: list, language: str) -> str:
        """Convert numbers 21-99 to words."""
        if num <= 20:
            return words[num]
        
        tens = num // 10
        ones = num % 10
        
        # Tens words for different languages
        tens_words = {
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
        
        tens_list = tens_words.get(language, tens_words['en'])
        
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
        
        # Hundreds words for different languages
        hundreds_words = {
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
        
        hundreds_list = hundreds_words.get(language, hundreds_words['en'])
        
        result = hundreds_list[hundreds]
        if remainder > 0:
            if language in ['en', 'fr', 'de', 'it', 'pt']:
                result += f" {self._convert_tens_to_words(remainder, words, language)}"
            else:
                result += self._convert_tens_to_words(remainder, words, language)
        
        return result
    
    def _convert_thousands_to_words(self, num: int, words: list, language: str) -> str:
        """Convert numbers 1000-999999 to words."""
        thousands = num // 1000
        remainder = num % 1000
        
        # Guard: if thousands > 9, the lookup tables won't have an entry
        # Fall back to returning the number as string (same as numbers > 999999)
        if thousands > 9:
            return str(num)
        
        # Thousands words for different languages
        thousands_words = {
            'en': ['', 'one thousand', 'two thousand', 'three thousand', 'four thousand', 'five thousand', 'six thousand', 'seven thousand', 'eight thousand', 'nine thousand'],
            'es': ['', 'mil', 'dos mil', 'tres mil', 'cuatro mil', 'cinco mil', 'seis mil', 'siete mil', 'ocho mil', 'nueve mil'],
            'fr': ['', 'mille', 'deux mille', 'trois mille', 'quatre mille', 'cinq mille', 'six mille', 'sept mille', 'huit mille', 'neuf mille'],
            'de': ['', 'eintausend', 'zweitausend', 'dreitausend', 'viertausend', 'fünftausend', 'sechstausend', 'siebentausend', 'achttausend', 'neuntausend'],
            'it': ['', 'mille', 'duemila', 'tremila', 'quattromila', 'cinquemila', 'seimila', 'settemila', 'ottomila', 'novemila'],
            'pt': ['', 'mil', 'dois mil', 'três mil', 'quatro mil', 'cinco mil', 'seis mil', 'sete mil', 'oito mil', 'nove mil'],
            'ru': ['', 'тысяча', 'две тысячи', 'три тысячи', 'четыре тысячи', 'пять тысяч', 'шесть тысяч', 'семь тысяч', 'восемь тысяч', 'девять тысяч'],
            'zh': ['', '一千', '二千', '三千', '四千', '五千', '六千', '七千', '八千', '九千'],
            'ja': ['', '千', '二千', '三千', '四千', '五千', '六千', '七千', '八千', '九千'],
            'ko': ['', '천', '이천', '삼천', '사천', '오천', '육천', '칠천', '팔천', '구천'],
        }
        
        thousands_list = thousands_words.get(language, thousands_words['en'])
        
        result = thousands_list[thousands]
        if remainder > 0:
            if language in ['en', 'fr', 'de', 'it', 'pt']:
                result += f" {self._convert_hundreds_to_words(remainder, words, language)}"
            else:
                result += self._convert_hundreds_to_words(remainder, words, language)
        
        return result
    
    def _get_current_voice_language(self) -> str:
        """Get the language code of the current voice."""
        try:
            settings_manager = self._get_settings()
            current_voice = settings_manager.get("voice", "en-US-AriaNeural")
            
            # Extract language from voice short name
            if '-' in current_voice:
                return current_voice.split('-')[0].lower()
            
            return 'en'  # Default to English
        except:
            return 'en'
    
    def _add_natural_pauses(self, text: str) -> str:
        """
        Add natural pauses to improve speech flow.
        
        Note: edge-tts does not reliably support inline SSML tags in the text stream.
        The tags get spoken as plain text instead of being interpreted.
        This method now only handles text normalization without SSML injection.
        """
        # Normalize multiple spaces to single space
        text = re.sub(r' +', ' ', text)
        
        # Normalize multiple newlines to double newline (paragraph break)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Ensure space after punctuation if followed by letter
        text = re.sub(r'([.!?])([A-Za-z])', r'\1 \2', text)
        
        # Ensure space after comma if followed by letter
        text = re.sub(r',([A-Za-z])', r', \1', text)
        
        return text
    
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

    async def generate_speech(
        self, 
        text: str, 
        voice: str = "en-US-AriaNeural",
        rate: int = 0,
        volume: int = 100,
        pitch: int = 0,
        stop_event: Optional[threading.Event] = None,
        auto_select_voice: bool = False,
        use_cache: bool = True
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
            
        Returns:
            Tuple of (audio_data, error_message). 
            audio_data is None if error occurred.
        """
        start_time = time.time()
        
        if not text or not text.strip():
            return None, "Text is empty"
        
        # Validate and clamp parameters to valid ranges
        rate = max(-100, min(100, rate))
        volume = max(0, min(100, volume))
        pitch = max(-100, min(100, pitch))
        
        # Get current provider
        provider = self._get_current_provider()
        
        # Auto-select voice if requested and provider supports it
        actual_voice = voice
        voice_changed = False
        
        if auto_select_voice:
            suggested_voice = self.get_optimal_voice_for_text(text)
            if suggested_voice and suggested_voice != voice:
                actual_voice = suggested_voice
                voice_changed = True
                logger.info(f"Auto-selected voice '{actual_voice}' for text language")
        
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
                        voice_changed = True
                        logger.info(f"Using custom language voice '{actual_voice}' for text")
                    else:
                        actual_voice = detected_voice
                        voice_changed = True
                        logger.info(f"Auto-detected language voice '{actual_voice}' for text")
        except:
            pass
        
        # Validate voice before generation (cached)
        if not await self.validate_voice(actual_voice):
            return None, f"Invalid voice: {actual_voice}. Please select a valid voice in settings."
        
        # Preprocess text for better quality and speed
        processed_text = await self.preprocess_text(text)
        
        # Check audio cache first
        if use_cache and self._audio_cache:
            cached_audio = self._audio_cache.lookup(processed_text, actual_voice, rate, volume, pitch)
            if cached_audio:
                logger.debug(f"Cache hit for text ({len(cached_audio)} bytes)")
                return cached_audio, None
        
        # Log parameters being used for generation
        logger.debug(f"Generating speech with params: rate={rate}, volume={volume}, pitch={pitch}, voice={actual_voice}")
        
        try:
            # Generate speech using the provider with all parameters
            audio_data = await provider.generate_speech(processed_text, actual_voice, rate, volume, pitch)
            
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
                    generation_time=duration
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
        stop_event: Optional[threading.Event] = None
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
        except:
            pass
        
        # Validate voice before streaming
        if not await self.validate_voice(actual_voice):
            logger.error(f"Invalid voice for streaming: {actual_voice}")
            return
        
        # Preprocess text
        processed_text = await self.preprocess_text(text)
        
        # Track phrase usage
        if self._phrase_tracker:
            self._phrase_tracker.track_usage(text, actual_voice)
        
        logger.debug(f"Streaming speech with voice={actual_voice}, rate={rate}, volume={volume}, pitch={pitch}")
        
        try:
            # Stream speech using the provider
            async for chunk in provider.stream_speech(processed_text, actual_voice, rate, volume, pitch, stop_event):
                yield chunk
                
        except Exception as e:
            logger.error(f"Error streaming speech: {e}")
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
        
        # Script-based detection (high weight - very reliable)
        # Chinese characters (Simplified and Traditional)
        for char in text:
            if '\u4e00' <= char <= '\u9fff' or '\u3400' <= char <= '\u4dbf' or '\uf900' <= char <= '\ufaff':
                scores['zh'] += 5
        
        # Japanese Hiragana and Katakana
        for char in text:
            if '\u3040' <= char <= '\u309f':  # Hiragana
                scores['ja'] += 5
            if '\u30a0' <= char <= '\u30ff':  # Katakana
                scores['ja'] += 5
        
        # Korean Hangul
        for char in text:
            if '\uac00' <= char <= '\ud7af' or '\u1100' <= char <= '\u11ff' or '\u3130' <= char <= '\u318f':
                scores['ko'] += 5
        
        # Cyrillic (Russian and related)
        for char in text:
            if '\u0400' <= char <= '\u04ff' or '\u0500' <= char <= '\u052f':
                scores['ru'] += 5
        
        # Arabic
        for char in text:
            if '\u0600' <= char <= '\u06ff' or '\u0750' <= char <= '\u077f':
                scores['ar'] += 5
        
        # Devanagari (Hindi)
        for char in text:
            if '\u0900' <= char <= '\u097f':
                scores['hi'] += 5
        
        # Character-based indicators for Latin script languages (weight = 3)
        # Portuguese-specific characters
        for char in text_lower:
            if char in 'ãõç':
                scores['pt'] += 3
            elif char in 'áéíóúà':
                # Shared with Portuguese and Spanish, give points to both
                scores['pt'] += 1.5
                scores['es'] += 1
        
        # Spanish-specific characters
        for char in text_lower:
            if char == 'ñ':
                scores['es'] += 3
            elif char == 'ü':
                # ü is more common in Spanish than other languages
                scores['es'] += 2
        
        # French-specific characters
        for char in text_lower:
            if char in 'àâäéèêëîïôöùûüÿç':
                scores['fr'] += 3
            if char in 'æœ':
                scores['fr'] += 3
        
        # German-specific characters
        for char in text_lower:
            if char in 'äöü':
                scores['de'] += 3
            elif char == 'ß':
                scores['de'] += 3
        
        # Italian-specific characters (less distinctive, shared with other Romance languages)
        for char in text_lower:
            if char in 'ìòù':
                scores['it'] += 2
        
        # Word-based indicators (weight = 1 per word match)
        # Common words for each language
        language_words = {
            'en': ['the', 'and', 'to', 'of', 'a', 'in', 'is', 'it', 'for', 'as', 'with', 'on', 'be', 'at', 'by', 
                   'this', 'have', 'from', 'or', 'one', 'had', 'but', 'not', 'what', 'all', 'were', 'when', 'we', 
                   'there', 'can', 'an', 'your', 'which', 'their', 'said', 'each', 'has', 'will', 'would', 'been', 
                   'if', 'who', 'how', 'her', 'he', 'she', 'they', 'you', 'me', 'my', 'our', 'us', 'him', 'his'],
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
        
        # Normalize scores by text length to handle long vs short phrases fairly
        text_length = len(text.strip())
        if text_length > 0:
            # Apply a normalization factor based on text length
            # Longer texts will have more matches, so we normalize
            normalization_factor = min(1.0, 100.0 / text_length)
            for lang in scores:
                scores[lang] *= (1.0 + normalization_factor)
        
        return scores
    
    def _detect_language_voice(self, text: str) -> Optional[str]:
        """Detect language from text and return appropriate voice using weighted scoring."""
        if not text or not text.strip():
            return None
        
        # Calculate language scores
        scores = self._calculate_language_scores(text)
        
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
        
        # Find the language with the highest score
        max_score = 0
        detected_lang = 'en'  # Default to English
        
        for lang, score in scores.items():
            if score > max_score:
                max_score = score
                detected_lang = lang
        
        # Log the detection results
        logger.debug(f"Language detection scores: {scores}, selected: {detected_lang}")
        
        # Minimum threshold to avoid false positives
        # If no language scores above threshold, default to English
        if max_score < 5 and detected_lang not in ['zh', 'ja', 'ko', 'ru', 'ar', 'hi']:
            # Check if there are any Latin characters at all
            has_latin = any(c.isalpha() and ord(c) < 0x0250 for c in text)
            if has_latin:
                detected_lang = 'en'
        
        return voice_mapping.get(detected_lang, "en-US-AriaNeural")
    
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
    
    def _detect_language_from_text(self, text: str) -> Optional[str]:
        """Detect language code from text using weighted scoring."""
        if not text or not text.strip():
            return None
        
        # Check if text is primarily numbers or symbols (no clear language indicators)
        # This handles cases like "1 2 3 4 5 6 7" or "Hello 123"
        text_lower = text.lower()
        text_without_numbers = re.sub(r'[0-9\s\.,!?;:()\-_]+', '', text_lower)
        has_letters = any(c.isalpha() for c in text_without_numbers)
        
        # If text has no letters or very few letters compared to numbers/symbols,
        # return None to indicate no clear language detection
        if not has_letters or len(text_without_numbers) < len(text_lower) * 0.3:
            return None
        
        # Calculate language scores using the shared method
        scores = self._calculate_language_scores(text)
        
        # Find the language with the highest score
        max_score = 0
        detected_lang = None
        
        for lang, score in scores.items():
            if score > max_score:
                max_score = score
                detected_lang = lang
        
        # Log the detection results
        logger.debug(f"Language detection scores: {scores}, selected: {detected_lang}")
        
        # Minimum threshold to avoid false positives
        # If no language scores above threshold, return None
        if max_score < 5 and detected_lang not in ['zh', 'ja', 'ko', 'ru', 'ar', 'hi']:
            # Check if there are any Latin characters at all
            has_latin = any(c.isalpha() and ord(c) < 0x0250 for c in text)
            if has_latin:
                return 'en'
            return None
        
        return detected_lang
    
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
        - Shutting down the text processing executor
        """
        # Shutdown audio cache
        if self._audio_cache is not None:
            self._audio_cache.shutdown()
        
        # Shutdown phrase tracker
        if self._phrase_tracker is not None:
            self._phrase_tracker.shutdown()
        
        # Shutdown thread pool executor
        self._text_processing_executor.shutdown(wait=False)
        
        logger.info("TTS engine shutdown complete")
