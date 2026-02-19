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
    
    def _preprocess_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Preprocess audio data before transcription.
        
        Applies:
        1. Minimum duration check
        2. Silence trimming
        3. Amplitude normalization
        4. High-pass filter (optional)
        
        Args:
            audio_data: Raw int16 audio array
            
        Returns:
            Preprocessed audio data
            
        Raises:
            ValueError: If audio is too short or all silence
        """
        # Get settings
        min_duration_ms = self.settings_manager.get("stt_min_duration_ms", 300) if self.settings_manager else 300
        silence_threshold = self.settings_manager.get("stt_silence_threshold", 200) if self.settings_manager else 200
        highpass_filter = self.settings_manager.get("stt_highpass_filter", True) if self.settings_manager else True
        
        # 1. Minimum duration check
        duration_ms = len(audio_data) / self._sample_rate * 1000
        if duration_ms < min_duration_ms:
            raise ValueError(f"Recording too short ({duration_ms:.0f}ms < {min_duration_ms}ms minimum)")
        
        logger.debug(f"Audio duration: {duration_ms:.0f}ms, samples: {len(audio_data)}")
        
        # 2. Silence trimming using rolling RMS
        # Use 20ms frames for RMS calculation
        frame_size = int(self._sample_rate * 0.02)  # 20ms frames
        
        if len(audio_data) < frame_size:
            raise ValueError("Audio too short for silence detection")
        
        # Calculate RMS for each frame
        num_frames = len(audio_data) // frame_size
        rms_values = np.zeros(num_frames)
        
        for i in range(num_frames):
            frame = audio_data[i * frame_size:(i + 1) * frame_size]
            # RMS for int16 data
            rms_values[i] = np.sqrt(np.mean(frame.astype(np.float64) ** 2))
        
        # Find first and last frame above threshold
        above_threshold = rms_values > silence_threshold
        
        if not np.any(above_threshold):
            raise ValueError("No speech detected (all silence)")
        
        first_voice_frame = np.argmax(above_threshold)
        last_voice_frame = len(above_threshold) - 1 - np.argmax(above_threshold[::-1])
        
        # Slice audio to voice region (with small padding)
        padding_frames = 2  # 40ms padding
        start_frame = max(0, first_voice_frame - padding_frames)
        end_frame = min(num_frames, last_voice_frame + padding_frames + 1)
        
        start_sample = start_frame * frame_size
        end_sample = end_frame * frame_size
        
        audio_data = audio_data[start_sample:end_sample].copy()
        
        logger.debug(f"Trimmed silence: {start_sample} to {end_sample} samples ({(end_sample - start_sample) / self._sample_rate * 1000:.0f}ms)")
        
        # 3. Amplitude normalization
        # Scale so peak reaches ~80% of int16 max
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            target_peak = 32767 * 0.8
            scale_factor = target_peak / max_val
            audio_data = (audio_data.astype(np.float64) * scale_factor).astype(np.int16)
            logger.debug(f"Normalized audio: peak {max_val} -> {np.max(np.abs(audio_data))}")
        
        # 4. High-pass filter (optional)
        if highpass_filter:
            try:
                from scipy.signal import butter, filtfilt
                
                # Design high-pass filter at 80 Hz
                nyquist = self._sample_rate / 2
                cutoff = 80 / nyquist
                
                # Ensure cutoff is valid (must be < 1)
                if cutoff < 1:
                    b, a = butter(1, cutoff, btype='high')
                    
                    # Convert to float for filtering, then back to int16
                    audio_float = audio_data.astype(np.float64)
                    audio_filtered = filtfilt(b, a, audio_float)
                    
                    # Clip and convert back to int16
                    audio_data = np.clip(audio_filtered, -32768, 32767).astype(np.int16)
                    logger.debug("Applied 80Hz high-pass filter")
            except ImportError:
                logger.warning("scipy not available, skipping high-pass filter")
            except Exception as e:
                logger.warning(f"High-pass filter failed: {e}")
        
        return audio_data
    
    def _postprocess_transcript(self, text: str) -> str:
        """
        Postprocess transcribed text.
        
        Applies:
        1. Capitalize first letter
        2. Strip trailing whitespace
        3. Optionally add trailing punctuation
        
        Args:
            text: Raw transcribed text
            
        Returns:
            Postprocessed text
        """
        if not text:
            return text
        
        # Get settings
        capitalize = self.settings_manager.get("stt_capitalize", True) if self.settings_manager else True
        add_punctuation = self.settings_manager.get("stt_add_punctuation", False) if self.settings_manager else False
        
        # Strip whitespace
        text = text.strip()
        
        if not text:
            return text
        
        # Capitalize first letter
        if capitalize:
            text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
        
        # Add trailing punctuation if enabled and missing
        if add_punctuation and text:
            if text[-1] not in '.!?':
                text += '.'
        
        return text
    
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
            
            # Preprocess audio
            try:
                audio_data = self._preprocess_audio(audio_data)
            except ValueError as e:
                logger.warning(f"Audio preprocessing failed: {e}")
                on_error(e)
                return
            except Exception as e:
                logger.error(f"Audio preprocessing error: {e}")
                on_error(e)
                return
            
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
            
            # Get confidence threshold from settings
            confidence_threshold = self.settings_manager.get("stt_confidence_threshold", 0.0) if self.settings_manager else 0.0
            
            # Transcribe using Google Web Speech API with show_all=True
            try:
                response = self.recognizer.recognize_google(audio, language=language, show_all=True)
            except sr.UnknownValueError:
                logger.warning("Speech not understood")
                on_error(sr.UnknownValueError("Could not understand audio"))
                return
            except sr.RequestError as e:
                logger.error(f"Speech recognition service error: {e}")
                on_error(sr.RequestError(f"Network error: {e}"))
                return
            
            # Parse response for best alternative
            text = None
            confidence = 0.0
            
            if isinstance(response, dict) and 'alternative' in response:
                alternatives = response.get('alternative', [])
                
                if alternatives:
                    # Find alternative with highest confidence
                    best_alt = None
                    best_confidence = -1
                    
                    for alt in alternatives:
                        alt_confidence = alt.get('confidence', 0.0)
                        if alt_confidence > best_confidence:
                            best_confidence = alt_confidence
                            best_alt = alt
                    
                    if best_alt:
                        text = best_alt.get('transcript', '')
                        confidence = best_alt.get('confidence', 0.0)
                        
                        # If no confidence scores provided, use first alternative
                        if confidence == 0.0 and alternatives:
                            text = alternatives[0].get('transcript', '')
            elif isinstance(response, str):
                # Fallback: response is just a string
                text = response
            
            # Check confidence threshold
            if confidence_threshold > 0.0 and confidence < confidence_threshold:
                logger.warning(f"Confidence {confidence:.2f} below threshold {confidence_threshold}")
                on_error(sr.UnknownValueError(f"Low confidence result ({confidence:.0%})"))
                return
            
            if not text:
                logger.warning("No transcription result")
                on_error(sr.UnknownValueError("Could not understand audio"))
                return
            
            # Postprocess text
            text = self._postprocess_transcript(text)
            
            logger.info(f"Transcription successful: '{text}' (confidence: {confidence:.0%})")
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