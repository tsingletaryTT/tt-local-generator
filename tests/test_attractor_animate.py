"""
Unit tests for AttractorWindow animate auto-generation branch.
No GTK display required — we only test the non-GTK _enqueue_generation logic
by constructing the object without GTK init.

gi (PyGObject) lives in the system dist-packages on this machine, not in the
venv.  We add it to sys.path early so `import gi` inside attractor.py works
during unit tests without a running display.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the system PyGObject package is importable inside the venv.
_SYSTEM_DIST = "/usr/lib/python3/dist-packages"
if _SYSTEM_DIST not in sys.path:
    sys.path.insert(0, _SYSTEM_DIST)

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))


def _make_attractor(model_source="video", get_animate_inputs=None):
    """Build a minimal AttractorWindow with all GTK bypassed."""
    import attractor as att

    with patch("attractor.Gtk.ApplicationWindow.__init__", return_value=None), \
         patch.object(att.AttractorWindow, "_build", return_value=None), \
         patch.object(att.AttractorWindow, "maximize", return_value=None), \
         patch.object(att.AttractorWindow, "get_display", return_value=MagicMock()):
        win = att.AttractorWindow.__new__(att.AttractorWindow)
        win._alive = True
        win._model_source = model_source
        win._on_enqueue = MagicMock()
        win._get_animate_inputs = get_animate_inputs
    return win


def test_enqueue_generation_animate_calls_get_inputs():
    """When model_source=='animate', _enqueue_generation calls get_animate_inputs."""
    inputs_called = []

    def fake_inputs():
        inputs_called.append(True)
        return ("/tmp/motion.mp4", "/tmp/char.jpg")

    win = _make_attractor(model_source="animate", get_animate_inputs=fake_inputs)
    win._enqueue_generation("a prompt")

    assert inputs_called, "get_animate_inputs was not called"
    win._on_enqueue.assert_called_once()
    call_kwargs = win._on_enqueue.call_args[1]
    assert call_kwargs["ref_video_path"] == "/tmp/motion.mp4"
    assert call_kwargs["ref_char_path"] == "/tmp/char.jpg"
    assert call_kwargs["model_source"] == "animate"


def test_enqueue_generation_animate_skips_when_no_callback():
    """When get_animate_inputs is None, animate generation is skipped silently."""
    win = _make_attractor(model_source="animate", get_animate_inputs=None)
    win._enqueue_generation("a prompt")
    win._on_enqueue.assert_not_called()


def test_enqueue_generation_animate_skips_when_inputs_empty():
    """When get_animate_inputs returns ('', ''), no job is enqueued."""
    win = _make_attractor(model_source="animate", get_animate_inputs=lambda: ("", ""))
    win._enqueue_generation("a prompt")
    win._on_enqueue.assert_not_called()


def test_enqueue_generation_animate_skips_when_ref_video_empty():
    """Missing ref_video alone is enough to skip enqueueing."""
    win = _make_attractor(
        model_source="animate",
        get_animate_inputs=lambda: ("", "/tmp/char.jpg"),
    )
    win._enqueue_generation("a prompt")
    win._on_enqueue.assert_not_called()


def test_enqueue_generation_video_mode_unchanged():
    """For model_source=='video', _enqueue_generation works as before (no animate inputs)."""
    win = _make_attractor(model_source="video", get_animate_inputs=None)
    win._enqueue_generation("a video prompt")
    win._on_enqueue.assert_called_once()
    call_kwargs = win._on_enqueue.call_args[1]
    assert call_kwargs["ref_video_path"] == ""
    assert call_kwargs["ref_char_path"] == ""
    assert call_kwargs["model_source"] == "video"
