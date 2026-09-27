"""
PhantomSuite Pointer Scanner Dialog
Allows users to discover pointer paths and multi-level offsets for dynamic variables.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QProgressBar, QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal
from phantom_suite.core.pointer_scanner import PointerScanner, PointerPath


class PointerScanWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, pid: int, target_addr: int, max_offset: int, max_depth: int):
        super().__init__()
        self.pid = pid
        self.target_addr = target_addr
        self.max_offset = max_offset
        self.max_depth = max_depth

    def run(self):
        try:
            results = PointerScanner.scan_for_pointers(
                self.pid, self.target_addr, self.max_offset, self.max_depth
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class PointerDialog(QDialog):
    """Dialog for running pointer scans and exporting pointer paths."""

    pointer_selected = Signal(str, str) # description, path_str

    def __init__(self, pid: int, target_address: int, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.target_address = target_address
        self.results: List[PointerPath] = []
        self._worker: Optional[PointerScanWorker] = None

        self.setWindowTitle(f"Pointer Scanner // Target: 0x{target_address:X}")
        self.resize(750, 480)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header info
        info_lbl = QLabel(f"Scanning for pointers resolving to target address: <b>0x{self.target_address:X}</b>")
        info_lbl.setStyleSheet("color: #00f0ff; font-size: 13px;")
        layout.addWidget(info_lbl)

        # Settings
        settings_layout = QHBoxLayout()
        offset_lbl = QLabel("Max Offset:")
        offset_lbl.setStyleSheet("color: #7d90b3;")
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(64, 65536)
        self.offset_spin.setValue(4096)
        self.offset_spin.setSingleStep(256)

        depth_lbl = QLabel("Max Depth:")
        depth_lbl.setStyleSheet("color: #7d90b3;")
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(1, 3)
        self.depth_spin.setValue(2)

        self.scan_btn = QPushButton("🔍 Scan for Pointers")
        self.scan_btn.setObjectName("accent_btn")
        self.scan_btn.clicked.connect(self._start_scan)

        settings_layout.addWidget(offset_lbl)
        settings_layout.addWidget(self.offset_spin)
        settings_layout.addWidget(depth_lbl)
        settings_layout.addWidget(self.depth_spin)
        settings_layout.addStretch()
        settings_layout.addWidget(self.scan_btn)
        layout.addLayout(settings_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate animation
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Results Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Base Module", "Base Offset", "Offsets", "Full Pointer Path"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        self.count_lbl = QLabel("0 pointer paths found")
        self.count_lbl.setStyleSheet("color: #7d90b3;")

        self.add_btn = QPushButton("⬇ Add to Address Table")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._on_add_clicked)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        bottom_layout.addWidget(self.count_lbl)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.add_btn)
        bottom_layout.addWidget(close_btn)
        layout.addLayout(bottom_layout)

    def _start_scan(self):
        self.scan_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.count_lbl.setText("Scanning memory for pointer chains...")

        self._worker = PointerScanWorker(
            self.pid, self.target_address, self.offset_spin.value(), self.depth_spin.value()
        )
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()

    def _on_scan_finished(self, results: List[PointerPath]):
        self.results = results
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.add_btn.setEnabled(len(results) > 0)
        self.count_lbl.setText(f"{len(results)} pointer paths found")

        self.table.setRowCount(len(results))
        for row, p in enumerate(results):
            mod_item = QTableWidgetItem(p.module_name)
            mod_item.setForeground(Qt.cyan)

            base_item = QTableWidgetItem(f"0x{p.base_offset:X}")
            base_item.setForeground(Qt.yellow)

            offs_str = ", ".join(f"0x{o:X}" for o in p.offsets)
            offs_item = QTableWidgetItem(offs_str)

            path_item = QTableWidgetItem(p.to_string())
            path_item.setForeground(Qt.green)

            self.table.setItem(row, 0, mod_item)
            self.table.setItem(row, 1, base_item)
            self.table.setItem(row, 2, offs_item)
            self.table.setItem(row, 3, path_item)

    def _on_scan_error(self, err: str):
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, "Pointer Scan Error", err)

    def _on_add_clicked(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.results):
            QMessageBox.warning(self, "No Selection", "Please select a pointer path first.")
            return

        p = self.results[row]
        self.pointer_selected.emit(f"Ptr: {p.module_name}", p.to_string())
        self.close()
