"""
PhantomSuite Glibc Heap Allocator Introspector Dialog
Visualizes heap chunks (ptmalloc / tcache), validates chunk boundaries,
calculates fragmentation, and highlights heap corruption anomalies.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from phantom_suite.core.heap_inspector import HeapInspector, HeapSnapshot, HeapChunk


class HeapDialog(QDialog):
    """Dialog for inspecting process heap chunks and allocator state."""

    def __init__(self, pid: int, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.snapshot: Optional[HeapSnapshot] = None

        self.setWindowTitle(f"Heap Allocator Introspector // PID: {pid}")
        self.resize(900, 560)
        self._init_ui()
        self._refresh_heap()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header KPIs
        kpi_bar = QHBoxLayout()

        self.base_lbl = QLabel("Base: -")
        self.base_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.size_lbl = QLabel("Size: -")
        self.size_lbl.setStyleSheet("color: #7d90b3;")
        self.alloc_lbl = QLabel("Alloc: 0")
        self.alloc_lbl.setStyleSheet("color: #00ff9d;")
        self.freed_lbl = QLabel("Freed: 0")
        self.freed_lbl.setStyleSheet("color: #ffb700;")
        self.frag_lbl = QLabel("Fragmentation: 0.0%")
        self.frag_lbl.setStyleSheet("color: #ff0055;")

        kpi_bar.addWidget(self.base_lbl)
        kpi_bar.addWidget(self.size_lbl)
        kpi_bar.addWidget(self.alloc_lbl)
        kpi_bar.addWidget(self.freed_lbl)
        kpi_bar.addWidget(self.frag_lbl)
        kpi_bar.addStretch()

        refresh_btn = QPushButton("🔄 Refresh Heap")
        refresh_btn.setObjectName("accent_btn")
        refresh_btn.clicked.connect(self._refresh_heap)
        kpi_bar.addWidget(refresh_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        kpi_bar.addWidget(close_btn)

        layout.addLayout(kpi_bar)

        # Chunks Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Address", "Chunk Size", "Prev Size", "State", "Prev InUse", "User Data", "Anomaly"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)

    def _refresh_heap(self):
        self.snapshot = HeapInspector.audit_heap(self.pid, max_chunks=300)
        if not self.snapshot:
            QMessageBox.warning(self, "Heap Warning", f"Could not find or read [heap] region for PID {self.pid}.")
            return

        self.base_lbl.setText(f"Heap Base: 0x{self.snapshot.heap_base:X}")
        self.size_lbl.setText(f"Size: {self.snapshot.total_size / 1024:.1f} KB")
        self.alloc_lbl.setText(f"Allocated: {self.snapshot.allocated_count}")
        self.freed_lbl.setText(f"Freed: {self.snapshot.freed_count}")
        self.frag_lbl.setText(f"Fragmentation: {self.snapshot.fragmentation_ratio * 100:.1f}%")

        self.table.setRowCount(len(self.snapshot.chunks))
        for row, c in enumerate(self.snapshot.chunks):
            addr_item = QTableWidgetItem(f"0x{c.address:X}")
            addr_item.setForeground(QColor("#00f0ff"))

            size_item = QTableWidgetItem(f"0x{c.chunk_size:X} ({c.chunk_size})")
            prev_item = QTableWidgetItem(f"0x{c.prev_size:X}")

            state_item = QTableWidgetItem(c.state.upper())
            if c.state == "allocated":
                state_item.setForeground(QColor("#00ff9d"))
            elif c.state == "freed":
                state_item.setForeground(QColor("#ffb700"))
            elif c.state == "top_chunk":
                state_item.setForeground(QColor("#7d90b3"))
            else: # Corrupted
                state_item.setForeground(QColor("#ff0055"))

            inuse_item = QTableWidgetItem("YES" if c.is_prev_inuse else "NO")
            user_item = QTableWidgetItem(f"0x{c.user_data_addr:X} ({c.user_data_size}b)")
            anomaly_item = QTableWidgetItem(c.anomaly or "-")
            if c.anomaly:
                anomaly_item.setForeground(QColor("#ff0055"))

            self.table.setItem(row, 0, addr_item)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, prev_item)
            self.table.setItem(row, 3, state_item)
            self.table.setItem(row, 4, inuse_item)
            self.table.setItem(row, 5, user_item)
            self.table.setItem(row, 6, anomaly_item)
