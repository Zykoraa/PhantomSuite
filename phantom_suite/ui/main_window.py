"""
PhantomSuite Main Window
Orchestrates the tabs, active target lifecycle, and Hyprland active window binding.
"""

import os
import subprocess
import json
from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QStatusBar, QMessageBox
)
from PySide6.QtCore import Qt

from phantom_suite.theme import CYBERPUNK_QSS
from phantom_suite.ui.process_tab import ProcessTab
from phantom_suite.ui.scanner_tab import ScannerTab
from phantom_suite.ui.injector_tab import InjectorTab
from phantom_suite.ui.hex_tab import HexTab
from phantom_suite.ui.handles_tab import HandlesTab


class MainWindow(QMainWindow):
    """Main application shell for PhantomSuite."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhantomSuite // Linux Reverse-Engineering & Process Workbench")
        self.resize(1150, 780)
        self.setStyleSheet(CYBERPUNK_QSS)

        self.current_target_pid: Optional[int] = None
        self.current_target_name: str = ""

        self._init_ui()
        self._check_environment()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 6)
        main_layout.setSpacing(8)

        # Header Bar
        header = QHBoxLayout()
        header.setSpacing(12)

        title_lbl = QLabel("PHANTOM<font color='#00f0ff'>SUITE</font> <font color='#ff007f'>v1.0</font>")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: bold; letter-spacing: 1px;")

        self.target_badge = QLabel("[ NO TARGET ATTACHED ]")
        self.target_badge.setStyleSheet(
            "background-color: #121824; color: #6d7f9e; border: 1px solid #1c2638; "
            "border-radius: 4px; padding: 4px 10px; font-weight: bold;"
        )

        self.quick_attach_btn = QPushButton("🎯 Attach Active Window")
        self.quick_attach_btn.setToolTip("Quickly attach to the currently focused Hyprland window")
        self.quick_attach_btn.clicked.connect(self._attach_active_hyprland_window)

        self.detach_btn = QPushButton("✕ Detach")
        self.detach_btn.setObjectName("danger_btn")
        self.detach_btn.setEnabled(False)
        self.detach_btn.clicked.connect(self.detach_target)

        header.addWidget(title_lbl)
        header.addSpacing(15)
        header.addWidget(self.target_badge)
        header.addStretch()
        header.addWidget(self.quick_attach_btn)
        header.addWidget(self.detach_btn)
        main_layout.addLayout(header)

        # Tab Widget
        self.tabs = QTabWidget()

        self.process_tab = ProcessTab()
        self.scanner_tab = ScannerTab()
        self.injector_tab = InjectorTab()
        self.hex_tab = HexTab()
        self.handles_tab = HandlesTab()

        self.tabs.addTab(self.process_tab, "⚡ Processes & Windows")
        self.tabs.addTab(self.scanner_tab, "🔍 Memory Scanner")
        self.tabs.addTab(self.injector_tab, "💉 .so Injector")
        self.tabs.addTab(self.hex_tab, "🧬 Hex Editor")
        self.tabs.addTab(self.handles_tab, "🌐 Sockets & Handles")

        main_layout.addWidget(self.tabs, 1)

        # Connect signals
        self.process_tab.target_attached.connect(self.attach_target)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_lbl = QLabel("Ready")
        self.status_bar.addWidget(self.status_lbl, 1)

        self.yama_lbl = QLabel("ptrace: ?")
        self.yama_lbl.setStyleSheet("color: #7d90b3; padding-right: 12px;")
        self.status_bar.addPermanentWidget(self.yama_lbl)

    def _check_environment(self):
        # Read yama ptrace scope
        try:
            with open("/proc/sys/kernel/yama/ptrace_scope", "r") as f:
                scope = f.read().strip()
                if scope == "0":
                    self.yama_lbl.setText("Yama ptrace_scope: 0 (Classic / Unrestricted)")
                    self.yama_lbl.setStyleSheet("color: #00ff9d; font-weight: bold; padding-right: 12px;")
                else:
                    self.yama_lbl.setText(f"Yama ptrace_scope: {scope} (Restricted)")
                    self.yama_lbl.setStyleSheet("color: #ffb700; font-weight: bold; padding-right: 12px;")
        except Exception:
            self.yama_lbl.setText("Yama ptrace_scope: Unknown")

    def attach_target(self, pid: int, name: str, window_title: str = ""):
        self.current_target_pid = pid
        self.current_target_name = name

        title_display = f" - \"{window_title}\"" if window_title else ""
        self.target_badge.setText(f"[ ATTACHED: PID {pid} — {name}{title_display} ]")
        self.target_badge.setStyleSheet(
            "background-color: #0b1f2e; color: #00f0ff; border: 1px solid #00f0ff; "
            "border-radius: 4px; padding: 4px 10px; font-weight: bold;"
        )
        self.detach_btn.setEnabled(True)

        # Notify tabs
        self.scanner_tab.set_target(pid, name)
        self.injector_tab.set_target(pid, name)
        self.hex_tab.set_target(pid, name)
        self.handles_tab.set_target(pid, name)

        self.status_lbl.setText(f"Attached to process {name} (PID: {pid}).")
        # Automatically advance to Scanner tab
        self.tabs.setCurrentIndex(1)

    def detach_target(self):
        self.current_target_pid = None
        self.current_target_name = ""

        self.target_badge.setText("[ NO TARGET ATTACHED ]")
        self.target_badge.setStyleSheet(
            "background-color: #121824; color: #6d7f9e; border: 1px solid #1c2638; "
            "border-radius: 4px; padding: 4px 10px; font-weight: bold;"
        )
        self.detach_btn.setEnabled(False)

        self.scanner_tab.clear_target()
        self.injector_tab.clear_target()
        self.hex_tab.clear_target()
        self.handles_tab.clear_target()

        self.status_lbl.setText("Detached from target process.")

    def _attach_active_hyprland_window(self):
        """Attempts to discover and attach to the currently focused Hyprland window."""
        try:
            res = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if res.returncode == 0 and res.stdout.strip():
                win = json.loads(res.stdout)
                pid = win.get("pid")
                title = win.get("title", "")
                cls_name = win.get("class", "window")
                if pid and pid > 0:
                    self.attach_target(pid, cls_name, title)
                    return
        except Exception:
            pass
        QMessageBox.information(
            self, "Active Window",
            "Could not identify active Hyprland window. Please pick a target from the Process list."
        )
