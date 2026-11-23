"""Tests for screen capture lifecycle and LSL event markers."""

import threading
from typing import Dict
from unittest.mock import Mock, patch

import numpy as np

from screen_recorder import ScreenRecorder


class FakeScreenCapture:
    monitors = [
        {"left": 0, "top": 0, "width": 4, "height": 2},
        {"left": 4, "top": 0, "width": 2, "height": 2},
    ]

    def __init__(self) -> None:
        self.frame_captured = threading.Event()

    def grab(self, monitor: Dict[str, int]) -> np.ndarray:
        self.frame_captured.set()
        return np.zeros((monitor["height"], monitor["width"], 4), dtype=np.uint8)


def test_available_screens_include_combined_and_individual_monitors() -> None:
    capture = FakeScreenCapture()
    with patch("screen_recorder.mss.mss", return_value=capture):
        recorder = ScreenRecorder({"fps": 30}, Mock())

    assert recorder.get_available_screens() == [
        {
            "index": 0,
            "name": "All Screens Combined",
            "width": 4,
            "height": 2,
        },
        {"index": 1, "name": "Monitor 1", "width": 2, "height": 2},
    ]


def test_recording_flushes_frames_and_sends_markers(tmp_path) -> None:
    capture = FakeScreenCapture()
    markers = Mock()
    writer = Mock()
    with patch("screen_recorder.mss.mss", return_value=capture):
        with patch("screen_recorder.imageio.get_writer", return_value=writer):
            recorder = ScreenRecorder({"fps": 30}, markers)

            assert recorder.start_recording("subject001", str(tmp_path), 1)
            assert capture.frame_captured.wait(timeout=2)
            assert recorder.stop_recording()

    writer.append_data.assert_called()
    writer.close.assert_called_once_with()
    markers.send_screen_start_marker.assert_called_once()
    markers.send_screen_stop_marker.assert_called_once_with(
        markers.send_screen_start_marker.call_args.args[1]
    )


def test_invalid_monitor_does_not_open_writer() -> None:
    capture = FakeScreenCapture()
    with patch("screen_recorder.mss.mss", return_value=capture):
        with patch("screen_recorder.imageio.get_writer") as get_writer:
            recorder = ScreenRecorder({"fps": 30}, Mock())

            assert not recorder.start_recording("subject001", "recordings", 2)

    get_writer.assert_not_called()


def test_writer_failure_is_reported_when_stopping(tmp_path) -> None:
    capture = FakeScreenCapture()
    markers = Mock()
    writer = Mock()
    writer.append_data.side_effect = OSError("encoding failed")
    with patch("screen_recorder.mss.mss", return_value=capture):
        with patch("screen_recorder.imageio.get_writer", return_value=writer):
            recorder = ScreenRecorder({"fps": 30}, markers)

            assert recorder.start_recording("subject001", str(tmp_path), 1)
            assert capture.frame_captured.wait(timeout=2)
            assert not recorder.stop_recording()

    writer.close.assert_called_once_with()
