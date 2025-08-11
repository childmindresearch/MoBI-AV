"""Audio recording module for lab data collection."""

import os
import wave
import logging
from datetime import datetime
from typing import Dict, List, Optional, Union, Any, Tuple, cast

import pyaudio  # type: ignore


class AudioRecorder:
    """Audio recorder with multi-device and synchronized recording support.

    Attributes:
        config: Audio recording configuration dictionary.
        marker_streams: LSL marker streams instance.
        recording: Whether recording is currently in progress.
        audio_streams: PyAudio stream objects keyed by device index.
        audio_p: PyAudio instance for device management.
        audio_frames: Audio frame data lists keyed by device index.
        audio_filenames: Output file paths keyed by device index.
        device_configs: Per-device audio settings and metadata.
        audio_threads: Recording thread objects keyed by device index.
    """

    config: Dict[str, Any]
    marker_streams: Any
    recording: bool
    audio_streams: Dict[Union[int, str], Any]
    audio_p: Optional[pyaudio.PyAudio]
    audio_frames: Dict[Union[int, str], List[bytes]]
    audio_filenames: Dict[Union[int, str], str]
    device_configs: Dict[Union[int, str], Dict[str, Any]]
    audio_threads: Dict[Union[int, str], Any]

    def __init__(self, config: Dict[str, Any], marker_streams: Any) -> None:
        """Initialize audio recorder.

        Args:
            config: Audio recording configuration dictionary.
            marker_streams: LSL marker streams instance.
        """
        self.config = config
        self.marker_streams = marker_streams
        self.recording = False
        self.audio_streams: Dict[Union[int, str], Any] = {}
        self.audio_p: Optional[pyaudio.PyAudio] = None
        self.audio_frames: Dict[Union[int, str], List[bytes]] = {}
        self.audio_filenames: Dict[Union[int, str], str] = {}
        self.device_configs: Dict[Union[int, str], Dict[str, Any]] = {}
        self.audio_threads: Dict[Union[int, str], Any] = {}

    def get_available_devices(self) -> List[Dict[str, Union[int, str]]]:
        """Get available audio input devices.

        Returns:
            List of device dictionaries with index, name, channels, sample_rate,
            and host_api information.
        """
        devices = []
        p = pyaudio.PyAudio()

        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev["maxInputChannels"] > 0:
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

    def find_device(
        self, device_name: str, host_api: list
    ) -> Tuple[Optional[pyaudio.PyAudio], Optional[int]]:
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

    def _start_device_recording(
        self, device_index: Optional[int], filename: str, pre_initialize: bool = False
    ) -> bool:
        """Start recording for a specific device.

        Args:
            device_index: Device index to record from (None for default).
            filename: Output filename for this device.
            pre_initialize: Whether to prepare but not start recording.

        Returns:
            Boolean indicating success.
        """
        try:
            # Get device info if device_index is specified
            if device_index is not None:
                if self.audio_p is None:
                    return False
                device_info = self.audio_p.get_device_info_by_index(device_index)
            else:
                # Find default device using original logic
                device_name = self.config.get("device_name", "Default")
                host_api = self.config.get("host_api", [0, 1, 2, 3])
                temp_p, temp_device_idx = self.find_device(device_name, host_api)
                if temp_device_idx is None:
                    return False
                if self.audio_p is None:
                    return False
                device_info = self.audio_p.get_device_info_by_index(temp_device_idx)
                device_index = temp_device_idx

            use_defaults = self.config.get("use_device_defaults", False)

            # Determine actual parameters based on device capabilities
            if use_defaults:
                # Use the device's default settings
                device_channels = min(int(device_info["maxInputChannels"]), 2)
                device_sample_rate = int(device_info["defaultSampleRate"])
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
                device_channels = min(
                    requested_channels, int(device_info["maxInputChannels"])
                )
                device_sample_rate = self.config.get(
                    "sample_rate", fallback.get("sample_rate", 44100)
                )
                chunk_duration = self.config.get(
                    "chunk_duration", fallback.get("chunk_duration", 0.1)
                )
                format_name = self.config.get(
                    "format", fallback.get("format", "paInt16")
                )
                format_value = getattr(pyaudio, format_name)

            # Calculate chunk size based on sample rate
            chunk = int(device_sample_rate * chunk_duration)

            # Store format for WAV writing
            format_map = {
                pyaudio.paInt16: 2,
                pyaudio.paInt24: 3,
                pyaudio.paInt32: 4,
                pyaudio.paFloat32: 4,
            }
            device_sample_width = format_map.get(format_value, 2)

            # Store device-specific configuration
            device_key = device_index if device_index is not None else "default"
            self.device_configs[device_key] = {
                "channels": device_channels,
                "sample_rate": device_sample_rate,
                "sample_width": device_sample_width,
                "format": format_value,
                "chunk": chunk,
                "device_name": device_info["name"],
            }

            logging.info(
                f"Device {device_index} ({device_info['name']}): {device_channels} channels, {device_sample_rate} Hz"
            )

            # Create audio stream but don't start it yet if in pre-initialize mode
            if self.audio_p is None:
                return False
            stream = self.audio_p.open(
                format=format_value,
                channels=device_channels,
                rate=device_sample_rate,
                input=True,
                frames_per_buffer=chunk,
                input_device_index=device_index,
                stream_callback=lambda in_data,
                frame_count,
                time_info,
                status: self.audio_callback(
                    in_data, frame_count, time_info, status, device_index
                ),
                start=not pre_initialize,  # Only start if not pre-initializing
            )

            # Store stream and initialize frames list for this device
            self.audio_streams[device_key] = stream
            self.audio_frames[device_key] = []
            self.audio_filenames[device_key] = filename

            return True

        except Exception as e:
            logging.error(f"Failed to start recording for device {device_index}: {e}")
            return False

    def audio_callback(
        self,
        in_data: bytes,
        frame_count: int,
        time_info: dict,
        status: int,
        device_index: Optional[int],
    ) -> Tuple[bytes, int]:
        """Callback function for audio stream.

        Args:
            in_data: Audio frame data from PyAudio.
            frame_count: Number of frames in this buffer.
            time_info: Dictionary with timing information.
            status: Status flag from PyAudio.
            device_index: Index of the device providing this data.

        Returns:
            Tuple of (in_data, flag) where flag indicates if more audio is expected.
        """
        if self.recording:
            device_key: Union[int, str] = (
                device_index if device_index is not None else "default"
            )
            if device_key in self.audio_frames:
                self.audio_frames[device_key].append(in_data)
        return (in_data, pyaudio.paContinue)

    def start_recording(
        self,
        subject_id: str,
        destination: str,
        device_index_or_indices: Optional[Union[int, List[int]]] = None,
        pre_initialize: bool = False,
        filename: Optional[str] = None,
    ) -> bool:
        """Start audio recording or prepare for synchronized start.

        Args:
            subject_id: Identifier for the recording subject.
            destination: Directory path where recording will be saved.
            device_index_or_indices: Single device index, list of indices, or None.
            pre_initialize: If True, prepare recording but don't start streaming.
            filename: Optional specific filename to use instead of auto-generated one.

        Returns:
            Boolean indicating success or failure.
        """
        if self.recording:
            logging.warning("Audio recording already in progress")
            return False

        # Handle device indices - convert to list for uniform processing
        if device_index_or_indices is None:
            device_indices: List[Optional[int]] = [None]
        elif isinstance(device_index_or_indices, int):
            device_indices = [device_index_or_indices]
        elif isinstance(device_index_or_indices, list):
            # Cast list[int] to list[Optional[int]] for mypy (contents are ints)
            device_indices = cast(List[Optional[int]], list(device_index_or_indices))
        else:
            logging.error("Invalid device indices specification type")
            return False

        # Initialize PyAudio once
        self.audio_p = pyaudio.PyAudio()

        # Clear previous data
        self.audio_streams = {}
        self.audio_frames = {}
        self.audio_filenames = {}
        self.device_configs = {}
        self.audio_threads = {}

        success_count = 0
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for device_index in device_indices:
            try:
                device_name = "default"
                if device_index is not None and self.audio_p is not None:
                    device_info = self.audio_p.get_device_info_by_index(device_index)
                    device_name = (
                        "".join(
                            c
                            for c in device_info["name"]
                            if c.isalnum() or c in (" ", "-", "_")
                        )
                        .strip()
                        .replace(" ", "_")
                    )
                os.makedirs(destination, exist_ok=True)
                if filename and len(device_indices) == 1:
                    device_filename = filename
                elif len(device_indices) > 1:
                    device_filename = os.path.join(
                        destination, f"{subject_id}_{device_name}_{timestamp}.wav"
                    )
                else:
                    suffix = self.config.get("filename_suffix", "_audio")
                    device_filename = os.path.join(
                        destination, f"{subject_id}{suffix}_{timestamp}.wav"
                    )
                if self._start_device_recording(
                    device_index, device_filename, pre_initialize
                ):
                    success_count += 1
                    logging.info(
                        f"Started recording from device {device_index or 'default'}: {device_filename}"
                    )
                else:
                    logging.error(
                        f"Failed to start recording from device {device_index or 'default'}"
                    )
            except Exception as e:  # noqa: BLE001
                logging.error(
                    f"Error starting recording for device {device_index}: {e}"
                )
        if success_count > 0:
            self.recording = not pre_initialize
            if not pre_initialize:
                first_filename = next(iter(self.audio_filenames.values()))
                first_device_key = next(iter(self.device_configs.keys()))
                first_device_config = self.device_configs[first_device_key]
                self.marker_streams.send_audio_start_marker(
                    subject_id,
                    first_filename,
                    timestamp,
                    first_device_config["channels"],
                    first_device_config["sample_rate"],
                )
            return True
        if self.audio_p:
            self.audio_p.terminate()
        logging.error("Failed to start recording on any device")
        return False

    def start_pre_initialized(self, subject_id: str) -> bool:
        """Start a pre-initialized audio recording.

        Args:
            subject_id: Identifier for the recording subject.

        Returns:
            Boolean indicating success or failure.
        """
        if not self.audio_streams:
            logging.error("No pre-initialized audio recording to start")
            return False

        success_count = 0

        # Start all pre-initialized streams
        for device_key, stream in self.audio_streams.items():
            try:
                stream.start_stream()
                success_count += 1
            except Exception as e:
                logging.error(
                    f"Failed to start pre-initialized stream for device {device_key}: {e}"
                )

        if success_count > 0:
            self.recording = True

            # Record exact start time for synchronization
            start_time = datetime.now()
            timestamp = start_time.strftime("%Y%m%d_%H%M%S")
            iso_timestamp = start_time.isoformat()

            # Send marker with precise timestamp using first device
            first_filename = next(iter(self.audio_filenames.values()))
            first_device_key = next(iter(self.device_configs.keys()))
            first_device_config = self.device_configs[first_device_key]

            self.marker_streams.send_audio_start_marker(
                subject_id,
                first_filename,
                timestamp,
                first_device_config["channels"],
                first_device_config["sample_rate"],
                iso_timestamp,
            )

            logging.info(f"Started pre-initialized audio recording at {iso_timestamp}")
            return True
        else:
            logging.error("Failed to start any pre-initialized audio streams")
            return False

    def stop_recording(self) -> bool:
        """Stop audio recording and save to WAV file(s).

        Returns:
            Boolean indicating success or failure.
        """
        if not self.recording:
            logging.warning("No audio recording in progress")
            return False

        try:
            self.recording = False
            success_count = 0

            # Stop and save each device's recording
            for device_key, stream in self.audio_streams.items():
                device_key_typed: Union[int, str] = cast(Union[int, str], device_key)
                try:
                    stream.stop_stream()
                    stream.close()
                    device_config = self.device_configs[device_key_typed]
                    filename = self.audio_filenames[device_key_typed]
                    frames = self.audio_frames[device_key_typed]
                    wf = wave.open(filename, "wb")
                    wf.setnchannels(device_config["channels"])
                    wf.setsampwidth(device_config["sample_width"])
                    wf.setframerate(device_config["sample_rate"])
                    wf.writeframes(b"".join(frames))
                    wf.close()
                    logging.info(
                        f"Stopped audio recording: {filename} ({device_config['device_name']}, {device_config['sample_rate']} Hz)"
                    )
                    success_count += 1
                except Exception as e:  # noqa: BLE001
                    logging.error(
                        f"Error stopping recording for device {device_key}: {e}"
                    )

            # Terminate PyAudio
            if self.audio_p:
                self.audio_p.terminate()

            # Send marker to LSL if at least one recording succeeded
            if success_count > 0:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                first_filename = next(iter(self.audio_filenames.values()))
                self.marker_streams.send_audio_stop_marker(first_filename, timestamp)

            # Clear data structures
            self.audio_streams = {}
            self.audio_frames = {}
            self.audio_filenames = {}
            self.device_configs = {}
            self.audio_threads = {}

            return success_count > 0

        except Exception as e:
            logging.error(f"Failed to stop audio recording: {e}")
            self.recording = False
            return False
