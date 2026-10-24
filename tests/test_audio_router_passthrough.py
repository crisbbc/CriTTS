from math import ceil

from sounddevice import PortAudioError

import src.audio.audio_router as audio_router_module
from src.audio.audio_router import AudioRouter


class _Stream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        pass


def test_duplex_passthrough_tries_each_distinct_candidate_rate(monkeypatch):
    attempted = []

    def stream(**kwargs):
        attempted.append(kwargs["samplerate"])
        if kwargs["samplerate"] == 48000:
            raise PortAudioError("unsupported")
        return _Stream(**kwargs)

    monkeypatch.setattr(audio_router_module.sd, "query_devices", lambda _index: {"default_samplerate": 44100})
    monkeypatch.setattr(audio_router_module.sd, "Stream", stream)

    router = AudioRouter()
    ok, error = router.start_mic_passthrough(1, 1)

    assert (ok, error) == (True, None)
    assert attempted == [48000, 44100]
    router.stop_mic_passthrough()


def test_split_passthrough_retries_at_input_native_rate(monkeypatch):
    attempted_inputs = []
    attempted_outputs = []

    def query(index):
        return {"default_samplerate": 44100 if index == 1 else 32000}

    def input_stream(**kwargs):
        attempted_inputs.append(kwargs["samplerate"])
        if kwargs["samplerate"] == 48000:
            raise PortAudioError("unsupported")
        return _Stream(**kwargs)

    def output_stream(**kwargs):
        attempted_outputs.append(kwargs["samplerate"])
        return _Stream(**kwargs)

    monkeypatch.setattr(audio_router_module.sd, "query_devices", query)
    monkeypatch.setattr(audio_router_module.sd, "InputStream", input_stream)
    monkeypatch.setattr(audio_router_module.sd, "OutputStream", output_stream)

    router = AudioRouter()
    ok, error = router.start_mic_passthrough(1, 2)

    assert (ok, error) == (True, None)
    assert attempted_inputs == [48000, 44100]
    assert attempted_outputs == [44100]
    router.stop_mic_passthrough()


def test_split_passthrough_falls_back_to_dual_native_rates(monkeypatch):
    opened = []

    def query(index):
        return {"default_samplerate": 44100 if index == 1 else 48000}

    def input_stream(**kwargs):
        opened.append(("input", kwargs["samplerate"], kwargs["blocksize"]))
        if kwargs["samplerate"] != 44100:
            raise PortAudioError("unsupported input rate")
        return _Stream(**kwargs)

    def output_stream(**kwargs):
        opened.append(("output", kwargs["samplerate"], kwargs["blocksize"]))
        if kwargs["samplerate"] != 48000:
            raise PortAudioError("unsupported output rate")
        return _Stream(**kwargs)

    monkeypatch.setattr(audio_router_module.sd, "query_devices", query)
    monkeypatch.setattr(audio_router_module.sd, "InputStream", input_stream)
    monkeypatch.setattr(audio_router_module.sd, "OutputStream", output_stream)

    router = AudioRouter()
    monkeypatch.setattr(router, "_resample_high_quality", lambda data, *_args, **_kwargs: data)
    ok, error = router.start_mic_passthrough(1, 2)

    assert (ok, error) == (True, None)
    assert opened[-2:] == [
        ("input", 44100, router._PASSTHROUGH_BLOCKSIZE),
        ("output", 48000, ceil(router._PASSTHROUGH_BLOCKSIZE * 48000 / 44100)),
    ]
    router.stop_mic_passthrough()
