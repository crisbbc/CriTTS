import asyncio
import threading
import time
from unittest.mock import AsyncMock

import numpy as np
import pytest

import src.audio.audio_router as audio_router_module
from src.audio.audio_router import AudioRouter
from src.tts.tts_engine import TTSEngine


class _NoopTicket:
    def opened(self) -> None:
        pass

    def close(self) -> None:
        pass


class _Reader:
    def __init__(self, data: bytes):
        self.data = data

    async def read(self, size: int) -> bytes:
        await asyncio.sleep(0)
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


class _Stdin:
    def write(self, _data: bytes) -> None:
        pass

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


class _LateReader(_Reader):
    """Releases its data only after *delay* seconds (ffmpeg stderr lagging stdout)."""

    def __init__(self, data: bytes, delay: float):
        super().__init__(data)
        self.delay = delay

    async def read(self, size: int) -> bytes:
        await asyncio.sleep(self.delay)
        self.delay = 0
        return await super().read(size)


class _Process:
    def __init__(self, pcm: bytes, stderr: bytes = b"48000 Hz", stderr_delay: float = 0.0):
        self.stdin = _Stdin()
        self.stdout = _Reader(pcm)
        self.stderr = _LateReader(stderr, stderr_delay)
        self.returncode = None

    def kill(self) -> None:
        self.returncode = 0

    async def wait(self) -> int:
        self.returncode = 0
        return 0


class _OutputStream:
    played_frames = 0

    def __init__(self, *, callback, finished_callback, **_kwargs):
        self.callback = callback
        self.finished_callback = finished_callback
        self.active = False
        self._thread = None

    def __enter__(self):
        self.active = True

        def play():
            while self.active:
                out = np.zeros((512, 2), dtype=np.float32)
                try:
                    self.callback(out, 512, None, None)
                except audio_router_module.sd.CallbackStop:
                    self.active = False
                    self.finished_callback()
                    return
                type(self).played_frames += int(np.count_nonzero(np.any(out != 0, axis=1)))
                time.sleep(0.0001)

        self._thread = threading.Thread(target=play)
        self._thread.start()
        return self

    def __exit__(self, *_args):
        if self._thread:
            self._thread.join(timeout=1)

    def close(self):
        self.active = False
        if self._thread:
            self._thread.join(timeout=1)


async def _one_chunk_then(error=None):
    yield b"encoded"
    if error:
        raise error


@pytest.mark.asyncio
async def test_streaming_drains_every_decoded_frame(monkeypatch):
    expected_frames = 2048 * 8 + 333
    process = _Process(np.ones((expected_frames, 2), dtype=np.float32).tobytes())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    monkeypatch.setattr(audio_router_module.sd, "OutputStream", _OutputStream)

    router = AudioRouter()
    monkeypatch.setattr(router, "_process_playback_audio", lambda data, sample_rate, *_args: (data, sample_rate))
    monkeypatch.setattr(router, "_begin_stream_open", AsyncMock(return_value=_NoopTicket()))
    _OutputStream.played_frames = 0

    assert await router.play_audio_streaming(_one_chunk_then())
    assert _OutputStream.played_frames == expected_frames


@pytest.mark.asyncio
async def test_streaming_reports_errors_after_playback_starts(monkeypatch):
    process = _Process(np.ones((4096, 2), dtype=np.float32).tobytes())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    monkeypatch.setattr(audio_router_module.sd, "OutputStream", _OutputStream)

    router = AudioRouter()
    monkeypatch.setattr(router, "_process_playback_audio", lambda data, sample_rate, *_args: (data, sample_rate))
    monkeypatch.setattr(router, "_begin_stream_open", AsyncMock(return_value=_NoopTicket()))

    assert not await router.play_audio_streaming(_one_chunk_then(RuntimeError("network failed")))


@pytest.mark.asyncio
async def test_streaming_does_not_retry_after_emitting_audio(monkeypatch):
    class Provider:
        calls = 0

        async def stream_speech(self, *_args):
            self.calls += 1
            yield b"prefix"
            raise ConnectionError("reset")

    engine = object.__new__(TTSEngine)
    provider = Provider()
    engine._phrase_tracker = None
    engine._get_active_provider_name = lambda: "edge"
    engine._get_provider_by_name = lambda _name: provider
    engine._get_settings = lambda: type("Settings", (), {"get": lambda self, _key, default=None: default})()
    engine.validate_voice = AsyncMock(return_value=True)
    engine.preprocess_text = AsyncMock(return_value="hello")

    chunks = []
    with pytest.raises(ConnectionError):
        async for chunk in engine.stream_speech("hello", max_retries=2):
            chunks.append(chunk)

    assert chunks == [b"prefix"]
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_streaming_eq_uses_detected_rate_even_when_stderr_lags(monkeypatch):
    # fast_preview does not resample, so the rate comes from ffmpeg's stderr,
    # which here arrives after the first PCM chunk.
    process = _Process(np.ones((4096, 2), dtype=np.float32).tobytes(), stderr=b"24000 Hz", stderr_delay=0.05)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    monkeypatch.setattr(audio_router_module.sd, "OutputStream", _OutputStream)
    rates = []
    real_processor = audio_router_module._StreamingPlaybackProcessor

    def recording_processor(sample_rate, *args):
        rates.append(sample_rate)
        return real_processor(sample_rate, *args)

    monkeypatch.setattr(audio_router_module, "_StreamingPlaybackProcessor", recording_processor)
    router = AudioRouter()
    monkeypatch.setattr(router, "_begin_stream_open", AsyncMock(return_value=_NoopTicket()))

    assert await router.play_audio_streaming(_one_chunk_then(), processing_profile="fast_preview")
    assert rates == [24000]
