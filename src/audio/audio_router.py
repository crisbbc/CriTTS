"""
Audio Router Module
Handles audio device enumeration and routing audio to specific output devices.
"""
import threading
import queue
import re
import sys
import inspect
from dataclasses import dataclass
import sounddevice as sd
from sounddevice import PortAudioError
import numpy as np
import io
import asyncio
import logging
from typing import Any, List, Dict, Optional, Tuple, cast
from scipy import signal
from math import ceil, gcd, sqrt

from .linux_sink import LinuxSinkManager, StreamOpenTicket

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


# Playback channels.  Each channel is cancelled independently, so stopping a
# settings-window voice preview never cuts off the main speech (and vice versa).
MAIN_CHANNEL = "main"
PREVIEW_CHANNEL = "preview"

# pyloudnorm's integrated loudness needs at least one 400 ms gating block.
_LUFS_MIN_SECONDS = 0.4


def _clarity_eq_sos(sample_rate: int) -> np.ndarray:
    """Second-order sections for the speech clarity EQ (see _apply_clarity_eq)."""
    sections = []

    # Stage 1: high-pass at 80 Hz
    hp_norm = 80.0 / (sample_rate / 2.0)
    if 0.0 < hp_norm < 1.0:
        sections.append(signal.butter(2, hp_norm, btype='high', output='sos'))

    # Stage 2: peaking EQ at 2500 Hz, +2.5 dB, Q=0.8
    f0 = 2500.0
    gain_db = 2.5
    Q = 0.8
    A = 10 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / sample_rate
    alpha = np.sin(w0) / (2.0 * Q)
    cos_w0 = np.cos(w0)
    b_peak = np.array([1.0 + alpha * A, -2.0 * cos_w0, 1.0 - alpha * A])
    a_peak = np.array([1.0 + alpha / A, -2.0 * cos_w0, 1.0 - alpha / A])
    sections.append(signal.tf2sos(b_peak, a_peak))

    return np.vstack(sections)


class _StreamingPlaybackProcessor:
    """Chunk-by-chunk counterpart of AudioRouter._process_playback_audio.

    Streaming audio arrives in ~40 ms chunks, so whole-signal processing does
    not work: per-chunk peak normalization boosts quiet tails and breaths to
    full scale, restarting the EQ filters on every chunk clicks at each chunk
    boundary, and LUFS cannot be measured on such short blocks at all.  This
    processor keeps the EQ filter state across chunks and normalizes with a
    single gain derived from the loudest peak so far (never raised again),
    whatever normalization type is configured.
    """

    _TARGET_PEAK = 0.891  # -1 dBFS, matching non-streaming Peak normalization
    _MAX_GAIN = 4.0
    _CLIP_LEVEL = 0.99

    def __init__(self, sample_rate: int, normalize: bool, enable_clarity_eq: bool):
        self._normalize = normalize
        self._running_peak = 0.0
        self._sos = _clarity_eq_sos(sample_rate) if enable_clarity_eq else None
        self._zi: Optional[np.ndarray] = None

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """Process one (frames, channels) chunk, carrying state to the next."""
        if chunk.size == 0:
            return chunk
        if self._sos is not None:
            if self._zi is None:
                self._zi = np.zeros((self._sos.shape[0], 2, chunk.shape[1]))
            filtered, self._zi = signal.sosfilt(self._sos, chunk, axis=0, zi=self._zi)
            chunk = cast(np.ndarray, filtered)
        if self._normalize:
            self._running_peak = max(self._running_peak, float(np.max(np.abs(chunk))))
            if self._running_peak > 1e-10:
                chunk = chunk * min(self._TARGET_PEAK / self._running_peak, self._MAX_GAIN)
        return np.clip(chunk, -self._CLIP_LEVEL, self._CLIP_LEVEL).astype(np.float32, copy=False)


