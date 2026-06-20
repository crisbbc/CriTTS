"""
Audio Router Module
Handles audio device enumeration and routing audio to specific output devices.
"""
import threading
import queue
import re
from dataclasses import dataclass
import sounddevice as sd
import numpy as np
import io
import asyncio
import logging
import subprocess
from typing import List, Dict, Optional, Tuple
from scipy import signal
from math import gcd

logger = logging.getLogger(__name__)
try:
    import pyloudnorm as pyln
except ImportError:
    pyln = None


@dataclass(frozen=True)
class PreparedAudioPayload:
    """Processed non-streaming audio ready for duration lookup and playback."""

    data: np.ndarray
    sample_rate: int

    @property
    def duration_seconds(self) -> float:
        """Return payload duration in seconds."""
        if self.sample_rate <= 0 or self.data.size == 0:
            return 0.0
        return len(self.data) / self.sample_rate



class AudioRouter:
    """Manages audio device enumeration and playback routing."""

    # Blocksize for passthrough streams to ensure synchronized callbacks
    _PASSTHROUGH_BLOCKSIZE = 512

    # Host API suffix pattern for deduplication
    _HOST_API_PATTERN = re.compile(r'\s*\[(?:MME|DirectSound|WASAPI|WDM-KS|ASIO)\]\s*$', re.IGNORECASE)

    def __init__(self):
        """Initialize the audio router."""
        self._current_stream = None
        self._stop_requested = threading.Event()
        self._amplitude_callback = None
        self._current_amplitude = 0.0

        # Microphone passthrough state
        self._passthrough_input_stream: Optional[sd.InputStream] = None
        self._passthrough_output_stream: Optional[sd.OutputStream] = None
        self._passthrough_duplex_stream: Optional[sd.Stream] = None
        self._passthrough_queue: queue.Queue = queue.Queue()
        self._passthrough_active: bool = False
        self._passthrough_lock = threading.Lock()  # Protects passthrough state transitions

    @staticmethod
    def _deduplicate_devices(devices: List[Dict]) -> List[Dict]:
        """
        Deduplicate audio device list using multi-pass algorithm.

        Handles:
        1. Exact name matches (case-insensitive) - same device from different host APIs
        2. Host API suffix patterns like "Device Name [MME]", "Device Name [DirectSound]"
        3. Prefix matches - truncated vs full names

        Args:
            devices: List of device dictionaries to deduplicate

        Returns:
            Deduplicated and sorted list of device dictionaries
        """
        if not devices:
            return []

        # Pass 1: Exact name deduplication (case-insensitive)
        seen_names_lower = {}
        for device in devices:
            name_lower = device['name'].lower().strip()
            if name_lower not in seen_names_lower:
                seen_names_lower[name_lower] = device

        # Pass 2: Remove host API suffixes and check for duplicates
        base_name_to_device = {}
        for device in seen_names_lower.values():
            name = device['name']
            base_name = AudioRouter._HOST_API_PATTERN.sub('', name).strip()
            base_lower = base_name.lower()

            if base_lower not in base_name_to_device:
                base_name_to_device[base_lower] = device
            else:
                existing = base_name_to_device[base_lower]
                existing_has_suffix = bool(AudioRouter._HOST_API_PATTERN.search(existing['name']))
                current_has_suffix = bool(AudioRouter._HOST_API_PATTERN.search(name))

                # Prefer device without host API suffix
                if current_has_suffix and not existing_has_suffix:
                    pass  # Keep existing
                elif not current_has_suffix and existing_has_suffix:
                    base_name_to_device[base_lower] = device  # Replace with cleaner name
                elif len(name) < len(existing['name']):
                    # Both have or don't have suffix, prefer shorter name
                    base_name_to_device[base_lower] = device

        # Pass 3: Prefix-based deduplication for truncated names
        # Sort by name length (longest first) to prefer full names over truncated
        devices_sorted = sorted(base_name_to_device.values(), key=lambda d: len(d['name']), reverse=True)

        final_devices = []
        final_devices_lower = []  # Cache lowercase versions to avoid repeated .lower() calls
        for device in devices_sorted:
            name_lower = device['name'].lower()
            is_duplicate = False

            # Check if this device's name is a prefix of or is prefixed by any existing device
            for existing_lower in final_devices_lower:
                if name_lower.startswith(existing_lower) or existing_lower.startswith(name_lower):
                    is_duplicate = True
                    break

            if not is_duplicate:
                final_devices.append(device)
                final_devices_lower.append(name_lower)

        # Sort by name for consistent display
        final_devices.sort(key=lambda d: d['name'].lower())

        return final_devices

    def get_audio_devices(self) -> List[Dict]:
        """
        Enumerate all available audio output devices.

        Returns:
            List of dictionaries with 'index', 'name', and 'channels' for each device.
        """
        device_list = sd.query_devices()

        # Collect all output devices
        all_output = []
        for i, device in enumerate(device_list):
            if device['max_output_channels'] > 0:
                all_output.append({
                    'index': i,
                    'name': device['name'],
                    'channels': device['max_output_channels'],
                    'sample_rate': device['default_samplerate']
                })

        return self._deduplicate_devices(all_output)

    def get_input_devices(self) -> List[Dict]:
        """
        Enumerate all available audio input devices (microphones).

        Returns:
            List of dictionaries with 'index', 'name', 'channels', and 'sample_rate' for each device.
        """
        device_list = sd.query_devices()

        # Collect all input devices
        all_input = []
        for i, device in enumerate(device_list):
            if device['max_input_channels'] > 0:
                all_input.append({
                    'index': i,
                    'name': device['name'],
                    'channels': device['max_input_channels'],
                    'sample_rate': device['default_samplerate']
                })

        return self._deduplicate_devices(all_input)

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

        Note:
            Normalization is controlled separately via the Audio tab settings
            (enable_normalization and normalization_type). The profile only
            controls resampling quality and stereo enhancement.
        """
        profiles = {
            "fast_preview": {
                "sample_rate": None,  # No resampling - use original
                "kaiser_beta": 0.0,   # No anti-aliasing filter
                "stereo_width": 0.0,  # No stereo enhancement
            },
            "balanced": {
                "sample_rate": 48000,
                "kaiser_beta": 5.0,
                "stereo_width": 0.15,
            },
            "high_quality": {
                "sample_rate": 48000,
                "kaiser_beta": 8.0,   # Higher quality anti-aliasing
                "stereo_width": 0.25,  # Gentle stereo enhancement for speech
            }
        }

        return profiles.get(profile, profiles["balanced"])

    def _resolve_playback_settings(
        self,
        enable_normalization: bool,
        normalization_type: str,
        processing_profile: str,
    ) -> Tuple[Optional[int], float, float, str]:
        """Resolve the shared playback configuration for non-streaming audio."""
        profile_settings = self._get_profile_settings(processing_profile)
        target_sr = profile_settings["sample_rate"]
        kaiser_beta = profile_settings["kaiser_beta"]
        stereo_width = profile_settings["stereo_width"]
        norm_type = normalization_type if enable_normalization else "None"
        return target_sr, kaiser_beta, stereo_width, norm_type

    def _process_playback_audio(
        self,
        data: np.ndarray,
        sample_rate: int,
        target_sample_rate: Optional[int],
        kaiser_beta: float,
        norm_type: str,
        enable_clarity_eq: bool,
        stereo_width: float,
    ) -> Tuple[np.ndarray, int]:
        """Apply the shared speech-friendly playback processing pipeline."""
        if target_sample_rate is not None and sample_rate != target_sample_rate:
            data = self._resample_high_quality(data, sample_rate, target_sample_rate, kaiser_beta)
            effective_sr = target_sample_rate
        else:
            effective_sr = sample_rate

        if norm_type != "None" and len(data) > 0:
            data = self._normalize_audio(data, norm_type, sample_rate=effective_sr)

        if enable_clarity_eq and len(data) > 0:
            data = self._apply_clarity_eq(data, effective_sr)

        if len(data.shape) == 1 and stereo_width > 0:
            data = self._stereo_enhancement(data, width=stereo_width)

        if len(data.shape) == 1:
            data = np.column_stack((data, data))

        return data, effective_sr

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

    def _apply_clarity_eq(self, data: np.ndarray, sample_rate: int) -> np.ndarray:
        """Apply a two-stage speech clarity EQ for improved intelligibility.

        Stage 1 – High-pass at 80 Hz:
            Removes low-frequency rumble that Piper ONNX models sometimes
            produce, which can mask consonants over VBCable / voice chat.

        Stage 2 – Presence peak at 2.5 kHz (+2.5 dB, Q=0.8):
            The 2–4 kHz band carries the bulk of speech intelligibility
            (fricatives, plosives, formant transitions).  A gentle boost here
            makes voices noticeably clearer without sounding harsh.
        """
        nyquist = sample_rate / 2.0

        # --- Stage 1: high-pass at 80 Hz ---
        hp_norm = 80.0 / nyquist
        if 0.0 < hp_norm < 1.0:
            sos_hp = signal.butter(2, hp_norm, btype='high', output='sos')
        else:
            sos_hp = None

        # --- Stage 2: peaking EQ at 2500 Hz, +2.5 dB, Q=0.8 ---
        f0 = 2500.0
        gain_db = 2.5
        Q = 0.8
        A = 10 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * f0 / sample_rate
        sin_w0 = np.sin(w0)
        cos_w0 = np.cos(w0)
        alpha = sin_w0 / (2.0 * Q)
        b_peak = np.array([1.0 + alpha * A, -2.0 * cos_w0, 1.0 - alpha * A])
        a_peak = np.array([1.0 + alpha / A, -2.0 * cos_w0, 1.0 - alpha / A])
        sos_peak = signal.tf2sos(b_peak, a_peak)

        def _process(ch: np.ndarray) -> np.ndarray:
            if sos_hp is not None:
                ch = signal.sosfilt(sos_hp, ch)
            return signal.sosfilt(sos_peak, ch)

        if data.ndim == 1:
            result = _process(data)
        else:
            result = np.column_stack([_process(data[:, i]) for i in range(data.shape[1])])

        # Soft-limit to prevent any post-EQ clipping
        peak = np.max(np.abs(result))
        if peak > 0.99:
            result = result * (0.99 / peak)
        return result

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

    async def _decode_mp3_audio(self, audio_data: bytes, target_sample_rate: Optional[int] = 48000) -> Tuple[np.ndarray, int]:
        """
        Decode MP3 audio data to PCM float32 numpy array using ffmpeg.

        This method uses ffmpeg for reliable MP3 decoding, as soundfile often
        lacks MP3 support due to licensing restrictions.

        Args:
            audio_data: Raw MP3 audio bytes
            target_sample_rate: Target sample rate for output (default 48000).
                               If None, decode at native sample rate without resampling.

        Returns:
            Tuple of (audio_data as float32 numpy array, sample_rate)

        Raises:
            RuntimeError: If decoding fails or ffmpeg is not available
        """
        try:
            # Use ffmpeg to decode MP3 to raw PCM
            # -i = input, -f f32le = output format (32-bit float little-endian)
            # -acodec pcm_f32le = PCM codec, -ar = sample rate
            # - = output to stdout

            # Build ffmpeg command - omit -ar if target_sample_rate is None for native rate
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', 'pipe:0',           # Read from stdin
                '-f', 'f32le',            # Output format: 32-bit float little-endian
                '-acodec', 'pcm_f32le',   # PCM codec
            ]

            if target_sample_rate is not None:
                # Cast target_sample_rate to int to prevent command injection
                ffmpeg_cmd.extend(['-ar', str(int(target_sample_rate))])

            ffmpeg_cmd.extend([
                '-ac', '2',               # Stereo output for consistency
                '-'                       # Output to stdout
            ])

            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=audio_data),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                raise RuntimeError("ffmpeg decode timeout - MP3 may be corrupted or too large")

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace') if stderr else 'Unknown ffmpeg error'
                logger.error("ffmpeg MP3 decode failed (return code %d): %s", process.returncode, error_msg[:500])
                raise RuntimeError(f"ffmpeg failed to decode MP3: {error_msg[:200]}")

            if len(stdout) == 0:
                raise RuntimeError("ffmpeg produced no output - MP3 may be empty or corrupted")

            # Convert raw bytes to numpy array (stereo float32)
            # Each sample is 2 channels * 4 bytes (float32) = 8 bytes per frame
            audio_array = np.frombuffer(stdout, dtype=np.float32)

            # Reshape to stereo (2 channels)
            audio_array = audio_array.reshape(-1, 2)

            # Determine the actual sample rate
            if target_sample_rate is not None:
                actual_sr = target_sample_rate
            else:
                # Extract native sample rate from ffmpeg stderr output
                # Look for patterns like "Stream #0:0: Audio: mp3, 44100 Hz, stereo"
                stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ''
                sr_match = re.search(r'(\d+)\s*Hz', stderr_text)
                if sr_match:
                    actual_sr = int(sr_match.group(1))
                else:
                    # Fallback: assume 44100 Hz (common MP3 sample rate)
                    actual_sr = 44100
                    logger.warning("Could not detect native sample rate, assuming %d Hz", actual_sr)

            logger.debug("Successfully decoded MP3: %d samples at %d Hz", len(audio_array), actual_sr)

            return audio_array, actual_sr

        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found - please install ffmpeg for MP3 decoding support")
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            logger.error("MP3 decode error: %s", e)
            raise RuntimeError(f"Failed to decode MP3: {str(e)}")


    async def _decode_audio_data(self, audio_data: bytes, target_sample_rate: Optional[int] = 48000) -> Tuple[np.ndarray, int]:
        """
        Decode audio data (MP3 or WAV) to PCM float32 numpy array.

        Attempts to use ffmpeg for MP3 decoding first (reliable), with fallback
        to soundfile for WAV files. This ensures MP3 support is always available
        when ffmpeg is installed.

        Args:
            audio_data: Raw audio bytes (MP3 or WAV)
            target_sample_rate: Target sample rate for MP3 decoding.
                               If None, decode at native sample rate without resampling.

        Returns:
            Tuple of (audio_data as float32 numpy array, sample_rate)

        Raises:
            RuntimeError: If decoding fails
        """
        # Try ffmpeg first - it handles MP3 reliably
        try:
            return await self._decode_mp3_audio(audio_data, target_sample_rate)
        except RuntimeError as e:
            # If ffmpeg fails, try soundfile as fallback (for WAV files)
            logger.debug("ffmpeg decode failed, trying soundfile: %s", e)
            try:
                import soundfile as sf
                audio_buffer = io.BytesIO(audio_data)
                data, sr = sf.read(audio_buffer, dtype="float32")
                if data.size == 0:
                    raise RuntimeError("soundfile produced empty audio")
                return data, sr
            except Exception as sf_error:
                logger.error("soundfile also failed: %s", sf_error)
                # Re-raise the original ffmpeg error with context
                raise RuntimeError(f"Audio decode failed - ffmpeg: {e}; soundfile: {sf_error}")

    async def prepare_audio_for_playback(
        self,
        audio_data: bytes,
        enable_normalization: bool = True,
        normalization_type: str = "Peak",
        processing_profile: str = "balanced",
        enable_clarity_eq: bool = True,
    ) -> PreparedAudioPayload:
        """Decode and process one non-streaming segment for reuse."""
        target_sr, kaiser_beta, stereo_width, norm_type = self._resolve_playback_settings(
            enable_normalization,
            normalization_type,
            processing_profile,
        )
        data, sr = await self._decode_audio_data(audio_data, target_sr)
        processed_data, effective_sr = self._process_playback_audio(
            data,
            sr,
            target_sr,
            kaiser_beta,
            norm_type,
            enable_clarity_eq,
            stereo_width,
        )
        return PreparedAudioPayload(data=processed_data, sample_rate=effective_sr)

    async def _play_prepared_audio(
        self,
        prepared_audio: PreparedAudioPayload,
        device_index: Optional[int] = None,
        amplitude_callback=None,
        wait_interval: float = 0.1,
    ) -> bool:
        """Play a previously prepared non-streaming payload."""
        self._stop_requested.clear()
        self._amplitude_callback = amplitude_callback

        data = prepared_audio.data
        effective_sr = prepared_audio.sample_rate
        data_index = 0
        data_len = len(data)

        def callback(outdata, frames, time, status):
            if self._stop_requested.is_set():
                raise sd.CallbackStop()

            nonlocal data_index, data_len
            if data_index < data_len:
                chunksize = min(frames, data_len - data_index)
                outdata[:chunksize] = data[data_index:data_index + chunksize]
                if chunksize < frames:
                    outdata[chunksize:] = 0

                if self._amplitude_callback:
                    start = data_index
                    chunk_for_amp = data[start:start + chunksize]
                    amp = self._calculate_chunk_amplitude(chunk_for_amp)
                    self._current_amplitude = amp
                    try:
                        self._amplitude_callback(amp)
                    except Exception:
                        pass

                data_index += chunksize
            else:
                outdata[:] = 0
                self._current_amplitude = 0.0
                if self._amplitude_callback:
                    try:
                        self._amplitude_callback(0.0)
                    except Exception:
                        pass
                raise sd.CallbackStop()

        channels = data.shape[1] if len(data.shape) > 1 else 1
        self._current_stream = sd.OutputStream(
            device=device_index,
            samplerate=effective_sr,
            channels=channels,
            callback=callback,
            finished_callback=self._stream_finished
        )

        with self._current_stream:
            while self._current_stream.active and not self._stop_requested.is_set():
                await asyncio.sleep(wait_interval)

        return not self._stop_requested.is_set()

    async def play_audio_to_device(
        self,
        audio_data: bytes,
        sample_rate: int = 48000,
        device_index: Optional[int] = None,
        enable_normalization: bool = True,
        normalization_type: str = "Peak",
        processing_profile: str = "balanced",
        enable_clarity_eq: bool = True,
        prepared_audio: Optional[PreparedAudioPayload] = None,
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
            if prepared_audio is None:
                try:
                    prepared_audio = await self.prepare_audio_for_playback(
                        audio_data,
                        enable_normalization=enable_normalization,
                        normalization_type=normalization_type,
                        processing_profile=processing_profile,
                        enable_clarity_eq=enable_clarity_eq,
                    )
                except RuntimeError as e:
                    logger.error("Failed to decode audio data: %s", e)
                    return False

            return await self._play_prepared_audio(
                prepared_audio,
                device_index=device_index,
                wait_interval=0.1,
            )

        except sd.PortAudioError:
            return False
        except Exception as e:
            logger.error("play_audio_to_device error: %s", e)
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

    async def get_audio_duration(self, audio_data: bytes) -> float:
        """
        Calculate the duration of audio data in seconds.

        Args:
            audio_data: Raw audio data bytes (MP3/WAV)

        Returns:
            Duration in seconds as a float, or 0.0 on error.
        """
        try:
            prepared_audio = await self.prepare_audio_for_playback(
                audio_data,
                enable_normalization=False,
                normalization_type="None",
                processing_profile="balanced",
                enable_clarity_eq=False,
            )
            return prepared_audio.duration_seconds
        except Exception:
            return 0.0

    def stop_playback(self):
        """Stop current audio playback."""
        self._stop_requested.set()
        self._current_amplitude = 0.0
        stream = self._current_stream
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass

    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        stream = self._current_stream
        return stream is not None and stream.active

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
        processing_profile: str = "balanced",
        enable_clarity_eq: bool = True,
        prepared_audio: Optional[PreparedAudioPayload] = None,
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
            if prepared_audio is None:
                try:
                    prepared_audio = await self.prepare_audio_for_playback(
                        audio_data,
                        enable_normalization=enable_normalization,
                        normalization_type=normalization_type,
                        processing_profile=processing_profile,
                        enable_clarity_eq=enable_clarity_eq,
                    )
                except RuntimeError as e:
                    logger.error("Failed to decode audio data: %s", e)
                    return False

            return await self._play_prepared_audio(
                prepared_audio,
                device_index=device_index,
                amplitude_callback=amplitude_callback,
                wait_interval=0.05,
            )

        except sd.PortAudioError:
            return False
        except Exception as e:
            logger.error("play_audio_with_amplitude error: %s", e)
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
        stop_event=None,
        enable_normalization: bool = True,
        normalization_type: str = "Peak",
        amplitude_callback=None,
        enable_clarity_eq: bool = True,
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
            enable_normalization: Whether to apply normalization
            normalization_type: Type of normalization ("Peak", "RMS", "LUFS", or "None")
            amplitude_callback: Optional callback for real-time amplitude updates

        Returns:
            True if playback succeeded, False otherwise.
        """
        import queue
        import threading as th

        process = None

        try:
            self._stop_requested.clear()

            # Get profile settings
            profile_settings = self._get_profile_settings(processing_profile)
            target_sr = profile_settings["sample_rate"]  # None for fast_preview means no resampling
            kaiser_beta = profile_settings["kaiser_beta"]
            stereo_width = profile_settings["stereo_width"]

            # Determine normalization type: respect enable_normalization flag
            if enable_normalization:
                norm_type = normalization_type
            else:
                norm_type = "None"

            # Queue for decoded audio chunks - bounded to provide backpressure
            audio_queue = queue.Queue(maxsize=5)
            playback_started = asyncio.Event()
            playback_finished = th.Event()
            decode_error = [None]  # type: List[Optional[Exception]]
            detected_sr = [None]  # type: List[Optional[int]]

            # Build persistent ffmpeg decoder
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', 'pipe:0',
                '-f', 'f32le',
                '-acodec', 'pcm_f32le',
            ]

            if target_sr is not None:
                ffmpeg_cmd.extend(['-ar', str(int(target_sr))])

            ffmpeg_cmd.extend([
                '-ac', '2',
                '-'
            ])

            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            async def feed_stdin():
                """Feed MP3 chunks into ffmpeg stdin."""
                try:
                    async for chunk in audio_chunk_generator:
                        if self._stop_requested.is_set() or (stop_event and stop_event.is_set()):
                            break
                        if process.stdin:
                            process.stdin.write(chunk)
                            await process.stdin.drain()
                except Exception as e:
                    decode_error[0] = e
                finally:
                    if process.stdin:
                        try:
                            process.stdin.close()
                        except Exception:
                            pass

            async def read_stderr():
                """Parse ffmpeg stderr to detect sample rate when needed."""
                if not process.stderr:
                    return
                buffer = bytearray()
                try:
                    while True:
                        chunk = await process.stderr.read(512)
                        if not chunk:
                            break
                        if detected_sr[0] is None:
                            buffer.extend(chunk)
                            text = buffer.decode('utf-8', errors='replace')
                            match = re.search(r'(\d+)\s*Hz', text)
                            if match:
                                detected_sr[0] = int(match.group(1))
                            if len(buffer) > 4096:
                                buffer = buffer[-2048:]
                except Exception:
                    pass

            async def read_stdout():
                """Read decoded PCM from ffmpeg stdout and enqueue for playback."""
                if not process.stdout:
                    decode_error[0] = RuntimeError("ffmpeg stdout unavailable")
                    audio_queue.put(None)
                    return

                buffer = bytearray()
                frame_bytes = 8  # stereo float32
                frames_per_chunk = 2048
                min_bytes = frame_bytes * frames_per_chunk

                try:
                    while True:
                        if self._stop_requested.is_set() or (stop_event and stop_event.is_set()):
                            break

                        data = await process.stdout.read(4096)
                        if not data:
                            break
                        buffer.extend(data)

                        while len(buffer) >= min_bytes:
                            chunk_bytes = buffer[:min_bytes]
                            del buffer[:min_bytes]

                            chunk = np.frombuffer(chunk_bytes, dtype=np.float32).reshape(-1, 2)
                            effective_sr = target_sr if target_sr is not None else (detected_sr[0] or sample_rate)
                            chunk, effective_sr = self._process_playback_audio(
                                chunk,
                                effective_sr,
                                None,
                                kaiser_beta,
                                norm_type,
                                enable_clarity_eq,
                                stereo_width,
                            )

                            while True:
                                if self._stop_requested.is_set() or (stop_event and stop_event.is_set()):
                                    return
                                try:
                                    audio_queue.put(chunk, block=True, timeout=0.1)
                                    break
                                except queue.Full:
                                    continue

                            if not playback_started.is_set():
                                playback_started.set()

                    # Flush remaining buffer
                    if buffer:
                        usable = (len(buffer) // frame_bytes) * frame_bytes
                        if usable > 0:
                            chunk_bytes = buffer[:usable]
                            chunk = np.frombuffer(chunk_bytes, dtype=np.float32).reshape(-1, 2)
                            effective_sr = target_sr if target_sr is not None else (detected_sr[0] or sample_rate)
                            chunk, effective_sr = self._process_playback_audio(
                                chunk,
                                effective_sr,
                                None,
                                kaiser_beta,
                                norm_type,
                                enable_clarity_eq,
                                stereo_width,
                            )
                            audio_queue.put(chunk)

                except Exception as e:
                    decode_error[0] = e
                finally:
                    audio_queue.put(None)

            # Closure variable to hold leftover samples between callbacks
            leftover = [None]

            def audio_callback(outdata, frames, time, status):
                """Sounddevice callback for streaming playback."""
                if self._stop_requested.is_set():
                    raise sd.CallbackStop()

                if leftover[0] is not None:
                    chunk = leftover[0]
                    leftover[0] = None
                else:
                    try:
                        chunk = audio_queue.get_nowait()
                        if chunk is None:
                            self._current_amplitude = 0.0
                            if amplitude_callback:
                                try:
                                    amplitude_callback(0.0)
                                except Exception:
                                    pass
                            raise sd.CallbackStop()
                    except queue.Empty:
                        outdata[:] = 0
                        return

                if len(chunk) >= frames:
                    outdata[:] = chunk[:frames]
                    remaining = chunk[frames:]
                    if len(remaining) > 0:
                        leftover[0] = remaining
                    if amplitude_callback:
                        amp = self._calculate_chunk_amplitude(chunk[:frames])
                        self._current_amplitude = amp
                        try:
                            amplitude_callback(amp)
                        except Exception:
                            pass
                else:
                    outdata[:len(chunk)] = chunk
                    outdata[len(chunk):] = 0
                    if amplitude_callback:
                        amp = self._calculate_chunk_amplitude(chunk)
                        self._current_amplitude = amp
                        try:
                            amplitude_callback(amp)
                        except Exception:
                            pass

            feed_task = asyncio.create_task(feed_stdin())
            stderr_task = asyncio.create_task(read_stderr())
            stdout_task = asyncio.create_task(read_stdout())

            try:
                await asyncio.wait_for(playback_started.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                return False

            if decode_error[0]:
                return False

            output_sr = target_sr if target_sr is not None else (detected_sr[0] or sample_rate)

            if output_sr is None:
                logger.error("Could not determine sample rate for playback stream")
                return False

            self._current_stream = sd.OutputStream(
                device=device_index,
                samplerate=output_sr,
                channels=2,
                callback=audio_callback,
                finished_callback=lambda: playback_finished.set()
            )

            with self._current_stream:
                while self._current_stream.active and not self._stop_requested.is_set():
                    if stop_event and stop_event.is_set():
                        self._stop_requested.set()
                        break
                    await asyncio.sleep(0.05)

            try:
                await asyncio.wait_for(stdout_task, timeout=1.0)
            except asyncio.TimeoutError:
                stdout_task.cancel()

            feed_task.cancel()
            stderr_task.cancel()

            return not self._stop_requested.is_set()

        except sd.PortAudioError:
            return False
        except Exception:
            return False
        finally:
            if process is not None:
                try:
                    process.kill()
                except Exception:
                    pass
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
    ) -> Tuple[bool, Optional[str]]:
        """
        Start continuous microphone passthrough to an output device.

        Creates an input stream from the microphone and an output stream to the
        target device, with audio flowing through a queue in real-time.

        For same-device (input == output), uses a single full-duplex stream
        for glitch-free passthrough without queue overhead.

        Args:
            input_device_index: Input device index (None for system default)
            output_device_index: Output device index (None for system default)
            volume: Volume multiplier (0.0 to 2.0, where 1.0 is normal)
            sample_rate: Sample rate for both streams (will be negotiated if unsupported)

        Returns:
            Tuple of (success: bool, error_message: Optional[str]).
            If successful, error_message will be None.
        """
        with self._passthrough_lock:
            # Stop any existing passthrough first (without re-acquiring lock)
            self._stop_mic_passthrough_unlocked()

            try:
                # Query native sample rates from devices for negotiation
                input_native_sr = None
                output_native_sr = None

                if input_device_index is not None:
                    try:
                        input_device_info = sd.query_devices(input_device_index)
                        input_native_sr = int(input_device_info.get('default_samplerate', sample_rate))
                    except Exception as e:
                        logger.warning("Could not query input device sample rate: %s", e)

                if output_device_index is not None:
                    try:
                        output_device_info = sd.query_devices(output_device_index)
                        output_native_sr = int(output_device_info.get('default_samplerate', sample_rate))
                    except Exception as e:
                        logger.warning("Could not query output device sample rate: %s", e)

                # Determine the best sample rate to use
                # Priority: caller's preference > input native > output native > default
                chosen_sr = sample_rate

                # Check if same device (treat None == None as equal)
                same_device = (input_device_index == output_device_index)

                # ========== SAME-DEVICE PATH: Full-duplex stream ==========
                if same_device:
                    # Duplex callback: handles both input and output atomically
                    def duplex_callback(indata, outdata, frames, time, status):
                        try:
                            # Direct copy with volume - no queue needed
                            outdata[:] = indata * volume
                        except Exception as e:
                            logger.warning("Passthrough duplex callback error: %s", e)
                            outdata[:] = 0

                    # Try to open duplex stream with negotiated sample rate
                    # Attempt 1: Use caller-provided sample rate
                    try:
                        self._passthrough_duplex_stream = sd.Stream(
                            device=input_device_index,
                            samplerate=chosen_sr,
                            channels=1,
                            dtype='float32',
                            blocksize=self._PASSTHROUGH_BLOCKSIZE,
                            callback=duplex_callback
                        )
                        self._passthrough_duplex_stream.start()

                    except sd.PortAudioError as e:
                        # Attempt 2: Use input device's native sample rate
                        if input_native_sr is not None and input_native_sr != chosen_sr:
                            logger.info("Retrying passthrough with input device native sample rate: %d", input_native_sr)
                            self._stop_mic_passthrough_unlocked()
                            chosen_sr = input_native_sr

                            try:
                                self._passthrough_duplex_stream = sd.Stream(
                                    device=input_device_index,
                                    samplerate=chosen_sr,
                                    channels=1,
                                    dtype='float32',
                                    blocksize=self._PASSTHROUGH_BLOCKSIZE,
                                    callback=duplex_callback
                                )
                                self._passthrough_duplex_stream.start()

                            except sd.PortAudioError as e2:
                                # Attempt 3: Use output device's native sample rate
                                if output_native_sr is not None and output_native_sr != chosen_sr:
                                    logger.info("Retrying passthrough with output device native sample rate: %d", output_native_sr)
                                    self._stop_mic_passthrough_unlocked()
                                    chosen_sr = output_native_sr

                                    self._passthrough_duplex_stream = sd.Stream(
                                        device=input_device_index,
                                        samplerate=chosen_sr,
                                        channels=1,
                                        dtype='float32',
                                        blocksize=self._PASSTHROUGH_BLOCKSIZE,
                                        callback=duplex_callback
                                    )
                                    self._passthrough_duplex_stream.start()
                                else:
                                    raise e2
                        else:
                            raise

                    self._passthrough_active = True

                    logger.info("Microphone passthrough started (duplex mode, device=%s, sample_rate=%d, volume=%.2f)",
                               input_device_index, chosen_sr, volume)
                    return (True, None)

                # ========== DIFFERENT-DEVICE PATH: Two streams with synchronized blocksize ==========

                # Create bounded queue (smaller for tighter latency)
                self._passthrough_queue = queue.Queue(maxsize=10)

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
                        # Flatten to 1-D if needed, then reshape to (frames, 1)
                        flat = audio_chunk.flatten()
                        chunk_len = min(len(flat), frames)
                        outdata[:chunk_len, 0] = flat[:chunk_len]
                        if chunk_len < frames:
                            outdata[chunk_len:] = 0
                    except queue.Empty:
                        # No data available, output silence
                        outdata[:] = 0
                    except Exception as e:
                        logger.warning("Passthrough output callback error: %s", e)
                        outdata[:] = 0

                # Pre-fill silence chunks for startup buffer
                silence_chunk = np.zeros((self._PASSTHROUGH_BLOCKSIZE, 1), dtype='float32')

                # Helper function to clean up partially created streams
                def cleanup_partial_streams():
                    """Clean up any partially created streams on error."""
                    if self._passthrough_input_stream is not None:
                        try:
                            self._passthrough_input_stream.stop()
                            self._passthrough_input_stream.close()
                        except Exception:
                            pass
                        self._passthrough_input_stream = None
                    if self._passthrough_output_stream is not None:
                        try:
                            self._passthrough_output_stream.stop()
                            self._passthrough_output_stream.close()
                        except Exception:
                            pass
                        self._passthrough_output_stream = None

                # Try to open streams with negotiated sample rate
                # Attempt 1: Use caller-provided sample rate
                stream_opened = False
                try:
                    # Open input stream (mono) with fixed blocksize
                    self._passthrough_input_stream = sd.InputStream(
                        device=input_device_index,
                        samplerate=chosen_sr,
                        channels=1,
                        dtype='float32',
                        blocksize=self._PASSTHROUGH_BLOCKSIZE,
                        callback=input_callback
                    )

                    # Open output stream (mono) with fixed blocksize
                    self._passthrough_output_stream = sd.OutputStream(
                        device=output_device_index,
                        samplerate=chosen_sr,
                        channels=1,
                        dtype='float32',
                        blocksize=self._PASSTHROUGH_BLOCKSIZE,
                        callback=output_callback
                    )

                    # Start input stream first
                    self._passthrough_input_stream.start()

                    # Pre-fill queue with 2 silence chunks before starting output
                    self._passthrough_queue.put(silence_chunk)
                    self._passthrough_queue.put(silence_chunk)

                    # Now start output stream
                    self._passthrough_output_stream.start()
                    stream_opened = True

                except sd.PortAudioError as e:
                    # Attempt 2: Use input device's native sample rate
                    if input_native_sr is not None and input_native_sr != chosen_sr:
                        logger.info("Retrying passthrough with input device native sample rate: %d", input_native_sr)
                        cleanup_partial_streams()
                        chosen_sr = input_native_sr

                        try:
                            self._passthrough_input_stream = sd.InputStream(
                                device=input_device_index,
                                samplerate=chosen_sr,
                                channels=1,
                                dtype='float32',
                                blocksize=self._PASSTHROUGH_BLOCKSIZE,
                                callback=input_callback
                            )

                            self._passthrough_output_stream = sd.OutputStream(
                                device=output_device_index,
                                samplerate=chosen_sr,
                                channels=1,
                                dtype='float32',
                                blocksize=self._PASSTHROUGH_BLOCKSIZE,
                                callback=output_callback
                            )

                            self._passthrough_input_stream.start()

                            # Pre-fill queue with 2 silence chunks
                            self._passthrough_queue.put(silence_chunk)
                            self._passthrough_queue.put(silence_chunk)

                            self._passthrough_output_stream.start()
                            stream_opened = True

                        except sd.PortAudioError as e2:
                            # Attempt 3: Use output device's native sample rate
                            if output_native_sr is not None and output_native_sr != chosen_sr:
                                logger.info("Retrying passthrough with output device native sample rate: %d", output_native_sr)
                                cleanup_partial_streams()
                                chosen_sr = output_native_sr

                                try:
                                    self._passthrough_input_stream = sd.InputStream(
                                        device=input_device_index,
                                        samplerate=chosen_sr,
                                        channels=1,
                                        dtype='float32',
                                        blocksize=self._PASSTHROUGH_BLOCKSIZE,
                                        callback=input_callback
                                    )

                                    self._passthrough_output_stream = sd.OutputStream(
                                        device=output_device_index,
                                        samplerate=chosen_sr,
                                        channels=1,
                                        dtype='float32',
                                        blocksize=self._PASSTHROUGH_BLOCKSIZE,
                                        callback=output_callback
                                    )

                                    self._passthrough_input_stream.start()

                                    # Pre-fill queue with 2 silence chunks
                                    self._passthrough_queue.put(silence_chunk)
                                    self._passthrough_queue.put(silence_chunk)

                                    self._passthrough_output_stream.start()
                                    stream_opened = True

                                except sd.PortAudioError as e3:
                                    # Attempt 4: Use each device's native rate with resampling
                                    # This handles the case where input and output only support different rates
                                    if (input_native_sr is not None and output_native_sr is not None and
                                        input_native_sr != output_native_sr):
                                        logger.info("Retrying passthrough with native rates (input=%d, output=%d) and resampling",
                                                   input_native_sr, output_native_sr)
                                        cleanup_partial_streams()

                                        # Store sample rates for resampling in callbacks
                                        input_sr_for_resample = input_native_sr
                                        output_sr_for_resample = output_native_sr

                                        # Resampling input callback: captures at input native rate
                                        def resampling_input_callback(indata, frames, time, status):
                                            try:
                                                # Apply volume and copy data
                                                audio_chunk = indata.copy() * volume
                                                # Resample from input rate to output rate
                                                resampled = self._resample_high_quality(
                                                    audio_chunk.flatten(),
                                                    input_sr_for_resample,
                                                    output_sr_for_resample,
                                                    kaiser_beta=5.0
                                                )
                                                # Reshape to match expected output format
                                                resampled = resampled.reshape(-1, 1)
                                                # Put into queue, drop oldest if full
                                                if self._passthrough_queue.full():
                                                    try:
                                                        self._passthrough_queue.get_nowait()
                                                    except queue.Empty:
                                                        pass
                                                self._passthrough_queue.put(resampled)
                                            except Exception as e:
                                                logger.warning("Passthrough resampling input callback error: %s", e)

                                        # Resampling output callback: plays at output native rate
                                        def resampling_output_callback(outdata, frames, time, status):
                                            try:
                                                audio_chunk = self._passthrough_queue.get_nowait()
                                                # Flatten to 1-D if needed, then reshape to (frames, 1)
                                                flat = audio_chunk.flatten()
                                                chunk_len = min(len(flat), frames)
                                                outdata[:chunk_len, 0] = flat[:chunk_len]
                                                if chunk_len < frames:
                                                    outdata[chunk_len:] = 0
                                            except queue.Empty:
                                                # No data available, output silence
                                                outdata[:] = 0
                                            except Exception as e:
                                                logger.warning("Passthrough resampling output callback error: %s", e)
                                                outdata[:] = 0

                                        # Calculate appropriate blocksize for output based on resampling ratio
                                        ratio = output_sr_for_resample / input_sr_for_resample
                                        output_blocksize = int(self._PASSTHROUGH_BLOCKSIZE * ratio)

                                        self._passthrough_input_stream = sd.InputStream(
                                            device=input_device_index,
                                            samplerate=input_native_sr,
                                            channels=1,
                                            dtype='float32',
                                            blocksize=self._PASSTHROUGH_BLOCKSIZE,
                                            callback=resampling_input_callback
                                        )

                                        self._passthrough_output_stream = sd.OutputStream(
                                            device=output_device_index,
                                            samplerate=output_native_sr,
                                            channels=1,
                                            dtype='float32',
                                            blocksize=output_blocksize,
                                            callback=resampling_output_callback
                                        )

                                        self._passthrough_input_stream.start()

                                        # Pre-fill queue with silence chunks (at output rate)
                                        output_silence_chunk = np.zeros((output_blocksize, 1), dtype='float32')
                                        self._passthrough_queue.put(output_silence_chunk)
                                        self._passthrough_queue.put(output_silence_chunk)

                                        self._passthrough_output_stream.start()

                                        # Update chosen_sr for logging
                                        chosen_sr = f"{input_native_sr}->{output_native_sr}"
                                        stream_opened = True
                                    else:
                                        raise e3
                            else:
                                raise e2
                    else:
                        raise

                if stream_opened:
                    self._passthrough_active = True

                    logger.info("Microphone passthrough started (input=%s, output=%s, sample_rate=%s, volume=%.2f, blocksize=%d)",
                               input_device_index, output_device_index, chosen_sr, volume, self._PASSTHROUGH_BLOCKSIZE)
                    return (True, None)
                else:
                    return (False, "Failed to open audio streams")

            except sd.PortAudioError as e:
                logger.error("PortAudio error starting mic passthrough: %s", e)
                self.stop_mic_passthrough()
                return (False, str(e))
            except Exception as e:
                logger.error("Error starting mic passthrough: %s", e)
                self.stop_mic_passthrough()
                return (False, str(e))

    def _stop_mic_passthrough_unlocked(self):
        """
        Internal method to stop microphone passthrough without acquiring lock.

        This must only be called while holding _passthrough_lock to avoid race conditions.
        Used internally by start_mic_passthrough to restart with different devices.
        """
        self._passthrough_active = False

        # Stop and close duplex stream (same-device mode)
        if self._passthrough_duplex_stream is not None:
            try:
                self._passthrough_duplex_stream.stop()
                self._passthrough_duplex_stream.close()
            except Exception as e:
                logger.warning("Error closing passthrough duplex stream: %s", e)
            finally:
                self._passthrough_duplex_stream = None

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

    def stop_mic_passthrough(self):
        """Stop microphone passthrough and clean up resources."""
        self._stop_mic_passthrough_unlocked()
        logger.info("Microphone passthrough stopped")

    def is_mic_passthrough_active(self) -> bool:
        """
        Check if microphone passthrough is currently active.

        Returns:
            True if passthrough is active, False otherwise.
        """
        return self._passthrough_active
