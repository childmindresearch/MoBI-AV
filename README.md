# MoBI Lab Audio & Video Recorder

A simple application for recording audio and video simultaneously with device selection and synchronization capabilities.

## Installation

### Windows Installation with UV

1. Install UV if you don't have it:

```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. Clone or download this repository

3. Install dependencies:

```bash
uv pip install -r requirements.txt
```

## Creating an Executable (Windows)

To create a standalone executable that can be run with a double-click:

1. Install PyInstaller:

```bash
uv pip install pyinstaller
```

2. Create the executable with LSL support:

```bash
python -m PyInstaller --onefile --windowed --add-binary "C:\Program Files\whereever_lsl_was_installed\liblsl64.dll;pylsl\lib" run.py
```

3. The executable will be created in the `dist` folder

4. To modify settings, copy and edit the `config.json` file in the same folder as the executable

## Usage

1. Double-click the executable to launch the application
2. Select your audio and video devices
3. Enter a subject ID and choose a destination folder
4. Click "Start Recording" to begin capturing

## Features

- Record audio and video separately or together
- Select from available audio and video input devices
- Configurable recording parameters
- Visual status indicators

## LSL Integration

This application features Lab Streaming Layer (LSL) integration for synchronizing recordings with other data streams:

- Automatically creates two LSL marker streams (audio and video) when the application launches
- Streams event markers for recording start/stop events with detailed metadata
- Audio markers include: subject ID, filename, timestamp, channels, and sample rate
- Video markers include: subject ID, filename, timestamp, precise ISO timestamp, and fps
- Marker stream names and sampling rates are configurable in config.json
- Useful for time-synchronizing recordings with other experimental data sources

### LSL Configuration

In the `config.json` file, you can adjust the LSL settings:
```json
"lsl_settings": {
  "audio_stream_name": "AudioMarkers",  
  "video_stream_name": "VideoMarkers",
  "marker_sampling_rate": 0
}
```
Note: `sampling rate: 0` indicates irregular sampling rate for pylsl


## Configuration

Edit `config.json` to customize:

- Default subject ID
- Recording destination
- Preferred default Audio device
- Video resolution and frame rate

Note: The `device_name` and `preferred_sample_rate` in the config will be used to pre-select the matching audio device in the dropdown menu.

## Troubleshooting

If your configured audio device isn't selected automatically, check that:

1. The device name in config.json matches part of the actual device name
2. The device is properly connected to your computer
3. Click "Refresh Devices" to update available devices
