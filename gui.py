import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from recorder_core import RecorderCore


class RecorderApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Audio & Video Recorder")
        self.geometry("800x600")
        self.resizable(True, True)

        # Initialize the recorder core
        self.core = RecorderCore()

        # Create main frame with padding
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create and place widgets
        self.create_input_fields(main_frame)
        self.create_control_buttons(main_frame)
        self.create_status_display(main_frame)

        # Apply styling
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 11))
        self.style.configure("TLabel", font=("Arial", 11))
        self.style.configure("TFrame", background="#f5f5f5")

        # Window close handler
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.log_message("Application initialized")

    def create_input_fields(self, parent):
        # Input frame
        input_frame = ttk.LabelFrame(parent, text="Recording Settings", padding="10")
        input_frame.pack(fill=tk.X, pady=10)

        # Subject ID
        ttk.Label(input_frame, text="Subject ID:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.subject_id_var = tk.StringVar(value=self.core.config["default_subject_id"])
        self.subject_id_entry = ttk.Entry(
            input_frame, textvariable=self.subject_id_var, width=30
        )
        self.subject_id_entry.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)

        # Destination folder
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

        # Audio device selection
        ttk.Label(input_frame, text="Audio Device:").grid(
            row=2, column=0, sticky=tk.W, pady=5
        )
        self.audio_device_var = tk.StringVar()
        self.audio_device_menu = ttk.Combobox(
            input_frame, textvariable=self.audio_device_var, width=30
        )
        self.audio_device_menu.grid(row=2, column=1, sticky=tk.W + tk.E, pady=5, padx=5)

        # Video device selection
        ttk.Label(input_frame, text="Video Device:").grid(
            row=3, column=0, sticky=tk.W, pady=5
        )
        self.video_device_var = tk.StringVar()
        self.video_device_menu = ttk.Combobox(
            input_frame, textvariable=self.video_device_var, width=30
        )
        self.video_device_menu.grid(row=3, column=1, sticky=tk.W + tk.E, pady=5, padx=5)

        # Refresh devices button
        refresh_btn = ttk.Button(
            input_frame, text="Refresh Devices", command=self.refresh_devices
        )
        refresh_btn.grid(row=2, column=2, rowspan=2, padx=5, pady=5)

        # Configure grid to expand properly
        input_frame.columnconfigure(1, weight=1)

        # Populate device lists
        self.refresh_devices()

    def refresh_devices(self):
        """Update the lists of available audio and video devices"""
        # Get audio devices
        audio_devices = self.core.get_available_audio_devices()
        self.audio_devices_map = {
            f"{dev['name']} (Channels: {dev['channels']}, Rate: {dev['sample_rate']})": dev[
                "index"
            ]
            for dev in audio_devices
        }
        self.audio_device_menu["values"] = list(self.audio_devices_map.keys())

        if self.audio_devices_map:
            # Get the configured device name and preferred sample rate
            configured_device_name = self.core.config["audio_settings"]["device_name"]
            preferred_sample_rate = self.core.config["audio_settings"].get(
                "preferred_sample_rate", None
            )
            configured_device_found = False

            # First try to find a device that matches both name AND sample rate
            if preferred_sample_rate is not None:
                for i, device_key in enumerate(self.audio_device_menu["values"]):
                    if (
                        configured_device_name in device_key
                        and f"Rate: {preferred_sample_rate}" in device_key
                    ):
                        self.audio_device_menu.current(i)
                        configured_device_found = True
                        self.log_message(
                            f"Selected device matching name '{configured_device_name}' and sample rate {preferred_sample_rate}Hz"
                        )
                        break

            # If no exact match, fall back to just matching the name
            if not configured_device_found:
                for i, device_key in enumerate(self.audio_device_menu["values"]):
                    if configured_device_name in device_key:
                        self.audio_device_menu.current(i)
                        configured_device_found = True
                        self.log_message(
                            f"Selected device by name only: {configured_device_name}"
                        )
                        break

            # Fall back to first device if configured one not found
            if not configured_device_found:
                self.audio_device_menu.current(0)
                self.log_message(
                    f"Configured audio device '{configured_device_name}' not found, using default"
                )

        # Get video devices
        video_devices = self.core.get_available_video_devices()
        self.video_devices_map = {dev["name"]: dev["index"] for dev in video_devices}
        self.video_device_menu["values"] = list(self.video_devices_map.keys())
        if self.video_devices_map:
            self.video_device_menu.current(0)

        self.log_message("Device lists refreshed")

    def create_status_display(self, parent):
        # Status frame
        status_frame = ttk.LabelFrame(parent, text="Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # Audio status
        ttk.Label(status_frame, text="Audio:").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.audio_status_var = tk.StringVar(value="Ready")
        self.audio_status_label = ttk.Label(
            status_frame, textvariable=self.audio_status_var
        )
        self.audio_status_label.grid(row=0, column=1, sticky=tk.W, pady=5)

        # Video status
        ttk.Label(status_frame, text="Video:").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.video_status_var = tk.StringVar(value="Ready")
        self.video_status_label = ttk.Label(
            status_frame, textvariable=self.video_status_var
        )
        self.video_status_label.grid(row=1, column=1, sticky=tk.W, pady=5)

        # Log display
        self.log_text = tk.Text(status_frame, height=6, width=50, wrap=tk.WORD)
        self.log_text.grid(
            row=2, column=0, columnspan=2, sticky=tk.W + tk.E + tk.N + tk.S, pady=5
        )

        # Scrollbar for log
        scrollbar = ttk.Scrollbar(status_frame, command=self.log_text.yview)
        scrollbar.grid(row=2, column=2, sticky=tk.N + tk.S)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # Configure grid to expand properly
        status_frame.rowconfigure(2, weight=1)
        status_frame.columnconfigure(1, weight=1)

    def create_control_buttons(self, parent):
        # Control buttons frame
        btn_frame = ttk.Frame(parent, padding="10")
        btn_frame.pack(fill=tk.X, pady=10)

        # Audio controls
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

        # Video controls
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

        # Both controls
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

        # Configure grid to expand properly
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.destination_var.set(folder)

    def log_message(self, message):
        """Log a message to the log text area if it exists"""
        if hasattr(self, "log_text"):
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)  # Auto-scroll
        else:
            # Fall back to console logging if the log_text widget isn't created yet
            print(f"GUI Log: {message}")

    def start_audio(self):
        subject_id = self.subject_id_var.get().strip()
        destination = self.destination_var.get().strip()

        if not subject_id or not destination:
            messagebox.showwarning(
                "Missing Information",
                "Please enter both Subject ID and Destination folder.",
            )
            return

        # Get selected audio device index
        selected_device = self.audio_device_var.get()
        device_index = self.audio_devices_map.get(selected_device)

        success = self.core.start_audio_recording(subject_id, destination, device_index)
        if success:
            self.audio_status_var.set("Recording...")
            self.start_audio_btn.config(state=tk.DISABLED)
            self.stop_audio_btn.config(state=tk.NORMAL)
            self.log_message(f"Started audio recording for {subject_id}")
        else:
            messagebox.showerror(
                "Error", "Failed to start audio recording. Check the log file."
            )

    def stop_audio(self):
        if not self.core.recording_audio:
            self.log_message("No audio recording in progress")
            return

        success = self.core.stop_audio_recording()
        if success:
            self.audio_status_var.set("Ready")
            self.start_audio_btn.config(state=tk.NORMAL)
            self.stop_audio_btn.config(state=tk.DISABLED)

            # Also enable the Start Both button if both recordings are stopped
            if not self.core.recording_video:
                self.start_both_btn.config(state=tk.NORMAL)
                self.stop_both_btn.config(state=tk.DISABLED)

            self.log_message("Stopped audio recording")
        else:
            messagebox.showerror(
                "Error", "Failed to stop audio recording. Check the log file."
            )

    def start_video(self):
        subject_id = self.subject_id_var.get().strip()
        destination = self.destination_var.get().strip()

        if not subject_id or not destination:
            messagebox.showwarning(
                "Missing Information",
                "Please enter both Subject ID and Destination folder.",
            )
            return

        # Get selected video device index
        selected_device = self.video_device_var.get()
        device_index = self.video_devices_map.get(selected_device)

        success = self.core.start_video_recording(subject_id, destination, device_index)
        if success:
            self.video_status_var.set("Recording...")
            self.start_video_btn.config(state=tk.DISABLED)
            self.stop_video_btn.config(state=tk.NORMAL)
            self.log_message(f"Started video recording for {subject_id}")
        else:
            messagebox.showerror(
                "Error", "Failed to start video recording. Check the log file."
            )

    def stop_video(self):
        if not self.core.recording_video:
            self.log_message("No video recording in progress")
            return

        success = self.core.stop_video_recording()
        if success:
            self.video_status_var.set("Ready")
            self.start_video_btn.config(state=tk.NORMAL)
            self.stop_video_btn.config(state=tk.DISABLED)

            # Also enable the Start Both button if both recordings are stopped
            if not self.core.recording_audio:
                self.start_both_btn.config(state=tk.NORMAL)
                self.stop_both_btn.config(state=tk.DISABLED)

            self.log_message("Stopped video recording")
        else:
            messagebox.showerror(
                "Error", "Failed to stop video recording. Check the log file."
            )

    def start_both(self):
        subject_id = self.subject_id_var.get().strip()
        destination = self.destination_var.get().strip()

        if not subject_id or not destination:
            messagebox.showwarning(
                "Missing Information",
                "Please enter both Subject ID and Destination folder.",
            )
            return

        # Get selected device indices
        audio_device = self.audio_device_var.get()
        audio_index = self.audio_devices_map.get(audio_device)

        video_device = self.video_device_var.get()
        video_index = self.video_devices_map.get(video_device)

        # Pass both device indices to start_both_recordings
        success = self.core.start_both_recordings(
            subject_id, destination, audio_index, video_index
        )

        if success:
            self.audio_status_var.set("Recording...")
            self.video_status_var.set("Recording...")

            self.start_audio_btn.config(state=tk.DISABLED)
            self.stop_audio_btn.config(state=tk.NORMAL)
            self.start_video_btn.config(state=tk.DISABLED)
            self.stop_video_btn.config(state=tk.NORMAL)
            self.start_both_btn.config(state=tk.DISABLED)
            self.stop_both_btn.config(state=tk.NORMAL)

            self.log_message(f"Started audio and video recording for {subject_id}")
        else:
            messagebox.showerror(
                "Error", "Failed to start recordings. Check the log file."
            )

    def stop_both(self):
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

    def on_close(self):
        """Handle window close event"""
        if self.core.recording_audio or self.core.recording_video:
            confirm = messagebox.askyesno(
                "Confirm Exit", "Recording is in progress. Stop recording and exit?"
            )
            if confirm:
                if self.core.recording_audio:
                    self.core.stop_audio_recording()
                if self.core.recording_video:
                    self.core.stop_video_recording()
                self.destroy()
        else:
            self.destroy()


# For testing
if __name__ == "__main__":
    app = RecorderApp()
    app.mainloop()
