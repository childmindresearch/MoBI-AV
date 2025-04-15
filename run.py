#!/usr/bin/env python3
"""
Main entry point for the Audio & Video Recorder application.
This file launches the GUI and sets up necessary environment.
"""

import os
import sys
import logging
from gui import RecorderApp


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


def main():
    """Main entry point for the application"""
    # Set up logging
    setup_logging()

    try:
        # Create and run the GUI application
        app = RecorderApp()
        app.mainloop()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"An unexpected error occurred: {e}")
        return 1

    logging.info("Application closed normally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
