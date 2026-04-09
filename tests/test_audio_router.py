import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import numpy as np
import sys

# Mock sounddevice to avoid PortAudio dependency in tests
sys.modules['sounddevice'] = MagicMock()

from src.audio.audio_router import AudioRouter
from src.audio.audio_router import PreparedAudioPayload

@pytest.fixture
def audio_router():
    return AudioRouter()

@pytest.mark.asyncio
async def test_decode_mp3_audio_valid_sample_rate(audio_router):
    with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
        # Mock the process returned by create_subprocess_exec
        mock_process = MagicMock()
        mock_process.returncode = 0

        # We need realistic stdout so np.frombuffer doesn't fail.
        # 10 samples of float32 stereo (2 channels * 4 bytes) = 80 bytes
        mock_stdout = np.zeros((10, 2), dtype=np.float32).tobytes()
        mock_stderr = b"Stream #0:0: Audio: mp3, 44100 Hz, stereo"

        # mock_process.communicate returns a tuple (stdout, stderr)
        mock_process.communicate = AsyncMock(return_value=(mock_stdout, mock_stderr))
        mock_exec.return_value = mock_process

        # Valid sample rate
        audio_data, sr = await audio_router._decode_mp3_audio(b"dummy_mp3_data", target_sample_rate=48000)

        # Verify it cast the integer and built the command
        expected_cmd_args = [
            'ffmpeg',
            '-i', 'pipe:0',
            '-f', 'f32le',
            '-acodec', 'pcm_f32le',
            '-ar', '48000',
            '-ac', '2',
            '-'
        ]
        mock_exec.assert_called_once_with(
            *expected_cmd_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        assert sr == 48000
        assert audio_data.shape == (10, 2)

@pytest.mark.asyncio
async def test_decode_mp3_audio_invalid_sample_rate_injection(audio_router):
    # If a malicious string is provided, it should raise a RuntimeError
    # (since the original exception is wrapped in a RuntimeError by the exception handler)
    with pytest.raises(RuntimeError) as exc_info:
        await audio_router._decode_mp3_audio(b"dummy", target_sample_rate="48000; rm -rf /")
    assert "invalid literal for int()" in str(exc_info.value)

@pytest.mark.asyncio
async def test_decode_mp3_audio_no_target_sample_rate(audio_router):
    with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_stdout = np.zeros((5, 2), dtype=np.float32).tobytes()
        mock_stderr = b"Stream #0:0: Audio: mp3, 44100 Hz, stereo"
        mock_process.communicate = AsyncMock(return_value=(mock_stdout, mock_stderr))
        mock_exec.return_value = mock_process

        # None sample rate should detect rate from stderr
        audio_data, sr = await audio_router._decode_mp3_audio(b"dummy_mp3_data", target_sample_rate=None)

        expected_cmd_args = [
            'ffmpeg',
            '-i', 'pipe:0',
            '-f', 'f32le',
            '-acodec', 'pcm_f32le',
            '-ac', '2',
            '-'
        ]
        mock_exec.assert_called_once_with(
            *expected_cmd_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        assert sr == 44100
        assert audio_data.shape == (5, 2)


def test_processing_profiles_use_speech_friendly_stereo_width(audio_router):
    balanced = audio_router._get_profile_settings("balanced")
    high_quality = audio_router._get_profile_settings("high_quality")

    assert balanced["stereo_width"] <= 0.15
    assert high_quality["stereo_width"] <= 0.25


@pytest.mark.asyncio
async def test_prepare_audio_for_playback_builds_reusable_payload(audio_router):
    decoded_audio = np.arange(12, dtype=np.float32)
    processed_audio = np.zeros((6, 2), dtype=np.float32)

    audio_router._decode_audio_data = AsyncMock(return_value=(decoded_audio, 24000))
    audio_router._process_playback_audio = MagicMock(return_value=(processed_audio, 48000))

    prepared = await audio_router.prepare_audio_for_playback(
        b"segment-bytes",
        enable_normalization=True,
        normalization_type="RMS",
        processing_profile="balanced",
        enable_clarity_eq=False,
    )

    audio_router._decode_audio_data.assert_awaited_once_with(b"segment-bytes", 48000)
    audio_router._process_playback_audio.assert_called_once_with(
        decoded_audio,
        24000,
        48000,
        5.0,
        "RMS",
        False,
        0.15,
    )
    assert prepared.sample_rate == 48000
    assert prepared.data is processed_audio
    assert prepared.duration_seconds == pytest.approx(6 / 48000)


@pytest.mark.asyncio
async def test_play_audio_with_amplitude_reuses_prepared_payload_without_decoding(audio_router):
    prepared = PreparedAudioPayload(
        data=np.zeros((8, 2), dtype=np.float32),
        sample_rate=48000,
    )
    audio_router._decode_audio_data = AsyncMock(side_effect=AssertionError("decode should not run"))

    class _FakeOutputStream:
        def __init__(self, **kwargs):
            self.active = False
            self.finished_callback = kwargs.get("finished_callback")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            if self.finished_callback:
                self.finished_callback()

        def close(self):
            pass

    with patch("src.audio.audio_router.sd.OutputStream", side_effect=lambda **kwargs: _FakeOutputStream(**kwargs)):
        result = await audio_router.play_audio_with_amplitude(
            b"ignored",
            amplitude_callback=lambda amplitude: None,
            prepared_audio=prepared,
        )

    assert result is True
