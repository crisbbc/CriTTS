"""
Edge TTS Provider Module
Provides text-to-speech synthesis using Microsoft Edge's online TTS service.
"""
import asyncio
import time
import edge_tts
from typing import List, Dict, Any, Optional
from . import TTSProvider
import logging

logger = logging.getLogger(__name__)

class EdgeTTSProvider(TTSProvider):
    """Edge TTS provider implementation"""

    def __init__(self, settings_manager=None):
        self._voice_cache = None
        self._cache_time = 0
        self._cache_duration = 300  # 5 minutes
        self._settings_manager = settings_manager

    def _get_proxy_url(self) -> Optional[str]:
        """Get the formatted proxy URL from settings if enabled, else None."""
        if not self._settings_manager:
            return None

        proxy_enabled = self._settings_manager.get("proxy_enabled", False)
        if not proxy_enabled:
            return None

        proxy_type = self._settings_manager.get("proxy_type", "http")
        proxy_server = self._settings_manager.get("proxy_server", "")
        if not proxy_server:
            return None

        proxy_username = self._settings_manager.get("proxy_username", "")
        proxy_password = self._settings_manager.get("proxy_password", "")

        # Build proxy URL
        auth = ""
        if proxy_username:
            if proxy_password:
                import urllib.parse
                safe_pass = urllib.parse.quote(proxy_password, safe='')
                safe_user = urllib.parse.quote(proxy_username, safe='')
                auth = f"{safe_user}:{safe_pass}@"
            else:
                import urllib.parse
                safe_user = urllib.parse.quote(proxy_username, safe='')
                auth = f"{safe_user}@"

        # Ensure proxy_server doesn't already start with the protocol
        if proxy_server.startswith(f"{proxy_type}://"):
            proxy_server = proxy_server[len(f"{proxy_type}://"):]
        elif "://" in proxy_server:
            # Strip whatever protocol is there to ensure we use the selected proxy_type
            proxy_server = proxy_server.split("://", 1)[1]

        return f"{proxy_type}://{auth}{proxy_server}"

    def _format_prosody_parameters(self, rate: int, volume: int, pitch: int) -> tuple:
        """
        Convert integer parameters to edge-tts format strings.

        Args:
            rate: Speech rate (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100, 100 is normal)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)

        Returns:
            Tuple of (rate_str, volume_str, pitch_str) for edge-tts
        """
        # Clamp rate to valid range (-100 to 100)
        rate = max(-100, min(100, rate))
        # Format rate as percentage string
        if rate == 0:
            rate_str = "+0%"
        elif rate > 0:
            rate_str = f"+{rate}%"
        else:
            rate_str = f"{rate}%"

        # Clamp volume to valid range (0 to 100)
        volume = max(0, min(100, volume))
        # Format volume as percentage string relative to 100% baseline
        # edge-tts expects volume as percentage relative to default (100%)
        if volume == 100:
            volume_str = "+0%"
        else:
            volume_str = f"-{100 - volume}%"

        # Clamp pitch to valid range (-100 to 100)
        pitch = max(-100, min(100, pitch))
        # Format pitch as Hz string
        if pitch == 0:
            pitch_str = "+0Hz"
        elif pitch > 0:
            pitch_str = f"+{pitch}Hz"
        else:
            pitch_str = f"{pitch}Hz"

        return rate_str, volume_str, pitch_str

    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get list of available voices from Edge TTS"""
        current_time = time.monotonic()

        # Check cache
        if self._voice_cache is not None and (current_time - self._cache_time) < self._cache_duration:
            return self._voice_cache

        try:
            # Fetch voices from Edge TTS
            proxy_url = self._get_proxy_url()
            if proxy_url:
                voices = await edge_tts.list_voices(proxy=proxy_url)
            else:
                voices = await edge_tts.list_voices()

            # Process voices into our format
            processed_voices = []
            for voice in voices:
                # Extract locale from voice name (e.g., "en-US-AriaNeural" -> "en-US")
                locale = voice.get("Locale", "")
                if "-" in locale:
                    language_code = locale.split("-")[0]
                else:
                    language_code = locale

                processed_voices.append({
                    "name": voice.get("FriendlyName", ""),
                    "short_name": voice.get("ShortName", ""),
                    "gender": voice.get("Gender", ""),
                    "locale": locale,
                    "language_code": language_code,
                    "provider": "edge_tts"
                })

            self._voice_cache = processed_voices
            self._cache_time = current_time
            return processed_voices

        except Exception as e:
            logger.error("Error fetching Edge TTS voices: %s", e)
            return []

    async def generate_speech(self, text: str, voice: str, rate: int = 0, volume: int = 100, pitch: int = 0, stop_event=None) -> Optional[bytes]:
        """Generate speech from text using Edge TTS.

        Args:
            text: Text to synthesize (already preprocessed by TTS engine)
            voice: Voice identifier (short name)
            rate: Speech rate adjustment (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100, 100 is normal)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)
            stop_event: Optional threading.Event to signal stop

        Returns:
            Audio bytes in MP3 format, or None if generation was cancelled
        """
        MAX_RETRIES = 3
        RETRY_DELAY = 1.0  # seconds

        # Format prosody parameters for edge-tts
        rate_str, volume_str, pitch_str = self._format_prosody_parameters(rate, volume, pitch)

        proxy_url = self._get_proxy_url()
        logger.debug("Edge TTS parameters: rate=%s, volume=%s, pitch=%s, voice=%s", rate_str, volume_str, pitch_str, voice)

        for attempt in range(MAX_RETRIES):
            try:
                # Generate speech with prosody parameters
                communicate = edge_tts.Communicate(
                    text,
                    voice,
                    rate=rate_str,
                    volume=volume_str,
                    pitch=pitch_str,
                    proxy=proxy_url
                )
                audio_chunks = []

                async for chunk in communicate.stream():
                    # Check if stop was requested
                    if stop_event and stop_event.is_set():
                        logger.debug("Edge TTS generation stopped by request")
                        return None  # Return None to indicate cancellation

                    if chunk["type"] == "audio":
                        audio_chunks.append(chunk["data"])

                return b"".join(audio_chunks)

            except Exception as e:
                error_str = str(e).lower()
                # Check if this is a retryable error (transient network/server issues)
                # Retryable errors include: HTTP 500, timeouts, connection errors, network issues
                is_retryable = any(keyword in error_str for keyword in [
                    '500', '502', '503', '504',  # Server errors
                    'timeout', 'timed out',      # Timeout errors
                    'connection', 'connect',     # Connection errors
                    'network', 'reset', 'unreachable', 'temporarily'  # Network issues
                ])

                if is_retryable and attempt < MAX_RETRIES - 1:
                    logger.warning("Edge TTS error (retryable): %s, retrying (attempt %d/%d)...", e, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    # Non-retryable error or final attempt - log and raise
                    logger.error("Error generating Edge TTS speech: %s", e)
                    raise

    async def validate_voice(self, voice: str) -> bool:
        """Validate if a voice exists in Edge TTS"""
        voices = await self.get_available_voices()
        return any(v["short_name"] == voice for v in voices)

    async def stream_speech(self, text: str, voice: str, rate: int = 0, volume: int = 100, pitch: int = 0, stop_event=None):
        """
        Stream speech from text using Edge TTS, yielding audio chunks as they arrive.

        This enables low-latency playback where audio starts playing before the entire
        TTS generation is complete.

        Args:
            text: Text to synthesize (already preprocessed by TTS engine)
            voice: Voice identifier (short name)
            rate: Speech rate adjustment (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100, 100 is normal)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)
            stop_event: Optional threading.Event to signal stop

        Yields:
            Audio bytes chunks in MP3 format
        """
        # Format prosody parameters for edge-tts
        rate_str, volume_str, pitch_str = self._format_prosody_parameters(rate, volume, pitch)

        proxy_url = self._get_proxy_url()
        logger.debug("Edge TTS streaming parameters: rate=%s, volume=%s, pitch=%s, voice=%s", rate_str, volume_str, pitch_str, voice)

        try:
            # Generate speech with prosody parameters
            communicate = edge_tts.Communicate(
                text,
                voice,
                rate=rate_str,
                volume=volume_str,
                pitch=pitch_str,
                proxy=proxy_url
            )

            async for chunk in communicate.stream():
                # Check if stop was requested
                if stop_event and stop_event.is_set():
                    logger.debug("Edge TTS streaming stopped by request")
                    return

                if chunk["type"] == "audio":
                    yield chunk["data"]

        except Exception as e:
            logger.error("Error streaming Edge TTS speech: %s", e)
            raise

    def clear_cache(self) -> None:
        """Clear the voice cache."""
        self._voice_cache = None
        self._cache_time = 0
