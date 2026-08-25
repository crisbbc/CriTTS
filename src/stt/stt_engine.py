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


# Helper function for STT corrections (imported from text_preprocessor pattern)
def _apply_word_corrections(text: str, corrections: dict) -> str:
    """
    Apply word-level corrections to text.
    
    Args:
        text: Text to correct
        corrections: Dictionary mapping words to their corrections
        
    Returns:
        Corrected text
    """
    if not corrections or not text:
        return text
    
    words = text.split()
    corrected_words = []
    
    for word in words:
        # Check for exact match (case-insensitive)
        word_lower = word.lower()
        if word_lower in corrections:
            # Preserve original capitalization pattern
            correction = corrections[word_lower]
            if word.isupper():
                correction = correction.upper()
            elif word and word[0].isupper():
                correction = correction.capitalize()
            corrected_words.append(correction)
        else:
            corrected_words.append(word)
    
    return ' '.join(corrected_words)


class STTEngine:
    """
    Speech-to-Text engine that records microphone audio and transcribes it
    using Google Web Speech API (free, no API key required).
    """
    
    # Maximum recording duration in seconds to prevent unbounded memory growth
    _MAX_RECORDING_DURATION_SECONDS = 300  # 5 minutes max
    
    def __init__(self, settings_manager=None, on_auto_stop: Callable[[], None] = None):
        """
        Initialize the STT engine.
        
        Args:
            settings_manager: SettingsManager instance for accessing STT settings
            on_auto_stop: Optional callback fired when recording auto-stops due to buffer limit
        """
        self.settings_manager = settings_manager
        self._on_auto_stop = on_auto_stop
        self.recognizer = sr.Recognizer()
        self._is_listening_event = threading.Event()  # Thread-safe flag for cross-thread visibility
        self._audio_buffer: List[np.ndarray] = []
        self._sample_rate = 16000  # Standard sample rate for speech recognition
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        self._buffer_lock = threading.Lock()  # Protects _audio_buffer/_buffer_size_bytes
        self._buffer_size_bytes = 0  # Track total buffer size for memory limit
        self._max_buffer_bytes = self._MAX_RECORDING_DURATION_SECONDS * self._sample_rate * 2  # 2 bytes per sample (int16)
        self._auto_stopped_event = threading.Event()  # Thread-safe flag for auto-stop signaling
        
        logger.info("STT Engine initialized (max recording duration: %d seconds)", self._MAX_RECORDING_DURATION_SECONDS)
    
    def start_listening(self) -> bool:
        """
        Start recording from the microphone.
        
        Returns:
            True if recording started successfully, False otherwise
        """
        with self._lock:
            if self._is_listening_event.is_set():
                logger.warning("Already listening, ignoring start_listening call")
                return False
            
            try:
                # Clear the audio buffer and reset size counter
                with self._buffer_lock:
                    self._audio_buffer = []
                    self._buffer_size_bytes = 0
                self._auto_stopped_event.clear()  # Reset auto-stop flag (thread-safe)
                
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
                self._is_listening_event.set()
                
                logger.info("Started recording from microphone")
                return True
                
            except Exception as e:
                logger.error("Failed to start recording: %s", e)
                self._is_listening_event.clear()
                if self._stream:
                    try:
                        self._stream.close()
                    except Exception:
                        logger.debug("STT stream close failed during cleanup", exc_info=True)
                    self._stream = None
                return False
    
    def _audio_callback(self, indata: np.ndarray, _frames: int, _time_info, status):
        """
        Callback function for the audio stream.
        
        Args:
            indata: Input audio data
            _frames: Number of frames (unused, required by callback signature)
            _time_info: Time information (unused, required by callback signature)
            status: Status flags
        
        Note:
            This callback runs in a high-priority PortAudio thread. To avoid
            audio glitches and potential deadlocks, we minimize work here and
            use a thread-safe flag instead of calling Python callbacks directly.
        """
        if status:
            logger.warning("Audio stream status: %s", status)
        
        # Check if buffer size limit would be exceeded.  Buffer mutations are
        # guarded by _buffer_lock so stop_and_transcribe()/shutdown() can copy or
        # reset the buffer without racing this realtime callback.
        chunk_size_bytes = indata.nbytes
        with self._buffer_lock:
            if self._buffer_size_bytes + chunk_size_bytes > self._max_buffer_bytes:
                # Stop recording to prevent memory exhaustion
                logger.error(
                    "Recording buffer exceeded maximum size (%d seconds), stopping recording. "
                    "Recording may be incomplete.",
                    self._MAX_RECORDING_DURATION_SECONDS
                )
                # Reset listening flag (thread-safe operation)
                # The main thread polls this flag via the is_listening property
                self._is_listening_event.clear()
                # Set thread-safe event to signal auto-stop occurred - the main thread will
                # handle the callback via polling in stop_and_transcribe
                self._auto_stopped_event.set()
                # Signal stop by raising an exception in the callback
                # This will stop the stream
                raise sd.CallbackStop()

            # Append a copy of the audio data to the buffer
            self._audio_buffer.append(indata.copy())
            self._buffer_size_bytes += chunk_size_bytes
    
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
        stream = None
        with self._lock:
            is_listening = self._is_listening_event.is_set()
            auto_stopped = self._auto_stopped_event.is_set()
            if not is_listening and not auto_stopped:
                logger.warning("Not currently listening, ignoring stop_and_transcribe call")
                return

            self._is_listening_event.clear()
            stream = self._stream
            self._stream = None
            self._auto_stopped_event.clear()

        # Stop and close the stream OUTSIDE the lock.  InputStream.stop() waits
        # for the current audio callback to return, and the callback now takes
        # _buffer_lock — holding any lock across stop() could deadlock.
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logger.error("Error closing audio stream: %s", e)

        # Copy the audio buffer for processing (under its own lock).
        with self._buffer_lock:
            audio_buffer = list(self._audio_buffer)
        
        logger.info("Stopped recording, %d audio chunks to process", len(audio_buffer))
        
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
        
        logger.debug("Audio duration: %.0fms, samples: %d", duration_ms, len(audio_data))
        
        # 2. Silence trimming using rolling RMS
        # Use 20ms frames for RMS calculation
        frame_size = int(self._sample_rate * 0.02)  # 20ms frames
        
        if len(audio_data) < frame_size:
            raise ValueError("Audio too short for silence detection")
        
        # Calculate RMS for each frame (vectorized for performance)
        num_frames = len(audio_data) // frame_size
        # Reshape audio data into frames and compute RMS in one vectorized operation
        framed_audio = audio_data[:num_frames * frame_size].reshape(num_frames, frame_size)
        rms_values = np.sqrt(np.mean(framed_audio.astype(np.float64) ** 2, axis=1))
        
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
        
        logger.debug("Trimmed silence: %d to %d samples (%.0fms)", start_sample, end_sample, (end_sample - start_sample) / self._sample_rate * 1000)
        
        # 3. Amplitude normalization
        # Scale so peak reaches ~80% of int16 max
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            target_peak = 32767 * 0.8
            scale_factor = target_peak / max_val
            audio_data = (audio_data.astype(np.float64) * scale_factor).astype(np.int16)
            logger.debug("Normalized audio: peak %d -> %d", max_val, np.max(np.abs(audio_data)))
        
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
                logger.warning("High-pass filter failed: %s", e)
        
        return audio_data
    
    def _postprocess_transcript(self, text: str) -> str:
        """
        Postprocess transcribed text.
        
        Applies:
        1. Word-level corrections (stt_corrections)
        2. Capitalize first letter
        3. Strip trailing whitespace
        4. Optionally add trailing punctuation
        
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
        stt_corrections = self.settings_manager.get("stt_corrections", {}) if self.settings_manager else {}
        
        # Strip whitespace
        text = text.strip()
        
        if not text:
            return text
        
        # Apply word-level corrections
        if stt_corrections:
            text = _apply_word_corrections(text, stt_corrections)
        
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
                logger.warning("Audio preprocessing failed: %s", e)
                on_error(e)
                return
            except Exception as e:
                logger.error("Audio preprocessing error: %s", e)
                on_error(e)
                return
            
            # Convert to bytes (int16 = 2 bytes per sample)
            raw_data = audio_data.tobytes()
            
            logger.debug("Audio data: %d bytes, sample_rate: %d", len(raw_data), self._sample_rate)
            
            # Create AudioData object for speech_recognition
            audio = sr.AudioData(raw_data, self._sample_rate, 2)  # 2 = sample_width (int16)
            
            # Get language from settings
            language = "en-US"
            if self.settings_manager:
                language = self.settings_manager.get("stt_language", "en-US")
            
            logger.debug("Transcribing with language: %s", language)
            
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
                logger.error("Speech recognition service error: %s", e)
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
                logger.warning("Confidence %.2f below threshold %.2f", confidence, confidence_threshold)
                on_error(sr.UnknownValueError("Low confidence result (%.0f%%)" % (confidence * 100)))
                return
            
            if not text:
                logger.warning("No transcription result")
                on_error(sr.UnknownValueError("Could not understand audio"))
                return
            
            # Postprocess text
            text = self._postprocess_transcript(text)
            
            logger.info("Transcription successful: '%s' (confidence: %.0f%%)", text, confidence * 100)
            on_result(text)
            
        except sr.UnknownValueError:
            logger.warning("Speech not understood")
            on_error(sr.UnknownValueError("Could not understand audio"))
        except sr.RequestError as e:
            logger.error("Speech recognition service error: %s", e)
            on_error(sr.RequestError(f"Network error: {e}"))
        except Exception as e:
            logger.error("Transcription error: %s", e)
            on_error(e)
    
    @property
    def is_listening(self) -> bool:
        """Check if currently recording."""
        return self._is_listening_event.is_set()
    
    def check_auto_stopped(self) -> bool:
        """
        Check if recording was auto-stopped due to buffer limit.
        
        This method should be called from the main thread to safely check
        if the audio callback triggered an auto-stop. If True, the caller
        should handle the UI update and call the on_auto_stop callback.
        
        Returns:
            True if auto-stop occurred, False otherwise
        """
        return self._auto_stopped_event.is_set()
    
    def clear_auto_stopped(self):
        """Clear the auto-stop flag after handling."""
        self._auto_stopped_event.clear()
    
    def shutdown(self):
        """
        Shutdown the STT engine and stop any active recording.
        Called from CriTTSApp._on_closing.
        """
        stream = None
        with self._lock:
            if self._is_listening_event.is_set():
                logger.info("Shutting down STT engine, stopping active recording")
                self._is_listening_event.clear()
                stream = self._stream
                self._stream = None

        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logger.error("Error closing audio stream during shutdown: %s", e)

        with self._buffer_lock:
            self._audio_buffer = []
            self._buffer_size_bytes = 0
        
        logger.info("STT Engine shutdown complete")
