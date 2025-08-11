"""Video recording module for lab data collection.

This module provides video recording capabilities using OpenCV, with support
for device selection and LSL marker synchronization.
"""

import os
import cv2  # type: ignore[import-not-found, import-untyped]
import logging
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Any


class VideoRecorder:
    """Video recorder supporting multiple devices and synchronized recordings.

    Attributes:
        config: Video recording configuration.
        marker_streams: MarkerStreams instance for sending LSL markers.
        recording: Boolean indicating if recording is in progress.
        thread_active: Boolean indicating if recording thread is running.
        video_capture: OpenCV VideoCapture object.
        video_writer: OpenCV VideoWriter object.
        video_filename: Path to the current recording file.
        actual_fps: Actual frames per second being used for recording.
        show_preview: Boolean indicating if preview window should be shown.
        preview_thread: Thread for preview window updates.
        preview_active: Boolean indicating if preview thread is running.
    """

    config: Dict[str, Any]
    marker_streams: Any
    recording: bool
    thread_active: bool
    video_capture: Optional[cv2.VideoCapture]
    video_writer: Optional[cv2.VideoWriter]
    video_filename: Optional[str]
    actual_fps: Optional[float]
    show_preview: bool
    preview_thread: Optional[threading.Thread]
    preview_active: bool
    latest_preview_frame: Optional[Any]

    def __init__(self, config: Dict[str, Any], marker_streams: Any) -> None:
        """Initialize the video recorder.

        Args:
            config: Dictionary containing video recording settings.
            marker_streams: MarkerStreams instance for sending LSL markers.
        """
        self.config = config
        self.marker_streams = marker_streams
        self.recording = False
        self.thread_active = False
        self.video_capture = None
        self.video_writer = None
        self.video_filename = None
        self.actual_fps = None
        self.show_preview = False
        self.preview_thread = None
        self.preview_active = False
        self.latest_preview_frame = None

    def get_available_devices(self) -> List[Dict[str, Any]]:
        """Get a list of available video capture devices.

        Returns:
            List of dictionaries containing device information.
            Each dictionary includes: index and name.
        """
        devices = []

        # Try to detect multiple cameras by testing indices 0-5
        for i in range(6):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                # Try to read a frame to confirm it's working
                ret, frame = cap.read()
                if ret and frame is not None:
                    # Get some basic info about the camera
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = int(cap.get(cv2.CAP_PROP_FPS))

                    if i == 0:
                        name = f"Camera 0 (Default) - {width}x{height}@{fps}fps"
                    else:
                        name = f"Camera {i} - {width}x{height}@{fps}fps"

                    devices.append({"index": i, "name": name})
                    logging.info(f"Found video device {i}: {name}")
                cap.release()

        # Add a fallback option if no cameras detected
        if not devices:
            devices.append({"index": 0, "name": "Default Camera (may not work)"})
            logging.warning("No video devices detected, added fallback option")

        return devices

    def start_recording(
        self,
        subject_id: str,
        destination: str,
        device_index: Optional[int] = None,
        pre_initialize: bool = False,
        filename: Optional[str] = None,
    ) -> bool:
        """Start video recording or prepare for synchronized start.

        Args:
            subject_id: Identifier for the recording subject.
            destination: Directory path where recording will be saved.
            device_index: Optional device index to use, otherwise uses default.
            pre_initialize: If True, prepare recording but don't start thread.
            filename: Optional specific filename to use instead of auto-generated one.

        Returns:
            Boolean indicating success or failure.
        """
        if self.recording and not pre_initialize:
            logging.warning("Video recording already in progress")
            return False

        try:
            # Create destination folder if it doesn't exist
            os.makedirs(destination, exist_ok=True)

            # Initialize camera with specified device index
            camera_index = 0 if device_index is None else device_index

            # Use existing capture if preview is active, otherwise create new one
            if not self.video_capture or not self.video_capture.isOpened():
                self.video_capture = cv2.VideoCapture(camera_index)

            self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config["width"])
            self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config["height"])

            if not self.video_capture.isOpened():
                logging.error(f"Could not open video device at index {camera_index}")
                return False

            # Query camera's actual capabilities
            actual_fps = self.video_capture.get(cv2.CAP_PROP_FPS)
            if actual_fps > 0 and actual_fps < self.config["fps"]:
                logging.info(
                    f"Camera reports actual FPS of {actual_fps}, "
                    f"adjusting from requested {self.config['fps']}"
                )
                self.actual_fps = actual_fps
            else:
                self.actual_fps = self.config["fps"]

            # Use provided filename or generate one based on subject_id and timestamp
            if filename:
                self.video_filename = filename
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                suffix = self.config.get("filename_suffix", "_video")
                self.video_filename = os.path.join(
                    destination, f"{subject_id}{suffix}_{timestamp}.mp4"
                )

            # For synchronization
            self.video_start_time = datetime.now()

            # Create video writer with adjusted frame rate
            fourcc = cv2.VideoWriter_fourcc(*self.config["codec"])
            self.video_writer = cv2.VideoWriter(
                self.video_filename,
                fourcc,
                self.actual_fps,
                (self.config["width"], self.config["height"]),
            )

            # Wait for camera to warm up and capture first frame
            warm_up_success = False
            for _ in range(10):  # Try 10 times to get first frame
                ret, frame = self.video_capture.read()
                if ret:
                    # Got first frame!
                    warm_up_success = True
                    # Only write the first frame if not pre-initializing
                    if not pre_initialize:
                        self.video_writer.write(frame)
                    break
                time.sleep(0.1)  # Short delay between attempts

            if not warm_up_success:
                logging.warning(
                    "Camera couldn't provide first frame, recording may be delayed"
                )

            # Start the recording thread only if not pre-initializing
            if not pre_initialize:
                self.recording = True
                self.thread_active = True

                self.video_thread = threading.Thread(target=self._recording_thread)
                self.video_thread.daemon = True
                self.video_thread.start()

                # Record exact start time after warm-up for precise synchronization
                self.exact_video_start = datetime.now()
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                # Send marker to LSL with timestamp
                self.marker_streams.send_video_start_marker(
                    subject_id,
                    self.video_filename,
                    timestamp,
                    self.exact_video_start.isoformat(),
                    self.actual_fps,
                )

                logging.info(
                    f"Started video recording: {self.video_filename} at "
                    f"{self.exact_video_start.isoformat()} with {self.actual_fps} fps"
                )
            else:
                logging.info(
                    f"Pre-initialized video recording for: {self.video_filename}"
                )

            return True

        except Exception as e:
            logging.error(f"Failed to start video recording: {e}")
            if self.video_capture:
                self.video_capture.release()
            return False

    def start_pre_initialized(self, subject_id: str) -> bool:
        """Start a pre-initialized video recording.

        Args:
            subject_id: Identifier for the recording subject.

        Returns:
            Boolean indicating success or failure.
        """
        if not hasattr(self, "video_capture") or self.video_capture is None:
            logging.error("No pre-initialized video recording to start")
            return False

        # Start the recording thread
        self.recording = True
        self.thread_active = True

        self.video_thread = threading.Thread(target=self._recording_thread)
        self.video_thread.daemon = True
        self.video_thread.start()

        # Record exact start time for synchronization
        start_time = datetime.now()
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        iso_timestamp = start_time.isoformat()

        # Send marker
        self.marker_streams.send_video_start_marker(
            subject_id, self.video_filename, timestamp, iso_timestamp, self.actual_fps
        )

        logging.info(f"Started pre-initialized video recording at {iso_timestamp}")
        return True

    def _recording_thread(self) -> None:
        """Thread function for continuous video recording.

        This method runs in a separate thread and continuously reads frames
        from the camera and writes them to the video file until stopped.
        """
        # Guard required resources for type checking
        if self.video_capture is None or self.video_writer is None:
            logging.error("Video resources not initialized")
            return
        if self.actual_fps is None:
            self.actual_fps = float(self.config.get("fps", 30))
        target_fps: float = float(self.actual_fps)
        frame_time_ms = 1000.0 / target_fps if target_fps > 0 else 0.0
        frame_count = 0
        start_time = datetime.now()
        frame_times: List[datetime] = []

        while self.thread_active and self.recording:
            if self.video_capture is None or self.video_writer is None:
                break
            frame_start = datetime.now()
            try:
                ret, frame = self.video_capture.read()
                if ret and frame is not None:
                    frame_time = datetime.now()
                    frame_times.append(frame_time)
                    if self.config.get("show_timestamp", False):
                        ts = frame_time.strftime("%H:%M:%S.%f")[:-3]
                        info = f"Frame: {frame_count} | {ts}"
                        cv2.putText(
                            frame,
                            info,
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 0),
                            2,
                        )
                    self.video_writer.write(frame)
                    frame_count += 1
                    if self.show_preview:
                        self.latest_preview_frame = frame.copy()
                    if frame_count % 100 == 0:
                        elapsed = (frame_time - start_time).total_seconds()
                        fps = frame_count / elapsed if elapsed > 0 else 0.0
                        logging.info(
                            f"Video recording: {frame_count} frames, {fps:.2f} fps"
                        )
                    frame_end = datetime.now()
                    process_time = (frame_end - frame_start).total_seconds() * 1000.0
                    sleep_time = max(0.0, frame_time_ms - process_time)
                    if sleep_time > 0:
                        time.sleep(sleep_time / 1000.0)
                else:
                    logging.warning("Failed to capture video frame, attempting recover")
                    time.sleep(0.01)
                    recover_attempts = 0
                    max_attempts = 30
                    while (
                        recover_attempts < max_attempts
                        and self.thread_active
                        and self.video_capture is not None
                        and self.video_writer is not None
                    ):
                        ret, frame = self.video_capture.read()
                        if ret and frame is not None:
                            frame_time = datetime.now()
                            frame_times.append(frame_time)
                            if self.config.get("show_timestamp", False):
                                ts = frame_time.strftime("%H:%M:%S.%f")[:-3]
                                info = f"Frame: {frame_count} | {ts} (recovered)"
                                cv2.putText(
                                    frame,
                                    info,
                                    (10, 30),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.7,
                                    (0, 255, 0),
                                    2,
                                )
                            self.video_writer.write(frame)
                            frame_count += 1
                            break
                        time.sleep(0.01)
                        recover_attempts += 1
                    if recover_attempts >= max_attempts:
                        logging.error("Failed to recover video recording")
                        break
            except Exception as e:  # noqa: BLE001
                logging.error(f"Error in video recording thread: {e}")
                break
        if frame_times and hasattr(self, "video_start_time"):
            first_delay = (frame_times[0] - self.video_start_time).total_seconds()
            avg_interval = (
                (frame_times[-1] - frame_times[0]).total_seconds()
                / (len(frame_times) - 1)
                if len(frame_times) > 1
                else 0.0
            )
            actual_fps = 1.0 / avg_interval if avg_interval > 0 else 0.0
            logging.info(
                f"Video statistics: first frame delay={first_delay:.3f}s, actual fps={actual_fps:.2f}"
            )
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        expected_frames = target_fps * duration
        frame_difference = expected_frames - frame_count
        logging.info(f"Video recording thread ended after {duration:.2f} seconds")
        logging.info(
            f"Captured {frame_count} frames (expected ~{int(expected_frames)}, difference: {int(frame_difference)})"
        )
        if duration > 0:
            logging.info(
                f"Average FPS: {frame_count / duration:.2f} (target: {target_fps})"
            )

    def stop_recording(self) -> bool:
        """Stop video recording and release resources.

        Returns:
            Boolean indicating success or failure.
        """
        if not self.recording:
            logging.warning("No video recording in progress")
            return False

        try:
            # Signal the thread to stop
            self.thread_active = False
            self.recording = False

            # Wait longer for thread to finish
            if hasattr(self, "video_thread"):
                logging.info("Waiting for video thread to complete...")
                self.video_thread.join(timeout=5.0)  # Increased timeout

                if self.video_thread.is_alive():
                    logging.warning(
                        "Video thread did not terminate gracefully, "
                        "forcing resources to close"
                    )

            # Release resources
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None

            # Don't release video_capture if preview is still active
            if self.video_capture and not self.show_preview:
                self.video_capture.release()
                self.video_capture = None

            # Send marker to LSL
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.marker_streams.send_video_stop_marker(self.video_filename, timestamp)

            logging.info(f"Stopped video recording: {self.video_filename}")
            return True

        except Exception as e:
            logging.error(f"Error stopping video recording: {e}")
            import traceback

            logging.error(traceback.format_exc())
            self.recording = False
            return False

    def toggle_preview(self) -> bool:
        """Toggle the video preview window on/off.

        Returns:
            Boolean indicating the new preview state.
        """
        if self.show_preview:
            self.stop_preview()
        else:
            self.start_preview()
        return self.show_preview

    def start_preview(self) -> bool:
        """Start the video preview window."""
        if self.preview_active:
            return True

        # Initialize video capture if not already done
        if not self.video_capture:
            # Use the device index set by GUI, or default to first available
            device_index = getattr(self, "preview_device_index", 0)
            if device_index is None:
                devices = self.get_available_devices()
                if not devices:
                    logging.error("No video devices available for preview")
                    return False
                device_index = devices[0]["index"]

            self.video_capture = cv2.VideoCapture(device_index)

            if not self.video_capture.isOpened():
                logging.error(f"Could not open video device {device_index} for preview")
                return False

            # Set preview resolution
            self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config["width"])
            self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config["height"])

        self.show_preview = True
        self.preview_active = True

        # Start preview thread
        self.preview_thread = threading.Thread(target=self._preview_thread)
        self.preview_thread.daemon = True
        self.preview_thread.start()

        logging.info("Started video preview")
        return True

    def stop_preview(self) -> bool:
        """Stop the video preview window."""
        if not self.preview_active:
            return True

        self.show_preview = False
        self.preview_active = False

        # Wait for preview thread to finish
        if self.preview_thread and self.preview_thread.is_alive():
            self.preview_thread.join(timeout=2.0)

        # Clean up frame reference
        self.latest_preview_frame = None

        # Close OpenCV window
        try:
            cv2.destroyWindow("Video Preview")
        except Exception:
            pass

        # Only release capture if not recording
        if not self.recording and self.video_capture:
            self.video_capture.release()
            self.video_capture = None

        logging.info("Stopped video preview")
        return True

    def _preview_thread(self) -> None:
        """Thread function for video preview at 5fps."""
        preview_fps = 5  # Low fps for preview to minimize impact
        frame_interval = 1.0 / preview_fps

        while self.preview_active and self.show_preview:
            try:
                if self.video_capture and self.video_capture.isOpened():
                    ret, frame = self.video_capture.read()
                    if ret:
                        # Resize frame for preview window
                        display_frame = cv2.resize(frame, (640, 480))

                        # Add status text
                        status_text = (
                            "RECORDING" if self.recording else "PREVIEW - 5 FPS"
                        )
                        text_color = (0, 0, 255) if self.recording else (0, 255, 0)

                        cv2.putText(
                            display_frame,
                            status_text,
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            text_color,
                            2,
                        )

                        # Store the frame for main thread display
                        self.latest_preview_frame = display_frame.copy()

                time.sleep(frame_interval)

            except Exception as e:
                logging.error(f"Error in preview thread: {e}")
                break

        # Clean up when thread ends
        self.latest_preview_frame = None

    def get_preview_frame(self) -> Optional[Any]:
        """Get the latest preview frame for display.

        Returns:
            OpenCV frame if available, None otherwise.
        """
        return self.latest_preview_frame

    def show_preview_window(self) -> Optional[bool]:
        """Show the preview frame in an OpenCV window.

        This should be called from the main thread to avoid macOS threading issues.
        """
        if self.show_preview and self.latest_preview_frame is not None:
            cv2.imshow("Video Preview", self.latest_preview_frame)

            # Check for window close or ESC key
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC key
                self.stop_preview()
                return False

            # Check if window was closed
            try:
                if cv2.getWindowProperty("Video Preview", cv2.WND_PROP_VISIBLE) < 1:
                    self.stop_preview()
                    return False
            except cv2.error:
                # Window was closed
                self.stop_preview()
                return False

        return True
