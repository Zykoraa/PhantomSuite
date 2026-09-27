"""
PhantomSuite Handles & Sockets Tab
Inspects open file descriptors, network connections, pipes, and devices.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QGroupBox, QAbstractItemView
)
from PySide6.QtCore import Qt
from phantom_suite.core.handle_tracer import HandleTracer, HandleInfo


class HandlesTab(QWidget):
    """File Descriptors, Network Sockets, and IPC Handle Explorer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.handles: List[HandleInfo] = []

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.refresh_btn.setEnabled(True)
        self.refresh_handles()

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.refresh_btn.setEnabled(False)
        self.table.setRowCount(0)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target Banner
        banner_layout = QHBoxLayout()
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.count_lbl = QLabel("0 handles")
        self.count_lbl.setStyleSheet("color: #7d90b3;")
        banner_layout.addWidget(self.target_lbl)
        banner_layout.addStretch()
        banner_layout.addWidget(self.count_lbl)
        layout.addLayout(banner_layout)

        # Filter Bar
        filter_group = QGroupBox("Filter Handles")
        filter_layout = QHBoxLayout(filter_group)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by FD, path, IP, or socket...")
        self.search_input.textChanged.connect(self._filter_table)

        self.kind_combo = QComboBox()
        self.kind_combo.addItems([
            "All Handle Types",
            "Sockets (Network / IPC)",
            "Regular Files",
            "Pipes (IPC)",
            "Devices"
        ])
        self.kind_combo.currentIndexChanged.connect(self._filter_table)

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.clicked.connect(self.refresh_handles)

        filter_layout.addWidget(self.search_input, 2)
        filter_layout.addWidget(self.kind_combo)
        filter_layout.addWidget(self.refresh_btn)
        layout.addWidget(filter_group)

        # Handles Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["FD", "Type", "Target / Inode", "Details"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        layout.addWidget(self.table, 1)

    def refresh_handles(self):
        if not self.target_pid:
            self.table.setRowCount(0)
            self.count_lbl.setText("0 handles")
            return
        self.handles = HandleTracer.list_handles(self.target_pid)
        self.count_lbl.setText(f"{len(self.handles)} open handles")
        self._filter_table()

    def _filter_table(self):
        query = self.search_input.text().strip().lower()
        filter_idx = self.kind_combo.currentIndex()

        kind_map = {
            1: "SOCKET",
            2: "FILE",
            3: "PIPE",
            4: "DEVICE"
        }
        target_kind = kind_map.get(filter_idx)

        filtered = []
        for h in self.handles:
            if target_kind and h.kind != target_kind:
                continue
            if query:
                haystack = f"{h.fd} {h.kind} {h.target} {h.details}".lower()
                if query not in haystack:
                    continue
            filtered.append(h)

        self.table.setRowCount(len(filtered))
        for row, h in enumerate(filtered):
            fd_item = QTableWidgetItem(str(h.fd))
            kind_item = QTableWidgetItem(h.kind)

            if h.kind == "SOCKET":
                kind_item.setForeground(Qt.green)
            elif h.kind == "PIPE":
                kind_item.setForeground(Qt.yellow)
            elif h.kind == "FILE":
                kind_item.setForeground(Qt.cyan)

            target_item = QTableWidgetItem(h.target)
            details_item = QTableWidgetItem(h.details)

            self.table.setItem(row, 0, fd_item)
            self.table.setItem(row, 1, kind_item)
            self.table.setItem(row, 2, target_item)
            self.table.setItem(row, 3, details_item)
