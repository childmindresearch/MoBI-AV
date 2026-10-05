"""Regression tests for optional subject and destination launch arguments."""

import json
import os
import runpy
import tkinter as tk
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Callable, Iterator, List, Optional
from unittest.mock import DEFAULT, Mock, mock_open, patch

import pytest

import gui
import recorder_core as core_module
import run


@pytest.fixture
def recorder_core() -> Iterator[Mock]:
    """Provide headless GUI widgets and a recording core without hardware."""
    interpreter = tk.Tcl()
    core = Mock(
        config={
            "default_subject_id": "configured-subject",
            "default_destination": "/configured/destination",
        }
    )
    core.get_available_audio_devices.return_value = []
    core.get_available_video_devices.return_value = []

    def start_worker(target: Callable[[], None], daemon: bool = False) -> Mock:
        worker = Mock()
        worker.start.side_effect = target
        return worker

    def run_callback(delay: int, callback: Callable[[], None]) -> None:
        callback()

    with ExitStack() as stack:
        stack.enter_context(patch("gui.RecorderCore", return_value=core))
        stack.enter_context(patch.object(tk.Tk, "__init__", return_value=None))
        stack.enter_context(patch("gui.threading.Thread", side_effect=start_worker))
        stack.enter_context(
            patch.object(gui.RecorderApp, "after", side_effect=run_callback)
        )
        stack.enter_context(
            patch.multiple(
                gui.RecorderApp,
                title=DEFAULT,
                geometry=DEFAULT,
                resizable=DEFAULT,
                protocol=DEFAULT,
                create_control_buttons=DEFAULT,
                create_status_display=DEFAULT,
                update_preview_window=DEFAULT,
                log_message=DEFAULT,
            )
        )
        stack.enter_context(
            patch.multiple(
                gui.ttk,
                Frame=DEFAULT,
                LabelFrame=DEFAULT,
                Label=DEFAULT,
                Entry=DEFAULT,
                Button=DEFAULT,
                Combobox=DEFAULT,
                Style=DEFAULT,
            )
        )
        string_var = tk.StringVar
        stack.enter_context(
            patch.object(
                tk,
                "StringVar",
                side_effect=lambda **kwargs: string_var(master=interpreter, **kwargs),
            )
        )
        yield core


def test_omitted_arguments_leave_defaults_to_the_gui() -> None:
    argv: List[str] = []

    args = run.parse_arguments(argv)

    assert args.subject_id is None
    assert args.destination is None


def test_supplied_arguments_preserve_ids_and_paths_with_spaces() -> None:
    argv = ["--subject-id", "00042", "--output-path", "C:\\Test Data\\00042"]

    args = run.parse_arguments(argv)

    assert args.subject_id == "00042"
    assert args.destination == "C:\\Test Data\\00042"


@pytest.mark.parametrize(
    "argv, subject_id, destination",
    [
        (["--subject-id", "subject001"], "subject001", None),
        (["--output-path", "recordings/subject001"], None, "recordings/subject001"),
    ],
)
def test_arguments_can_be_supplied_independently(
    argv: List[str], subject_id: Optional[str], destination: Optional[str]
) -> None:
    expected_subject_id = subject_id
    expected_destination = destination

    args = run.parse_arguments(argv)

    assert args.subject_id == expected_subject_id
    assert args.destination == expected_destination


def test_argument_whitespace_matches_gui_recording_behavior() -> None:
    argv = ["--subject-id", " subject001 ", "--output-path", " recordings/subject001 "]

    args = run.parse_arguments(argv)

    assert args.subject_id == "subject001"
    assert args.destination == "recordings/subject001"


@pytest.mark.parametrize(
    "argv",
    [
        ["--subject-id", ""],
        ["--subject-id", " \t "],
        ["--output-path", ""],
        ["--output-path", " \t "],
        ["--subject-id"],
        ["--output-path"],
        ["--unknown"],
    ],
)
def test_invalid_arguments_report_errors_before_startup(argv: List[str]) -> None:
    stderr = StringIO()
    with ExitStack() as stack:
        setup_logging = stack.enter_context(patch("run.setup_logging"))
        app_class = stack.enter_context(patch("gui.RecorderApp"))

        with redirect_stderr(stderr), pytest.raises(SystemExit) as error:
            run.main(argv)

        assert error.value.code == 2
        assert "error:" in stderr.getvalue()
        setup_logging.assert_not_called()
        app_class.assert_not_called()


def test_help_does_not_initialize_the_application() -> None:
    stdout = StringIO()
    with ExitStack() as stack:
        setup_logging = stack.enter_context(patch("run.setup_logging"))
        app_class = stack.enter_context(patch("gui.RecorderApp"))

        with redirect_stdout(stdout), pytest.raises(SystemExit) as error:
            run.main(["--help"])

        assert error.value.code == 0
        assert "--subject-id" in stdout.getvalue()
        assert "--output-path" in stdout.getvalue()
        setup_logging.assert_not_called()
        app_class.assert_not_called()


