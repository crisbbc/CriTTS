"""Regressions for the codebase-review fixes (playback cancellation, streaming
processing, LUFS on short clips, and voice validation while offline)."""

import asyncio
import shutil
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.audio.audio_router import (
    MAIN_CHANNEL,
    PREVIEW_CHANNEL,
    AudioRouter,
    PreparedAudioPayload,
    _StreamingPlaybackProcessor,
)
from src.config.settings_manager import SettingsManager
from src.tts.tts_engine import TTSEngine


def _prepared(seconds: float = 0.1, sample_rate: int = 48000) -> PreparedAudioPayload:
    return PreparedAudioPayload(data=np.zeros((int(seconds * sample_rate), 2), dtype=np.float32), sample_rate=sample_rate)


@pytest.mark.asyncio
async def test_stop_during_decode_cancels_playback():
    router = AudioRouter()

    async def decode_then_user_presses_stop(*_args, **_kwargs):
        router.stop_playback()
        return _prepared()

    with patch.object(router, "prepare_audio_for_playback", side_effect=decode_then_user_presses_stop), \
            patch("src.audio.audio_router.sd.OutputStream") as output_stream:
        result = await router.play_audio_to_device(b"audio")

    assert result is False
    output_stream.assert_not_called()


@pytest.mark.asyncio
async def test_stop_event_set_before_playback_skips_stream():
    router = AudioRouter()
    stop_event = MagicMock()
    stop_event.is_set.return_value = True

    with patch("src.audio.audio_router.sd.OutputStream") as output_stream:
        result = await router.play_audio_to_device(b"", prepared_audio=_prepared(), stop_event=stop_event)

    assert result is False
    output_stream.assert_not_called()


def test_preview_stop_does_not_cancel_main_channel():
    router = AudioRouter()
    main_token = router._playback_token(MAIN_CHANNEL)
    preview_token = router._playback_token(PREVIEW_CHANNEL)

    router.stop_playback(channel=PREVIEW_CHANNEL)

    assert router._stream_stop_requested(None, MAIN_CHANNEL, main_token) is False
    assert router._stream_stop_requested(None, PREVIEW_CHANNEL, preview_token) is True

    router.stop_playback()
    assert router._stream_stop_requested(None, MAIN_CHANNEL, main_token) is True


def test_streaming_processor_does_not_boost_quiet_tail():
    processor = _StreamingPlaybackProcessor(48000, normalize=True, enable_clarity_eq=False)
    loud = np.full((2048, 2), 0.5, dtype=np.float32)
    quiet = np.full((2048, 2), 0.001, dtype=np.float32)

    processor.process(loud)
    tail = processor.process(quiet)

    # Same gain as the loud part (0.891 / 0.5), not re-normalized to -1 dBFS.
    assert np.max(np.abs(tail)) == pytest.approx(0.001 * 0.891 / 0.5, rel=1e-3)


def test_streaming_processor_eq_is_continuous_across_chunks():
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal((8192, 2)) * 0.1).astype(np.float32)

    whole = _StreamingPlaybackProcessor(48000, normalize=False, enable_clarity_eq=True).process(audio)
    chunked_processor = _StreamingPlaybackProcessor(48000, normalize=False, enable_clarity_eq=True)
    chunked = np.concatenate([chunked_processor.process(audio[i:i + 2048]) for i in range(0, 8192, 2048)])

    np.testing.assert_allclose(chunked, whole, atol=1e-5)


def test_lufs_on_short_clip_falls_back_to_peak():
    router = AudioRouter()
    short = np.full(2048, 0.1, dtype=np.float32)

    result = router._normalize_audio(short, "LUFS", sample_rate=48000)

    assert np.max(np.abs(result)) == pytest.approx(0.891, rel=1e-3)


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
async def test_streaming_fails_fast_when_provider_errors_before_audio():
    router = AudioRouter()

    async def failing_generator():
        raise ValueError("voice not available")
        yield b""  # pragma: no cover - makes this an async generator

    started = time.monotonic()
    result = await router.play_audio_streaming(failing_generator())

    assert result is False
    assert time.monotonic() - started < 3.0


def _engine(tmp_path) -> TTSEngine:
    settings = SettingsManager(config_path=tmp_path / "config.json")
    settings.set("audio_cache_enabled", False)
    return TTSEngine(settings_manager=settings)


def test_offline_start_does_not_poison_voice_validation(tmp_path):
    engine = _engine(tmp_path)
    online = {"value": False}

    async def voices():
        return [{"short_name": "en-US-AriaNeural", "name": "Aria"}] if online["value"] else []

    async def generate(*_args, **_kwargs):
        return b"audio"

    engine._edge_tts_provider.get_available_voices = voices
    engine._edge_tts_provider.generate_speech = generate
    try:
        audio, error = asyncio.run(engine.generate_speech("hello there", "en-US-AriaNeural", use_cache=False))
        assert audio is None
        assert error is not None and "Could not load the voice list" in error

        online["value"] = True
        audio, error = asyncio.run(engine.generate_speech("hello there", "en-US-AriaNeural", use_cache=False))
        assert (audio, error) == (b"audio", None)
    finally:
        engine.shutdown()


