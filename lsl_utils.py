"""LSL utilities module for audio/video recorder.

This module provides utilities for Lab Streaming Layer (LSL) integration,
including marker stream creation and standardized marker formatting.
"""

import socket
from pylsl import StreamInfo, StreamOutlet
import logging


class MarkerStreams:
    """Creates and manages LSL marker streams for audio and video.

    Attributes:
        audio_marker_outlet: StreamOutlet for audio recording markers.
        video_marker_outlet: StreamOutlet for video recording markers.
    """

    def __init__(self, config):
        """Initialize LSL marker streams based on provided configuration.

        Args:
            config: Dictionary containing LSL configuration parameters.

        Raises:
            RuntimeError: If LSL streams cannot be created.
        """
        try:
            # Get LSL sampling rates from config
            marker_rate = config.get("marker_sampling_rate", 0)

            # Audio marker outlet
            audio_info = StreamInfo(
                config["audio_stream_name"],
                "Markers",
                1,
                marker_rate,
                "string",
                f"audio_markers_{socket.gethostname()}",
            )
            self.audio_marker_outlet = StreamOutlet(audio_info)

            # Video marker outlet
            video_info = StreamInfo(
                config["video_stream_name"],
                "Markers",
                1,
                marker_rate,
                "string",
                f"video_markers_{socket.gethostname()}",
            )
            self.video_marker_outlet = StreamOutlet(video_info)
            logging.info("LSL outlets created successfully")
        except Exception as e:
            logging.error(f"Failed to create LSL outlets: {e}")
            raise RuntimeError(f"Failed to create LSL outlets: {e}")

    def send_audio_start_marker(
        self, subject_id, filename, timestamp, channels, sample_rate, iso_timestamp=None
    ):
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

    def send_audio_stop_marker(self, filename, timestamp):
        """Send audio recording stop marker to LSL.

        Args:
            filename: Path to the recording file.
            timestamp: String timestamp for the event.
        """
        marker = f"AUDIO_STOP,{filename},{timestamp}"
        self.audio_marker_outlet.push_sample([marker])

    def send_video_start_marker(
        self, subject_id, filename, timestamp, iso_timestamp, fps
    ):
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

    def send_video_stop_marker(self, filename, timestamp):
        """Send video recording stop marker to LSL.

        Args:
            filename: Path to the recording file.
            timestamp: String timestamp for the event.
        """
        marker = f"VIDEO_STOP,{filename},{timestamp}"
        self.video_marker_outlet.push_sample([marker])
