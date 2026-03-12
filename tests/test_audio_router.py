import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import numpy as np
import sys

# Mock sounddevice to avoid PortAudio dependency in tests
sys.modules['sounddevice'] = MagicMock()

from src.audio.audio_router import AudioRouter

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
