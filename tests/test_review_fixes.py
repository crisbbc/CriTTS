"""Regression tests for reliability and safety fixes from the code review."""
import importlib.util
import json
import shutil
import sys
import threading
import types
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Keep imports headless in environments without the optional audio/TTS stack.
for module_name in (
    "customtkinter",
    "edge_tts",
    "sounddevice",
    "soundfile",
    "pyloudnorm",
    "keyboard",
    "langid",
):
    sys.modules.setdefault(module_name, MagicMock())

# scipy is optional in the review environment; AudioRouter only needs the
# module to import for these state/persistence tests.
if "scipy" not in sys.modules:
    scipy = types.ModuleType("scipy")
    scipy.signal = types.ModuleType("scipy.signal")
    sys.modules["scipy"] = scipy
    sys.modules["scipy.signal"] = scipy.signal

from src.config.settings_manager import SettingsManager
from src.tts.audio_cache import AudioCache, PhraseTracker
from src.audio.audio_router import AudioRouter
from src.gui.main_window import MainWindow


@pytest.mark.parametrize(
    ("key", "raw_value", "expected"),
    [
        ("rate", "not-a-number", 0),
        ("mic_passthrough_volume", "not-a-number", 100),
        ("volume", 55, 55),
    ],
)
def test_malformed_persisted_numeric_settings_are_normalized(tmp_path, key, raw_value, expected):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({key: raw_value}), encoding="utf-8")

    manager = SettingsManager(config_path=config_path)

    assert manager.get(key) == expected
    assert manager.validate_settings() == []


def test_coqui_voice_with_spaces_survives_startup_migration(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"tts_provider": "coqui", "voice": "Claribel Dervla"}),
        encoding="utf-8",
    )

    manager = SettingsManager(config_path=config_path)

    assert manager.get("tts_provider") == "coqui"
    assert manager.get("voice") == "Claribel Dervla"


def test_future_coqui_voice_id_survives_provider_switch(tmp_path):
    manager = SettingsManager(config_path=tmp_path / "config.json")
    manager.set("voice", "Future Speaker Name")
    manager.set("tts_provider", "coqui")

    assert manager.get("voice") == "Future Speaker Name"


def test_phrase_tracker_discards_wrong_root_shape(tmp_path):
    stats_path = tmp_path / "phrase_stats.json"
    stats_path.write_text("[]", encoding="utf-8")

    tracker = PhraseTracker(stats_path=stats_path)
    tracker.track_usage("hello", "voice")

    assert tracker.get_common_phrases() == []
    assert len(tracker._stats) == 1
    tracker.shutdown()
    assert isinstance(json.loads(stats_path.read_text(encoding="utf-8")), dict)


def test_audio_cache_persists_valid_json_after_store(tmp_path):
    cache = AudioCache(cache_dir=tmp_path, enabled=True)
    try:
        assert cache.store(b"audio", "hello", "voice", provider="edge")
        cache.shutdown()

        index = json.loads((tmp_path / "cache_index.json").read_text(encoding="utf-8"))
        assert index["version"] == AudioCache.CACHE_VERSION
        assert len(index["entries"]) == 1
    finally:
        # shutdown is idempotent for this test and prevents a timer leak if an
        # assertion fails before the explicit shutdown above.
        cache.shutdown()


def test_passthrough_stop_is_reentrant_and_lock_protected():
    router = AudioRouter()
    with router._passthrough_lock:
        router.stop_mic_passthrough()
    assert router.is_mic_passthrough_active() is False


def test_stream_stop_requested_honors_external_event():
    router = AudioRouter()
    external_stop = threading.Event()

    assert router._stream_stop_requested(external_stop) is False
    external_stop.set()
    assert router._stream_stop_requested(external_stop) is True


def test_main_window_timer_cancellation_tolerates_destroyed_root():
    window = MainWindow.__new__(MainWindow)
    window.root = MagicMock()
    window.root.after_cancel.side_effect = RuntimeError("root destroyed")

    MainWindow._cancel_after(window, "after#1")

    window.root.after_cancel.assert_called_once_with("after#1")


def test_main_window_queued_callback_is_ignored_after_shutdown():
    window = MainWindow.__new__(MainWindow)
    window.root = MagicMock()
    window._async_callbacks_active = True
    scheduled = []
    window.root.after.side_effect = lambda _delay, callback: scheduled.append(callback) or "after#1"
    applied = []

    MainWindow._safe_after(window, 0, lambda: applied.append("ran"))
    window._async_callbacks_active = False
    scheduled[0]()

    assert applied == []


def _load_update_module():
    module_path = Path(__file__).parents[1] / "scripts" / "update_check.py"
    spec = importlib.util.spec_from_file_location("critts_update_check", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_updater_rejects_zip_path_traversal(tmp_path):
    update_module = _load_update_module()
    archive = tmp_path / "malicious.zip"
    destination = tmp_path / "out"

    with zipfile.ZipFile(archive, "w") as archive_file:
        archive_file.writestr("repo/../../outside.txt", "unsafe")

    with pytest.raises(ValueError, match="Unsafe update archive"):
        update_module._safe_extract_zip(archive, destination)

    assert not (tmp_path / "outside.txt").exists()


def test_updater_move_failure_preserves_original(tmp_path, monkeypatch):
    update_module = _load_update_module()
    install_dir = tmp_path / "install"
    extracted = tmp_path / "repo"
    install_dir.mkdir()
    extracted.mkdir()
    original = install_dir / "first.py"
    original.write_text("old first", encoding="utf-8")
    (extracted / "first.py").write_text("new first", encoding="utf-8")

    def fail_move(source, destination, *args, **kwargs):
        raise OSError("simulated move failure")

    monkeypatch.setattr(update_module, "SCRIPT_DIR", install_dir)
    monkeypatch.setattr(update_module.shutil, "move", fail_move)

    with pytest.raises(OSError, match="simulated move failure"):
        update_module._apply_staged_update(extracted)

    assert original.read_text(encoding="utf-8") == "old first"


def test_updater_rollback_does_not_delete_unprocessed_originals(tmp_path, monkeypatch):
    update_module = _load_update_module()
    install_dir = tmp_path / "install"
    extracted = tmp_path / "repo"
    install_dir.mkdir()
    extracted.mkdir()
    (install_dir / "first.py").write_text("old first", encoding="utf-8")
    (install_dir / "second.py").write_text("old second", encoding="utf-8")
    (install_dir / "untouched.py").write_text("untouched", encoding="utf-8")
    (extracted / "first.py").write_text("new first", encoding="utf-8")
    (extracted / "second.py").write_text("new second", encoding="utf-8")

    real_copy2 = shutil.copy2

    def copy2_then_fail(source, destination, *args, **kwargs):
        if Path(source).name == "second.py":
            raise OSError("simulated copy failure")
        return real_copy2(source, destination, *args, **kwargs)

    monkeypatch.setattr(update_module, "SCRIPT_DIR", install_dir)
    monkeypatch.setattr(update_module.shutil, "copy2", copy2_then_fail)

    with pytest.raises(OSError, match="simulated copy failure"):
        update_module._apply_staged_update(extracted)

    assert (install_dir / "first.py").read_text(encoding="utf-8") == "old first"
    assert (install_dir / "second.py").read_text(encoding="utf-8") == "old second"
    assert (install_dir / "untouched.py").read_text(encoding="utf-8") == "untouched"