@pytest.mark.parametrize(
    "argv, subject_id, destination",
    [
        ([], None, None),
        (["--subject-id", "subject001"], "subject001", None),
        (["--output-path", "recordings/subject001"], None, "recordings/subject001"),
        (
            ["--subject-id", "subject001", "--output-path", "recordings/subject001"],
            "subject001",
            "recordings/subject001",
        ),
    ],
)
def test_main_forwards_each_argument_combination_to_the_gui(
    argv: List[str], subject_id: Optional[str], destination: Optional[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch("run.setup_logging"))
        app_class = stack.enter_context(patch("gui.RecorderApp"))

        exit_code = run.main(argv)

        assert exit_code == 0
        app_class.assert_called_once_with(
            subject_id=subject_id, destination=destination
        )
        app_class.return_value.mainloop.assert_called_once_with()


def test_main_reads_arguments_from_the_process_command_line() -> None:
    argv = [
        "mobi-av",
        "--subject-id",
        "00042",
        "--output-path",
        "recordings/Test Data",
    ]
    with ExitStack() as stack:
        stack.enter_context(patch.object(run.sys, "argv", argv))
        stack.enter_context(patch("run.setup_logging"))
        app_class = stack.enter_context(patch("gui.RecorderApp"))

        exit_code = run.main()

        assert exit_code == 0
        app_class.assert_called_once_with(
            subject_id="00042", destination="recordings/Test Data"
        )
        app_class.return_value.mainloop.assert_called_once_with()


def test_direct_gui_launch_uses_the_shared_entry_point() -> None:
    script_path = gui.__file__
    with patch("run.main", return_value=0) as launch_main:
        with pytest.raises(SystemExit) as error:
            runpy.run_path(script_path, run_name="__main__")

        assert error.value.code == 0
        launch_main.assert_called_once_with()


@pytest.mark.parametrize(
    "configured_destination",
    [None, "", "relative/path", "absolute"],
)
def test_configured_defaults_are_loaded_from_the_source_directory(
    tmp_path: Path, configured_destination: Optional[str]
) -> None:
    absolute_destination = str(tmp_path / "recordings")
    config = {"default_subject_id": "configured-subject"}
    if configured_destination is not None:
        config["default_destination"] = (
            absolute_destination
            if configured_destination == "absolute"
            else configured_destination
        )
    expected_destination = (
        absolute_destination
        if configured_destination == "absolute"
        else os.path.join(os.path.expanduser("~"), "Documents")
    )
    config_path = os.path.join(os.path.dirname(core_module.__file__), "config.json")
    core = core_module.RecorderCore.__new__(core_module.RecorderCore)
    with patch("builtins.open", mock_open(read_data=json.dumps(config))) as read_config:
        core.load_config()

        read_config.assert_called_once_with(config_path, "r")
        assert core.config["default_subject_id"] == "configured-subject"
        assert core.config["default_destination"] == expected_destination


def test_no_arguments_preserve_configured_defaults(recorder_core: Mock) -> None:
    expected_subject_id = recorder_core.config["default_subject_id"]
    expected_destination = recorder_core.config["default_destination"]

    app = gui.RecorderApp()

    assert app.subject_id_var.get() == expected_subject_id
    assert app.destination_var.get() == expected_destination


def test_launch_values_override_defaults_without_changing_config(
    recorder_core: Mock,
) -> None:
    config = dict(recorder_core.config)

    app = gui.RecorderApp(subject_id="00042", destination="C:\\Test Data\\00042")

    assert app.subject_id_var.get() == "00042"
    assert app.destination_var.get() == "C:\\Test Data\\00042"
    assert recorder_core.config == config
    recorder_core.get_available_audio_devices.assert_called_once_with()
    recorder_core.get_available_video_devices.assert_called_once_with()


@pytest.mark.parametrize(
    "subject_id, destination",
    [("subject001", None), (None, "recordings/subject001")],
)
def test_each_omitted_value_uses_its_configured_default(
    recorder_core: Mock,
    subject_id: Optional[str],
    destination: Optional[str],
) -> None:
    expected_subject_id = (
        recorder_core.config["default_subject_id"] if subject_id is None else subject_id
    )
    expected_destination = (
        recorder_core.config["default_destination"]
        if destination is None
        else destination
    )

    app = gui.RecorderApp(subject_id=subject_id, destination=destination)

    assert app.subject_id_var.get() == expected_subject_id
    assert app.destination_var.get() == expected_destination


def test_prefilled_fields_remain_editable(recorder_core: Mock) -> None:
    config = dict(recorder_core.config)
    app = gui.RecorderApp(subject_id="subject001", destination="recordings/subject001")

    app.subject_id_var.set("subject002")
    app.destination_var.set("recordings/subject002")

    assert app.subject_id_var.get() == "subject002"
    assert app.destination_var.get() == "recordings/subject002"
    assert recorder_core.config == config


def test_all_recording_modes_use_the_current_field_values(
    recorder_core: Mock,
) -> None:
    app = gui.RecorderApp(subject_id="subject001", destination="recordings/subject001")
    app.subject_id_var.set("subject002")
    app.destination_var.set("recordings/subject002")
    app.audio_device_vars = {"Microphone": Mock(get=Mock(return_value=True))}
    app.audio_devices_map = {"Microphone": 4}
    app.video_device_var.set("Camera")
    app.video_devices_map = {"Camera": 2}
    app.audio_status_var = tk.StringVar(value="Ready")
    app.video_status_var = tk.StringVar(value="Ready")
    for name in (
        "start_audio_btn",
        "stop_audio_btn",
        "start_video_btn",
        "stop_video_btn",
        "start_both_btn",
        "stop_both_btn",
    ):
        setattr(app, name, Mock())
    recorder_core.start_audio_recording.return_value = True
    recorder_core.start_video_recording.return_value = True
    recorder_core.start_both_recordings.return_value = True

    app.start_audio()
    app.start_video()
    app.start_both()

    recorder_core.start_audio_recording.assert_called_once_with(
        "subject002", "recordings/subject002", [4]
    )
    recorder_core.start_video_recording.assert_called_once_with(
        "subject002", "recordings/subject002", 2
    )
    recorder_core.start_both_recordings.assert_called_once_with(
        "subject002", "recordings/subject002", [4], 2
    )
    assert app.audio_status_var.get() == "Recording..."
    assert app.video_status_var.get() == "Recording..."
