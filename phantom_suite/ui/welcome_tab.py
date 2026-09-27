"""
PhantomSuite Welcome & Quick Launch Hub
High-level mission control dashboard with 1-click actions and recent targets.
"""

from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLabel, QFrame, QListWidget, QListWidgetItem, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from phantom_suite.core.recent_targets import RecentTargetsManager
from phantom_suite.core.process_manager import ProcessManager


class WelcomeTab(QWidget):
    """Mission control dashboard offering quick actions and recent targets."""

    attach_active_requested = Signal()
    browse_processes_requested = Signal()
    load_table_requested = Signal()
    open_console_requested = Signal()
    target_selected = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        # Hero Banner
        banner = QVBoxLayout()
        banner.setSpacing(6)

        title_lbl = QLabel("PHANTOM<font color='#00f0ff'>SUITE</font> // <font color='#ff007f'>MISSION CONTROL</font>")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; letter-spacing: 2px;")
        banner.addWidget(title_lbl)

        sub_lbl = QLabel("High-Performance Native Linux Reverse Engineering, Memory Scanner & Process Workbench")
        sub_lbl.setStyleSheet("color: #798aa8; font-size: 13px;")
        banner.addWidget(sub_lbl)

        layout.addLayout(banner)

        # Quick Action Cards (2x2 Grid)
        grid = QGridLayout()
        grid.setSpacing(14)

        card_attach = self._create_card(
            "🎯 Attach Active Window",
            "Auto-detect and attach to the currently focused Hyprland / Wayland window.",
            self.attach_active_requested.emit
        )
        card_procs = self._create_card(
            "⚡ Process Explorer",
            "Search and filter through running system processes, daemons, and application windows.",
            self.browse_processes_requested.emit
        )
        card_table = self._create_card(
            "📂 Load Saved Cheat Table",
            "Open an ASLR-resilient .phantom table to freeze values and track pointers.",
            self.load_table_requested.emit
        )
        card_console = self._create_card(
            "🐍 Python Scripting Console",
            "Automate memory reading, AOB patching, and struct dissection via Python REPL.",
            self.open_console_requested.emit
        )

        grid.addWidget(card_attach, 0, 0)
        grid.addWidget(card_procs, 0, 1)
        grid.addWidget(card_table, 1, 0)
        grid.addWidget(card_console, 1, 1)

        layout.addLayout(grid)

        # Recent Targets Section
        recents_box = QVBoxLayout()
        recents_box.setSpacing(8)

        recents_header = QHBoxLayout()
        recents_title = QLabel("RECENT TARGETS")
        recents_title.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 12px; letter-spacing: 1px;")
        recents_header.addWidget(recents_title)
        recents_header.addStretch()

        clear_btn = QPushButton("Clear History")
        clear_btn.setStyleSheet(
            "background: transparent; color: #5d6f8f; border: none; font-size: 11px;"
        )
        clear_btn.clicked.connect(self._on_clear_history)
        recents_header.addWidget(clear_btn)
        recents_box.addLayout(recents_header)

        self.recents_list = QListWidget()
        self.recents_list.setStyleSheet(
            "QListWidget {"
            "  background-color: #0b0e14;"
            "  border: 1px solid #1c2638;"
            "  border-radius: 6px;"
            "  padding: 6px;"
            "}"
            "QListWidget::item {"
            "  padding: 8px 12px;"
            "  border-radius: 4px;"
            "  margin-bottom: 3px;"
            "}"
            "QListWidget::item:hover {"
            "  background-color: #162438;"
            "  color: #00f0ff;"
            "}"
        )
        self.recents_list.itemActivated.connect(self._on_recent_activated)
        recents_box.addWidget(self.recents_list, 1)

        layout.addLayout(recents_box, 1)
        self.refresh_recents()

    def _create_card(self, title: str, desc: str, callback) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame {"
            "  background-color: #0e131d;"
            "  border: 1px solid #1d2a3f;"
            "  border-radius: 6px;"
            "  padding: 12px;"
            "}"
            "QFrame:hover {"
            "  border: 1px solid #00f0ff;"
            "  background-color: #121926;"
            "}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(6)

        btn = QPushButton(title)
        btn.setStyleSheet(
            "QPushButton {"
            "  text-align: left;"
            "  font-size: 14px;"
            "  font-weight: bold;"
            "  color: #00f0ff;"
            "  background: transparent;"
            "  border: none;"
            "  padding: 0px;"
            "}"
        )
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(callback)
        card_layout.addWidget(btn)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet("color: #798aa8; font-size: 11px;")
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(desc_lbl)

        return card

    def refresh_recents(self):
        """Reloads recent targets from disk and displays them."""
        self.recents_list.clear()
        recents = RecentTargetsManager.get_recents()
        if not recents:
            item = QListWidgetItem("No recent targets recorded yet. Attach to any process to get started.")
            item.setForeground(Qt.gray)
            self.recents_list.addItem(item)
            return

        for r in recents:
            pid = r.get("pid", 0)
            name = r.get("name", "Unknown")
            time_str = r.get("time_str", "")
            exe_path = r.get("exe_path", "")
            item = QListWidgetItem(f"⚡ [{pid}] {name}  —  {exe_path}  ({time_str})")
            item.setData(Qt.UserRole, r)
            self.recents_list.addItem(item)

    def _on_recent_activated(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        target_name = data.get("name")
        target_pid = data.get("pid")

        # Check if process is still running with that PID
        procs = ProcessManager.get_all_processes()
        matched = next((p for p in procs if p.pid == target_pid and p.name == target_name), None)
        if matched:
            self.target_selected.emit(matched.pid, matched.name)
            return

        # If not, look for running process with matching name
        name_match = next((p for p in procs if p.name == target_name), None)
        if name_match:
            self.target_selected.emit(name_match.pid, name_match.name)
            return

        # If process not found, emit original PID/name
        self.target_selected.emit(target_pid, target_name)

    def _on_clear_history(self):
        RecentTargetsManager.clear()
        self.refresh_recents()
