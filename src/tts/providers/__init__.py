"""
TTS Provider Abstraction Layer

This module defines the abstract base class for TTS providers and provides
a common interface for TTS services like Edge TTS and Bark TTS.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""
    
    @abstractmethod
    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get list of available voices from the provider.
        
        Returns:
            List of voice dictionaries with keys: name, id, provider, and provider-specific metadata
        """
        pass
    
    @abstractmethod
    async def generate_speech(self, text: str, voice: str, rate: int = 0, volume: int = 100, pitch: int = 0, stop_event=None) -> Optional[bytes]:
        """Generate speech from text using the specified voice.
        
        Args:
            text: Text to synthesize
            voice: Voice identifier
            rate: Speech rate adjustment (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100, 100 is normal)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)
            stop_event: Optional threading.Event to signal cancellation
            
        Returns:
            Audio bytes in the provider's format, or None if generation
            was cancelled via *stop_event*.
        """
        pass
    
    @abstractmethod
    async def validate_voice(self, voice: str) -> bool:
        """Validate if a voice ID is valid for this provider.
        
        Args:
            voice: Voice identifier to validate
            
        Returns:
            True if voice is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def clear_cache(self) -> None:
        """Clear any cached data (voices, etc.)."""
        pass

    def get_default_voice(self) -> Optional[str]:
        """Return the default voice identifier for this provider.

        Override in subclasses to provide a sensible provider-specific default.
        Returns None if no default is defined.
        """
        return None
