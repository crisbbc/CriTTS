"""
Audio Router Module
Handles audio device enumeration and routing audio to specific output devices.
"""
import threading
import queue
import sounddevice as sd
import soundfile as sf
import numpy as np
import io
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from scipy import signal
from math import gcd

logger = logging.getLogger(__name__)
try:
    import pyloudnorm as pyln
except ImportError:
    pyln = None



class AudioRouter:
    """Manages audio device enumeration and playback routing."""
    
    def __init__(self):
        """Initialize the audio router."""
        self._current_stream = None
        self._stop_requested = threading.Event()
        self._amplitude_callback = None
        self._current_amplitude = 0.0
        
        # Microphone passthrough state
        self._passthrough_input_stream: Optional[sd.InputStream] = None
        self._passthrough_output_stream: Optional[sd.OutputStream] = None
        self._passthrough_queue: queue.Queue = queue.Queue()
        self._passthrough_active: bool = False
    
    def get_audio_devices(self) -> List[Dict]:
        """
        Enumerate all available audio output devices.
        
        Returns:
            List of dictionaries with 'index', 'name', and 'channels' for each device.
        """
        devices = []
        device_list = sd.query_devices()
        
        for i, device in enumerate(device_list):
            if device['max_output_channels'] > 0:
                devices.append({
                    'index': i,
                    'name': device['name'],
                    'channels': device['max_output_channels'],
                    'sample_rate': device['default_samplerate']
                })
        
        return devices
    
    def get_input_devices(self) -> List[Dict]:
        """
        Enumerate all available audio input devices (microphones).
        
        Returns:
            List of dictionaries with 'index', 'name', 'channels', and 'sample_rate' for each device.
        """
        devices = []
        device_list = sd.query_devices()
        
        for i, device in enumerate(device_list):
            if device['max_input_channels'] > 0:
                devices.append({
                    'index': i,
                    'name': device['name'],
                    'channels': device['max_input_channels'],
                    'sample_rate': device['default_samplerate']
                })
        
        return devices
    
    def get_default_device(self) -> Optional[Dict]:
        """Get the system default output device."""
        try:
            default = sd.query_devices(kind='output')
            return {
                'index': sd.default.device[1] if isinstance(sd.default.device, tuple) else 0,
                'name': default['name'],
                'channels': default['max_output_channels'],
                'sample_rate': default['default_samplerate']
            }
        except Exception:
            return None
    
    def _normalize_audio(self, data: np.ndarray, norm_type: str = "Peak", sample_rate: int = 48000) -> np.ndarray:
        """
        Apply audio normalization to prevent clipping and ensure consistent volume.
        
        Args:
            data: Audio data array
            norm_type: Type of normalization ("Peak", "RMS", or "None")
            sample_rate: Sample rate of the audio data (used for LUFS measurement)
            
        Returns:
            Normalized audio data
        """
        if norm_type == "None" or data.size == 0:
            return data
        
        # Prevent division by zero
        max_val = np.max(np.abs(data))
        if max_val < 1e-10:
            return data
        
        if norm_type == "Peak":
            # Peak normalization to -1 dB (prevents clipping)
            target_peak = 0.891  # -1 dB
            gain = target_peak / max_val
            return data * gain
        
        elif norm_type == "RMS":
            # RMS normalization for consistent loudness
            current_rms = np.sqrt(np.mean(data**2))
            if current_rms < 1e-10:
                return data
            target_rms = 0.15  # Increased from 0.1 for better perceived loudness
            gain = target_rms / current_rms
            # Limit gain to prevent excessive amplification
            gain = min(gain, 10.0)
            return data * gain
        
        elif norm_type == "LUFS":
            # LUFS normalization for professional loudness standards
            if pyln is None:
                # Fallback to Peak normalization if pyloudnorm is not available
                target_peak = 0.891  # -1 dB
                gain = target_peak / max_val
                return data * gain
            
            # Create meter for loudness measurement using the actual sample rate
            meter = pyln.Meter(sample_rate)
            
            # Handle both mono and stereo
            if len(data.shape) == 1:
                # Mono audio
                loudness = meter.integrated_loudness(data)
            else:
                # Stereo audio - use left channel for measurement
                loudness = meter.integrated_loudness(data[:, 0])
            
            # Target loudness levels (industry standards)
            # -14 LUFS for streaming platforms (Spotify, YouTube)
            # -23 LUFS for broadcast (EBU R128)
            target_lufs = -14.0  # Default to streaming standard
            
            # Calculate gain needed to reach target loudness
            gain_db = target_lufs - loudness
            gain = 10 ** (gain_db / 20)
            
            # Limit gain to prevent excessive amplification
            gain = min(gain, 10.0)
            
            return data * gain
        
        return data
    
    def _get_profile_settings(self, profile: str) -> Dict:
        """
        Get processing settings for a given profile.
        
        Args:
            profile: Processing profile name ("fast_preview", "balanced", "high_quality")
            
        Returns:
            Dictionary with processing settings
        """
        profiles = {
            "fast_preview": {
                "sample_rate": None,  # No resampling - use original
                "kaiser_beta": 0.0,   # No anti-aliasing filter
                "stereo_width": 0.0,  # No stereo enhancement
                "normalization_type": "None"
            },
            "balanced": {
                "sample_rate": 48000,
                "kaiser_beta": 5.0,
                "stereo_width": 0.3,
                "normalization_type": "Peak"
            },
            "high_quality": {
                "sample_rate": 48000,
                "kaiser_beta": 8.0,   # Higher quality anti-aliasing
                "stereo_width": 0.5,  # More stereo enhancement
                "normalization_type": "LUFS"
            }
        }
        
        return profiles.get(profile, profiles["balanced"])
    
    def _resample_high_quality(self, data: np.ndarray, orig_sr: int, target_sr: int, kaiser_beta: float = 5.0) -> np.ndarray:
        """
        High-quality resampling using scipy's polyphase resampling with anti-aliasing.
        
        Args:
            data: Audio data array
            orig_sr: Original sample rate
            target_sr: Target sample rate
            kaiser_beta: Kaiser window beta parameter (higher = better anti-aliasing)
            
        Returns:
            Resampled audio data
        """
        if orig_sr == target_sr:
            return data
        
        # Calculate GCD for optimal resampling ratio
        g = gcd(orig_sr, target_sr)
        up = target_sr // g
        down = orig_sr // g
        
        # Use polyphase resampling with anti-aliasing filter
        resampled = signal.resample_poly(data, up, down, window=('kaiser', kaiser_beta))
        
        return resampled
    
    def _stereo_enhancement(self, data: np.ndarray, width: float = 0.5) -> np.ndarray:
        """
        Convert mono to stereo with width enhancement for more natural sound.
        
        Args:
            data: Mono audio data
            width: Stereo width factor (0.0 to 1.0)
            
        Returns:
            Stereo audio data (2D array with left and right channels)
        """
        if len(data.shape) > 1:
            # Already stereo, return as-is
            return data
        
        # Create stereo with slight delay for width
        left = data * (1.0 - width * 0.5)
        right = data * (1.0 - width * 0.5)
        
        # Add slight phase shift for width enhancement
        if width > 0 and len(data) > 10:
            delay_samples = int(0.001 * 48000)  # 1ms delay at 48kHz
            if delay_samples < len(data):
                right[delay_samples:] += data[:-delay_samples] * width * 0.3
        
        stereo = np.column_stack((left, right))
        return stereo
    
    async def play_audio_to_device(
        self, 
        audio_data: bytes, 
        sample_rate: int = 48000, 
        device_index: Optional[int] = None,
        enable_normalization: bool = True,
        normalization_type: str = "Peak",
        processing_profile: str = "balanced"
    ) -> bool:

        """
        Play audio data to a specific output device.
        
        Args:
            audio_data: Raw audio data (MP3/WAV bytes from edge_tts)
            sample_rate: Sample rate of the audio
            device_index: Output device index (None for default)
            enable_normalization: Whether to apply normalization (overridden by processing_profile)
            normalization_type: Type of normalization (overridden by processing_profile)
            processing_profile: Processing profile ("fast_preview", "balanced", "high_quality")
            
        Returns:
            True if playback succeeded, False otherwise.
        """
        try:
            self._stop_requested.clear()
            
            # Derive processing settings from profile
            profile_settings = self._get_profile_settings(processing_profile)
            target_sr = profile_settings["sample_rate"]
            kaiser_beta = profile_settings["kaiser_beta"]
            stereo_width = profile_settings["stereo_width"]
            
            # Determine normalization type: respect enable_normalization flag
            # If normalization is disabled, use "None"; otherwise use caller-provided type
            if enable_normalization:
                norm_type = normalization_type
            else:
                norm_type = "None"
            
            # Load audio data using soundfile
            audio_buffer = io.BytesIO(audio_data)
            data, sr = sf.read(audio_buffer, dtype=np.float32)
            
            # High-quality resampling using scipy (skip for fast_preview)
            # Do resampling BEFORE normalization so LUFS uses correct sample rate
            if sr != target_sr and target_sr is not None:
                data = self._resample_high_quality(data, sr, target_sr, kaiser_beta)
                effective_sr = target_sr
            else:
                effective_sr = sr
            
            # Apply normalization after resampling, using the effective sample rate for LUFS
            if norm_type != "None":
                data = self._normalize_audio(data, norm_type, sample_rate=effective_sr)
            
            # Convert mono to stereo with enhancement (skip for fast_preview)
            if len(data.shape) == 1 and stereo_width > 0:
                data = self._stereo_enhancement(data, width=stereo_width)
            
            # Play audio using sounddevice
            def callback(outdata, frames, time, status):
                # Check if stop was requested
                if self._stop_requested.is_set():
                    raise sd.CallbackStop()
                
                # Fill buffer with audio data
                nonlocal data
                if len(data) > 0:
                    chunksize = min(frames, len(data))
                    outdata[:chunksize] = data[:chunksize]
                    if chunksize < frames:
                        outdata[chunksize:] = 0
                    data = data[chunksize:]
                else:
                    outdata[:] = 0
                    raise sd.CallbackStop()
            
            # Create output stream
            # Use the effective_sr already computed during resampling
            channels = data.shape[1] if len(data.shape) > 1 else 1

            self._current_stream = sd.OutputStream(
                device=device_index,
                samplerate=effective_sr,
                channels=channels,
                callback=callback,
                finished_callback=self._stream_finished
            )

            
            with self._current_stream:
                # Wait for playback to complete or stop requested
                while self._current_stream.active and not self._stop_requested.is_set():
                    await asyncio.sleep(0.1)
            
            # Return False when playback was interrupted by stop request
            return not self._stop_requested.is_set()
            
        except sd.PortAudioError:
            return False
        except Exception:
            return False
        finally:
            try:
                if self._current_stream is not None:
                    try:
                        self._current_stream.close()
                    except Exception:
                        pass
            finally:
                self._current_stream = None
    
    def _stream_finished(self):
        """Callback when audio stream finishes."""
        # Reset amplitude when stream finishes
        self._current_amplitude = 0.0
        if self._amplitude_callback:
            try:
                self._amplitude_callback(0.0)
            except Exception:
                pass
    
    def set_amplitude_callback(self, callback):
        """
        Set a callback function to receive amplitude updates during playback.
        
        Args:
            callback: Function that takes a float (0.0-1.0) amplitude value
        """
        self._amplitude_callback = callback
    
    def _calculate_chunk_amplitude(self, chunk: np.ndarray) -> float:
        """
        Calculate RMS amplitude for an audio chunk.
        
        Args:
            chunk: Audio data chunk
            
        Returns:
            Normalized amplitude value (0.0-1.0)
        """
        if chunk.size == 0:
            return 0.0
        
        # Calculate RMS
        rms = np.sqrt(np.mean(chunk ** 2))
        
        # Normalize to 0.0-1.0 range (typical speech RMS is 0.1-0.3)
        normalized = min(1.0, rms * 3.0)
        
        return float(normalized)
    
    def get_current_amplitude(self) -> float:
        """Get the current amplitude value."""
        return self._current_amplitude
    
    def get_audio_duration(self, audio_data: bytes) -> float:
        """
        Calculate the duration of audio data in seconds.
        
        Args:
            audio_data: Raw audio data bytes (MP3/WAV)
            
        Returns:
            Duration in seconds as a float, or 0.0 on error.
        """
        try:
            audio_buffer = io.BytesIO(audio_data)
            info = sf.info(audio_buffer)
            return info.duration
        except Exception:
            return 0.0
    
    def stop_playback(self):
        """Stop current audio playback."""
        self._stop_requested.set()
        self._current_amplitude = 0.0
        if self._current_stream is not None:
            try:
                self._current_stream.stop()
            except Exception:
                pass
    
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        return self._current_stream is not None and self._current_stream.active
    
    def is_vbcable_installed(self) -> bool:
        """
        Check if VB-Cable or similar virtual audio cable is installed.
        
        Returns:
            True if a virtual audio cable device is found, False otherwise.
        """
        # Keywords that identify VB-Cable and similar virtual audio devices
        vbcable_keywords = ["cable", "vb-audio", "vbaudio", "vb cable"]
        
        devices = self.get_audio_devices()
        for device in devices:
            device_name_lower = device['name'].lower()
            if any(keyword in device_name_lower for keyword in vbcable_keywords):
                return True
        
        return False
    
    async def play_audio_with_amplitude(
        self, 
        audio_data: bytes, 
        sample_rate: int = 48000, 
        device_index: Optional[int] = None,
        enable_normalization: bool = True,
        normalization_type: str = "Peak",
        amplitude_callback=None,
        processing_profile: str = "balanced"
    ) -> bool:
        """
        Play audio data with real-time amplitude analysis.
        
        Args:
            audio_data: Raw audio data (MP3/WAV bytes from edge_tts)
            sample_rate: Sample rate of the audio
            device_index: Output device index (None for default)
            enable_normalization: Whether to apply normalization
            normalization_type: Type of normalization
            amplitude_callback: Callback function for amplitude updates
            processing_profile: Processing profile ("fast_preview", "balanced", "high_quality")
            
        Returns:
            True if playback succeeded, False otherwise.
        """
        try:
            self._stop_requested.clear()
            self._amplitude_callback = amplitude_callback
            
            # Derive processing settings from profile
            profile_settings = self._get_profile_settings(processing_profile)
            target_sr = profile_settings["sample_rate"]
            kaiser_beta = profile_settings["kaiser_beta"]
            stereo_width = profile_settings["stereo_width"]
            
            # Determine normalization type: respect enable_normalization flag
            if enable_normalization:
                norm_type = normalization_type
            else:
                norm_type = "None"
            
            # Load audio data using soundfile
            audio_buffer = io.BytesIO(audio_data)
            data, sr = sf.read(audio_buffer, dtype=np.float32)
            
            # High-quality resampling using scipy (skip for fast_preview)
            if sr != target_sr and target_sr is not None:
                data = self._resample_high_quality(data, sr, target_sr, kaiser_beta)
                effective_sr = target_sr
            else:
                effective_sr = sr
            
            # Apply normalization after resampling
            if norm_type != "None":
                data = self._normalize_audio(data, norm_type, sample_rate=effective_sr)
            
            # Convert mono to stereo with enhancement (skip for fast_preview)
            if len(data.shape) == 1 and stereo_width > 0:
                data = self._stereo_enhancement(data, width=stereo_width)
            
            # Store original data for amplitude calculation
            original_data = data.copy()
            
            # Play audio using sounddevice
            def callback(outdata, frames, time, status):
                # Check if stop was requested
                if self._stop_requested.is_set():
                    raise sd.CallbackStop()
                
                # Fill buffer with audio data
                nonlocal data, original_data
                if len(data) > 0:
                    chunksize = min(frames, len(data))
                    outdata[:chunksize] = data[:chunksize]
                    if chunksize < frames:
                        outdata[chunksize:] = 0
                    
                    # Calculate amplitude for this chunk
                    if self._amplitude_callback:
                        chunk_for_amp = original_data[:chunksize]
                        amp = self._calculate_chunk_amplitude(chunk_for_amp)
                        self._current_amplitude = amp
                        try:
                            self._amplitude_callback(amp)
                        except:
                            pass
                    
                    data = data[chunksize:]
                    original_data = original_data[chunksize:]
                else:
                    outdata[:] = 0
                    self._current_amplitude = 0.0
                    if self._amplitude_callback:
                        try:
                            self._amplitude_callback(0.0)
                        except:
                            pass
                    raise sd.CallbackStop()
            
            # Create output stream - use effective_sr from processing
            channels = data.shape[1] if len(data.shape) > 1 else 1

            self._current_stream = sd.OutputStream(
                device=device_index,
                samplerate=effective_sr,
                channels=channels,
                callback=callback,
                finished_callback=self._stream_finished
            )

            
            with self._current_stream:
                # Wait for playback to complete or stop requested
                while self._current_stream.active and not self._stop_requested.is_set():
                    await asyncio.sleep(0.05)  # Faster updates for amplitude
            
            # Return False when playback was interrupted by stop request
            return not self._stop_requested.is_set()
            
        except sd.PortAudioError:
            return False
        except Exception:
            return False
        finally:
            try:
                if self._current_stream is not None:
                    try:
                        self._current_stream.close()
                    except Exception:
                        pass
            finally:
                self._current_stream = None
                self._current_amplitude = 0.0
    
    async def play_audio_streaming(
        self,
        audio_chunk_generator,
        sample_rate: int = 48000,
        device_index: Optional[int] = None,
        processing_profile: str = "balanced",
        stop_event=None
    ) -> bool:
        """
        Play streaming audio data to a specific output device.
        
        This method receives audio chunks from an async generator and plays them
        in real-time, enabling low-latency playback where audio starts before
        the entire TTS generation is complete.
        
        Args:
            audio_chunk_generator: Async generator yielding MP3 audio chunks
            sample_rate: Target sample rate for playback
            device_index: Output device index (None for default)
            processing_profile: Processing profile ("fast_preview", "balanced", "high_quality")
            stop_event: Optional threading.Event to signal stop
            
        Returns:
            True if playback succeeded, False otherwise.
        """
        import queue
        import threading as th
        
        try:
            self._stop_requested.clear()
            
            # Get profile settings
            profile_settings = self._get_profile_settings(processing_profile)
            target_sr = profile_settings["sample_rate"] or sample_rate
            norm_type = profile_settings["normalization_type"]
            kaiser_beta = profile_settings["kaiser_beta"]
            stereo_width = profile_settings["stereo_width"]
            
            # Queue for decoded audio chunks
            audio_queue = queue.Queue()
            playback_started = asyncio.Event()
            playback_finished = th.Event()
            decode_error = [None]
            stream_ended = [False]  # Track when generator is exhausted
            
            # Accumulated MP3 data for decoding - need enough for valid MP3 frames
            mp3_buffer = bytearray()
            # Minimum buffer size before attempting decode (MP3 frames need ~100-500 bytes minimum)
            MIN_DECODE_BUFFER = 4096
            
            async def decode_chunks():
                """Decode incoming MP3 chunks incrementally and add to playback queue."""
                nonlocal mp3_buffer
                
                try:
                    async for chunk in audio_chunk_generator:
                        # Check for stop
                        if self._stop_requested.is_set() or (stop_event and stop_event.is_set()):
                            break
                        
                        # Add chunk to buffer
                        mp3_buffer.extend(chunk)
                        
                        # Try to decode incrementally when we have enough data
                        while len(mp3_buffer) >= MIN_DECODE_BUFFER:
                            try:
                                # Try to decode the current buffer
                                audio_buffer = io.BytesIO(bytes(mp3_buffer))
                                data, sr = sf.read(audio_buffer, dtype=np.float32)
                                
                                # Calculate how many bytes were consumed
                                consumed = audio_buffer.tell()
                                
                                if data.size > 0 and consumed > 0:
                                    # Remove consumed bytes from buffer
                                    mp3_buffer = mp3_buffer[consumed:]
                                    
                                    # Resample if needed (before normalization for correct LUFS)
                                    if sr != target_sr:
                                        data = self._resample_high_quality(data, sr, target_sr, kaiser_beta)
                                        effective_sr = target_sr
                                    else:
                                        effective_sr = sr
                                    
                                    # Apply normalization
                                    if norm_type != "None":
                                        data = self._normalize_audio(data, norm_type, sample_rate=effective_sr)
                                    
                                    # Convert to stereo if needed
                                    if len(data.shape) == 1 and stereo_width > 0:
                                        data = self._stereo_enhancement(data, width=stereo_width)
                                    elif len(data.shape) == 1:
                                        # Convert to stereo without enhancement for consistent output
                                        data = np.column_stack((data, data))
                                    
                                    # Queue for playback
                                    audio_queue.put(data)
                                    
                                    # Signal that playback can start
                                    if not playback_started.is_set():
                                        playback_started.set()
                                else:
                                    # Couldn't decode yet, wait for more data
                                    break
                                    
                            except Exception:
                                # Decoding failed, might need more data
                                # Keep the buffer and continue accumulating
                                break
                    
                    # Decode any remaining data in the buffer
                    if len(mp3_buffer) > 0:
                        try:
                            audio_buffer = io.BytesIO(bytes(mp3_buffer))
                            data, sr = sf.read(audio_buffer, dtype=np.float32)
                            
                            if data.size > 0:
                                # Resample if needed
                                if sr != target_sr:
                                    data = self._resample_high_quality(data, sr, target_sr, kaiser_beta)
                                    effective_sr = target_sr
                                else:
                                    effective_sr = sr
                                
                                # Apply normalization
                                if norm_type != "None":
                                    data = self._normalize_audio(data, norm_type, sample_rate=effective_sr)
                                
                                # Convert to stereo if needed
                                if len(data.shape) == 1 and stereo_width > 0:
                                    data = self._stereo_enhancement(data, width=stereo_width)
                                elif len(data.shape) == 1:
                                    data = np.column_stack((data, data))
                                
                                # Queue for playback
                                audio_queue.put(data)
                                
                                if not playback_started.is_set():
                                    playback_started.set()
                        except Exception as e:
                            decode_error[0] = e
                    
                    # Signal end of stream
                    stream_ended[0] = True
                    audio_queue.put(None)
                    
                except Exception as e:
                    decode_error[0] = e
                    stream_ended[0] = True
                    audio_queue.put(None)
            
            # Closure variable to hold leftover samples between callbacks
            leftover = [None]
            
            def audio_callback(outdata, frames, time, status):
                """Sounddevice callback for streaming playback."""
                if self._stop_requested.is_set():
                    raise sd.CallbackStop()
                
                # Check leftover first (guarantees ordering)
                if leftover[0] is not None:
                    chunk = leftover[0]
                    leftover[0] = None
                else:
                    # Get data from queue (non-blocking)
                    try:
                        chunk = audio_queue.get_nowait()
                        if chunk is None:
                            # End of stream
                            raise sd.CallbackStop()
                    except queue.Empty:
                        # No data available yet, output silence
                        outdata[:] = 0
                        return
                
                # Fill output buffer
                if len(chunk) >= frames:
                    outdata[:] = chunk[:frames]
                    # Store remaining data in leftover for next callback
                    remaining = chunk[frames:]
                    if len(remaining) > 0:
                        leftover[0] = remaining
                else:
                    outdata[:len(chunk)] = chunk
                    outdata[len(chunk):] = 0
            
            # Start decode task
            decode_task = asyncio.create_task(decode_chunks())
            
            # Wait for first chunk or timeout
            try:
                await asyncio.wait_for(playback_started.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # No audio received within timeout
                decode_task.cancel()
                return False
            
            # Check for decode errors
            if decode_error[0]:
                return False
            
            # Start playback stream
            self._current_stream = sd.OutputStream(
                device=device_index,
                samplerate=target_sr,
                channels=2,
                callback=audio_callback,
                finished_callback=lambda: playback_finished.set()
            )
            
            with self._current_stream:
                # Wait for playback to complete or stop
                while self._current_stream.active and not self._stop_requested.is_set():
                    if stop_event and stop_event.is_set():
                        self._stop_requested.set()
                        break
                    await asyncio.sleep(0.05)
            
            # Wait for decode task to complete
            try:
                await asyncio.wait_for(decode_task, timeout=1.0)
            except asyncio.TimeoutError:
                decode_task.cancel()
            
            return not self._stop_requested.is_set()
            
        except sd.PortAudioError:
            return False
        except Exception:
            return False
        finally:
            if self._current_stream is not None:
                try:
                    self._current_stream.close()
                except Exception:
                    pass
                self._current_stream = None
    
    def start_mic_passthrough(
        self,
        input_device_index: Optional[int],
        output_device_index: Optional[int],
        volume: float = 1.0,
        sample_rate: int = 48000
    ) -> bool:
        """
        Start continuous microphone passthrough to an output device.
        
        Creates an input stream from the microphone and an output stream to the
        target device, with audio flowing through a queue in real-time.
        
        Args:
            input_device_index: Input device index (None for system default)
            output_device_index: Output device index (None for system default)
            volume: Volume multiplier (0.0 to 2.0, where 1.0 is normal)
            sample_rate: Sample rate for both streams
            
        Returns:
            True if passthrough started successfully, False otherwise.
        """
        try:
            # Stop any existing passthrough first
            self.stop_mic_passthrough()
            
            # Create bounded queue to prevent unbounded growth
            self._passthrough_queue = queue.Queue(maxsize=50)
            
            # Input callback: puts audio data into the queue
            def input_callback(indata, frames, time, status):
                try:
                    # Apply volume and copy data
                    audio_chunk = indata.copy() * volume
                    # Put into queue, drop oldest if full
                    if self._passthrough_queue.full():
                        try:
                            self._passthrough_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self._passthrough_queue.put(audio_chunk)
                except Exception as e:
                    logger.warning("Passthrough input callback error: %s", e)
            
            # Output callback: gets audio data from the queue
            def output_callback(outdata, frames, time, status):
                try:
                    audio_chunk = self._passthrough_queue.get_nowait()
                    # Handle mono to mono output
                    if len(audio_chunk.shape) == 1:
                        outdata[:len(audio_chunk)] = audio_chunk.reshape(-1, 1)
                        if len(audio_chunk) < frames:
                            outdata[len(audio_chunk):] = 0
                    else:
                        if len(audio_chunk) >= frames:
                            outdata[:] = audio_chunk[:frames]
                        else:
                            outdata[:len(audio_chunk)] = audio_chunk
                            outdata[len(audio_chunk):] = 0
                except queue.Empty:
                    # No data available, output silence
                    outdata[:] = 0
                except Exception as e:
                    logger.warning("Passthrough output callback error: %s", e)
                    outdata[:] = 0
            
            # Open input stream (mono)
            self._passthrough_input_stream = sd.InputStream(
                device=input_device_index,
                samplerate=sample_rate,
                channels=1,
                dtype='float32',
                callback=input_callback
            )
            
            # Open output stream (mono)
            self._passthrough_output_stream = sd.OutputStream(
                device=output_device_index,
                samplerate=sample_rate,
                channels=1,
                dtype='float32',
                callback=output_callback
            )
            
            # Start both streams
            self._passthrough_input_stream.start()
            self._passthrough_output_stream.start()
            self._passthrough_active = True
            
            logger.info("Microphone passthrough started (input=%s, output=%s, volume=%.2f)",
                       input_device_index, output_device_index, volume)
            return True
            
        except sd.PortAudioError as e:
            logger.error("PortAudio error starting mic passthrough: %s", e)
            self.stop_mic_passthrough()
            return False
        except Exception as e:
            logger.error("Error starting mic passthrough: %s", e)
            self.stop_mic_passthrough()
            return False
    
    def stop_mic_passthrough(self):
        """Stop microphone passthrough and clean up resources."""
        self._passthrough_active = False
        
        # Stop and close input stream
        if self._passthrough_input_stream is not None:
            try:
                self._passthrough_input_stream.stop()
                self._passthrough_input_stream.close()
            except Exception as e:
                logger.warning("Error closing passthrough input stream: %s", e)
            finally:
                self._passthrough_input_stream = None
        
        # Stop and close output stream
        if self._passthrough_output_stream is not None:
            try:
                self._passthrough_output_stream.stop()
                self._passthrough_output_stream.close()
            except Exception as e:
                logger.warning("Error closing passthrough output stream: %s", e)
            finally:
                self._passthrough_output_stream = None
        
        # Clear the queue by draining it
        if self._passthrough_queue is not None:
            try:
                while not self._passthrough_queue.empty():
                    self._passthrough_queue.get_nowait()
            except queue.Empty:
                pass
        
        logger.info("Microphone passthrough stopped")
    
    def is_mic_passthrough_active(self) -> bool:
        """
        Check if microphone passthrough is currently active.
        
        Returns:
            True if passthrough is active, False otherwise.
        """
        return self._passthrough_active
