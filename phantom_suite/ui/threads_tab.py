"""
PhantomSuite Thread Explorer Tab
Inspects threads, per-thread state, CPU core affinity, and controls.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QGroupBox, QInputDialog, QAbstractItemView
)
from PySide6.QtCore import Qt
from phantom_suite.core.thread_manager import ThreadManager, ThreadInfo


class ThreadsTab(QWidget):
    """Thread Explorer, tgkill signal controller, and core affinity manager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.threads: List[ThreadInfo] = []

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.refresh_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(True)
        self.affinity_btn.setEnabled(True)
        self.refresh_threads()

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.refresh_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.affinity_btn.setEnabled(False)
        self.table.setRowCount(0)
        self.count_lbl.setText("0 threads")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target Banner
        banner_layout = QHBoxLayout()
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.count_lbl = QLabel("0 threads")
        self.count_lbl.setStyleSheet("color: #7d90b3;")
        banner_layout.addWidget(self.target_lbl)
        banner_layout.addStretch()
        banner_layout.addWidget(self.count_lbl)
        layout.addLayout(banner_layout)

        # Controls & Search Bar
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter threads by TID or name...")
        self.search_input.textChanged.connect(self._filter_table)

        self.refresh_btn = QPushButton("⟳ Refresh Threads")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.clicked.connect(self.refresh_threads)

        top_bar.addWidget(self.search_input, 2)
        top_bar.addWidget(self.refresh_btn)
        layout.addLayout(top_bar)

        # Threads Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "TID", "Thread Name", "State", "Core", "CPU Time (u/s)", "Affinity Cores"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()
        self.pause_btn = QPushButton("⏸ Pause Thread (SIGSTOP)")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._pause_selected)

        self.resume_btn = QPushButton("▶ Resume Thread (SIGCONT)")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self._resume_selected)

        self.affinity_btn = QPushButton("⚙ Set CPU Affinity")
        self.affinity_btn.setEnabled(False)
        self.affinity_btn.clicked.connect(self._set_affinity)

        bottom_bar.addWidget(self.pause_btn)
        bottom_bar.addWidget(self.resume_btn)
        bottom_bar.addWidget(self.affinity_btn)
        bottom_bar.addStretch()
        layout.addLayout(bottom_bar)

    def refresh_threads(self):
        if not self.target_pid:
            return
        self.threads = ThreadManager.list_threads(self.target_pid)
        self.count_lbl.setText(f"{len(self.threads)} active threads")
        self._filter_table()

    def _filter_table(self):
        query = self.search_input.text().strip().lower()
        filtered = []
        for t in self.threads:
            if query:
                haystack = f"{t.tid} {t.name} {t.state}".lower()
                if query not in haystack:
                    continue
            filtered.append(t)

        self.table.setRowCount(len(filtered))
        for row, t in enumerate(filtered):
            tid_item = QTableWidgetItem(str(t.tid))
            tid_item.setData(Qt.UserRole, t.tid)
            tid_item.setForeground(Qt.yellow)

            name_item = QTableWidgetItem(t.name)
            name_item.setForeground(Qt.cyan)

            state_item = QTableWidgetItem(t.state)
            if t.state == "R":
                state_item.setForeground(Qt.green)
            elif t.state == "T":
                state_item.setForeground(Qt.magenta)

            core_item = QTableWidgetItem(str(t.cpu_id))
            cpu_item = QTableWidgetItem(f"{t.utime}s / {t.stime}s")

            aff_str = f"{len(t.affinity)} cores" if len(t.affinity) > 4 else ", ".join(str(c) for c in t.affinity)
            aff_item = QTableWidgetItem(aff_str)

            self.table.setItem(row, 0, tid_item)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, state_item)
            self.table.setItem(row, 3, core_item)
            self.table.setItem(row, 4, cpu_item)
            self.table.setItem(row, 5, aff_item)

    def _get_selected_tid(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        tid_item = self.table.item(row, 0)
        return tid_item.data(Qt.UserRole) if tid_item else None

    def _pause_selected(self):
        tid = self._get_selected_tid()
        if not tid or not self.target_pid:
            QMessageBox.warning(self, "No Selection", "Please select a thread first.")
            return
        if ThreadManager.pause_thread(self.target_pid, tid):
            self.refresh_threads()

    def _resume_selected(self):
        tid = self._get_selected_tid()
        if not tid or not self.target_pid:
            QMessageBox.warning(self, "No Selection", "Please select a thread first.")
            return
        if ThreadManager.resume_thread(self.target_pid, tid):
            self.refresh_threads()

    def _set_affinity(self):
        tid = self._get_selected_tid()
        if not tid:
            QMessageBox.warning(self, "No Selection", "Please select a thread first.")
            return

        cores_str, ok = QInputDialog.getText(
            self, "Set Thread Affinity",
            f"Enter comma-separated CPU cores for TID {tid} (e.g. 0, 1 or 2):",
            text="0"
        )
        if ok and cores_str.strip():
            try:
                cpus = [int(c.strip()) for c in cores_str.split(",") if c.strip()]
                if ThreadManager.set_thread_affinity(tid, cpus):
                    self.refresh_threads()
                    QMessageBox.information(self, "Affinity Updated", f"TID {tid} pinned to CPU cores: {cpus}")
                else:
                    QMessageBox.critical(self, "Failed", "Could not set CPU affinity.")
            except ValueError:
                QMessageBox.warning(self, "Invalid Cores", "Please enter valid integers separated by commas.")
