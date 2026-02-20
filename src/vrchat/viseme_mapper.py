"""
Viseme Mapper Module
Maps phonemes to VRChat viseme values for realistic lip-sync animation.
"""
import re
import time
import logging
import threading
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)


class Viseme(IntEnum):
    """VRChat viseme indices for /avatar/parameters/Viseme."""
    SIL = 0   # Silence
    PP = 1    # p, b, m
    FF = 2    # f, v
    TH = 3    # th
    DD = 4    # t, d
    KK = 5    # k, g
    CH = 6    # ch, sh, j
    SS = 7    # s, z
    NN = 8    # n, l
    RR = 9    # r
    AA = 10   # a, ah, aw
    E = 11    # e, eh
    I = 12    # i, ee, ih
    O = 13    # o, oh
    U = 14    # u, oo, ou


@dataclass
class VisemeFrame:
    """A single viseme frame with timing information."""
    viseme: Viseme
    duration: float  # Duration in seconds
    intensity: float = 1.0  # Intensity 0.0-1.0


class VisemeMapper:
    """
    Maps text to viseme sequences for VRChat lip-sync.
    
    Uses rule-based phoneme detection and maps to VRChat's 15 viseme values.
    """
    
    # Phoneme to viseme mapping
    PHONEME_TO_VISEME = {
        # Consonants
        'p': Viseme.PP, 'b': Viseme.PP, 'm': Viseme.PP,
        'f': Viseme.FF, 'v': Viseme.FF,
        'th': Viseme.TH,
        't': Viseme.DD, 'd': Viseme.DD,
        'k': Viseme.KK, 'g': Viseme.KK,
        'ch': Viseme.CH, 'sh': Viseme.CH, 'j': Viseme.CH,
        's': Viseme.SS, 'z': Viseme.SS, 'c': Viseme.SS,
        'n': Viseme.NN, 'l': Viseme.NN,
        'r': Viseme.RR,
        'w': Viseme.U,
        'h': Viseme.AA,  # h is often silent or transitional
        
        # Vowels
        'a': Viseme.AA, 'ah': Viseme.AA, 'aw': Viseme.AA,
        'e': Viseme.E, 'eh': Viseme.E,
        'i': Viseme.I, 'ee': Viseme.I, 'ih': Viseme.I, 'y': Viseme.I,
        'o': Viseme.O, 'oh': Viseme.O,
        'u': Viseme.U, 'oo': Viseme.U, 'ou': Viseme.U,
        
        # Silence
        'sil': Viseme.SIL,
    }
    
    # Common letter combinations that form specific phonemes
    DIGRAPHS = {
        'th': 'th',
        'ch': 'ch',
        'sh': 'sh',
        'ph': 'f',
        'gh': 'g',
        'ng': 'n',
        'ck': 'k',
        'wh': 'w',
        'ou': 'ou',
        'oo': 'oo',
        'ee': 'ee',
        'ea': 'ee',
        'ai': 'i',
        'ay': 'i',
        'ei': 'i',
        'ey': 'i',
        'oa': 'o',
        'ow': 'ou',
        'aw': 'aw',
        'oy': 'o',
        'oi': 'o',
    }
    
    # Average phoneme durations (in seconds) - can be adjusted for speech rate
    BASE_PHONEME_DURATION = 0.08  # 80ms base duration
    
    def __init__(self, smoothing: float = 0.1):
        """
        Initialize the viseme mapper.
        
        Args:
            smoothing: Smoothing factor for viseme transitions (0.0-1.0)
        """
        self.smoothing = smoothing
        self._current_viseme = Viseme.SIL
        self._stop_event = threading.Event()
        self._viseme_thread: Optional[threading.Thread] = None
    
    def text_to_phonemes(self, text: str) -> List[str]:
        """
        Convert text to a sequence of phonemes using rule-based mapping.
        
        Args:
            text: Input text
            
        Returns:
            List of phoneme strings
        """
        # Clean and normalize text
        text = text.lower().strip()
        
        # Remove non-alphabetic characters except spaces
        text = re.sub(r'[^a-z\s]', '', text)
        
        phonemes = []
        i = 0
        
        while i < len(text):
            # Skip spaces (add silence)
            if text[i] == ' ':
                phonemes.append('sil')
                i += 1
                continue
            
            # Check for digraphs (2-letter combinations)
            if i + 1 < len(text):
                digraph = text[i:i+2]
                if digraph in self.DIGRAPHS:
                    phonemes.append(self.DIGRAPHS[digraph])
                    i += 2
                    continue
            
            # Single letter
            char = text[i]
            if char in self.PHONEME_TO_VISEME:
                phonemes.append(char)
            elif char in 'qx':  # Rare letters
                phonemes.append('k')  # Approximate
            
            i += 1
        
        return phonemes
    
    def phonemes_to_visemes(self, phonemes: List[str]) -> List[Viseme]:
        """
        Convert phonemes to viseme values.
        
        Args:
            phonemes: List of phoneme strings
            
        Returns:
            List of viseme values
        """
        visemes = []
        
        for phoneme in phonemes:
            if phoneme in self.PHONEME_TO_VISEME:
                visemes.append(self.PHONEME_TO_VISEME[phoneme])
            else:
                visemes.append(Viseme.SIL)
        
        return visemes
    
    def generate_viseme_timeline(
        self,
        text: str,
        duration: Optional[float] = None,
        speech_rate: int = 0
    ) -> List[VisemeFrame]:
        """
        Generate a timeline of viseme frames for the given text.
        
        Args:
            text: Input text to animate
            duration: Target duration in seconds (if None, calculated from text)
            speech_rate: Speech rate adjustment (-100 to 100)
            
        Returns:
            List of VisemeFrame objects with timing
        """
        if not text or not text.strip():
            return [VisemeFrame(Viseme.SIL, 0.1)]
        
        # Convert text to phonemes
        phonemes = self.text_to_phonemes(text)
        
        # Convert to visemes
        visemes = self.phonemes_to_visemes(phonemes)
        
        if not visemes:
            return [VisemeFrame(Viseme.SIL, 0.1)]
        
        # Calculate duration per viseme
        # Adjust for speech rate
        rate_factor = 1.0 - (speech_rate / 200.0)  # -100% = 1.5x slower, +100% = 0.5x faster
        base_duration = self.BASE_PHONEME_DURATION * rate_factor
        
        # If total duration is specified, adjust accordingly
        if duration and duration > 0:
            total_base_duration = len(visemes) * base_duration
            if total_base_duration > 0:
                scale = duration / total_base_duration
                base_duration *= scale
        
        # Create frames
        frames = []
        
        # Group consecutive identical visemes
        current_viseme = visemes[0]
        count = 1
        
        for i in range(1, len(visemes)):
            if visemes[i] == current_viseme:
                count += 1
            else:
                # Add frame for previous viseme group
                frame_duration = count * base_duration
                # Reduce duration for silence
                if current_viseme == Viseme.SIL:
                    frame_duration *= 0.5
                frames.append(VisemeFrame(current_viseme, frame_duration))
                current_viseme = visemes[i]
                count = 1
        
        # Add final frame
        frame_duration = count * base_duration
        if current_viseme == Viseme.SIL:
            frame_duration *= 0.5
        frames.append(VisemeFrame(current_viseme, frame_duration))
        
        return frames
    
    def start_viseme_animation(
        self,
        text: str,
        send_callback: Callable[[int], None],
        duration: Optional[float] = None,
        speech_rate: int = 0,
        amplitude_callback: Optional[Callable[[], float]] = None
    ):
        """
        Start viseme animation in a background thread.
        
        Args:
            text: Text to animate
            send_callback: Function to call with viseme value
            duration: Target duration (if None, calculated from text)
            speech_rate: Speech rate adjustment
            amplitude_callback: Optional callback to get current amplitude (0.0-1.0)
        """
        self.stop_viseme_animation()
        
        self._stop_event.clear()
        
        def animate():
            frames = self.generate_viseme_timeline(text, duration, speech_rate)
            
            for frame in frames:
                if self._stop_event.is_set():
                    break
                
                # Get intensity from amplitude if available
                intensity = 1.0
                if amplitude_callback:
                    intensity = amplitude_callback()
                
                # Send viseme value
                try:
                    send_callback(int(frame.viseme))
                except Exception as e:
                    logger.debug(f"Failed to send viseme: {e}")
                
                # Wait for frame duration
                # Use small sleep intervals for smoother amplitude updates
                elapsed = 0.0
                update_interval = 0.02  # 20ms updates
                while elapsed < frame.duration and not self._stop_event.is_set():
                    sleep_time = min(update_interval, frame.duration - elapsed)
                    time.sleep(sleep_time)
                    elapsed += sleep_time
                    
                    # Update intensity during frame
                    if amplitude_callback and elapsed < frame.duration:
                        new_intensity = amplitude_callback()
                        # Could send intensity updates here if needed
            
            # Reset to silence when done
            if not self._stop_event.is_set():
                try:
                    send_callback(int(Viseme.SIL))
                except Exception:
                    pass
        
        self._viseme_thread = threading.Thread(target=animate, daemon=True)
        self._viseme_thread.start()
    
    def stop_viseme_animation(self):
        """Stop the current viseme animation."""
        self._stop_event.set()
        
        if self._viseme_thread and self._viseme_thread.is_alive():
            self._viseme_thread.join(timeout=0.5)
        
        self._viseme_thread = None
    
    def is_animating(self) -> bool:
        """Check if viseme animation is currently running."""
        return self._viseme_thread is not None and self._viseme_thread.is_alive()


