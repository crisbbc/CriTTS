from unittest.mock import MagicMock
from src.gui.main_window import MainWindow


def test_rapid_resize_events_coalesce_to_single_apply(monkeypatch):
    window = MainWindow.__new__(MainWindow)
    window.root = MagicMock()
    window._resize_after_id = None

    apply_calls = []
    monkeypatch.setattr(window, "_apply_resize", lambda width: apply_calls.append(width))

    scheduled = []
    cancels = []

    def fake_after(ms, fn=None, *a, **k):
        scheduled.append((ms, fn))
        return f"tok-{len(scheduled)}"

    monkeypatch.setattr(window.root, "after", fake_after)
    monkeypatch.setattr(window.root, "after_cancel", lambda token: cancels.append(token))

    class E:
        def __init__(self, w, widget):
            self.width = w
            self.widget = widget

    # Fire a burst of 20 rapid resize events over the root widget.
    for w in range(1100, 1120):
        window._on_window_resize(E(w, window.root))

    # Each event schedules one after() and cancels the prior pending one.
    assert len(scheduled) == 20
    assert len(cancels) == 19
    # No apply has run yet (deferred).
    assert apply_calls == []
    # Only the last scheduled callback is live — firing it runs apply once.
    last_ms, last_fn = scheduled[-1]
    last_fn()
    assert apply_calls == [1119]
    # _resize_after_id cleared after apply fires.
    assert window._resize_after_id is None


def test_resize_event_ignored_when_widget_is_not_root(monkeypatch):
    window = MainWindow.__new__(MainWindow)
    window.root = MagicMock()
    window._resize_after_id = None
    monkeypatch.setattr(window, "_apply_resize", lambda width: None)
    monkeypatch.setattr(window.root, "after", lambda ms, fn=None, *a, **k: "tok")
    monkeypatch.setattr(window.root, "after_cancel", lambda token: None)

    class E:
        def __init__(self, w, widget):
            self.width = w
            self.widget = widget

    other = MagicMock()
    window._on_window_resize(E(1100, other))  # widget != root -> ignored
    # No after() should have been scheduled.
    # (root.after is a lambda with no record; assert _resize_after_id unchanged)
    assert window._resize_after_id is None
