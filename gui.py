"""GUI module for video and audio recording application.

This module provides the main GUI interface for configuring and controlling
video and audio recording with device selection and preview capabilities.
"""

import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from typing import List
import threading
from recorder_core import RecorderCore


class RecorderApp(tk.Tk):
    """Main GUI application for video and audio recording.

    Provides device selection, recording controls, and status/log display.
    Widgets are grouped by function: audio controls, video controls, and status/log.
    """

    def __init__(self) -> None:
        """Initialize the main GUI, widgets, and layout."""
        super().__init__()
        self.title("Audio & Video Recorder")
        self.geometry("850x850")
        self.resizable(True, True)
        self.core = RecorderCore()

        # Main frame
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Input fields (subject, destination, device selectors)
        self.create_input_fields(main_frame)

        # Controls grouped by function
        self.create_control_buttons(main_frame)

        # Status and log display
        self.create_status_display(main_frame)

        # Style
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 11))
        self.style.configure("TLabel", font=("Arial", 11))
        self.style.configure("TFrame", background="#f5f5f5")

        # Window close handler
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Preview window update
        self.update_preview_window()
        self.log_message("Application initialized")

    def create_input_fields(self, parent: tk.Widget) -> None:
        """Create subject, destination, and device selection widgets."""
        input_frame = ttk.LabelFrame(parent, text="Recording Settings", padding="10")
        input_frame.pack(fill=tk.X, pady=10)
        ttk.Label(input_frame, text="Subject ID:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.subject_id_var = tk.StringVar(value=self.core.config["default_subject_id"])
        self.subject_id_entry = ttk.Entry(
            input_frame, textvariable=self.subject_id_var, width=30
        )
        self.subject_id_entry.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        ttk.Label(input_frame, text="Save to:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.destination_var = tk.StringVar(
            value=self.core.config["default_destination"]
        )
        self.destination_entry = ttk.Entry(
            input_frame, textvariable=self.destination_var, width=30
        )
        self.destination_entry.grid(row=1, column=1, sticky=tk.W + tk.E, pady=5, padx=5)
        browse_btn = ttk.Button(
            input_frame, text="Browse...", command=self.browse_folder
        )
        browse_btn.grid(row=1, column=2, padx=5, pady=5)
        ttk.Label(input_frame, text="Audio Devices:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        self.audio_devices_frame = ttk.Frame(input_frame)
        self.audio_devices_frame.grid(
            row=2, column=1, sticky=tk.W + tk.E, pady=5, padx=5
        )
        self.audio_device_vars = {}  # type: ignore
        self.audio_devices_map = {}  # type: ignore
        self.video_devices_map = {}  # type: ignore
        ttk.Label(input_frame, text="Video Device:").grid(
            row=3, column=0, sticky=tk.W, pady=5
        )
        self.video_device_var = tk.StringVar()
        self.video_device_menu = ttk.Combobox(
            input_frame, textvariable=self.video_device_var, width=30
        )
        self.video_device_menu.grid(row=3, column=1, sticky=tk.W + tk.E, pady=5, padx=5)
        self.video_device_menu.bind("<<ComboboxSelected>>", self._on_video_device_changed)
        refresh_btn = ttk.Button(
            input_frame, text="Refresh Devices", command=self.refresh_devices
        )
        refresh_btn.grid(row=2, column=2, rowspan=2, padx=5, pady=5)
        input_frame.columnconfigure(1, weight=1)
        self.refresh_devices()

    def refresh_devices(self) -> None:
        """Update the lists of available audio and video devices in background."""
        # Clear existing audio device checkboxes
        for widget in self.audio_devices_frame.winfo_children():
            widget.destroy()
        label = ttk.Label(self.audio_devices_frame, text="Scanning devices...")
        label.grid(row=0, column=0, sticky=tk.W)
        self.video_device_menu["values"] = ["Scanning..."]
        self.video_device_menu.set("Scanning...")

        def _scan() -> None:
            audio_devices = self.core.get_available_audio_devices()
            video_devices = self.core.get_available_video_devices()
            self.after(0, lambda: self._populate_devices(audio_devices, video_devices))

        threading.Thread(target=_scan, daemon=True).start()

    def _populate_devices(self, audio_devices: list, video_devices: list) -> None:
        """Populate device lists on the main thread after background scan."""
        # Clear scanning placeholder
        for widget in self.audio_devices_frame.winfo_children():
            widget.destroy()
        self.audio_devices_map = {}
        self.audio_device_vars = {}
        if audio_devices:
            # Determine which device to auto-select: prefer configured name + sample rate, else first
            auto_select_index = 0
            for i, dev in enumerate(audio_devices):
                if self._should_auto_select_audio_device(dev["name"], dev["sample_rate"]):
                    auto_select_index = i
                    break

            # Create checkboxes for each audio device
            for i, dev in enumerate(audio_devices):
                device_key = f"{dev['name']} (Channels: {dev['channels']}, Rate: {dev['sample_rate']})"
                self.audio_devices_map[device_key] = dev["index"]
                # Create checkbox variable
                var = tk.BooleanVar(value=(i == auto_select_index))
                self.audio_device_vars[device_key] = var
                # Create checkbox
                checkbox = tk.Checkbutton(
                    self.audio_devices_frame, text=device_key, variable=var
                )
                checkbox.grid(row=i, column=0, sticky=tk.W, pady=2)
            self.log_message("GUI Log: Audio devices refreshed")
        else:
            # No devices found
            label = ttk.Label(self.audio_devices_frame, text="No audio devices found")
            label.grid(row=0, column=0, sticky=tk.W)
            self.log_message("GUI Log: No audio devices found")
        # Get video devices
        self.video_devices_map = {dev["name"]: dev["index"] for dev in video_devices}
        self.video_device_menu["values"] = list(self.video_devices_map.keys())
        if self.video_devices_map:
            self.video_device_menu.current(0)
        self.log_message("GUI Log: Device lists refreshed")

    def _on_video_device_changed(self, event: object = None) -> None:
        """Pre-warm the newly selected camera in a background thread."""
        selected = self.video_device_var.get()
        device_index = self.video_devices_map.get(selected)
        if device_index is None:
            return
        recorder = self.core.video_recorder
        # Skip if already warmed to this device
        if recorder._capture_device_index == device_index and recorder.video_capture and recorder.video_capture.isOpened():
            return
        self.log_message(f"Warming up camera {device_index}...")

        def _warm() -> None:
            success = recorder.warm_up_device(device_index)
            if success:
                self.after(0, lambda: self.log_message(f"Camera {device_index} ready"))
            else:
                self.after(0, lambda: self.log_message(f"Failed to open camera {device_index}"))

        threading.Thread(target=_warm, daemon=True).start()

    def _should_auto_select_audio_device(self, device_name: str, sample_rate: int) -> bool:
        """Check if this audio device should be auto-selected based on config."""
        try:
            audio_cfg = self.core.config["audio_settings"]
            configured_device_name = audio_cfg["device_name"]
            if configured_device_name.lower() not in device_name.lower():
                return False
            preferred_rate = audio_cfg.get("preferred_sample_rate")
            if preferred_rate is not None and sample_rate != preferred_rate:
                return False
            return True
        except Exception:
            return False

    def create_status_display(self, parent: tk.Widget) -> None:
        """Create status and log display widgets."""
        status_frame = ttk.LabelFrame(parent, text="Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        ttk.Label(status_frame, text="Audio:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.audio_status_var = tk.StringVar(value="Ready")
        self.audio_status_label = ttk.Label(
            status_frame, textvariable=self.audio_status_var
        )
        self.audio_status_label.grid(row=0, column=1, sticky=tk.W, pady=5)
        ttk.Label(status_frame, text="Video:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.video_status_var = tk.StringVar(value="Ready")
        self.video_status_label = ttk.Label(
            status_frame, textvariable=self.video_status_var
        )
        self.video_status_label.grid(row=1, column=1, sticky=tk.W, pady=5)
        self.log_text = tk.Text(status_frame, height=6, width=50, wrap=tk.WORD)
        self.log_text.grid(
            row=2, column=0, columnspan=2, sticky=tk.W + tk.E + tk.N + tk.S, pady=5
        )
        scrollbar = ttk.Scrollbar(status_frame, command=self.log_text.yview)
        scrollbar.grid(row=2, column=2, sticky=tk.N + tk.S)
        self.log_text.config(yscrollcommand=scrollbar.set)
        status_frame.rowconfigure(2, weight=1)
        status_frame.columnconfigure(1, weight=1)

    def create_control_buttons(self, parent: tk.Widget) -> None:
        """Create and place control buttons for recording."""
        btn_frame = ttk.Frame(parent, padding="10")
        btn_frame.pack(fill=tk.X, pady=10)
        audio_frame = ttk.LabelFrame(btn_frame, text="Audio", padding="10")
        audio_frame.grid(row=0, column=0, padx=5, sticky=tk.W + tk.E)
        self.start_audio_btn = ttk.Button(
            audio_frame, text="Start Recording", command=self.start_audio
        )
        self.start_audio_btn.pack(fill=tk.X, pady=2)
        self.stop_audio_btn = ttk.Button(
            audio_frame,
            text="Stop Recording",
            command=self.stop_audio,
            state=tk.DISABLED,
        )
        self.stop_audio_btn.pack(fill=tk.X, pady=2)
        video_frame = ttk.LabelFrame(btn_frame, text="Video", padding="10")
        video_frame.grid(row=0, column=1, padx=5, sticky=tk.W + tk.E)
        self.start_video_btn = ttk.Button(
            video_frame, text="Start Recording", command=self.start_video
        )
        self.start_video_btn.pack(fill=tk.X, pady=2)
        self.stop_video_btn = ttk.Button(
            video_frame,
            text="Stop Recording",
            command=self.stop_video,
            state=tk.DISABLED,
        )
        self.stop_video_btn.pack(fill=tk.X, pady=2)
        self.preview_btn = ttk.Button(
            video_frame, text="Toggle Preview", command=self.toggle_preview
        )
        self.preview_btn.pack(fill=tk.X, pady=2)
        both_frame = ttk.LabelFrame(btn_frame, text="Both", padding="10")
        both_frame.grid(row=0, column=2, padx=5, sticky=tk.W + tk.E)
        self.start_both_btn = ttk.Button(
            both_frame, text="Start Both", command=self.start_both
        )
        self.start_both_btn.pack(fill=tk.X, pady=2)
        self.stop_both_btn = ttk.Button(
            both_frame, text="Stop Both", command=self.stop_both, state=tk.DISABLED
        )
        self.stop_both_btn.pack(fill=tk.X, pady=2)
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

    def browse_folder(self) -> None:
        """Open a folder dialog to select the destination folder."""
        folder = filedialog.askdirectory()
        if folder:
            self.destination_var.set(folder)

    def log_message(self, message: str) -> None:
        """Log a message to the log text area if it exists."""
        if hasattr(self, "log_text"):
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
        else:
            print(f"GUI Log: {message}")

    def start_audio(self) -> None:
        """Start audio recording with the selected settings."""
        subject_id = self.subject_id_var.get().strip()
        destination = self.destination_var.get().strip()
        if not subject_id or not destination:
            messagebox.showwarning(
                "Missing Information",
                "Please enter both Subject ID and Destination folder.",
            )
            return
        selected_devices: List[int] = []
        for device_key, var in self.audio_device_vars.items():
            if var.get():
                device_index = self.audio_devices_map.get(device_key)
                if device_index is not None:
                    selected_devices.append(device_index)
        if not selected_devices:
            messagebox.showerror("Error", "Please select at least one audio device")
            return
        self.start_audio_btn.config(state=tk.DISABLED)
        self.log_message("Starting audio recording...")

        def _start() -> None:
            success = self.core.start_audio_recording(
                subject_id, destination, selected_devices
            )
            self.after(0, lambda: self._on_audio_started(success, subject_id))

        threading.Thread(target=_start, daemon=True).start()

    def _on_audio_started(self, success: bool, subject_id: str) -> None:
        if success:
            self.audio_status_var.set("Recording...")
            self.stop_audio_btn.config(state=tk.NORMAL)
            self.log_message(f"Started audio recording for {subject_id}")
        else:
            self.start_audio_btn.config(state=tk.NORMAL)
            messagebox.showerror(
                "Error", "Failed to start audio recording. Check the log file."
            )

    def stop_audio(self) -> None:
        """Stop the audio recording if it is in progress."""
        if not self.core.recording_audio:
            self.log_message("No audio recording in progress")
            return
        success = self.core.stop_audio_recording()
        if success:
            self.audio_status_var.set("Ready")
            self.start_audio_btn.config(state=tk.NORMAL)
            self.stop_audio_btn.config(state=tk.DISABLED)
            if not self.core.recording_video:
                self.start_both_btn.config(state=tk.NORMAL)
                self.stop_both_btn.config(state=tk.DISABLED)
            self.log_message("Stopped audio recording")
        else:
            messagebox.showerror(
                "Error", "Failed to stop audio recording. Check the log file."
            )

    def start_video(self) -> None:
        """Start video recording with the selected settings."""
        subject_id = self.subject_id_var.get().strip()
        destination = self.destination_var.get().strip()
        if not subject_id or not destination:
            messagebox.showwarning(
                "Missing Information",
                "Please enter both Subject ID and Destination folder.",
            )
            return
        selected_device = self.video_device_var.get()
        device_index = self.video_devices_map.get(selected_device)
        self.start_video_btn.config(state=tk.DISABLED)
        self.log_message("Starting video recording...")

        def _start() -> None:
            success = self.core.start_video_recording(subject_id, destination, device_index)
            self.after(0, lambda: self._on_video_started(success, subject_id))

        threading.Thread(target=_start, daemon=True).start()

    def _on_video_started(self, success: bool, subject_id: str) -> None:
        if success:
            self.video_status_var.set("Recording...")
            self.stop_video_btn.config(state=tk.NORMAL)
            self.log_message(f"Started video recording for {subject_id}")
        else:
            self.start_video_btn.config(state=tk.NORMAL)
            messagebox.showerror(
                "Error", "Failed to start video recording. Check the log file."
            )

    def stop_video(self) -> None:
        """Stop the video recording if it is in progress."""
        if not self.core.recording_video:
            self.log_message("No video recording in progress")
            return
        success = self.core.stop_video_recording()
        if success:
            self.video_status_var.set("Ready")
            self.start_video_btn.config(state=tk.NORMAL)
            self.stop_video_btn.config(state=tk.DISABLED)
            if not self.core.recording_audio:
                self.start_both_btn.config(state=tk.NORMAL)
                self.stop_both_btn.config(state=tk.DISABLED)
            self.log_message("Stopped video recording")
        else:
            messagebox.showerror(
                "Error", "Failed to stop video recording. Check the log file."
            )

    def start_both(self) -> None:
        """Start audio and video recording with the selected settings."""
        subject_id = self.subject_id_var.get().strip()
        destination = self.destination_var.get().strip()
        if not subject_id or not destination:
            messagebox.showwarning(
                "Missing Information",
                "Please enter both Subject ID and Destination folder.",
            )
            return
        selected_audio_devices: List[int] = []
        for device_key, var in self.audio_device_vars.items():
            if var.get():
                device_index = self.audio_devices_map.get(device_key)
                if device_index is not None:
                    selected_audio_devices.append(device_index)
        if not selected_audio_devices:
            messagebox.showerror("Error", "Please select at least one audio device")
            return
        video_device = self.video_device_var.get()
        video_index = self.video_devices_map.get(video_device)
        self.start_both_btn.config(state=tk.DISABLED)
        self.start_audio_btn.config(state=tk.DISABLED)
        self.start_video_btn.config(state=tk.DISABLED)
        self.log_message("Starting audio and video recording...")

        def _start() -> None:
            success = self.core.start_both_recordings(
                subject_id, destination, selected_audio_devices, video_index
            )
            self.after(0, lambda: self._on_both_started(success, subject_id))

        threading.Thread(target=_start, daemon=True).start()

    def _on_both_started(self, success: bool, subject_id: str) -> None:
        if success:
            self.audio_status_var.set("Recording...")
            self.video_status_var.set("Recording...")
            self.stop_audio_btn.config(state=tk.NORMAL)
            self.stop_video_btn.config(state=tk.NORMAL)
            self.stop_both_btn.config(state=tk.NORMAL)
            self.log_message(f"Started audio and video recording for {subject_id}")
        else:
            self.start_audio_btn.config(state=tk.NORMAL)
            self.start_video_btn.config(state=tk.NORMAL)
            self.start_both_btn.config(state=tk.NORMAL)
            messagebox.showerror(
                "Error", "Failed to start recordings. Check the log file."
            )

    def stop_both(self) -> None:
        """Stop audio and video recording if they are in progress."""
        if not self.core.recording_audio and not self.core.recording_video:
            self.log_message("No recordings in progress")
            return
        success = self.core.stop_both_recordings()
        if success:
            self.audio_status_var.set("Ready")
            self.video_status_var.set("Ready")
            self.start_audio_btn.config(state=tk.NORMAL)
            self.stop_audio_btn.config(state=tk.DISABLED)
            self.start_video_btn.config(state=tk.NORMAL)
            self.stop_video_btn.config(state=tk.DISABLED)
            self.start_both_btn.config(state=tk.NORMAL)
            self.stop_both_btn.config(state=tk.DISABLED)
            self.log_message("Stopped all active recordings")
        else:
            messagebox.showerror(
                "Error", "Failed to stop recordings. Check the log file."
            )

    def toggle_preview(self) -> None:
        """Toggle the video preview window."""
        selected_device = self.video_device_var.get()
        device_index = self.video_devices_map.get(selected_device, 0)
        if device_index is not None:
            self.core.video_recorder.preview_device_index = device_index

        if self.core.video_recorder.show_preview:
            self.core.video_recorder.stop_preview()
            self.log_message("Video preview stopped")
        else:
            self.preview_btn.config(state=tk.DISABLED)
            self.log_message("Starting video preview...")

            def _start() -> None:
                self.core.video_recorder.start_preview()
                self.after(0, self._on_preview_started)

            threading.Thread(target=_start, daemon=True).start()

    def _on_preview_started(self) -> None:
        self.preview_btn.config(state=tk.NORMAL)
        if self.core.video_recorder.show_preview:
            self.log_message(
                "Video preview started - separate OpenCV window will appear"
            )
        else:
            self.log_message("Failed to start video preview")

    def update_preview_window(self) -> None:
        """Update the OpenCV preview window from main thread."""
        try:
            if (
                hasattr(self.core, "video_recorder")
                and self.core.video_recorder
                and self.core.video_recorder.show_preview
            ):
                self.core.video_recorder.show_preview_window()
        except Exception:
            pass
        self.after(100, self.update_preview_window)

    def on_close(self) -> None:
        """Handle window close event."""
        if self.core.recording_audio or self.core.recording_video:
            confirm = messagebox.askyesno(
                "Confirm Exit", "Recording is in progress. Stop recording and exit?"
            )
            if confirm:
                if self.core.recording_audio:
                    self.core.stop_audio_recording()
                if self.core.recording_video:
                    self.core.stop_video_recording()
                if hasattr(self.core, "video_recorder") and self.core.video_recorder:
                    self.core.video_recorder.stop_preview()
                self.destroy()
        else:
            if hasattr(self.core, "video_recorder") and self.core.video_recorder:
                self.core.video_recorder.stop_preview()
            self.destroy()


# For testing
if __name__ == "__main__":
    app = RecorderApp()
    app.mainloop()
