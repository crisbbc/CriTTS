import asyncio
import time
import edge_tts
from typing import List, Dict, Any
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
        elif volume > 100:
            volume_str = f"+{volume - 100}%"
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
            logger.error(f"Error fetching Edge TTS voices: {e}")
            return []
    
    async def generate_speech(self, text: str, voice: str, rate: int = 0, volume: int = 100, pitch: int = 0, stop_event=None) -> bytes:
        """Generate speech from text using Edge TTS.
        
        Args:
            text: Text to synthesize (already preprocessed by TTS engine)
            voice: Voice identifier (short name)
            rate: Speech rate adjustment (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100, 100 is normal)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)
            stop_event: Optional threading.Event to signal stop
            
        Returns:
            Audio bytes in MP3 format
        """
        MAX_RETRIES = 3
        RETRY_DELAY = 1.0  # seconds
        
        # Format prosody parameters for edge-tts
        rate_str, volume_str, pitch_str = self._format_prosody_parameters(rate, volume, pitch)
        
        logger.debug(f"Edge TTS parameters: rate={rate_str}, volume={volume_str}, pitch={pitch_str}, voice={voice}")
        
        for attempt in range(MAX_RETRIES):
            try:
                # Generate speech with prosody parameters
                communicate = edge_tts.Communicate(
                    text, 
                    voice,
                    rate=rate_str,
                    volume=volume_str,
                    pitch=pitch_str
                )
                audio_data = b""
                
                async for chunk in communicate.stream():
                    # Check if stop was requested
                    if stop_event and stop_event.is_set():
                        logger.debug("Edge TTS generation stopped by request")
                        return None  # Return None to indicate cancellation
                    
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                
                return audio_data
                
            except Exception as e:
                error_str = str(e)
                # Check if this is an HTTP 500 error and we have retries left
                if "500" in error_str and attempt < MAX_RETRIES - 1:
                    logger.warning(f"Edge TTS returned 500, retrying (attempt {attempt + 1}/{MAX_RETRIES})...")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                else:
                    # Non-500 error or final attempt - log and raise
                    logger.error(f"Error generating Edge TTS speech: {e}")
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
        
        logger.debug(f"Edge TTS streaming parameters: rate={rate_str}, volume={volume_str}, pitch={pitch_str}, voice={voice}")
        
        try:
            # Generate speech with prosody parameters
            communicate = edge_tts.Communicate(
                text, 
                voice,
                rate=rate_str,
                volume=volume_str,
                pitch=pitch_str
            )
            
            async for chunk in communicate.stream():
                # Check if stop was requested
                if stop_event and stop_event.is_set():
                    logger.debug("Edge TTS streaming stopped by request")
                    return
                
                if chunk["type"] == "audio":
                    yield chunk["data"]
                    
        except Exception as e:
            logger.error(f"Error streaming Edge TTS speech: {e}")
            raise

    def clear_cache(self) -> None:
        """Clear the voice cache."""
        self._voice_cache = None
        self._cache_time = 0
