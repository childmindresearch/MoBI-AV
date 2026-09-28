"""Screen capture with an explicit LSL timestamp for each encoded frame.

The MP4 has a nominal constant frame rate. Its accompanying CSV is the timing
reference; playback time alone is not experimental time. MSS and FFmpeg resources
belong to their worker threads. Public lifecycle methods are serialized.
"""

import csv
import json
import logging
import math
import queue
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from pylsl import local_clock

LOGGER = logging.getLogger(__name__)


class ScreenRecorder:
    """Record one monitor (or monitor 0, the combined desktop).

    ``marker_streams`` is the application's shared MarkerStreams instance.
    Optional capture dependencies are imported only when screen capture is used.
    ``stop_recording`` must be called even after an asynchronous failure.
    """

    def __init__(self, config: Dict[str, Any], marker_streams: Any) -> None:
        self.config = config
        self.marker_streams = marker_streams
        self.fps = float(config.get("fps", 30))
        if not math.isfinite(self.fps) or self.fps <= 0:
            raise ValueError("Screen fps must be positive and finite")
        self.queue_size = int(config.get("queue_size", 8))
        if self.queue_size < 1:
            raise ValueError("Screen queue_size must be positive")
        self.recording = False
        self.last_error: Optional[str] = None
        self.video_filename: Optional[str] = None
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._gate = threading.Event()
        self._ready = threading.Event()
        self._first_frame = threading.Event()

    @staticmethod
    def get_available_screens() -> List[Dict[str, Any]]:
        """Enumerate monitors without sharing an MSS handle between threads."""
        import mss

        with mss.mss() as capture:
            return [
                dict(
                    index=index,
                    name="All screens" if index == 0 else f"Monitor {index}",
                    **monitor,
                )
                for index, monitor in enumerate(capture.monitors)
            ]

    @property
    def active(self) -> bool:
        """Whether preparation, capture, or finalization still owns resources."""
        return self._thread is not None and self._thread.is_alive()

    def start_recording(
        self,
        subject_id: str,
        destination: str,
        monitor_index: int = 1,
        pre_initialize: bool = False,
        filename: Optional[str] = None,
    ) -> bool:
        """Prepare capture and encoder; optionally start immediately.

        Returns False if preparation or the first frame fails. Existing output
        files are never overwritten. Calls from the GUI should run off its thread.
        """
        with self._lock:
            if self.active:
                LOGGER.warning("Screen recorder is already active")
                return False
            self.last_error = None
            self._stop.clear()
            self._gate.clear()
            self._ready.clear()
            self._first_frame.clear()
            self._frames: queue.Queue = queue.Queue(maxsize=self.queue_size)
            self._written = 0
            self._dropped = 0
            self._captured = 0
            self._shape = None
            self._session_id = uuid.uuid4().hex
            self._subject_id = subject_id
            try:
                if not subject_id or any(c in subject_id for c in "/\\\x00"):
                    raise ValueError(
                        "Subject ID must be nonempty and contain no path separators"
                    )
                if not isinstance(monitor_index, int) or monitor_index < 0:
                    raise ValueError("Monitor index must be a nonnegative integer")
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                path = (
                    Path(filename)
                    if filename
                    else Path(destination) / f"{subject_id}_screen_{stamp}.mp4"
                )
                if path.suffix.lower() != ".mp4":
                    raise ValueError("Screen video filename must end in .mp4")
                path.parent.mkdir(parents=True, exist_ok=True)
                self.video_filename = str(path)
                self._csv_path = path.with_suffix(".frames.csv")
                self._metadata_path = path.with_suffix(".json")
                # Reserve all three paths before starting any worker.
                reserved = []
                try:
                    for output in (path, self._csv_path, self._metadata_path):
                        with output.open("x"):
                            pass
                        reserved.append(output)
                except Exception:
                    for output in reserved:
                        output.unlink()
                    raise
                self._thread = threading.Thread(
                    target=self._capture, args=(monitor_index,), name="screen-capture"
                )
                self._thread.start()
                if not self._ready.wait(float(self.config.get("startup_timeout", 15))):
                    raise TimeoutError("Timed out preparing screen capture")
                if self.last_error:
                    self.stop_recording()
                    return False
                if pre_initialize:
                    return True
                return self.start_pre_initialized(subject_id)
            except Exception as exc:
                self._fail(exc)
                self.stop_recording()
                return False

    def start_pre_initialized(self, subject_id: str) -> bool:
        """Release capture and wait until its first frame has reached the encoder."""
        with self._lock:
            if (
                not self.active
                or self.recording
                or self.last_error
                or subject_id != self._subject_id
            ):
                return False
            self.recording = True
            self._gate.set()
            if not self._first_frame.wait(
                float(self.config.get("startup_timeout", 15))
            ):
                self._fail(TimeoutError("No screen frame reached the encoder"))
            if self.last_error or not self._written:
                self.stop_recording()
                return False
            return True

    def request_stop(self) -> None:
        """Signal capture to stop without waiting for the encoder to drain."""
        self._stop.set()
        self._gate.set()

    def stop_recording(self) -> bool:
        """Stop capture, drain queued frames, and check FFmpeg finalization."""
        with self._lock:
            self.request_stop()
            if self._thread is not None:
                self._thread.join(float(self.config.get("shutdown_timeout", 30)))
                if self._thread.is_alive():
                    self._fail(
                        TimeoutError("Screen worker is still finalizing; retry Stop")
                    )
                    return False
            self.recording = False
            return self.last_error is None

    def _fail(self, exc: Exception) -> None:
        if self.last_error is None:
            self.last_error = str(exc)
        LOGGER.error("Screen recording failed: %s", exc)
        self.request_stop()

    def _command(
        self, executable: str, width: int, height: int, output: str
    ) -> List[str]:
        # Software H.264 is predictable across Windows and macOS. Probe it before
        # reporting readiness; merely constructing an imageio writer is lazy.
        return [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(self.fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "15",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            output,
        ]

    def _capture(self, monitor_index: int) -> None:
        writer_thread = None
        monitor: Dict[str, Any] = {}
        try:
            import imageio_ffmpeg
            import mss

            self._check_capture_permission()
            executable = imageio_ffmpeg.get_ffmpeg_exe()
            with mss.mss() as capture:
                if monitor_index >= len(capture.monitors):
                    raise ValueError(f"Monitor {monitor_index} is not available")
                monitor = dict(capture.monitors[monitor_index])
                # Test permissions/capture in the same thread that will grab.
                sample = np.asarray(capture.grab(monitor))[:, :, :3][:, :, ::-1].copy()
                height, width = sample.shape[:2]
                self._shape = sample.shape
                self._monitor = dict(index=monitor_index, **monitor)
                with tempfile.TemporaryDirectory(prefix="mobi-screen-") as temp:
                    result = subprocess.run(
                        self._command(
                            executable, width, height, str(Path(temp) / "probe.mp4")
                        ),
                        input=sample.tobytes(),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        timeout=10,
                        check=False,
                        **self._process_options(),
                    )
                    if result.returncode:
                        raise RuntimeError(
                            result.stderr.decode("utf-8", errors="replace")
                        )
                writer_thread = threading.Thread(
                    target=self._write,
                    args=(executable, width, height),
                    name="screen-writer",
                )
                writer_thread.start()
                self._ready.set()
                self._gate.wait()
                deadline = time.perf_counter()
                while not self._stop.is_set():
                    begin = local_clock()
                    raw = capture.grab(monitor)
                    end = local_clock()
                    frame = np.asarray(raw)[:, :, :3][:, :, ::-1].copy()
                    if frame.shape != self._shape:
                        raise RuntimeError("Screen resolution changed during recording")
                    capture_index = self._captured
                    self._captured += 1
                    try:
                        self._frames.put_nowait((frame, capture_index, begin, end))
                    except queue.Full:
                        self._dropped += 1
                    # Do not burst to catch up after a slow grab.
                    deadline = max(deadline + 1 / self.fps, time.perf_counter())
                    self._stop.wait(max(0.0, deadline - time.perf_counter()))
        except Exception as exc:
            self._fail(exc)
        finally:
            self._ready.set()
            if writer_thread is not None:
                while writer_thread.is_alive():
                    try:
                        self._frames.put(None, timeout=0.1)
                        break
                    except queue.Full:
                        continue
                writer_thread.join()
            self.recording = False
            try:
                metadata = {
                    "schema_version": 1,
                    "session_id": self._session_id,
                    "subject_id": self._subject_id,
                    "video": self.video_filename,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "monitor": dict(index=monitor_index, **monitor),
                    "capture_shape": getattr(self, "_shape", None),
                    "nominal_fps": self.fps,
                    "codec": "libx264",
                    "crf": 15,
                    "captured_frames": self._captured,
                    "written_frames": self._written,
                    "queue_dropped_frames": self._dropped,
                    "status": "failed"
                    if self.last_error
                    else ("complete" if self._written else "cancelled"),
                    "error": self.last_error,
                    "timestamp_method": "midpoint of pylsl.local_clock before/after MSS grab",
                    "timing_reference": self._csv_path.name,
                    "playback": "constant frame rate; use CSV/XDF frame mapping for experimental time",
                }
                self._metadata_path.write_text(
                    json.dumps(metadata, indent=2), encoding="utf-8"
                )
            except Exception as exc:
                self._fail(exc)
            self._first_frame.set()

    @staticmethod
    def _check_capture_permission() -> None:
        """Reject macOS permission denial instead of saving wallpaper-only video."""
        import sys

        if sys.platform == "darwin":
            import ctypes

            graphics = ctypes.CDLL(
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            )
            check = getattr(graphics, "CGPreflightScreenCaptureAccess", None)
            if check is not None:
                check.restype = ctypes.c_bool
                check.argtypes = []
                if not check():
                    raise PermissionError(
                        "Grant Screen Recording access to the launching terminal/IDE/app "
                        "in macOS Privacy & Security, then restart it."
                    )

    @staticmethod
    def _process_options() -> Dict[str, Any]:
        """Avoid an FFmpeg console window on Windows."""
        import sys

        return (
            {"creationflags": subprocess.CREATE_NO_WINDOW}
            if sys.platform == "win32"
            else {}
        )

    def _marker(self, event: str, timestamp: float, **fields: Any) -> None:
        self.marker_streams.send_screen_marker(
            event,
            timestamp,
            session_id=self._session_id,
            filename=self.video_filename,
            **fields,
        )

    def _write(self, executable: str, width: int, height: int) -> None:
        process = None
        last_timestamp = None
        try:
            with (
                tempfile.TemporaryFile() as errors,
                self._csv_path.open("w", newline="", encoding="utf-8") as sidecar,
            ):
                rows = csv.writer(sidecar)
                rows.writerow(
                    [
                        "frame_index",
                        "capture_index",
                        "lsl_timestamp",
                        "grab_begin_lsl",
                        "grab_end_lsl",
                    ]
                )
                sidecar.flush()
                process = subprocess.Popen(
                    self._command(executable, width, height, self.video_filename),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=errors,
                    **self._process_options(),
                )
                try:
                    while True:
                        item = self._frames.get()
                        if item is None:
                            break
                        frame, capture_index, begin, end = item
                        timestamp = (begin + end) / 2
                        process.stdin.write(frame.tobytes())
                        process.stdin.flush()
                        index = self._written
                        rows.writerow(
                            [
                                index,
                                capture_index,
                                f"{timestamp:.9f}",
                                f"{begin:.9f}",
                                f"{end:.9f}",
                            ]
                        )
                        sidecar.flush()
                        self._written += 1
                        last_timestamp = timestamp
                        if index == 0:
                            self._marker(
                                "SCREEN_START",
                                timestamp,
                                subject_id=self._subject_id,
                                nominal_fps=self.fps,
                                monitor=self._monitor,
                            )
                        self._marker(
                            "SCREEN_FRAME",
                            timestamp,
                            frame_index=index,
                            capture_index=capture_index,
                            grab_begin_lsl=begin,
                            grab_end_lsl=end,
                        )
                        self._first_frame.set()
                finally:
                    try:
                        process.stdin.close()
                    except BrokenPipeError:
                        pass
                    return_code = process.wait(timeout=20)
                    if return_code:
                        errors.seek(0)
                        raise RuntimeError(
                            "FFmpeg failed: "
                            + errors.read().decode("utf-8", errors="replace")[-4000:]
                        )
                if last_timestamp is not None:
                    self._marker(
                        "SCREEN_STOP",
                        last_timestamp,
                        frame_count=self._written,
                        queue_dropped_frames=self._dropped,
                        error=self.last_error,
                    )
        except Exception as exc:
            self._fail(exc)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            self._first_frame.set()