class AudioRouter:
    """Manages audio device enumeration and playback routing."""

    MAIN_CHANNEL = MAIN_CHANNEL
    PREVIEW_CHANNEL = PREVIEW_CHANNEL

    # Blocksize for passthrough streams to ensure synchronized callbacks
    _PASSTHROUGH_BLOCKSIZE = 512

    # Host API suffix pattern for deduplication
    _HOST_API_PATTERN = re.compile(r'\s*\[(?:MME|DirectSound|WASAPI|WDM-KS|ASIO)\]\s*$', re.IGNORECASE)

    def __init__(self):
        """Initialize the audio router."""
        # Per-channel playback state.  A playback captures its channel's
        # generation when it starts; stop_playback() bumps the generation, so a
        # stop requested while audio is still being decoded is not lost.
        self._playback_lock = threading.Lock()
        self._playback_generation: Dict[str, int] = {}
        self._playback_streams: Dict[str, Any] = {}
        self._current_amplitude = 0.0
        self._cached_linux_audio_system: Optional[str] = None

        # Microphone passthrough state
        self._passthrough_input_stream: Optional[sd.InputStream] = None
        self._passthrough_output_stream: Optional[sd.OutputStream] = None
        self._passthrough_duplex_stream: Optional[sd.Stream] = None
        self._passthrough_queue: queue.Queue = queue.Queue()
        self._passthrough_active: bool = False
        # start_mic_passthrough() may need to stop a partially-created stream
        # while already holding this lock, so it must be re-entrant.
        self._passthrough_lock = threading.RLock()  # Protects passthrough state transitions

        # Linux PulseAudio sink routing (extracted into LinuxSinkManager;
        # the attributes below delegate to it for backward compatibility)
        self._linux_sink = LinuxSinkManager()

    @property
    def last_linux_sink_result(self) -> Optional[Tuple[bool, str]]:
        """Last startup auto-setup result, surfaced in the Audio Output tab."""
        return self._linux_sink.last_result

    @last_linux_sink_result.setter
    def last_linux_sink_result(self, value: Optional[Tuple[bool, str]]) -> None:
        self._linux_sink.last_result = value

    @staticmethod
    def _is_truncation_prefix(shorter: str, longer: str) -> bool:
        """Return True when *shorter* is a whitespace-boundary prefix of *longer*.

        Distinguishes a truncated name for the same device ("Speakers" →
        "Speakers (Realtek)") from a genuinely different device whose name only
        shares a prefix ("Speakers" vs "Speakers/Headphones").
        """
        if not longer.startswith(shorter):
            return False
        remainder = longer[len(shorter):]
        return not remainder or remainder[0].isspace()

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

            # Treat a device as a duplicate only when one name is a prefix of
            # the other at a whitespace boundary (a truncated version of the same
            # device).  A slash or other separator indicates a different device.
            for existing_lower in final_devices_lower:
                if (AudioRouter._is_truncation_prefix(name_lower, existing_lower)
                        or AudioRouter._is_truncation_prefix(existing_lower, name_lower)):
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
            # LUFS normalization for professional loudness standards.  Clips
            # shorter than one gating block cannot be measured (pyloudnorm
            # raises), so they fall back to Peak like a missing pyloudnorm.
            if pyln is None or len(data) <= _LUFS_MIN_SECONDS * sample_rate:
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
            data = self._stereo_enhancement(data, width=stereo_width, sample_rate=effective_sr)

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
        # (cast: scipy's stubs union a tuple return that never occurs here)
        resampled = cast(
            np.ndarray,
            signal.resample_poly(data, up, down, window=('kaiser', kaiser_beta)),
        )

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
        sos = _clarity_eq_sos(sample_rate)
        # cast: scipy stubs union an initial-conditions tuple return that does
        # not occur without the zi argument
        result = cast(np.ndarray, signal.sosfilt(sos, data, axis=0))

        # Soft-limit to prevent any post-EQ clipping
        peak = np.max(np.abs(result))
        if peak > 0.99:
            result = result * (0.99 / peak)
        return result

    def _stereo_enhancement(self, data: np.ndarray, width: float = 0.5, sample_rate: int = 48000) -> np.ndarray:
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
            delay_samples = max(1, sample_rate // 1000)  # 1ms delay at the actual rate
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
                raise RuntimeError("ffmpeg decode timeout - MP3 may be corrupted or too large") from None

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

        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg not found - please install ffmpeg for MP3 decoding support") from exc
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            logger.error("MP3 decode error: %s", e)
            raise RuntimeError(f"Failed to decode MP3: {str(e)}") from e


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
                raise RuntimeError(f"Audio decode failed - ffmpeg: {e}; soundfile: {sf_error}") from e

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

    def _playback_token(self, channel: str) -> int:
        """Return the channel's current generation (captured when playback starts)."""
        with self._playback_lock:
            return self._playback_generation.get(channel, 0)

    def _playback_cancelled(self, channel: str, token: int) -> bool:
        """True once stop_playback() has run for *channel* since *token* was taken."""
        return self._playback_generation.get(channel, 0) != token

    def _register_stream(self, channel: str, token: int, stream) -> bool:
        """Publish *stream* so stop_playback() can stop it; False if already cancelled."""
        with self._playback_lock:
            if self._playback_cancelled(channel, token):
                return False
            self._playback_streams[channel] = stream
            return True

    def _unregister_stream(self, channel: str, stream) -> None:
        """Forget *stream* unless a newer playback on the channel replaced it."""
        with self._playback_lock:
            if self._playback_streams.get(channel) is stream:
                del self._playback_streams[channel]

    async def _play_prepared_audio(
        self,
        prepared_audio: PreparedAudioPayload,
        device_index: Optional[int] = None,
        amplitude_callback=None,
        wait_interval: float = 0.1,
        skip_sink_routing: bool = False,
        *,
        channel: str = MAIN_CHANNEL,
        token: Optional[int] = None,
        stop_event=None,
    ) -> bool:
        """Play a previously prepared non-streaming payload.

        Returns False without playing if the channel was stopped (or
        *stop_event* set) after *token* was captured.
        """
        if token is None:
            token = self._playback_token(channel)

        def stopped() -> bool:
            return self._stream_stop_requested(stop_event, channel, token)

        if stopped():
            return False

        data = prepared_audio.data
        effective_sr = prepared_audio.sample_rate
        data_index = 0
        data_len = len(data)

        def report_amplitude(amp: float) -> None:
            self._current_amplitude = amp
            if amplitude_callback:
                try:
                    amplitude_callback(amp)
                except Exception:
                    logger.debug("Amplitude callback failed", exc_info=True)

        def callback(outdata, frames, time, status):
            nonlocal data_index
            if stopped():
                raise sd.CallbackStop()

            if data_index < data_len:
                chunksize = min(frames, data_len - data_index)
                outdata[:chunksize] = data[data_index:data_index + chunksize]
                if chunksize < frames:
                    outdata[chunksize:] = 0
                if amplitude_callback:
                    report_amplitude(self._calculate_chunk_amplitude(data[data_index:data_index + chunksize]))
                data_index += chunksize
            else:
                outdata[:] = 0
                report_amplitude(0.0)
                raise sd.CallbackStop()

        channels = data.shape[1] if len(data.shape) > 1 else 1

        # Linux: previews are not routed so the user hears the voice test
        # through their speakers; see LinuxSinkManager.begin_stream_open.
        ticket = await self._begin_stream_open(route=not skip_sink_routing, keep_on_default=skip_sink_routing)
        stream = None
        try:
            if stopped():
                return False
            stream = sd.OutputStream(
                device=device_index,
                samplerate=effective_sr,
                channels=channels,
                callback=callback,
                finished_callback=lambda: report_amplitude(0.0),
            )
            if not self._register_stream(channel, token, stream):
                return False

            with stream:
                ticket.opened()
                while stream.active and not stopped():
                    await asyncio.sleep(wait_interval)

            return not stopped()
        finally:
            ticket.close()
            if stream is not None:
                self._unregister_stream(channel, stream)
                try:
                    stream.close()
                except Exception:
                    logger.debug("Stream close failed during cleanup", exc_info=True)

    async def _play_audio_bytes(
        self,
        audio_data: bytes,
        device_index: Optional[int],
        enable_normalization: bool,
        normalization_type: str,
        processing_profile: str,
        enable_clarity_eq: bool,
        prepared_audio: Optional[PreparedAudioPayload],
        skip_sink_routing: bool,
        amplitude_callback,
        wait_interval: float,
        stop_event,
        channel: str,
    ) -> bool:
        """Shared body of play_audio_to_device / play_audio_with_amplitude."""
        # Capture the channel generation before decoding so a Stop pressed
        # while ffmpeg is still decoding cancels this playback.
        token = self._playback_token(channel)
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
                wait_interval=wait_interval,
                skip_sink_routing=skip_sink_routing,
                channel=channel,
                token=token,
                stop_event=stop_event,
            )
        except PortAudioError as e:
            logger.error("Audio device error during playback: %s", e)
            return False
        except Exception as e:
            logger.error("Audio playback error: %s", e)
            return False
        finally:
            self._current_amplitude = 0.0

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
        skip_sink_routing: bool = False,
        stop_event=None,
        channel: str = MAIN_CHANNEL,
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
            skip_sink_routing: If True, do not move the stream to the Linux sink
                               (useful for voice previews that should play through speakers).
            stop_event: Optional threading.Event that cancels this playback.
            channel: Playback channel; stop_playback(channel) only stops that channel.

        Returns:
            True if playback succeeded, False otherwise.
        """
        return await self._play_audio_bytes(
            audio_data,
            device_index,
            enable_normalization,
            normalization_type,
            processing_profile,
            enable_clarity_eq,
            prepared_audio,
            skip_sink_routing,
            amplitude_callback=None,
            wait_interval=0.1,
            stop_event=stop_event,
            channel=channel,
        )

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
        rms = sqrt(np.mean(chunk ** 2))

        # Normalize to 0.0-1.0 range (typical speech RMS is 0.1-0.3)
        normalized = min(1.0, rms * 3.0)

        return normalized

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
            # Decode at the native rate without resampling, EQ, or stereo
            # processing — duration is just frame count over sample rate.
            data, sample_rate = await self._decode_audio_data(audio_data, target_sample_rate=None)
            if sample_rate > 0 and data.size > 0:
                return data.shape[0] / sample_rate
            return 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _can_retry_with_native_rate(native_sr: Optional[int], chosen_sr: Optional[int]) -> bool:
        """True when a native-rate retry attempt differs from the failed rate."""
        return native_sr is not None and native_sr != chosen_sr

    @staticmethod
    def _can_resample_between_native_rates(input_sr: Optional[int], output_sr: Optional[int]) -> bool:
        """True when input and output only support different native rates."""
        return input_sr is not None and output_sr is not None and input_sr != output_sr


    @staticmethod
    def _start_stream(stream) -> None:
        """Start a sounddevice stream if construction succeeded.

        ``sd.*Stream`` constructors are typed as possibly returning None;
        starting a stream that failed to open would raise AttributeError.
        """
        if stream is not None:
            stream.start()

    def stop_playback(self, channel: Optional[str] = None):
        """Stop audio playback on *channel*, or on every channel when None.

        Also cancels playbacks of that channel that are still decoding and
        have not opened their output stream yet.
        """
        with self._playback_lock:
            if channel is None:
                channels = {MAIN_CHANNEL, PREVIEW_CHANNEL, *self._playback_generation, *self._playback_streams}
            else:
                channels = {channel}
            streams = []
            for ch in channels:
                self._playback_generation[ch] = self._playback_generation.get(ch, 0) + 1
                stream = self._playback_streams.get(ch)
                if stream is not None:
                    streams.append(stream)
        self._current_amplitude = 0.0
        for stream in streams:
            try:
                stream.stop()
            except Exception:
                logger.debug("Stream stop failed during cleanup", exc_info=True)

    def set_linux_sink_name(self, name: str) -> None:
        """Set the PulseAudio sink name to auto-route TTS audio to (Linux only)."""
        self._linux_sink.set_sink_name(name)

    @staticmethod
    def cleanup_linux_sink_modules() -> None:
        """Unload any PulseAudio/PipeWire modules created by CriTTS (idempotent).

        See :meth:`LinuxSinkManager.cleanup_modules` for details.
        """
        LinuxSinkManager.cleanup_modules()

    @staticmethod
    def ensure_linux_sink_modules(sink_name: str = "crittssink") -> tuple:
        """Idempotently create the CriTTS null sink + virtual mic (Linux only).

        See :meth:`LinuxSinkManager.ensure_modules` for details.
        """
        return LinuxSinkManager.ensure_modules(sink_name)

    async def _begin_stream_open(self, route: bool, keep_on_default: bool = False) -> StreamOpenTicket:
        """Run LinuxSinkManager.begin_stream_open off the event loop (it blocks on a lock and pactl)."""
        return await asyncio.to_thread(self._linux_sink.begin_stream_open, route, keep_on_default=keep_on_default)

    def is_playing(self) -> bool:
        """Check if audio is currently playing on any channel."""
        with self._playback_lock:
            streams = list(self._playback_streams.values())
        return any(stream.active for stream in streams)

    @property
    def is_linux(self) -> bool:
        """Return True if running on Linux."""
        return sys.platform.startswith("linux")

    @property
    def is_windows(self) -> bool:
        """Return True if running on Windows."""
        return sys.platform == "win32"

    @property
    def is_macos(self) -> bool:
        """Return True if running on macOS."""
        return sys.platform == "darwin"

    def detect_linux_audio_system(self) -> str:
        """Delegate to LinuxSinkManager to avoid duplicate detection / caches."""
        result = self._linux_sink.detect_audio_system()
        self._cached_linux_audio_system = result
        return result

    def is_vbcable_installed(self) -> bool:
        """
        Check if a virtual audio device is available for TTS routing.

        On Windows this looks for VB-Cable or similar virtual audio cables.
        On Linux this checks for PulseAudio null sinks / PipeWire virtual devices
        and always returns True when at least one output device exists (users can
        create virtual sinks on demand).  On macOS this simply checks whether any
        output device is present.

        Returns:
            True if a suitable audio-routing device is found, False otherwise.
        """
        devices = self.get_audio_devices()

        if self.is_windows:
            # Keywords that identify VB-Cable and similar virtual audio devices
            vbcable_keywords = ["cable", "vb-audio", "vbaudio", "vb cable"]
            for device in devices:
                device_name_lower = device['name'].lower()
                if any(keyword in device_name_lower for keyword in vbcable_keywords):
                    return True
            return False

        # Linux / macOS: virtual routing works differently.
        # On Linux users can create null sinks with pactl/pw-cli.
        # On macOS users can use BlackHole / Loopback.
        # Consider it "installed" if any output device exists.
        return len(devices) > 0

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
        skip_sink_routing: bool = False,
        stop_event=None,
        channel: str = MAIN_CHANNEL,
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
            skip_sink_routing: If True, do not move the stream to the Linux sink.
            stop_event: Optional threading.Event that cancels this playback.
            channel: Playback channel; stop_playback(channel) only stops that channel.

        Returns:
            True if playback succeeded, False otherwise.
        """
        return await self._play_audio_bytes(
            audio_data,
            device_index,
            enable_normalization,
            normalization_type,
            processing_profile,
            enable_clarity_eq,
            prepared_audio,
            skip_sink_routing,
            amplitude_callback=amplitude_callback,
            wait_interval=0.05,
            stop_event=stop_event,
            channel=channel,
        )

    def _stream_stop_requested(self, stop_event=None, channel: str = MAIN_CHANNEL, token: Optional[int] = None) -> bool:
        """Return whether playback was stopped via its channel or *stop_event*."""
        if token is not None and self._playback_cancelled(channel, token):
            return True
        return bool(stop_event is not None and stop_event.is_set())

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
        channel: str = MAIN_CHANNEL,
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
            channel: Playback channel; stop_playback(channel) only stops that channel.

        Normalization in streaming mode always uses a running peak (see
        _StreamingPlaybackProcessor); *normalization_type* only selects
        whether it is on ("None" turns it off).

        Returns:
            True if playback succeeded, False otherwise.
        """
        import queue
        import threading as th

        process = None
        stream_tasks = []
        ticket = None
        stream = None
        token = self._playback_token(channel)

        def stopped() -> bool:
            return self._stream_stop_requested(stop_event, channel, token)

        try:
            # Get profile settings
            profile_settings = self._get_profile_settings(processing_profile)
            target_sr = profile_settings["sample_rate"]  # None for fast_preview means no resampling
            normalize = enable_normalization and normalization_type != "None"

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
                        if stopped():
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
                            logger.debug("Decoder stdin close failed", exc_info=True)

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
                    logger.debug("MP3 decode chunk processing failed", exc_info=True)

            async def enqueue_audio(item) -> bool:
                """Queue decoded audio without blocking the event loop or dropping data."""
                while not stopped():
                    try:
                        audio_queue.put_nowait(item)
                        return True
                    except queue.Full:
                        await asyncio.sleep(0.01)
                return False

            async def enqueue_terminal_marker() -> None:
                """Signal playback completion after every queued audio chunk."""
                await enqueue_audio(None)

            processor: List[Optional[_StreamingPlaybackProcessor]] = [None]

            def process_chunk(chunk: np.ndarray) -> np.ndarray:
                """Run the stateful streaming pipeline (created on the first chunk)."""
                if processor[0] is None:
                    effective_sr = target_sr if target_sr is not None else (detected_sr[0] or sample_rate)
                    processor[0] = _StreamingPlaybackProcessor(effective_sr, normalize, enable_clarity_eq)
                return processor[0].process(chunk)

            async def read_stdout():
                """Read decoded PCM from ffmpeg stdout and enqueue for playback."""
                if not process.stdout:
                    decode_error[0] = RuntimeError("ffmpeg stdout unavailable")
                    await enqueue_terminal_marker()
                    return

                buffer = bytearray()
                frame_bytes = 8  # stereo float32
                frames_per_chunk = 2048
                min_bytes = frame_bytes * frames_per_chunk

                try:
                    while True:
                        if stopped():
                            break

                        data = await process.stdout.read(4096)
                        if not data:
                            break
                        buffer.extend(data)

                        while len(buffer) >= min_bytes:
                            chunk_bytes = buffer[:min_bytes]
                            del buffer[:min_bytes]

                            chunk = process_chunk(np.frombuffer(chunk_bytes, dtype=np.float32).reshape(-1, 2))

                            if not await enqueue_audio(chunk):
                                return

                            if not playback_started.is_set():
                                playback_started.set()

                    # Flush remaining buffer
                    if buffer:
                        usable = (len(buffer) // frame_bytes) * frame_bytes
                        if usable > 0:
                            chunk_bytes = buffer[:usable]
                            chunk = process_chunk(np.frombuffer(chunk_bytes, dtype=np.float32).reshape(-1, 2))
                            if not await enqueue_audio(chunk):
                                return
                            if not playback_started.is_set():
                                playback_started.set()

                except Exception as e:
                    decode_error[0] = e
                finally:
                    await enqueue_terminal_marker()
                    # Wake the startup wait even when no audio was decoded
                    # (provider error, empty input) instead of timing out.
                    playback_started.set()

            # Closure variable to hold leftover samples between callbacks
            leftover = [None]

            def audio_callback(outdata, frames, time, status):
                """Sounddevice callback for streaming playback."""
                if stopped():
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
                                    logger.debug("Amplitude reset callback failed", exc_info=True)
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
                            logger.debug("Amplitude callback failed", exc_info=True)
                else:
                    outdata[:len(chunk)] = chunk
                    outdata[len(chunk):] = 0
                    if amplitude_callback:
                        amp = self._calculate_chunk_amplitude(chunk)
                        self._current_amplitude = amp
                        try:
                            amplitude_callback(amp)
                        except Exception:
                            logger.debug("Amplitude callback failed", exc_info=True)

            feed_task = asyncio.create_task(feed_stdin())
            stderr_task = asyncio.create_task(read_stderr())
            stdout_task = asyncio.create_task(read_stdout())
            stream_tasks = [feed_task, stderr_task, stdout_task]

            try:
                await asyncio.wait_for(playback_started.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("Streaming playback: no audio received within 5 seconds")
                return False

            if decode_error[0]:
                logger.error("Streaming playback failed: %s", decode_error[0])
                return False
            if stopped():
                return False

            if target_sr is not None:
                output_sr = target_sr
            elif detected_sr[0] is not None:
                output_sr = detected_sr[0]
            else:
                logger.warning(
                    "Could not detect the decoded sample rate; assuming %d Hz",
                    sample_rate,
                )
                output_sr = sample_rate

            # Linux: route the stream to the configured sink once it has started.
            ticket = await self._begin_stream_open(route=True)
            if stopped():
                return False

            stream = sd.OutputStream(
                device=device_index,
                samplerate=output_sr,
                channels=2,
                callback=audio_callback,
                finished_callback=lambda: playback_finished.set()
            )
            if not self._register_stream(channel, token, stream):
                return False

            with stream:
                ticket.opened()
                while stream.active and not stopped():
                    await asyncio.sleep(0.05)

            try:
                await asyncio.wait_for(stdout_task, timeout=1.0)
            except asyncio.TimeoutError:
                return False

            if decode_error[0] is not None:
                logger.error("Streaming playback failed: %s", decode_error[0])
            return decode_error[0] is None and not stopped()

        except PortAudioError as e:
            logger.error("Audio device error during streaming playback: %s", e)
            return False
        except Exception as e:
            logger.error("Streaming playback error: %s", e)
            return False
        finally:
            # Every exit path (including startup timeout and decoder errors) must
            # cancel and await all reader/writer tasks before closing the loop.
            pending_tasks = [task for task in stream_tasks if not task.done()]
            for task in pending_tasks:
                task.cancel()
            if stream_tasks:
                await asyncio.gather(*stream_tasks, return_exceptions=True)

            if process is not None:
                try:
                    if process.stdin:
                        process.stdin.close()
                        wait_closed: Any = getattr(process.stdin, "wait_closed", None)
                        if callable(wait_closed):
                            close_result = wait_closed()
                            if inspect.isawaitable(close_result):
                                await close_result
                except Exception:
                    logger.debug("Closing decoder stdin/wait handle failed", exc_info=True)
                try:
                    if process.returncode is None:
                        process.kill()
                except Exception:
                    logger.debug("Killing decoder process failed", exc_info=True)
                try:
                    await process.wait()
                except Exception:
                    logger.debug("Waiting for decoder process exit failed", exc_info=True)
            if ticket is not None:
                ticket.close()
            if stream is not None:
                self._unregister_stream(channel, stream)
                try:
                    stream.close()
                except Exception:
                    logger.debug("Stream close failed during cleanup", exc_info=True)

    def start_mic_passthrough(
        self,
        input_device_index: Optional[int],
        output_device_index: Optional[int],
        volume: float = 1.0,
        sample_rate: int = 48000,
    ) -> Tuple[bool, Optional[str]]:
        """Start continuous microphone passthrough to an output device."""
        # Passthrough is never routed, but its stream must not appear inside a
        # routed TTS stream's open window (LinuxSinkManager.begin_stream_open).
        ticket = self._linux_sink.begin_stream_open(route=False)
        ok, error = self._start_mic_passthrough(input_device_index, output_device_index, volume, sample_rate)
        if ok:
            ticket.opened()
        else:
            ticket.close()
        return ok, error

    def _start_mic_passthrough(
        self,
        input_device_index: Optional[int],
        output_device_index: Optional[int],
        volume: float = 1.0,
        sample_rate: int = 48000,
    ) -> Tuple[bool, Optional[str]]:
        """Start continuous microphone passthrough to an output device."""
        with self._passthrough_lock:
            self._stop_mic_passthrough_unlocked()

            try:
                input_native_sr = None
                output_native_sr = None

                if input_device_index is not None:
                    try:
                        input_device_info = sd.query_devices(input_device_index)
                        input_native_sr = int(input_device_info.get("default_samplerate", sample_rate))
                    except Exception as e:
                        logger.warning("Could not query input device sample rate: %s", e)

                if output_device_index is not None:
                    try:
                        output_device_info = sd.query_devices(output_device_index)
                        output_native_sr = int(output_device_info.get("default_samplerate", sample_rate))
                    except Exception as e:
                        logger.warning("Could not query output device sample rate: %s", e)

                candidate_rates = list(
                    dict.fromkeys(
                        rate
                        for rate in (sample_rate, input_native_sr, output_native_sr)
                        if rate is not None
                    )
                )

                if input_device_index == output_device_index:
                    def duplex_callback(indata, outdata, frames, time, status):
                        try:
                            outdata[:] = indata * volume
                        except Exception as e:
                            logger.warning("Passthrough duplex callback error: %s", e)
                            outdata[:] = 0

                    last_error = None
                    for chosen_sr in candidate_rates:
                        try:
                            self._passthrough_duplex_stream = sd.Stream(
                                device=input_device_index,
                                samplerate=chosen_sr,
                                channels=1,
                                dtype="float32",
                                blocksize=self._PASSTHROUGH_BLOCKSIZE,
                                callback=duplex_callback,
                            )
                            self._start_stream(self._passthrough_duplex_stream)
                            break
                        except PortAudioError as e:
                            last_error = e
                            self._stop_mic_passthrough_unlocked()
                    else:
                        raise last_error or RuntimeError("No usable passthrough sample rate")

                    self._passthrough_active = True
                    logger.info(
                        "Microphone passthrough started (duplex mode, device=%s, sample_rate=%d, volume=%.2f)",
                        input_device_index,
                        chosen_sr,
                        volume,
                    )
                    return True, None

                self._passthrough_queue = queue.Queue(maxsize=10)

                def queue_chunk(audio_chunk):
                    if self._passthrough_queue.full():
                        try:
                            self._passthrough_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self._passthrough_queue.put_nowait(audio_chunk)

                def input_callback(indata, frames, time, status):
                    try:
                        queue_chunk(indata.copy() * volume)
                    except Exception as e:
                        logger.warning("Passthrough input callback error: %s", e)

                def output_callback(outdata, frames, time, status):
                    try:
                        audio_chunk = self._passthrough_queue.get_nowait()
                        flat = audio_chunk.flatten()
                        chunk_len = min(len(flat), frames)
                        outdata[:chunk_len, 0] = flat[:chunk_len]
                        if chunk_len < frames:
                            outdata[chunk_len:] = 0
                    except queue.Empty:
                        outdata[:] = 0
                    except Exception as e:
                        logger.warning("Passthrough output callback error: %s", e)
                        outdata[:] = 0

                def open_stream_pair(
                    input_rate,
                    output_rate,
                    input_stream_callback,
                    output_blocksize=self._PASSTHROUGH_BLOCKSIZE,
                ):
                    self._passthrough_queue = queue.Queue(maxsize=10)
                    self._passthrough_input_stream = sd.InputStream(
                        device=input_device_index,
                        samplerate=input_rate,
                        channels=1,
                        dtype="float32",
                        blocksize=self._PASSTHROUGH_BLOCKSIZE,
                        callback=input_stream_callback,
                    )
                    self._passthrough_output_stream = sd.OutputStream(
                        device=output_device_index,
                        samplerate=output_rate,
                        channels=1,
                        dtype="float32",
                        blocksize=output_blocksize,
                        callback=output_callback,
                    )
                    self._start_stream(self._passthrough_input_stream)
                    silence = np.zeros((output_blocksize, 1), dtype="float32")
                    self._passthrough_queue.put(silence)
                    self._passthrough_queue.put(silence)
                    self._start_stream(self._passthrough_output_stream)

                last_error = None
                chosen_sr = sample_rate
                for candidate_sr in candidate_rates:
                    try:
                        open_stream_pair(candidate_sr, candidate_sr, input_callback)
                        chosen_sr = candidate_sr
                        break
                    except PortAudioError as e:
                        last_error = e
                        logger.debug("Passthrough open failed at %d Hz", candidate_sr)
                        self._stop_mic_passthrough_unlocked()
                else:
                    if not self._can_resample_between_native_rates(input_native_sr, output_native_sr):
                        raise last_error or RuntimeError("No usable passthrough sample rate")
                    if input_native_sr is None or output_native_sr is None:
                        raise RuntimeError("Native sample rates unavailable for resampling")

                    logger.info(
                        "Retrying passthrough with native rates (input=%d, output=%d) and resampling",
                        input_native_sr,
                        output_native_sr,
                    )

                    def resampling_input_callback(indata, frames, time, status):
                        try:
                            resampled = self._resample_high_quality(
                                (indata.copy() * volume).flatten(),
                                input_native_sr,
                                output_native_sr,
                                kaiser_beta=5.0,
                            )
                            queue_chunk(resampled.reshape(-1, 1))
                        except Exception as e:
                            logger.warning("Passthrough resampling input callback error: %s", e)

                    # ponytail: ceil prevents a one-frame underrun for ratios such as 48k/44.1k.
                    output_blocksize = ceil(
                        self._PASSTHROUGH_BLOCKSIZE * output_native_sr / input_native_sr
                    )
                    open_stream_pair(
                        input_native_sr,
                        output_native_sr,
                        resampling_input_callback,
                        output_blocksize,
                    )
                    chosen_sr = f"{input_native_sr}->{output_native_sr}"

                self._passthrough_active = True
                logger.info(
                    "Microphone passthrough started (input=%s, output=%s, sample_rate=%s, volume=%.2f, blocksize=%d)",
                    input_device_index,
                    output_device_index,
                    chosen_sr,
                    volume,
                    self._PASSTHROUGH_BLOCKSIZE,
                )
                return True, None

            except PortAudioError as e:
                logger.error("PortAudio error starting mic passthrough: %s", e)
                self._stop_mic_passthrough_unlocked()
                return False, str(e)
            except Exception as e:
                logger.error("Error starting mic passthrough: %s", e)
                self._stop_mic_passthrough_unlocked()
                return False, str(e)

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
        with self._passthrough_lock:
            self._stop_mic_passthrough_unlocked()
        logger.info("Microphone passthrough stopped")

    def is_mic_passthrough_active(self) -> bool:
        """
        Check if microphone passthrough is currently active.

        Returns:
            True if passthrough is active, False otherwise.
        """
        return self._passthrough_active
