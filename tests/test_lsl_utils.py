"""Regression tests for recording rates in LSL marker stream metadata."""

import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Dict
from unittest.mock import mock_open, patch
from xml.etree import ElementTree

import pytest

from lsl_utils import MarkerStreams
from recorder_core import RecorderCore


@pytest.fixture
def config() -> Dict[str, Any]:
    with (Path(__file__).resolve().parents[1] / "config.json").open() as config_file:
        return json.load(config_file)


@pytest.mark.parametrize("fps", [24, 30, 29.97])
def test_video_metadata_saves_configured_fps_without_changing_marker_rates(
    config: Dict[str, Any], fps: float
) -> None:
    config["video_settings"]["fps"] = fps

    with patch("lsl_utils.StreamOutlet") as outlet_class:
        MarkerStreams(config)

    assert outlet_class.call_count == 3
    audio_info = outlet_class.call_args_list[0].args[0]
    video_info = outlet_class.call_args_list[1].args[0]
    screen_info = outlet_class.call_args_list[2].args[0]
    assert audio_info.name() == config["lsl_settings"]["audio_stream_name"]
    assert video_info.name() == config["lsl_settings"]["video_stream_name"]
    assert screen_info.name() == config["lsl_settings"]["screen_stream_name"]
    for info in (audio_info, video_info, screen_info):
        assert info.nominal_srate() == 0
        assert info.type() == "Markers"
        assert info.channel_count() == 1

    video_xml = ElementTree.fromstring(video_info.as_xml())
    assert video_xml.findtext("desc/nominal_fps") == str(fps)


def test_nominal_fps_remains_distinct_from_video_start_fps(
    config: Dict[str, Any],
) -> None:
    with patch("lsl_utils.StreamOutlet") as outlet_class:
        streams = MarkerStreams(config)
        video_info = outlet_class.call_args_list[1].args[0]
        streams.send_video_start_marker(
            "subject001", "video.mp4", "20261015_102413", "2026-10-15T10:24:13", 15.0
        )

        outlet_class.return_value.push_sample.assert_called_once_with(
            [
                "VIDEO_START,subject001,video.mp4,20261015_102413,"
                "2026-10-15T10:24:13,15.0"
            ]
        )
        video_xml = ElementTree.fromstring(video_info.as_xml())
        assert video_xml.findtext("desc/nominal_fps") == "24"


def test_screen_markers_use_capture_timestamps(config: Dict[str, Any]) -> None:
    with patch("lsl_utils.StreamOutlet") as outlet_class:
        streams = MarkerStreams(config)
        streams.send_screen_start_marker("subject001", 12.5)
        streams.send_screen_stop_marker(15.0)

    screen_outlet = outlet_class.return_value
    assert [call.args for call in screen_outlet.push_sample.call_args_list] == [
        (["SCREEN_RECORD_START:subject001"], 12.5),
        (["SCREEN_RECORD_STOP"], 15.0),
    ]


@pytest.mark.parametrize("use_fallback_config", [False, True])
def test_core_populates_nominal_fps_from_loaded_config(
    use_fallback_config: bool,
) -> None:
    with ExitStack() as stack:
        if use_fallback_config:
            stack.enter_context(
                patch("builtins.open", side_effect=OSError("Configuration unavailable"))
            )
        outlet_class = stack.enter_context(patch("lsl_utils.StreamOutlet"))
        audio_class = stack.enter_context(patch("recorder_core.AudioRecorder"))
        video_class = stack.enter_context(patch("recorder_core.VideoRecorder"))
        screen_class = stack.enter_context(patch("recorder_core.ScreenRecorder"))

        core = RecorderCore()

        video_info = outlet_class.call_args_list[1].args[0]
        video_xml = ElementTree.fromstring(video_info.as_xml())
        assert video_xml.findtext("desc/nominal_fps") == str(
            core.config["video_settings"]["fps"]
        )
        audio_class.assert_called_once_with(
            core.config["audio_settings"], core.marker_streams
        )
        video_class.assert_called_once_with(
            core.config["video_settings"], core.marker_streams
        )
        screen_class.assert_called_once_with(
            core.config["screen_settings"], core.marker_streams
        )


def test_core_defaults_screen_settings_for_existing_config(
    config: Dict[str, Any],
) -> None:
    del config["screen_settings"]
    del config["lsl_settings"]["screen_stream_name"]

    with ExitStack() as stack:
        stack.enter_context(
            patch("builtins.open", mock_open(read_data=json.dumps(config)))
        )
        outlet_class = stack.enter_context(patch("lsl_utils.StreamOutlet"))
        stack.enter_context(patch("recorder_core.AudioRecorder"))
        stack.enter_context(patch("recorder_core.VideoRecorder"))
        screen_class = stack.enter_context(patch("recorder_core.ScreenRecorder"))

        core = RecorderCore()

    screen_class.assert_called_once_with({"fps": 30}, core.marker_streams)
    screen_info = outlet_class.call_args_list[2].args[0]
    assert screen_info.name() == "ScreenMarkers"


def test_missing_video_fps_reports_stream_creation_failure(
    config: Dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    del config["video_settings"]["fps"]

    with patch("lsl_utils.StreamOutlet"):
        with pytest.raises(RuntimeError, match="Failed to create LSL outlets"):
            MarkerStreams(config)

    assert "Failed to create LSL outlets: 'fps'" in caplog.text
