"""LSL utilities module for audio, camera video, and screen recordings.

This module provides utilities for Lab Streaming Layer (LSL) integration,
including marker stream creation and standardized marker formatting.
"""

import socket
from pylsl import StreamInfo, StreamOutlet  # type: ignore[import-untyped]
import logging
from typing import Any, Dict, Optional


class MarkerStreams:
    """Creates and manages LSL marker streams for all recording sources.

    Attributes:
        audio_marker_outlet: StreamOutlet for audio recording markers.
        video_marker_outlet: StreamOutlet for video recording markers.
        screen_marker_outlet: StreamOutlet for screen recording markers.
    """

    audio_marker_outlet: StreamOutlet
    video_marker_outlet: StreamOutlet
    screen_marker_outlet: StreamOutlet

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize LSL marker streams based on provided configuration.

        Args:
            config: Application configuration, including LSL and video settings.

        Raises:
            RuntimeError: If LSL streams cannot be created.
        """
        try:
            lsl_config = config["lsl_settings"]
            marker_rate: int = lsl_config.get("marker_sampling_rate", 0)

            # Audio marker outlet
            audio_info = StreamInfo(
                lsl_config["audio_stream_name"],
                "Markers",
                1,
                marker_rate,
                "string",
                f"audio_markers_{socket.gethostname()}",
            )
            self.audio_marker_outlet = StreamOutlet(audio_info)

            # Video marker outlet
            video_info = StreamInfo(
                lsl_config["video_stream_name"],
                "Markers",
                1,
                marker_rate,
                "string",
                f"video_markers_{socket.gethostname()}",
            )
            video_info.desc().append_child_value(
                "nominal_fps", str(config["video_settings"]["fps"])
            )
            self.video_marker_outlet = StreamOutlet(video_info)

            screen_info = StreamInfo(
                lsl_config.get("screen_stream_name", "ScreenMarkers"),
                "Markers",
                1,
                marker_rate,
                "string",
                f"screen_markers_{socket.gethostname()}",
            )
            self.screen_marker_outlet = StreamOutlet(screen_info)
            logging.info("LSL outlets created successfully")
        except Exception as e:
            logging.error(f"Failed to create LSL outlets: {e}")
            raise RuntimeError(f"Failed to create LSL outlets: {e}")

    def send_audio_start_marker(
        self,
        subject_id: str,
        filename: str,
        timestamp: str,
        channels: int,
        sample_rate: int,
        iso_timestamp: Optional[str] = None,
    ) -> None:
        """Send audio recording start marker to LSL.

        Args:
            subject_id: Identifier for the recording subject.
            filename: Path to the recording file.
            timestamp: String timestamp for the filename.
            channels: Number of audio channels being recorded.
            sample_rate: Sample rate of the recording in Hz.
            iso_timestamp: Optional ISO-formatted timestamp for precise timing.
        """
        if iso_timestamp:
            marker = f"AUDIO_START,{subject_id},{filename},{timestamp},{channels},{sample_rate},{iso_timestamp}"
        else:
            marker = f"AUDIO_START,{subject_id},{filename},{timestamp},{channels},{sample_rate}"

        self.audio_marker_outlet.push_sample([marker])

    def send_audio_stop_marker(self, filename: str, timestamp: str) -> None:
        """Send audio recording stop marker to LSL.

        Args:
            filename: Path to the recording file.
            timestamp: String timestamp for the event.
        """
        marker = f"AUDIO_STOP,{filename},{timestamp}"
        self.audio_marker_outlet.push_sample([marker])

    def send_video_start_marker(
        self,
        subject_id: str,
        filename: str,
        timestamp: str,
        iso_timestamp: str,
        fps: float,
    ) -> None:
        """Send video recording start marker to LSL.

        Args:
            subject_id: Identifier for the recording subject.
            filename: Path to the recording file.
            timestamp: String timestamp for the filename.
            iso_timestamp: ISO-formatted timestamp for precise timing.
            fps: Frames per second of the video recording.
        """
        marker = (
            f"VIDEO_START,{subject_id},{filename},{timestamp},{iso_timestamp},{fps}"
        )
        self.video_marker_outlet.push_sample([marker])

    def send_video_stop_marker(self, filename: str, timestamp: str) -> None:
        """Send video recording stop marker to LSL.

        Args:
            filename: Path to the recording file.
            timestamp: String timestamp for the event.
        """
        marker = f"VIDEO_STOP,{filename},{timestamp}"
        self.video_marker_outlet.push_sample([marker])

    def send_screen_start_marker(self, subject_id: str, timestamp: float) -> None:
        """Send a screen recording start marker at the first captured frame."""
        self.screen_marker_outlet.push_sample(
            [f"SCREEN_RECORD_START:{subject_id}"], timestamp
        )

    def send_screen_stop_marker(self, timestamp: float) -> None:
        """Send a screen recording stop marker at the final captured frame."""
        self.screen_marker_outlet.push_sample(["SCREEN_RECORD_STOP"], timestamp)
