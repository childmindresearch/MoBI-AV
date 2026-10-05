# MoBI Lab Audio & Video Recorder

A simple application for recording audio and video simultaneously with device selection and synchronization capabilities.

## Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then clone
the repository and install the dependencies:

```bash
git clone https://github.com/childmindresearch/MoBI-AV.git
cd MoBI-AV
uv sync
```

## Usage

Launch the GUI from the repository directory:

```bash
uv run mobi-av
```

Then:

1. Select your audio and video devices.
2. Enter or confirm the subject ID and destination folder.
3. Click "Start Recording" to begin capturing.

### Optional launch arguments

An external launcher, such as the MSM protocol GUI, can prefill the subject ID
and destination folder:

```bash
uv run mobi-av --subject-id "ID001" --output-path "recordings/ID001"
```

Both arguments are optional and independent. An omitted argument uses the
existing configuration default: `default_subject_id` for the ID and
`default_destination` for the folder. With the shipped configuration, the ID is
`subject001` and the empty destination setting resolves to the user's Documents
folder. Launching without arguments continues to use these defaults.

These arguments only prefill the editable GUI fields for the current session.
They do not modify `config.json` or start recording automatically. Quote paths
containing spaces; relative paths are relative to the launcher's working
directory. Blank argument values are rejected with a command-line error.

Use `uv run mobi-av --help` to see the available arguments.

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

Edit [config.json](config.json) in the repository directory to customize:

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
