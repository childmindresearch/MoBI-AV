"""Screen recording module for lab data collection."""

import logging
import os
import platform
import queue
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import cv2  # type: ignore[import-not-found, import-untyped]
import imageio
import mss
import numpy as np
import pylsl


class ScreenRecorder:
    """Capture a selected monitor and encode it as an MP4 recording."""

    config: Dict[str, Any]
    marker_streams: Any
    recording: bool
    video_filename: Optional[str]
    capture_thread: Optional[threading.Thread]
    writer_thread: Optional[threading.Thread]
    frame_queue: queue.Queue

    def __init__(self, config: Dict[str, Any], marker_streams: Any) -> None:
        self.config = config
        self.marker_streams = marker_streams
        self.recording = False
        self.video_filename = None
        self.sct = mss.mss()
        self.frame_queue = queue.Queue(maxsize=150)
        self.capture_thread = None
        self.writer_thread = None
        self.worker_failed = False

    def get_available_screens(self) -> List[Dict[str, Any]]:
        """Return the combined desktop and individual monitors."""
        screens = []
        for index, monitor in enumerate(self.sct.monitors):
            name = "All Screens Combined" if index == 0 else f"Monitor {index}"
            screens.append(
                {
                    "index": index,
                    "name": name,
                    "width": monitor["width"],
                    "height": monitor["height"],
                }
            )
        return screens

    def _get_candidate_codecs(self) -> List[Dict[str, Any]]:
        """Return platform-preferred FFmpeg encoders with a portable fallback."""
        if platform.system() == "Windows":
            return [
                {
                    "codec": "h264_nvenc",
                    "params": ["-preset", "p6", "-cq", "15", "-b:v", "0"],
                },
                {
                    "codec": "h264_qsv",
                    "params": ["-preset", "veryfast", "-global_quality", "15"],
                },
                {
                    "codec": "h264_amf",
                    "params": [
                        "-quality",
                        "quality",
                        "-rc",
                        "cqp",
                        "-qp_i",
                        "15",
                        "-qp_p",
                        "15",
                    ],
                },
                {"codec": "libx264", "params": ["-preset", "veryfast", "-crf", "15"]},
            ]
        if platform.system() == "Darwin":
            return [
                {"codec": "h264_videotoolbox", "params": ["-b:v", "25M"]},
                {"codec": "libx264", "params": ["-preset", "veryfast", "-crf", "15"]},
            ]
        return [{"codec": "libx264", "params": ["-preset", "veryfast", "-crf", "15"]}]

    def _open_writer(self, filename: str, fps: int) -> Any:
        """Open the first available configured MP4 encoder."""
        errors = []
        for candidate in self._get_candidate_codecs():
            try:
                writer = imageio.get_writer(
                    filename,
                    fps=fps,
                    codec=candidate["codec"],
                    quality=None,
                    pixelformat="yuv420p",
                    macro_block_size=1,
                    output_params=candidate["params"],
                )
                logging.info(
                    "Initialized screen video writer with codec %s",
                    candidate["codec"],
                )
                return writer
            except Exception as exc:
                errors.append(f"{candidate['codec']}: {exc}")
                logging.warning(
                    "Screen video codec %s failed: %s",
                    candidate["codec"],
                    exc,
                )
        raise RuntimeError(
            "Unable to initialize a screen video encoder: " + "; ".join(errors)
        )

    def start_recording(
        self, subject_id: str, destination: str, monitor_index: int = 1
    ) -> bool:
        """Start recording the selected monitor."""
        if self.active:
            logging.warning("Screen recording already in progress")
            return False
        if monitor_index < 0 or monitor_index >= len(self.sct.monitors):
            logging.error("Screen monitor index %s is out of range", monitor_index)
            return False

        writer = None
        writer_started = False
        try:
            os.makedirs(destination, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(
                destination, f"{subject_id}_screen_{timestamp}.mp4"
            )
            fps = int(self.config.get("fps", 30))
            if fps <= 0:
                raise ValueError("Screen recording FPS must be greater than zero")
            writer = self._open_writer(filename, fps)
            monitor = dict(self.sct.monitors[monitor_index])
            self.frame_queue = queue.Queue(maxsize=150)
            self.video_filename = filename
            self.worker_failed = False
            self.recording = True
            self.writer_thread = threading.Thread(
                target=self._writer_thread,
                args=(writer, subject_id),
                daemon=True,
            )
            self.capture_thread = threading.Thread(
                target=self._capture_thread,
                args=(monitor, fps),
                daemon=True,
            )
            self.writer_thread.start()
            writer_started = True
            self.capture_thread.start()
            logging.info(
                "Started screen recording on monitor %s (%sx%s): %s",
                monitor_index,
                monitor["width"],
                monitor["height"],
                filename,
            )
            return True
        except Exception as exc:
            self.recording = False
            if writer is not None and not writer_started:
                try:
                    writer.close()
                except Exception:
                    logging.exception("Failed to close screen video writer")
            logging.error("Failed to start screen recording: %s", exc, exc_info=True)
            return False

    def _capture_thread(self, monitor: Dict[str, Any], fps: int) -> None:
        frame_interval = 1.0 / fps
        while self.recording:
            start_time = time.perf_counter()
            try:
                raw_frame = np.array(self.sct.grab(monitor))
                rgb_frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGRA2RGB)
                frame_timestamp = pylsl.local_clock()
                try:
                    self.frame_queue.put((rgb_frame, frame_timestamp), block=False)
                except queue.Full:
                    logging.warning("Screen encoding queue full; dropping frame")
            except Exception:
                logging.exception("Failed to capture screen frame")
                self.worker_failed = True
                self.recording = False
                break

            sleep_time = frame_interval - (time.perf_counter() - start_time)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _writer_thread(self, writer: Any, subject_id: str) -> None:
        first_written_frame = True
        last_frame_timestamp: Optional[float] = None
        try:
            while self.recording or not self.frame_queue.empty():
                try:
                    frame, captured_at = self.frame_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                writer.append_data(frame)
                last_frame_timestamp = captured_at
                if first_written_frame:
                    self.marker_streams.send_screen_start_marker(
                        subject_id, captured_at
                    )
                    first_written_frame = False
        except Exception:
            logging.exception("Failed while encoding screen recording")
            self.worker_failed = True
            self.recording = False
        finally:
            try:
                writer.close()
            except Exception:
                self.worker_failed = True
                logging.exception("Failed to close screen video writer")
            if last_frame_timestamp is not None:
                try:
                    self.marker_streams.send_screen_stop_marker(last_frame_timestamp)
                except Exception:
                    self.worker_failed = True
                    logging.exception("Failed to send screen recording stop marker")
            logging.info("Screen recording saved to %s", self.video_filename)

    def stop_recording(self) -> bool:
        """Stop capture, flush queued frames, and close the MP4 writer."""
        if not self.active:
            logging.warning("No screen recording in progress")
            return False

        self.recording = False
        if self.capture_thread is not None:
            self.capture_thread.join()
        if self.writer_thread is not None:
            self.writer_thread.join()
        self.capture_thread = None
        self.writer_thread = None
        success = not self.worker_failed
        self.worker_failed = False
        return success

    @property
    def active(self) -> bool:
        """Return whether recording or recorder worker threads are still active."""
        return self.recording or self.worker_failed or any(
            thread is not None and thread.is_alive()
            for thread in (self.capture_thread, self.writer_thread)
        )
