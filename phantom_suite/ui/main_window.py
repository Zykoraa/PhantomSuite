"""
PhantomSuite Main Window
Orchestrates the modern collapsible sidebar, tabs, command palette, and target lifecycle.
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
from PySide6.QtGui import QKeySequence, QShortcut

from phantom_suite.theme import CYBERPUNK_QSS
from phantom_suite.core.speedhack_controller import SpeedhackController
from phantom_suite.core.process_manager import ProcessManager
from phantom_suite.core.recent_targets import RecentTargetsManager

from phantom_suite.ui.sidebar import SidebarWidget
from phantom_suite.ui.command_palette import CommandPaletteDialog, CommandAction
from phantom_suite.ui.shortcuts_dialog import ShortcutsDialog
from phantom_suite.ui.welcome_tab import WelcomeTab
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
        self.resize(1280, 840)
        self.setStyleSheet(CYBERPUNK_QSS)

        self.current_target_pid: Optional[int] = None
        self.current_target_name: str = ""
        self._target_paused: bool = False
        self.osd_overlay = OsdOverlay()

        self.command_palette = CommandPaletteDialog(self)
        self.shortcuts_dialog = ShortcutsDialog(self)

        self._init_ui()
        self._setup_command_palette()
        self._setup_shortcuts()
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

        # Command Palette Button
        self.palette_header_btn = QPushButton("⌘ Palette [Ctrl+K]")
        self.palette_header_btn.setToolTip("Open Command Palette (Ctrl+K or Ctrl+P)")
        self.palette_header_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #121824;"
            "  color: #00f0ff;"
            "  border: 1px solid #1c2638;"
            "  border-radius: 4px;"
            "  padding: 4px 10px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover {"
            "  background-color: #00f0ff;"
            "  color: #0c0e14;"
            "}"
        )
        self.palette_header_btn.clicked.connect(self._open_command_palette)

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
        header.addWidget(self.palette_header_btn)
        header.addWidget(self.osd_btn)
        header.addWidget(self.quick_attach_btn)
        header.addWidget(self.detach_btn)
        main_layout.addLayout(header)

        # Central Layout: Sidebar on Left, Hidden-Bar Tab Stack on Right
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)

        self.sidebar = SidebarWidget()
        body_layout.addWidget(self.sidebar)

        # Tab Widget (with hidden native tab bar for seamless navigation)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()

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
        self.welcome_tab = WelcomeTab()

        self.tabs.addTab(self.process_tab, "⚡ Processes & Windows")       # Index 0
        self.tabs.addTab(self.scanner_tab, "🔍 Memory Scanner")            # Index 1
        self.tabs.addTab(self.injector_tab, "💉 .so Injector")             # Index 2
        self.tabs.addTab(self.hex_tab, "🧬 Hex & Disasm")                  # Index 3
        self.tabs.addTab(self.struct_tab, "🔬 Struct Dissector")           # Index 4
        self.tabs.addTab(self.symbols_tab, "📦 ELF Symbols")               # Index 5
        self.tabs.addTab(self.snapshot_tab, "📸 Snapshot Diff")            # Index 6
        self.tabs.addTab(self.treemap_tab, "🗺️ Memory Treemap")            # Index 7
        self.tabs.addTab(self.syscalls_tab, "📡 Syscall Monitor")          # Index 8
        self.tabs.addTab(self.deserializer_tab, "🧩 Data Deserializer")    # Index 9
        self.tabs.addTab(self.console_tab, "🐍 Python Console")            # Index 10
        self.tabs.addTab(self.threads_tab, "🧵 Threads")                   # Index 11
        self.tabs.addTab(self.handles_tab, "🌐 Sockets & Handles")         # Index 12
        self.tabs.addTab(self.welcome_tab, "🚀 Mission Control")           # Index 13

        body_layout.addWidget(self.tabs, 1)
        main_layout.addLayout(body_layout, 1)

        # Connect Sidebar & Tab Navigation
        self.sidebar.tab_requested.connect(self.switch_to_tab)
        self.sidebar.palette_requested.connect(self._open_command_palette)
        self.sidebar.shortcuts_requested.connect(self._open_shortcuts_dialog)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Connect Welcome Tab Signals
        self.welcome_tab.attach_active_requested.connect(self._attach_active_hyprland_window)
        self.welcome_tab.browse_processes_requested.connect(lambda: self.switch_to_tab(0))
        self.welcome_tab.load_table_requested.connect(self._load_table_shortcut)
        self.welcome_tab.open_console_requested.connect(lambda: self.switch_to_tab(10))
        self.welcome_tab.target_selected.connect(self.attach_target)

        # Connect Tab-to-Tab Signal Crossings
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

        # Default starting view: Mission Control Dashboard
        self.switch_to_tab(13)

    def _setup_command_palette(self):
        actions = [
            # Navigation Actions
            CommandAction("nav_welcome", "🚀 Mission Control", "NAVIGATION", "Dashboard and recent targets", "Ctrl+0", lambda: self.switch_to_tab(13)),
            CommandAction("nav_processes", "⚡ Processes & Windows", "NAVIGATION", "Inspect running processes and desktop windows", "Ctrl+1", lambda: self.switch_to_tab(0)),
            CommandAction("nav_scanner", "🔍 Memory Scanner", "NAVIGATION", "Memory scanner, value freezer & cheat tables", "Ctrl+2", lambda: self.switch_to_tab(1)),
            CommandAction("nav_snapshot", "📸 Snapshot Diff", "NAVIGATION", "Full-process memory snapshot comparison", "Ctrl+3", lambda: self.switch_to_tab(6)),
            CommandAction("nav_hex", "🧬 Hex & Disasm", "NAVIGATION", "Raw hex dump, live x86_64 disassembly & NOP patcher", "Ctrl+4", lambda: self.switch_to_tab(3)),
            CommandAction("nav_struct", "🔬 Struct Dissector", "NAVIGATION", "Heuristic struct dissection & live heatmaps", "Ctrl+5", lambda: self.switch_to_tab(4)),
            CommandAction("nav_symbols", "📦 ELF Symbols", "NAVIGATION", "Symbol table introspection & module explorer", "Ctrl+6", lambda: self.switch_to_tab(5)),
            CommandAction("nav_treemap", "🗺️ Memory Treemap", "NAVIGATION", "Virtual address space proportional map & KPIs", "Ctrl+7", lambda: self.switch_to_tab(7)),
            CommandAction("nav_syscalls", "📡 Syscall Monitor", "NAVIGATION", "Real-time strace syscall telemetry streaming", "Ctrl+8", lambda: self.switch_to_tab(8)),
            CommandAction("nav_console", "🐍 Python Console", "NAVIGATION", "Embedded Python scripting REPL & automation", "Ctrl+9", lambda: self.switch_to_tab(10)),
            CommandAction("nav_deserializer", "🧩 Data Deserializer", "NAVIGATION", "Decode std::string, std::vector & embedded JSON", "", lambda: self.switch_to_tab(9)),
            CommandAction("nav_injector", "💉 .so Injector", "NAVIGATION", "Dynamic library injection & module explorer", "", lambda: self.switch_to_tab(2)),
            CommandAction("nav_threads", "🧵 Threads & Affinity", "NAVIGATION", "Thread tasks, CPU time & core affinity", "", lambda: self.switch_to_tab(11)),
            CommandAction("nav_handles", "🌐 Sockets & Handles", "NAVIGATION", "File descriptors, TCP/UDP sockets & IPC pipes", "", lambda: self.switch_to_tab(12)),

            # Target & Tool Actions
            CommandAction("act_attach_active", "🎯 Attach Active Window", "ACTION", "Query Hyprland and attach to focused window", "", self._attach_active_hyprland_window),
            CommandAction("act_toggle_speed", "⚡ Speedhack: Toggle", "ACTION", "Toggle speedhack time dilation ON/OFF", "", self._toggle_speedhack),
            CommandAction("act_speed_half", "⚡ Set Speed: 0.5x (Slow-Mo)", "ACTION", "Slow down process execution to 0.5x", "", lambda: self._set_speed_preset(0.5)),
            CommandAction("act_speed_normal", "⚡ Set Speed: 1.0x (Normal)", "ACTION", "Reset process speed to standard 1.0x", "", lambda: self._set_speed_preset(1.0)),
            CommandAction("act_speed_2x", "⚡ Set Speed: 2.0x (Fast)", "ACTION", "Fast-forward process execution to 2.0x", "", lambda: self._set_speed_preset(2.0)),
            CommandAction("act_speed_5x", "⚡ Set Speed: 5.0x (Max)", "ACTION", "Maximum fast-forward to 5.0x", "", lambda: self._set_speed_preset(5.0)),
            CommandAction("act_toggle_hud", "🪟 Toggle HUD Overlay", "ACTION", "Toggle floating in-game OSD cheat HUD", "", self._toggle_osd_overlay),
            CommandAction("act_pause_target", "⏸ Pause / Resume Target", "ACTION", "Send SIGSTOP or SIGCONT to freeze/resume target", "F3", self._toggle_pause_target),
            CommandAction("act_detach", "✕ Detach Target", "ACTION", "Detach from current target process", "", self.detach_target),
            CommandAction("act_save_table", "💾 Save Cheat Table", "ACTION", "Export current address table to .phantom file", "Ctrl+S", self._save_table_shortcut),
            CommandAction("act_load_table", "📂 Load Cheat Table", "ACTION", "Import saved .phantom cheat table", "Ctrl+O", self._load_table_shortcut),
            CommandAction("act_snap_a", "📸 Take Snapshot A", "ACTION", "Capture baseline memory snapshot", "", lambda: (self.switch_to_tab(6), self.snapshot_tab._take_snapshot_a())),
            CommandAction("act_snap_b", "📸 Take Snapshot B", "ACTION", "Capture comparison memory snapshot", "", lambda: (self.switch_to_tab(6), self.snapshot_tab._take_snapshot_b())),
            CommandAction("act_shortcuts", "⌨ Keyboard Shortcuts", "ACTION", "View all global hotkeys and cheat sheet", "F1", self._open_shortcuts_dialog),
            CommandAction("act_toggle_sidebar", "◀ Toggle Sidebar", "ACTION", "Collapse or expand navigation sidebar", "Ctrl+B", self.sidebar.toggle_collapsed),
        ]
        self.command_palette.register_actions(actions)
        self.command_palette.set_address_jump_callback(self._on_address_jump)

    def _setup_shortcuts(self):
        """Registers global application hotkeys."""
        # Command Palette
        QShortcut(QKeySequence("Ctrl+K"), self, self._open_command_palette)
        QShortcut(QKeySequence("Ctrl+P"), self, self._open_command_palette)

        # Toggle Sidebar
        QShortcut(QKeySequence("Ctrl+B"), self, self.sidebar.toggle_collapsed)

        # Shortcuts Help
        QShortcut(QKeySequence("F1"), self, self._open_shortcuts_dialog)
        QShortcut(QKeySequence("?"), self, self._open_shortcuts_dialog)

        # Process Control
        QShortcut(QKeySequence("F3"), self, self._toggle_pause_target)
        QShortcut(QKeySequence("F5"), self, self._refresh_current_view)

        # Tables
        QShortcut(QKeySequence("Ctrl+S"), self, self._save_table_shortcut)
        QShortcut(QKeySequence("Ctrl+O"), self, self._load_table_shortcut)

        # Direct Tab Navigation
        tab_bindings = [
            ("Ctrl+0", 13), # Mission Control
            ("Ctrl+1", 0),  # Processes
            ("Ctrl+2", 1),  # Scanner
            ("Ctrl+3", 6),  # Snapshot
            ("Ctrl+4", 3),  # Hex
            ("Ctrl+5", 4),  # Struct
            ("Ctrl+6", 5),  # Symbols
            ("Ctrl+7", 7),  # Treemap
            ("Ctrl+8", 8),  # Syscalls
            ("Ctrl+9", 10), # Console
        ]
        for key, idx in tab_bindings:
            QShortcut(QKeySequence(key), self, lambda i=idx: self.switch_to_tab(i))

    def switch_to_tab(self, index: int):
        """Switches active view and synchronizes sidebar highlighting."""
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)
            self.sidebar.set_active_tab(index)

    def _on_tab_changed(self, index: int):
        self.sidebar.set_active_tab(index)

    def _open_command_palette(self):
        self.command_palette.show_palette()

    def _open_shortcuts_dialog(self):
        self.shortcuts_dialog.exec_()

    def _on_address_jump(self, target: str, addr: int):
        if target == "hex":
            self._jump_to_hex_address(addr)
        elif target == "struct":
            self._jump_to_struct_address(addr)
        elif target == "pointer":
            self._jump_to_pointer_solver(addr)

    def _jump_to_pointer_solver(self, addr: int):
        if not self.current_target_pid:
            self.status_lbl.setText("Cannot run Pointer Solver: No target attached.")
            return
        from phantom_suite.ui.pointer_dialog import PointerDialog
        from phantom_suite.core.memory_engine import TypeFormat
        dialog = PointerDialog(self.current_target_pid, addr, self)
        dialog.pointer_selected.connect(
            lambda desc, path: self.scanner_tab._insert_cheat_entry(addr, TypeFormat.INT32, f"{desc} [{path}]", "?")
        )
        dialog.exec()

    def _set_speed_preset(self, speed: float):
        if not self.current_target_pid:
            return
        self.speed_slider.setValue(int(speed * 10))
        self._on_speed_changed(int(speed * 10))

    def _toggle_pause_target(self):
        if not self.current_target_pid:
            self.status_lbl.setText("Cannot pause: No target attached.")
            return

        if self._target_paused:
            ProcessManager.resume_process(self.current_target_pid)
            self._target_paused = False
            self.status_lbl.setText(f"Resumed target process (PID: {self.current_target_pid}).")
        else:
            ProcessManager.pause_process(self.current_target_pid)
            self._target_paused = True
            self.status_lbl.setText(f"Paused target process (SIGSTOP) (PID: {self.current_target_pid}).")

    def _refresh_current_view(self):
        curr = self.tabs.currentWidget()
        if hasattr(curr, "refresh"):
            curr.refresh()
        elif hasattr(curr, "_refresh"):
            curr._refresh()
        elif hasattr(curr, "refresh_processes"):
            curr.refresh_processes()
        elif hasattr(curr, "refresh_modules"):
            curr.refresh_modules()
        elif hasattr(curr, "refresh_threads"):
            curr.refresh_threads()
        elif hasattr(curr, "refresh_handles"):
            curr.refresh_handles()
        elif hasattr(curr, "refresh_map"):
            curr.refresh_map()
        elif hasattr(curr, "refresh_recents"):
            curr.refresh_recents()
        self.status_lbl.setText("View refreshed.")

    def _save_table_shortcut(self):
        self.switch_to_tab(1)
        self.scanner_tab._save_table()

    def _load_table_shortcut(self):
        self.switch_to_tab(1)
        self.scanner_tab._load_table()

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
        self._target_paused = False

        # Add to recent target history
        RecentTargetsManager.add_target(pid, name)
        if hasattr(self, "welcome_tab"):
            self.welcome_tab.refresh_recents()

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
        self.switch_to_tab(1)

    def detach_target(self):
        self.current_target_pid = None
        self.current_target_name = ""
        self._target_paused = False

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
        self.switch_to_tab(13) # Return to Mission Control

    def _jump_to_hex_address(self, address: int):
        self.hex_tab.navigate_to_address(address)
        self.switch_to_tab(3)

    def _jump_to_disasm_address(self, address: int):
        self.hex_tab.navigate_to_address(address)
        self.switch_to_tab(3)

    def _jump_to_struct_address(self, address: int):
        self.struct_tab.set_base_address(address)
        self.switch_to_tab(4)

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
