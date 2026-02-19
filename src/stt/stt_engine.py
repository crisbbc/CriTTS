"""
STT Engine Module
Handles microphone recording and speech-to-text transcription using Google Web Speech API.
"""
import logging
import threading
import numpy as np
import sounddevice as sd
import speech_recognition as sr
from typing import Optional, Callable, List

logger = logging.getLogger(__name__)


class STTEngine:
    """
    Speech-to-Text engine that records microphone audio and transcribes it
    using Google Web Speech API (free, no API key required).
    """
    
    def __init__(self, settings_manager=None):
        """
        Initialize the STT engine.
        
        Args:
            settings_manager: SettingsManager instance for accessing STT settings
        """
        self.settings_manager = settings_manager
        self.recognizer = sr.Recognizer()
        self._is_listening = False
        self._audio_buffer: List[np.ndarray] = []
        self._sample_rate = 16000  # Standard sample rate for speech recognition
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        
        logger.info("STT Engine initialized")
    
    def start_listening(self) -> bool:
        """
        Start recording from the microphone.
        
        Returns:
            True if recording started successfully, False otherwise
        """
        with self._lock:
            if self._is_listening:
                logger.warning("Already listening, ignoring start_listening call")
                return False
            
            try:
                # Clear the audio buffer
                self._audio_buffer = []
                
                # Get microphone device index from settings
                device_index = None
                if self.settings_manager:
                    device_index = self.settings_manager.get("stt_mic_device_index", None)
                
                # Open input stream
                self._stream = sd.InputStream(
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype='int16',
                    device=device_index,
                    callback=self._audio_callback
                )
                self._stream.start()
                self._is_listening = True
                
                logger.info("Started recording from microphone")
                return True
                
            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
                self._is_listening = False
                if self._stream:
                    try:
                        self._stream.close()
                    except Exception:
                        pass
                    self._stream = None
                return False
    
    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """
        Callback function for the audio stream.
        
        Args:
            indata: Input audio data
            frames: Number of frames
            time_info: Time information
            status: Status flags
        """
        if status:
            logger.warning(f"Audio stream status: {status}")
        
        # Append a copy of the audio data to the buffer
        self._audio_buffer.append(indata.copy())
    
    def stop_and_transcribe(
        self,
        on_result: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ):
        """
        Stop recording and transcribe the recorded audio.
        Runs transcription in a background thread.
        
        Args:
            on_result: Callback function called with transcribed text
            on_error: Callback function called with exception on error
        """
        with self._lock:
            if not self._is_listening:
                logger.warning("Not currently listening, ignoring stop_and_transcribe call")
                return
            
            # Stop and close the stream
            self._is_listening = False
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.error(f"Error closing audio stream: {e}")
                self._stream = None
            
            # Copy the audio buffer for processing
            audio_buffer = list(self._audio_buffer)
        
        logger.info(f"Stopped recording, {len(audio_buffer)} audio chunks to process")
        
        # Start transcription in a background thread
        thread = threading.Thread(
            target=self._transcribe_thread,
            args=(audio_buffer, on_result, on_error),
            daemon=True
        )
        thread.start()
    
    def _transcribe_thread(
        self,
        audio_buffer: List[np.ndarray],
        on_result: Callable[[str], None],
        on_error: Callable[[Exception], None]
    ):
        """
        Transcribe audio in a background thread.
        
        Args:
            audio_buffer: List of audio data chunks
            on_result: Callback function called with transcribed text
            on_error: Callback function called with exception on error
        """
        try:
            if not audio_buffer:
                logger.warning("No audio data to transcribe")
                on_error(ValueError("No audio recorded"))
                return
            
            # Concatenate audio buffer into a single array
            audio_data = np.concatenate(audio_buffer, axis=0)
            
            # Flatten to 1D array
            audio_data = audio_data.flatten()
            
            # Convert to bytes (int16 = 2 bytes per sample)
            raw_data = audio_data.tobytes()
            
            logger.debug(f"Audio data: {len(raw_data)} bytes, sample_rate: {self._sample_rate}")
            
            # Create AudioData object for speech_recognition
            audio = sr.AudioData(raw_data, self._sample_rate, 2)  # 2 = sample_width (int16)
            
            # Get language from settings
            language = "en-US"
            if self.settings_manager:
                language = self.settings_manager.get("stt_language", "en-US")
            
            logger.debug(f"Transcribing with language: {language}")
            
            # Transcribe using Google Web Speech API
            text = self.recognizer.recognize_google(audio, language=language)
            
            logger.info(f"Transcription successful: '{text}'")
            on_result(text)
            
        except sr.UnknownValueError:
            logger.warning("Speech not understood")
            on_error(sr.UnknownValueError("Could not understand audio"))
        except sr.RequestError as e:
            logger.error(f"Speech recognition service error: {e}")
            on_error(sr.RequestError(f"Network error: {e}"))
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            on_error(e)
    
    @property
    def is_listening(self) -> bool:
        """Check if currently recording."""
        return self._is_listening
    
    def shutdown(self):
        """
        Shutdown the STT engine and stop any active recording.
        Called from CriTTSApp._on_closing.
        """
        with self._lock:
            if self._is_listening:
                logger.info("Shutting down STT engine, stopping active recording")
                self._is_listening = False
                
                if self._stream:
                    try:
                        self._stream.stop()
                        self._stream.close()
                    except Exception as e:
                        logger.error(f"Error closing audio stream during shutdown: {e}")
                    self._stream = None
            
            self._audio_buffer = []
        
        logger.info("STT Engine shutdown complete")