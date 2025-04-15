"""Audio recording module for lab data collection.

This module provides audio recording capabilities using PyAudio, with support
for device selection and LSL marker synchronization.
"""

import os
import wave
import pyaudio
import logging
from datetime import datetime


class AudioRecorder:
    """Audio recorder supporting multiple devices and synchronized recordings.

    Attributes:
        config: Audio recording configuration.
        recording: Boolean indicating if recording is in progress.
        audio_stream: PyAudio stream object when recording.
        audio_p: PyAudio instance.
        audio_frames: List of audio frame data.
        audio_filename: Path to the current recording file.
        actual_channels: Number of channels being used for recording.
        actual_sample_rate: Sample rate in Hz being used for recording.
        actual_sample_width: Sample width in bytes for the recording format.
    """

    def __init__(self, config, marker_streams):
        """Initialize the audio recorder.

        Args:
            config: Dictionary containing audio recording settings.
            marker_streams: MarkerStreams instance for sending LSL markers.
        """
        self.config = config
        self.marker_streams = marker_streams
        self.recording = False
        self.audio_stream = None
        self.audio_p = None
        self.audio_frames = []
        self.audio_filename = None
        self.actual_channels = None
        self.actual_sample_rate = None
        self.actual_sample_width = None

    def get_available_devices(self):
        """Get a list of available audio input devices.

        Returns:
            List of dictionaries containing device information.
            Each dictionary includes: index, name, channels, sample_rate, host_api.
        """
        devices = []
        p = pyaudio.PyAudio()

        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev["maxInputChannels"] > 0:  # Only include input devices
                devices.append(
                    {
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["maxInputChannels"],
                        "sample_rate": int(dev["defaultSampleRate"]),
                        "host_api": dev["hostApi"],
                    }
                )

        p.terminate()
        return devices

    def find_device(self, device_name, host_api):
        """Find audio device index by name and host API.

        Args:
            device_name: String containing part or all of the device name.
            host_api: List of integers representing acceptable host API indices.

        Returns:
            Tuple of (PyAudio instance, device_index) or (None, None) if not found.
        """
        p = pyaudio.PyAudio()

        device_index = None
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if (
                device_name in dev["name"]
                and dev["hostApi"] in host_api
                and dev["maxInputChannels"] > 0
            ):
                device_index = i
                break

        if device_index is None:
            available_devices = [
                p.get_device_info_by_index(i)["name"]
                for i in range(p.get_device_count())
            ]
            logging.error(
                f"Device '{device_name}' not found. Available devices: {available_devices}"
            )
            p.terminate()
            return None, None

        return p, device_index

    def audio_callback(self, in_data, frame_count, time_info, status):
        """Callback function for audio stream.

        Args:
            in_data: Audio frame data from PyAudio.
            frame_count: Number of frames in this buffer.
            time_info: Dictionary with timing information.
            status: Status flag from PyAudio.

        Returns:
            Tuple of (in_data, flag) where flag indicates if more audio is expected.
        """
        if self.recording:
            self.audio_frames.append(in_data)
        return (in_data, pyaudio.paContinue)

    def start_recording(
        self,
        subject_id,
        destination,
        device_index=None,
        pre_initialize=False,
        filename=None,
    ):
        """Start audio recording or prepare for synchronized start.

        Args:
            subject_id: Identifier for the recording subject.
            destination: Directory path where recording will be saved.
            device_index: Optional device index to use, otherwise uses default.
            pre_initialize: If True, prepare recording but don't start streaming.
            filename: Optional specific filename to use instead of auto-generated one.

        Returns:
            Boolean indicating success or failure.
        """
        if self.recording:
            logging.warning("Audio recording already in progress")
            return False

        # If device_index is provided, use it directly
        if device_index is not None:
            self.audio_p = pyaudio.PyAudio()
            device_idx = device_index
        else:
            # Otherwise use the default device finding logic
            device_name = self.config.get("device_name", "Default")
            host_api = self.config.get("host_api", [0, 1, 2, 3])
            self.audio_p, device_idx = self.find_device(device_name, host_api)

        if not self.audio_p or device_idx is None:
            return False

        use_defaults = self.config.get("use_device_defaults", False)
        device_info = self.audio_p.get_device_info_by_index(device_idx)

        # Determine actual parameters based on device capabilities
        if use_defaults:
            # Use the device's default settings
            self.actual_channels = min(int(device_info["maxInputChannels"]), 2)
            self.actual_sample_rate = int(device_info["defaultSampleRate"])
            chunk_duration = self.config.get("fallback_settings", {}).get(
                "chunk_duration", 0.1
            )
            format_value = pyaudio.paInt16
        else:
            # Use configured settings with fallbacks
            fallback = self.config.get("fallback_settings", {})
            requested_channels = self.config.get(
                "channels", fallback.get("channels", 1)
            )
            self.actual_channels = min(
                requested_channels, int(device_info["maxInputChannels"])
            )
            self.actual_sample_rate = self.config.get(
                "sample_rate", fallback.get("sample_rate", 44100)
            )
            chunk_duration = self.config.get(
                "chunk_duration", fallback.get("chunk_duration", 0.1)
            )
            format_name = self.config.get("format", fallback.get("format", "paInt16"))
            format_value = getattr(pyaudio, format_name)

        # Calculate chunk size based on sample rate
        chunk = int(self.actual_sample_rate * chunk_duration)

        # Store format for WAV writing
        format_map = {
            pyaudio.paInt16: 2,
            pyaudio.paInt24: 3,
            pyaudio.paInt32: 4,
            pyaudio.paFloat32: 4,
        }
        self.actual_sample_width = format_map.get(format_value, 2)

        try:
            # Create audio stream but don't start it yet if in pre-initialize mode
            self.audio_stream = self.audio_p.open(
                format=format_value,
                channels=self.actual_channels,
                rate=self.actual_sample_rate,
                input=True,
                frames_per_buffer=chunk,
                input_device_index=device_idx,
                stream_callback=self.audio_callback,
                start=not pre_initialize,  # Only start if not pre-initializing
            )

            # Clear previous frames
            self.audio_frames = []

            # Create destination folder if it doesn't exist
            os.makedirs(destination, exist_ok=True)

            # Use provided filename or generate one based on subject_id and timestamp
            if filename:
                self.audio_filename = filename
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                suffix = self.config.get("filename_suffix", "_audio")
                self.audio_filename = os.path.join(
                    destination, f"{subject_id}{suffix}_{timestamp}.wav"
                )

            # Only set recording flag and send marker if not pre-initializing
            if not pre_initialize:
                self.recording = True
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.marker_streams.send_audio_start_marker(
                    subject_id,
                    self.audio_filename,
                    timestamp,
                    self.actual_channels,
                    self.actual_sample_rate,
                )
                logging.info(
                    f"Started audio recording: {self.audio_filename} with "
                    f"{self.actual_channels} channels at {self.actual_sample_rate} Hz"
                )
            else:
                logging.info(
                    f"Pre-initialized audio recording setup for: {self.audio_filename}"
                )

            return True

        except Exception as e:
            logging.error(f"Failed to start audio recording: {e}")
            if self.audio_p:
                self.audio_p.terminate()
            return False

    def start_pre_initialized(self, subject_id):
        """Start a pre-initialized audio recording.

        Args:
            subject_id: Identifier for the recording subject.

        Returns:
            Boolean indicating success or failure.
        """
        if not hasattr(self, "audio_stream") or self.audio_stream is None:
            logging.error("No pre-initialized audio recording to start")
            return False

        # Start the stream
        self.audio_stream.start_stream()
        self.recording = True

        # Record exact start time for synchronization
        start_time = datetime.now()
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        iso_timestamp = start_time.isoformat()

        # Send marker with precise timestamp
        self.marker_streams.send_audio_start_marker(
            subject_id,
            self.audio_filename,
            timestamp,
            self.actual_channels,
            self.actual_sample_rate,
            iso_timestamp,
        )

        logging.info(f"Started pre-initialized audio recording at {iso_timestamp}")
        return True

    def stop_recording(self):
        """Stop audio recording and save to WAV file.

        Returns:
            Boolean indicating success or failure.
        """
        if not self.recording:
            logging.warning("No audio recording in progress")
            return False

        try:
            # Stop the stream
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio_p.terminate()

            # Save to WAV file with the actual parameters used
            wf = wave.open(self.audio_filename, "wb")
            wf.setnchannels(self.actual_channels)
            wf.setsampwidth(self.actual_sample_width)
            wf.setframerate(self.actual_sample_rate)
            wf.writeframes(b"".join(self.audio_frames))
            wf.close()

            # Send marker to LSL
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.marker_streams.send_audio_stop_marker(self.audio_filename, timestamp)

            self.recording = False
            logging.info(f"Stopped audio recording: {self.audio_filename}")
            return True

        except Exception as e:
            logging.error(f"Failed to stop audio recording: {e}")
            self.recording = False
            return False