def test_stream_speech_falls_back_to_provider_default_voice(tmp_path):
    engine = _engine(tmp_path)

    async def voices():
        return [{"short_name": "en-US-AriaNeural", "name": "Aria"}]

    used_voices = []

    async def stream(_text, voice, *_args, **_kwargs):
        used_voices.append(voice)
        yield b"chunk"

    engine._edge_tts_provider.get_available_voices = voices
    engine._edge_tts_provider.stream_speech = stream

    async def collect():
        return [chunk async for chunk in engine.stream_speech("hello there", "xx-XX-MissingNeural")]

    try:
        assert asyncio.run(collect()) == [b"chunk"]
        assert used_voices == ["en-US-AriaNeural"]
    finally:
        engine.shutdown()


def _fake_pactl(monkeypatch, listings):
    """Patch linux_sink so `pactl list` returns *listings* in turn (None = failure).

    Threads run inline, so a ticket's routing finishes inside opened().
    Returns the list of recorded move-sink-input commands.
    """
    import os
    import subprocess

    from src.audio import linux_sink

    pid = os.getpid()
    listings = iter(listings)
    moves = []

    def fake_run(cmd, **_kwargs):
        if cmd[:3] == ["pactl", "list", "sink-inputs"]:
            ids = next(listings, None)
            if ids is None:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="busy")
            stdout = "".join(
                f"Sink Input #{i}\n\tProperties:\n\t\tapplication.process.id = \"{pid}\"\n" for i in ids
            )
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        moves.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    class InlineThread:
        def __init__(self, target, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(linux_sink.sys, "platform", "linux")
    monkeypatch.setattr(linux_sink.subprocess, "run", fake_run)
    monkeypatch.setattr(linux_sink.threading, "Thread", InlineThread)
    return moves


def _routed_manager():
    from src.audio.linux_sink import LinuxSinkManager

    manager = LinuxSinkManager()
    manager.set_sink_name("crittssink")
    return manager


def test_linux_routing_moves_new_stream_not_existing_passthrough(monkeypatch):
    moves = _fake_pactl(monkeypatch, [[10], [10, 42]])
    manager = _routed_manager()

    ticket = manager.begin_stream_open(route=True)
    ticket.opened()

    assert moves == [["pactl", "move-sink-input", "42", "crittssink"]]
    assert not manager._open_lock.locked()


def test_linux_routing_skips_when_baseline_listing_fails(monkeypatch):
    # Without a baseline, the existing passthrough (10) looks new; never guess.
    moves = _fake_pactl(monkeypatch, [None, [10, 42]])
    manager = _routed_manager()

    ticket = manager.begin_stream_open(route=True)
    ticket.opened()
    ticket.close()

    assert moves == []
    assert not manager._open_lock.locked()


def test_linux_routing_does_nothing_when_stream_never_starts(monkeypatch):
    # Stop pressed (or the device failed to open) between the ticket and the stream.
    moves = _fake_pactl(monkeypatch, [[10], [10, 42]])
    manager = _routed_manager()

    ticket = manager.begin_stream_open(route=True)
    ticket.close()
    ticket.opened()  # a late opened() after close must not start routing

    assert moves == []
    assert not manager._open_lock.locked()


def test_linux_unrouted_stream_holds_open_lock_until_its_sink_input_appears(monkeypatch):
    moves = _fake_pactl(monkeypatch, [[10], [10, 50]])
    manager = _routed_manager()

    ticket = manager.begin_stream_open(route=False)
    assert manager._open_lock.locked()
    ticket.opened()

    assert moves == []
    assert not manager._open_lock.locked()


def test_linux_routing_ignores_ambiguous_streams_after_lock_released(monkeypatch):
    # Our stream did not show up within the identify window; once the lock is
    # released a preview (51) can appear too, and two new ids must not be guessed.
    from src.audio import linux_sink

    clock = iter([0.0, 0.0, 2.0, 2.0, 5.0, 5.0])
    monkeypatch.setattr(linux_sink.time, "monotonic", lambda: next(clock, 10.0))
    moves = _fake_pactl(monkeypatch, [[10], [10], [10, 42, 51]])
    manager = _routed_manager()

    ticket = manager.begin_stream_open(route=True)
    ticket._closed.wait = lambda _timeout: None
    ticket.opened()

    assert moves == []
    assert not manager._open_lock.locked()


def test_linux_preview_stream_is_kept_on_default_sink(monkeypatch):
    # Stream-restore would reopen a preview on our sink after TTS was routed there.
    moves = _fake_pactl(monkeypatch, [[10], [10, 50]])
    manager = _routed_manager()

    ticket = manager.begin_stream_open(route=False, keep_on_default=True)
    ticket.opened()

    assert moves == [["pactl", "move-sink-input", "50", "@DEFAULT_SINK@"]]
    assert not manager._open_lock.locked()
