"""
Main entry point for the Audio & Video Recorder application.
This file launches the GUI and sets up necessary environment.
"""

import argparse
import logging
import os
import sys
from typing import Optional, Sequence


def _non_empty_argument(value: str) -> str:
    """Reject blank launch values before initializing the application."""
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("must not be empty or whitespace-only")
    return value


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse optional recording settings supplied by an external launcher."""
    parser = argparse.ArgumentParser(
        description="Launch the MoBI-AV audio and video recorder."
    )
    parser.add_argument(
        "--subject-id",
        type=_non_empty_argument,
        help="Subject ID to prefill in the GUI (default: configured subject ID).",
    )
    parser.add_argument(
        "--output-path",
        dest="destination",
        metavar="PATH",
        type=_non_empty_argument,
        help="Destination folder to prefill in the GUI (default: configured destination).",
    )
    return parser.parse_args(argv)


def setup_logging():
    """Configure logging for the application"""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s:%(message)s",
        handlers=[
            logging.FileHandler(os.path.join(log_dir, "recorder.log")),
            logging.StreamHandler(),
        ],
    )

    logging.info("Application started")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Launch the application with optional subject and destination overrides."""
    args = parse_arguments(argv)

    # Set up logging
    setup_logging()

    try:
        from gui import RecorderApp

        # Create and run the GUI application
        app = RecorderApp(subject_id=args.subject_id, destination=args.destination)
        app.mainloop()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"An unexpected error occurred: {e}")
        return 1

    logging.info("Application closed normally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
