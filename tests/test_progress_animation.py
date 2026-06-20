from unittest.mock import MagicMock
from src.gui.main_window import MainWindow


def test_progress_frames_is_class_constant():
    assert hasattr(MainWindow, "_PROGRESS_FRAMES")
    assert isinstance(MainWindow._PROGRESS_FRAMES, (list, tuple))
    assert len(MainWindow._PROGRESS_FRAMES) == 10


def test_animate_progress_uses_class_constant_increments_and_schedules(monkeypatch):
    window = MainWindow.__new__(MainWindow)
    window.root = MagicMock()
    window.progress_label = MagicMock()
    window._progress_animation_running = True
    window._progress_animation_index = 0
    window._progress_base_message = "Generating"
    monkeypatch.setattr(window.root, "after", MagicMock(return_value="tok"))

    window._animate_progress()

    # index advanced by exactly one
    assert window._progress_animation_index == 1
    # configure called once with the first frame + base message
    expected = f"{MainWindow._PROGRESS_FRAMES[0]} Generating"
    window.progress_label.configure.assert_called_once_with(text=expected)
    # cadence relaxed to 150ms
    assert window.root.after.call_args.args[0] == 150


def test_animate_progress_noop_when_not_running(monkeypatch):
    window = MainWindow.__new__(MainWindow)
    window.root = MagicMock()
    window.progress_label = MagicMock()
    window._progress_animation_running = False
    monkeypatch.setattr(window.root, "after", MagicMock(return_value="tok"))
    window._animate_progress()
    window.progress_label.configure.assert_not_called()
    window.root.after.assert_not_called()
