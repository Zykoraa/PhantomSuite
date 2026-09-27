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
    QPushButton, QTabWidget, QStatusBar, QMessageBox, QSlider
)
from PySide6.QtCore import Qt

from phantom_suite.theme import CYBERPUNK_QSS
from phantom_suite.core.speedhack_controller import SpeedhackController
from phantom_suite.ui.process_tab import ProcessTab
from phantom_suite.ui.scanner_tab import ScannerTab
from phantom_suite.ui.injector_tab import InjectorTab
from phantom_suite.ui.hex_tab import HexTab
from phantom_suite.ui.threads_tab import ThreadsTab
from phantom_suite.ui.handles_tab import HandlesTab
from phantom_suite.ui.struct_tab import StructTab
from phantom_suite.ui.symbols_tab import SymbolsTab
from phantom_suite.ui.snapshot_tab import SnapshotTab
from phantom_suite.ui.treemap_tab import TreemapTab
from phantom_suite.ui.syscalls_tab import SyscallsTab
from phantom_suite.ui.deserializer_tab import DeserializerTab
from phantom_suite.ui.console_tab import ConsoleTab
from phantom_suite.ui.osd_overlay import OsdOverlay


class MainWindow(QMainWindow):
    """Main application shell for PhantomSuite."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PhantomSuite // Linux Reverse-Engineering & Process Workbench")
        self.resize(1200, 800)
        self.setStyleSheet(CYBERPUNK_QSS)

        self.current_target_pid: Optional[int] = None
        self.current_target_name: str = ""
        self.osd_overlay = OsdOverlay()

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

        title_lbl = QLabel("PHANTOM<font color='#00f0ff'>SUITE</font>")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: bold; letter-spacing: 1px;")

        self.target_badge = QLabel("[ NO TARGET ATTACHED ]")
        self.target_badge.setStyleSheet(
            "background-color: #121824; color: #6d7f9e; border: 1px solid #1c2638; "
            "border-radius: 4px; padding: 4px 10px; font-weight: bold;"
        )

        # Speedhack Controls
        speed_box = QHBoxLayout()
        self.speed_btn = QPushButton("⚡ Speedhack: OFF")
        self.speed_btn.setEnabled(False)
        self.speed_btn.clicked.connect(self._toggle_speedhack)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(2, 50) # 0.2x to 5.0x
        self.speed_slider.setValue(10)     # 1.0x
        self.speed_slider.setFixedWidth(110)
        self.speed_slider.setEnabled(False)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)

        self.speed_lbl = QLabel("1.0x")
        self.speed_lbl.setStyleSheet("color: #00f0ff; font-weight: bold; min-width: 32px;")

        speed_box.addWidget(self.speed_btn)
        speed_box.addWidget(self.speed_slider)
        speed_box.addWidget(self.speed_lbl)

        self.osd_btn = QPushButton("🪟 HUD Overlay: OFF")
        self.osd_btn.setToolTip("Toggle transparent in-game floating HUD overlay")
        self.osd_btn.clicked.connect(self._toggle_osd_overlay)

        self.quick_attach_btn = QPushButton("🎯 Attach Active Window")
        self.quick_attach_btn.setToolTip("Quickly attach to the currently focused Hyprland window")
        self.quick_attach_btn.clicked.connect(self._attach_active_hyprland_window)

        self.detach_btn = QPushButton("✕ Detach")
        self.detach_btn.setObjectName("danger_btn")
        self.detach_btn.setEnabled(False)
        self.detach_btn.clicked.connect(self.detach_target)

        header.addWidget(title_lbl)
        header.addSpacing(12)
        header.addWidget(self.target_badge)
        header.addSpacing(15)
        header.addLayout(speed_box)
        header.addStretch()
        header.addWidget(self.osd_btn)
        header.addWidget(self.quick_attach_btn)
        header.addWidget(self.detach_btn)
        main_layout.addLayout(header)

        # Tab Widget
        self.tabs = QTabWidget()

        self.process_tab = ProcessTab()
        self.scanner_tab = ScannerTab()
        self.injector_tab = InjectorTab()
        self.hex_tab = HexTab()
        self.struct_tab = StructTab()
        self.symbols_tab = SymbolsTab()
        self.snapshot_tab = SnapshotTab()
        self.treemap_tab = TreemapTab()
        self.syscalls_tab = SyscallsTab()
        self.deserializer_tab = DeserializerTab()
        self.console_tab = ConsoleTab()
        self.threads_tab = ThreadsTab()
        self.handles_tab = HandlesTab()

        self.tabs.addTab(self.process_tab, "⚡ Processes & Windows")
        self.tabs.addTab(self.scanner_tab, "🔍 Memory Scanner")
        self.tabs.addTab(self.injector_tab, "💉 .so Injector")
        self.tabs.addTab(self.hex_tab, "🧬 Hex & Disasm")
        self.tabs.addTab(self.struct_tab, "🔬 Struct Dissector")
        self.tabs.addTab(self.symbols_tab, "📦 ELF Symbols")
        self.tabs.addTab(self.snapshot_tab, "📸 Snapshot Diff")
        self.tabs.addTab(self.treemap_tab, "🗺️ Memory Treemap")
        self.tabs.addTab(self.syscalls_tab, "📡 Syscall Monitor")
        self.tabs.addTab(self.deserializer_tab, "🧩 Data Deserializer")
        self.tabs.addTab(self.console_tab, "🐍 Python Console")
        self.tabs.addTab(self.threads_tab, "🧵 Threads")
        self.tabs.addTab(self.handles_tab, "🌐 Sockets & Handles")

        main_layout.addWidget(self.tabs, 1)

        # Connect signals
        self.process_tab.target_attached.connect(self.attach_target)
        self.struct_tab.add_to_cheat_table.connect(self.scanner_tab.add_cheat_entry)
        self.struct_tab.jump_to_hex.connect(self._jump_to_hex_address)
        self.symbols_tab.add_to_cheat_table.connect(self.scanner_tab.add_cheat_entry)
        self.symbols_tab.jump_to_disasm.connect(self._jump_to_disasm_address)
        self.snapshot_tab.add_to_cheat_table.connect(self.scanner_tab.add_cheat_entry)
        self.snapshot_tab.jump_to_hex.connect(self._jump_to_hex_address)
        self.treemap_tab.jump_to_hex.connect(self._jump_to_hex_address)
        self.treemap_tab.jump_to_struct.connect(self._jump_to_struct_address)
        self.deserializer_tab.add_to_cheat_table.connect(self.scanner_tab.add_cheat_entry)
        self.deserializer_tab.jump_to_hex.connect(self._jump_to_hex_address)

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
        self.struct_tab.set_target(pid, name)
        self.symbols_tab.set_target(pid, name)
        self.snapshot_tab.set_target(pid, name)
        self.treemap_tab.set_target(pid, name)
        self.syscalls_tab.set_target(pid, name)
        self.deserializer_tab.set_target(pid, name)
        self.console_tab.set_target(pid, name)
        self.threads_tab.set_target(pid, name)
        self.handles_tab.set_target(pid, name)

        if self.osd_overlay.isVisible():
            self.osd_overlay.set_target(pid, name)
            self.osd_overlay.set_pinned_entries(self.scanner_tab.get_saved_entries())

        self.status_lbl.setText(f"Attached to process {name} (PID: {pid}).")
        
        # Check speedhack state
        self.speed_btn.setEnabled(True)
        is_inj = SpeedhackController.is_injected(pid)
        if is_inj:
            speed, enabled = SpeedhackController.get_speed(pid)
            self.speed_slider.setEnabled(True)
            self.speed_slider.setValue(int(speed * 10))
            self.speed_lbl.setText(f"{speed:.1f}x")
            self.speed_btn.setText(f"⚡ Speedhack: {'ON' if enabled else 'OFF'}")
            if enabled:
                self.speed_btn.setStyleSheet("color: #ff007f; border-color: #ff007f;")
        else:
            self.speed_btn.setText("⚡ Inject Speedhack")
            self.speed_btn.setStyleSheet("")
            self.speed_slider.setEnabled(False)

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
        self.speed_btn.setEnabled(False)
        self.speed_btn.setText("⚡ Speedhack: OFF")
        self.speed_btn.setStyleSheet("")
        self.speed_slider.setEnabled(False)

        self.scanner_tab.clear_target()
        self.injector_tab.clear_target()
        self.hex_tab.clear_target()
        self.struct_tab.clear_target()
        self.symbols_tab.clear_target()
        self.snapshot_tab.clear_target()
        self.treemap_tab.clear_target()
        self.syscalls_tab.clear_target()
        self.deserializer_tab.clear_target()
        self.console_tab.clear_target()
        self.threads_tab.clear_target()
        self.handles_tab.clear_target()
        self.osd_overlay.clear_target()

        self.status_lbl.setText("Detached from target process.")

    def _jump_to_hex_address(self, address: int):
        self.hex_tab.navigate_to_address(address)
        self.tabs.setCurrentWidget(self.hex_tab)

    def _jump_to_disasm_address(self, address: int):
        self.hex_tab.navigate_to_address(address)
        self.tabs.setCurrentWidget(self.hex_tab)

    def _jump_to_struct_address(self, address: int):
        self.struct_tab.set_base_address(address)
        self.tabs.setCurrentWidget(self.struct_tab)

    def _toggle_osd_overlay(self):
        if self.osd_overlay.isVisible():
            self.osd_overlay.hide()
            self.osd_btn.setText("🪟 HUD Overlay: OFF")
            self.osd_btn.setStyleSheet("")
        else:
            if self.current_target_pid:
                self.osd_overlay.set_target(self.current_target_pid, self.current_target_name)
                self.osd_overlay.set_pinned_entries(self.scanner_tab.get_saved_entries())
            self.osd_overlay.show()
            self.osd_btn.setText("🪟 HUD Overlay: ON")
            self.osd_btn.setStyleSheet("color: #00f0ff; border-color: #00f0ff;")

    def _toggle_speedhack(self):
        if not self.current_target_pid:
            return

        pid = self.current_target_pid
        if not SpeedhackController.is_injected(pid):
            self.status_lbl.setText(f"Injecting speedhack.so into PID {pid}...")
            ok, msg = SpeedhackController.inject(pid)
            if ok:
                self.status_lbl.setText(f"Speedhack active in PID {pid}!")
                self.speed_slider.setEnabled(True)
                self.speed_btn.setText("⚡ Speedhack: ON")
                self.speed_btn.setStyleSheet("color: #ff007f; border-color: #ff007f;")
                val = self.speed_slider.value() / 10.0
                SpeedhackController.set_speed(pid, val, enabled=True)
                # Refresh modules tab if open
                self.injector_tab.refresh_modules()
            else:
                QMessageBox.critical(self, "Speedhack Injection Failed", msg)
        else:
            # Toggle enabled state
            curr_speed, curr_enabled = SpeedhackController.get_speed(pid)
            new_state = not curr_enabled
            SpeedhackController.set_speed(pid, curr_speed, enabled=new_state)
            self.speed_btn.setText(f"⚡ Speedhack: {'ON' if new_state else 'OFF'}")
            if new_state:
                self.speed_btn.setStyleSheet("color: #ff007f; border-color: #ff007f;")
            else:
                self.speed_btn.setStyleSheet("")

    def _on_speed_changed(self, int_val: int):
        speed = int_val / 10.0
        self.speed_lbl.setText(f"{speed:.1f}x")
        if self.current_target_pid and SpeedhackController.is_injected(self.current_target_pid):
            SpeedhackController.set_speed(self.current_target_pid, speed, enabled=True)

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
