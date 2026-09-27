#!/usr/bin/env python3
"""
PhantomSuite - Linux Process Inspector, Memory Scanner, and Reverse-Engineering Workbench
Main Application Entry Point.
"""

import sys
import os
import argparse

# Ensure phantom_suite package root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from phantom_suite.ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="PhantomSuite - Linux Process & Memory Workbench")
    parser.add_argument("--pid", type=int, help="Automatically attach to target PID on startup")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("PhantomSuite")
    app.setApplicationDisplayName("PhantomSuite")

    window = MainWindow()

    if args.pid:
        window.attach_target(args.pid, f"PID_{args.pid}")

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