class AmplitudeAnalyzer:
    """
    Analyzes audio amplitude in real-time for mouth movement.
    """
    
    def __init__(self, window_size_ms: int = 50, smoothing: float = 0.3):
        """
        Initialize amplitude analyzer.
        
        Args:
            window_size_ms: Window size in milliseconds for RMS calculation
            smoothing: Smoothing factor for amplitude values (0.0-1.0)
        """
        self.window_size_ms = window_size_ms
        self.smoothing = smoothing
        self._current_amplitude = 0.0
        self._lock = threading.Lock()
    
    def calculate_rms(self, audio_data: bytes, sample_rate: int = 48000) -> float:
        """
        Calculate RMS amplitude from audio bytes.
        
        Args:
            audio_data: Raw audio bytes (assumed 16-bit PCM or float32)
            sample_rate: Sample rate of the audio
            
        Returns:
            RMS amplitude value (0.0-1.0)
        """
        import numpy as np
        
        if not audio_data or len(audio_data) < 4:
            return 0.0
        
        try:
            # Convert bytes to numpy array
            # Try float32 first (common for processed audio)
            try:
                samples = np.frombuffer(audio_data, dtype=np.float32)
            except (ValueError, TypeError):
                # Fall back to int16
                samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            if len(samples) == 0:
                return 0.0
            
            # Calculate RMS
            rms = np.sqrt(np.mean(samples ** 2))
            
            # Normalize to 0.0-1.0 range
            # Typical speech RMS is around 0.1-0.3
            normalized = min(1.0, rms * 3.0)
            
            return float(normalized)
            
        except Exception as e:
            logger.debug(f"Error calculating RMS: {e}")
            return 0.0
    
    def update_amplitude(self, amplitude: float) -> float:
        """
        Update amplitude with smoothing.
        
        Args:
            amplitude: New amplitude value
            
        Returns:
            Smoothed amplitude value
        """
        with self._lock:
            # Apply exponential smoothing
            self._current_amplitude = (
                self.smoothing * amplitude +
                (1 - self.smoothing) * self._current_amplitude
            )
            return self._current_amplitude
    
    def get_amplitude(self) -> float:
        """Get current smoothed amplitude."""
        with self._lock:
            return self._current_amplitude
    
    def reset(self):
        """Reset amplitude to zero."""
        with self._lock:
            self._current_amplitude = 0.0