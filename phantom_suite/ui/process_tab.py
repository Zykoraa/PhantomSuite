"""
PhantomSuite Process Explorer & Window Selector Tab
Displays running processes with Hyprland window detection and process controls.
"""

from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from phantom_suite.core.process_manager import ProcessManager, ProcessInfo


class ProcessTab(QWidget):
    """Process listing, filtering, Hyprland window selection, and process control."""

    target_attached = Signal(int, str, str)  # pid, name, window_title

    def __init__(self, parent=None):
        super().__init__(parent)
        self.procs: List[ProcessInfo] = []
        self._init_ui()
        self.refresh_processes()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top Controls Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        search_lbl = QLabel("Search:")
        search_lbl.setStyleSheet("color: #7d90b3; font-weight: bold;")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by PID, name, window title, or class...")
        self.search_input.textChanged.connect(self._filter_table)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "All Visible Processes",
            "Hyprland Windows Only",
            "My User Processes Only"
        ])
        self.filter_combo.currentIndexChanged.connect(self._filter_table)

        refresh_btn = QPushButton("⟳ Refresh")
        refresh_btn.clicked.connect(self.refresh_processes)

        top_bar.addWidget(search_lbl)
        top_bar.addWidget(self.search_input, 2)
        top_bar.addWidget(self.filter_combo)
        top_bar.addWidget(refresh_btn)
        layout.addLayout(top_bar)

        # Process Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "PID", "Name", "Window Title / Class", "RSS (MB)", "User", "State"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_row_double_click)

        layout.addWidget(self.table, 1)

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self.attach_btn = QPushButton("🎯 Attach Selected as Target")
        self.attach_btn.clicked.connect(self._attach_selected)

        self.pause_btn = QPushButton("⏸ Pause (SIGSTOP)")
        self.pause_btn.clicked.connect(self._pause_selected)

        self.resume_btn = QPushButton("▶ Resume (SIGCONT)")
        self.resume_btn.clicked.connect(self._resume_selected)

        self.term_btn = QPushButton("✖ Terminate (SIGTERM)")
        self.term_btn.setObjectName("danger_btn")
        self.term_btn.clicked.connect(self._terminate_selected)

        self.kill_btn = QPushButton("⚡ Kill (SIGKILL)")
        self.kill_btn.setObjectName("danger_btn")
        self.kill_btn.clicked.connect(self._kill_selected)

        bottom_bar.addWidget(self.attach_btn)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.pause_btn)
        bottom_bar.addWidget(self.resume_btn)
        bottom_bar.addWidget(self.term_btn)
        bottom_bar.addWidget(self.kill_btn)
        layout.addLayout(bottom_bar)

    def refresh_processes(self):
        """Reloads all processes and updates the view."""
        self.procs = ProcessManager.list_processes()
        self._filter_table()

    def _filter_table(self):
        query = self.search_input.text().strip().lower()
        filter_mode = self.filter_combo.currentIndex()

        filtered = []
        for p in self.procs:
            if filter_mode == 1 and not p.is_window:
                continue
            if filter_mode == 2 and p.user != os.environ.get("USER", ""):
                continue

            if query:
                haystack = f"{p.pid} {p.name} {p.window_title} {p.window_class} {p.cmdline} {p.user}".lower()
                if query not in haystack:
                    continue
            filtered.append(p)

        self.table.setRowCount(len(filtered))
        for row, p in enumerate(filtered):
            # PID
            pid_item = QTableWidgetItem(str(p.pid))
            pid_item.setData(Qt.UserRole, p.pid)
            if p.is_window:
                pid_item.setForeground(Qt.cyan)

            # Name
            name_text = f"🪟 {p.name}" if p.is_window else p.name
            name_item = QTableWidgetItem(name_text)
            if p.is_window:
                name_item.setForeground(Qt.cyan)

            # Window Title / Class
            win_desc = ""
            if p.is_window:
                win_desc = f"{p.window_title} [{p.window_class}]" if p.window_title else f"[{p.window_class}]"
            win_item = QTableWidgetItem(win_desc)
            if p.is_window:
                win_item.setForeground(Qt.green)

            # RSS
            rss_item = QTableWidgetItem(f"{p.rss_mb:.1f} MB")
            rss_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # User
            user_item = QTableWidgetItem(p.user)

            # State
            state_item = QTableWidgetItem(p.state)

            self.table.setItem(row, 0, pid_item)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, win_item)
            self.table.setItem(row, 3, rss_item)
            self.table.setItem(row, 4, user_item)
            self.table.setItem(row, 5, state_item)

    def _get_selected_proc(self) -> Optional[ProcessInfo]:
        row = self.table.currentRow()
        if row < 0:
            return None
        pid_item = self.table.item(row, 0)
        if not pid_item:
            return None
        pid = pid_item.data(Qt.UserRole)
        for p in self.procs:
            if p.pid == pid:
                return p
        return None

    def _attach_selected(self):
        p = self._get_selected_proc()
        if not p:
            QMessageBox.warning(self, "No Selection", "Please select a process from the list first.")
            return
        self.target_attached.emit(p.pid, p.name, p.window_title)

    def _on_row_double_click(self, index):
        self._attach_selected()

    def _pause_selected(self):
        p = self._get_selected_proc()
        if p and ProcessManager.pause_process(p.pid):
            self.refresh_processes()

    def _resume_selected(self):
        p = self._get_selected_proc()
        if p and ProcessManager.resume_process(p.pid):
            self.refresh_processes()

    def _terminate_selected(self):
        p = self._get_selected_proc()
        if p and ProcessManager.terminate_process(p.pid):
            self.refresh_processes()

    def _kill_selected(self):
        p = self._get_selected_proc()
        if p and ProcessManager.kill_process(p.pid):
            self.refresh_processes()
