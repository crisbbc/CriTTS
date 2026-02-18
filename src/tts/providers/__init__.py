"""
TTS Provider Abstraction Layer

This module defines the abstract base class for TTS providers and provides
a common interface for TTS services like Edge TTS.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union, Any
import asyncio


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
    async def generate_speech(self, text: str, voice_id: str, rate: int = 0, volume: int = 100, pitch: int = 0) -> bytes:
        """Generate speech from text using the specified voice.
        
        Args:
            text: Text to synthesize
            voice_id: Voice identifier
            rate: Speech rate adjustment (-100 to 100, 0 is normal)
            volume: Volume level (0 to 100, 100 is normal)
            pitch: Pitch adjustment (-100 to 100, 0 is normal)
            
        Returns:
            Audio bytes in the provider's format
        """
        pass
    
    @abstractmethod
    async def validate_voice(self, voice_id: str) -> bool:
        """Validate if a voice ID is valid for this provider.
        
        Args:
            voice_id: Voice identifier to validate
            
        Returns:
            True if voice is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def clear_cache(self) -> None:
        """Clear any cached data (voices, etc.)."""
        pass


