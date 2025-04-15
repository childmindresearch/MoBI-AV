"""Core recorder module that coordinates audio and video recording.

This module provides a unified interface for controlling audio and video
recording, handling configuration, and synchronizing recordings.
"""

import os
import json
import sys
import logging
from datetime import datetime
from lsl_utils import MarkerStreams
from audio_recorder import AudioRecorder
from video_recorder import VideoRecorder


class RecorderCore:
    """Core class that coordinates audio and video recording functionality.

    This class loads configuration, initializes audio and video recorders,
    and provides methods for starting and stopping recordings individually
    or together with synchronization.

    Attributes:
        config: Dictionary of configuration settings.
        marker_streams: LSL marker streams for audio and video.
        audio_recorder: AudioRecorder instance.
        video_recorder: VideoRecorder instance.
    """

    def __init__(self):
        """Initialize the RecorderCore with configuration and components."""
        self.load_config()
        self.marker_streams = MarkerStreams(self.config["lsl_settings"])
        self.audio_recorder = AudioRecorder(
            self.config["audio_settings"], self.marker_streams
        )
        self.video_recorder = VideoRecorder(
            self.config["video_settings"], self.marker_streams
        )

    def load_config(self):
        """Load configuration from config.json.

        Raises:
            RuntimeError: If configuration cannot be loaded.
        """
        try:
            # Use the executable directory when frozen; else use the script directory.
            if getattr(sys, "frozen", False):
                base_path = os.path.dirname(sys.executable)
            else:
                base_path = os.path.dirname(__file__)

            config_path = os.path.join(base_path, "config.json")
            with open(config_path, "r") as f:
                self.config = json.load(f)
            logging.info("Configuration loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load configuration: {e}")
            # Create default configuration
            self.config = {
                "default_subject_id": "subject001",
                "default_destination": "recordings",
                "audio_filename_suffix": "_audio",
                "video_filename_suffix": "_video",
                "audio_settings": {
                    "device_name": "Default",
                    "host_api": [0, 1, 2, 3],
                    "use_device_defaults": True,
                    "filename_suffix": "_audio",
                    "fallback_settings": {
                        "channels": 1,
                        "sample_rate": 44100,
                        "chunk_duration": 0.1,
                        "format": "paInt16",
                    },
                },
                "video_settings": {
                    "width": 640,
                    "height": 480,
                    "fps": 24,
                    "codec": "mp4v",
                    "filename_suffix": "_video",
                    "show_timestamp": False,
                },
                "lsl_settings": {
                    "audio_stream_name": "AudioMarkers",
                    "video_stream_name": "VideoMarkers",
                    "marker_sampling_rate": 0,
                },
            }

    @property
    def recording_audio(self):
        """Check if audio recording is in progress.

        Returns:
            Boolean indicating if audio is currently recording.
        """
        return (
            self.audio_recorder.recording if hasattr(self, "audio_recorder") else False
        )

    @property
    def recording_video(self):
        """Check if video recording is in progress.

        Returns:
            Boolean indicating if video is currently recording.
        """
        return (
            self.video_recorder.recording if hasattr(self, "video_recorder") else False
        )

    def get_available_audio_devices(self):
        """Get list of available audio devices.

        Returns:
            List of dictionaries containing audio device information.
        """
        return self.audio_recorder.get_available_devices()

    def get_available_video_devices(self):
        """Get list of available video devices.

        Returns:
            List of dictionaries containing video device information.
        """
        return self.video_recorder.get_available_devices()

    def start_audio_recording(
        self, subject_id, destination, device_index=None, pre_initialize=False
    ):
        """Start audio recording or prepare for synchronized start.

        Args:
            subject_id: Identifier for the recording subject.
            destination: Directory path where recording will be saved.
            device_index: Optional specific device to use.
            pre_initialize: If True, prepare but don't actually start recording.

        Returns:
            Boolean indicating success or failure.
        """
        return self.audio_recorder.start_recording(
            subject_id, destination, device_index, pre_initialize
        )

    def stop_audio_recording(self):
        """Stop audio recording and save to file.

        Returns:
            Boolean indicating success or failure.
        """
        return self.audio_recorder.stop_recording()

    def start_video_recording(
        self, subject_id, destination, device_index=None, pre_initialize=False
    ):
        """Start video recording or prepare for synchronized start.

        Args:
            subject_id: Identifier for the recording subject.
            destination: Directory path where recording will be saved.
            device_index: Optional specific device to use.
            pre_initialize: If True, prepare but don't actually start recording.

        Returns:
            Boolean indicating success or failure.
        """
        return self.video_recorder.start_recording(
            subject_id, destination, device_index, pre_initialize
        )

    def stop_video_recording(self):
        """Stop video recording and save to file.

        Returns:
            Boolean indicating success or failure.
        """
        return self.video_recorder.stop_recording()

    def start_pre_initialized_audio(self, subject_id):
        """Start a pre-initialized audio recording.

        Args:
            subject_id: Identifier for the recording subject.

        Returns:
            Boolean indicating success or failure.
        """
        return self.audio_recorder.start_pre_initialized(subject_id)

    def start_pre_initialized_video(self, subject_id):
        """Start a pre-initialized video recording.

        Args:
            subject_id: Identifier for the recording subject.

        Returns:
            Boolean indicating success or failure.
        """
        return self.video_recorder.start_pre_initialized(subject_id)

    def start_both_recordings(
        self, subject_id, destination, audio_device_index=None, video_device_index=None
    ):
        """Start both audio and video recordings with synchronized start times.

        Args:
            subject_id: Identifier for the recording subject.
            destination: Directory path where recordings will be saved.
            audio_device_index: Optional specific audio device to use.
            video_device_index: Optional specific video device to use.

        Returns:
            Boolean indicating if both recordings started successfully.
        """
        if self.recording_audio or self.recording_video:
            logging.warning("Recording already in progress")
            return False

        try:
            # Use same timestamp for both recordings to keep them in sync
            common_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Create destination folder if it doesn't exist
            os.makedirs(destination, exist_ok=True)

            # Create synchronized filenames
            audio_suffix = self.config["audio_filename_suffix"]
            video_suffix = self.config["video_filename_suffix"]
            audio_filename = os.path.join(
                destination, f"{subject_id}{audio_suffix}_{common_timestamp}.wav"
            )
            video_filename = os.path.join(
                destination, f"{subject_id}{video_suffix}_{common_timestamp}.mp4"
            )

            logging.info(
                f"Using synchronized filenames with timestamp {common_timestamp}"
            )

            # Pre-initialize both devices
            self.audio_recorder.start_recording(
                subject_id,
                destination,
                audio_device_index,
                pre_initialize=True,
                filename=audio_filename,
            )

            self.video_recorder.start_recording(
                subject_id,
                destination,
                video_device_index,
                pre_initialize=True,
                filename=video_filename,
            )

            # Start both recordings in quick succession
            audio_success = self.start_pre_initialized_audio(subject_id)
            video_success = self.start_pre_initialized_video(subject_id)

            if audio_success and video_success:
                logging.info(
                    f"Started synchronized audio and video recordings at {common_timestamp}"
                )
                return True
            else:
                logging.error("Failed to start synchronized recordings")
                return False

        except Exception as e:
            logging.error(f"Error in synchronized recording start: {e}")
            import traceback

            logging.error(traceback.format_exc())
            return False

    def stop_both_recordings(self):
        """Stop both audio and video recordings if they are in progress.

        Returns:
            Boolean indicating if all active recordings were stopped successfully.
        """
        success = True

        # Stop audio if it's recording
        if self.recording_audio:
            audio_success = self.stop_audio_recording()
            if not audio_success:
                success = False

        # Stop video if it's recording
        if self.recording_video:
            video_success = self.stop_video_recording()
            if not video_success:
                success = False

        return success
