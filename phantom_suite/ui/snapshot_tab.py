"""
PhantomSuite Memory Snapshot & Differential Comparison Tab
Dumps full-process memory states, computes diffs, and isolates changed variables.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QCheckBox, QMessageBox, QGroupBox, QAbstractItemView,
    QProgressBar, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from phantom_suite.core.snapshot_engine import SnapshotEngine, MemorySnapshot, SnapshotDiffItem
from phantom_suite.core.memory_engine import TypeFormat


class SnapshotWorker(QThread):
    finished = Signal(object) # MemorySnapshot
    error = Signal(str)

    def __init__(self, pid: int):
        super().__init__()
        self.pid = pid

    def run(self):
        try:
            snap = SnapshotEngine.take_snapshot(self.pid, writable_only=True)
            self.finished.emit(snap)
        except Exception as e:
            self.error.emit(str(e))


class DiffWorker(QThread):
    finished = Signal(list) # List[SnapshotDiffItem]
    error = Signal(str)

    def __init__(self, snap_a: MemorySnapshot, snap_b: MemorySnapshot, filter_type: str, stride: int, ignore_noise: bool):
        super().__init__()
        self.snap_a = snap_a
        self.snap_b = snap_b
        self.filter_type = filter_type
        self.stride = stride
        self.ignore_noise = ignore_noise

    def run(self):
        try:
            diffs = SnapshotEngine.compute_diff(
                self.snap_a, self.snap_b,
                filter_type=self.filter_type,
                stride=self.stride,
                ignore_high_noise=self.ignore_noise
            )
            self.finished.emit(diffs)
        except Exception as e:
            self.error.emit(str(e))


class SnapshotTab(QWidget):
    """Full-Process Memory Snapshot & Differential Comparison Tab."""

    add_to_cheat_table = Signal(object, str, str) # address, type, description
    jump_to_hex = Signal(object)                  # address

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.snapshot_a: Optional[MemorySnapshot] = None
        self.snapshot_b: Optional[MemorySnapshot] = None
        self.current_diffs: List[SnapshotDiffItem] = []
        self._worker: Optional[QThread] = None

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.snap_a_btn.setEnabled(True)
        self.snap_b_btn.setEnabled(True)

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.snap_a_btn.setEnabled(False)
        self.snap_b_btn.setEnabled(False)
        self.diff_btn.setEnabled(False)
        self.add_table_btn.setEnabled(False)
        self.jump_hex_btn.setEnabled(False)
        self.snapshot_a = None
        self.snapshot_b = None
        self.current_diffs.clear()
        self.snap_a_status.setText("Snapshot A: Not captured")
        self.snap_b_status.setText("Snapshot B: Not captured")
        self.diff_table.setRowCount(0)
        self.count_lbl.setText("0 differences")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target Banner
        banner_layout = QHBoxLayout()
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.count_lbl = QLabel("0 differences")
        self.count_lbl.setStyleSheet("color: #7d90b3;")
        banner_layout.addWidget(self.target_lbl)
        banner_layout.addStretch()
        banner_layout.addWidget(self.count_lbl)
        layout.addLayout(banner_layout)

        # Snapshot Controls Group
        ctrl_group = QGroupBox("Full-Process Memory Snapshot & Diff")
        ctrl_layout = QVBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(8)

        row1 = QHBoxLayout()
        self.snap_a_btn = QPushButton("📷 Take Snapshot A")
        self.snap_a_btn.setObjectName("accent_btn")
        self.snap_a_btn.setEnabled(False)
        self.snap_a_btn.clicked.connect(self._take_snapshot_a)

        self.snap_a_status = QLabel("Snapshot A: Not captured")
        self.snap_a_status.setStyleSheet("color: #7d90b3;")

        self.snap_b_btn = QPushButton("📸 Take Snapshot B")
        self.snap_b_btn.setObjectName("accent_btn")
        self.snap_b_btn.setEnabled(False)
        self.snap_b_btn.clicked.connect(self._take_snapshot_b)

        self.snap_b_status = QLabel("Snapshot B: Not captured")
        self.snap_b_status.setStyleSheet("color: #7d90b3;")

        row1.addWidget(self.snap_a_btn)
        row1.addWidget(self.snap_a_status)
        row1.addSpacing(20)
        row1.addWidget(self.snap_b_btn)
        row1.addWidget(self.snap_b_status)
        row1.addStretch()
        ctrl_layout.addLayout(row1)

        row2 = QHBoxLayout()
        filter_lbl = QLabel("Compare:")
        filter_lbl.setStyleSheet("color: #7d90b3;")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Changes", "Increased Values", "Decreased Values"])

        stride_lbl = QLabel("Stride:")
        stride_lbl.setStyleSheet("color: #7d90b3;")
        self.stride_combo = QComboBox()
        self.stride_combo.addItems(["4 Bytes (int32 / float)", "8 Bytes (int64 / ptr)", "1 Byte"])

        self.noise_chk = QCheckBox("Suppress High-Noise Buffers (>40% churn)")
        self.noise_chk.setChecked(True)

        self.diff_btn = QPushButton("⚡ Compute Delta Diff")
        self.diff_btn.setEnabled(False)
        self.diff_btn.clicked.connect(self._compute_diff)

        self.add_table_btn = QPushButton("⬇ Add to Address Table")
        self.add_table_btn.setEnabled(False)
        self.add_table_btn.clicked.connect(self._add_selected_to_table)

        self.jump_hex_btn = QPushButton("🔬 Jump to Hex")
        self.jump_hex_btn.setEnabled(False)
        self.jump_hex_btn.clicked.connect(self._jump_selected_to_hex)

        row2.addWidget(filter_lbl)
        row2.addWidget(self.filter_combo)
        row2.addWidget(stride_lbl)
        row2.addWidget(self.stride_combo)
        row2.addWidget(self.noise_chk)
        row2.addStretch()
        row2.addWidget(self.diff_btn)
        row2.addWidget(self.add_table_btn)
        row2.addWidget(self.jump_hex_btn)
        ctrl_layout.addLayout(row2)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0) # indeterminate
        ctrl_layout.addWidget(self.progress_bar)

        layout.addWidget(ctrl_group)

        # Diffs Table
        diff_group = QGroupBox("Detected Memory State Diffs")
        diff_layout = QVBoxLayout(diff_group)

        self.diff_table = QTableWidget()
        self.diff_table.setColumnCount(7)
        self.diff_table.setHorizontalHeaderLabels([
            "Address", "Module / Location", "Type", "Old Value (A)", "New Value (B)", "Delta (i32)", "Old Hex -> New Hex"
        ])
        self.diff_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.diff_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.diff_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.diff_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.diff_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.diff_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.diff_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.diff_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.diff_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.diff_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.diff_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        self.diff_table.doubleClicked.connect(self._jump_selected_to_hex)
        diff_layout.addWidget(self.diff_table)

        layout.addWidget(diff_group, 1)

    def _take_snapshot_a(self):
        if not self.target_pid:
            return
        self.snap_a_btn.setEnabled(False)
        self.progress_bar.setVisible(True)

        self._worker = SnapshotWorker(self.target_pid)
        self._worker.finished.connect(self._on_snapshot_a_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_snapshot_a_done(self, snap: MemorySnapshot):
        self.snapshot_a = snap
        self.snap_a_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        mb = snap.total_bytes / (1024 * 1024)
        self.snap_a_status.setText(f"Snapshot A: {mb:.1f} MB ({len(snap.regions)} regions)")
        self.snap_a_status.setStyleSheet("color: #00ff9d; font-weight: bold;")
        if self.snapshot_b:
            self.diff_btn.setEnabled(True)

    def _take_snapshot_b(self):
        if not self.target_pid:
            return
        self.snap_b_btn.setEnabled(False)
        self.progress_bar.setVisible(True)

        self._worker = SnapshotWorker(self.target_pid)
        self._worker.finished.connect(self._on_snapshot_b_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_snapshot_b_done(self, snap: MemorySnapshot):
        self.snapshot_b = snap
        self.snap_b_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        mb = snap.total_bytes / (1024 * 1024)
        self.snap_b_status.setText(f"Snapshot B: {mb:.1f} MB ({len(snap.regions)} regions)")
        self.snap_b_status.setStyleSheet("color: #00f0ff; font-weight: bold;")
        if self.snapshot_a:
            self.diff_btn.setEnabled(True)

    def _on_worker_error(self, err: str):
        self.snap_a_btn.setEnabled(True)
        self.snap_b_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Snapshot Error", f"Operation failed: {err}")

    def _compute_diff(self):
        if not self.snapshot_a or not self.snapshot_b:
            return

        f_txt = self.filter_combo.currentText()
        filter_type = "all"
        if "Increased" in f_txt:
            filter_type = "increased"
        elif "Decreased" in f_txt:
            filter_type = "decreased"

        stride_txt = self.stride_combo.currentText()
        stride = 4
        if "8" in stride_txt:
            stride = 8
        elif "1" in stride_txt:
            stride = 1

        self.diff_btn.setEnabled(False)
        self.progress_bar.setVisible(True)

        self._worker = DiffWorker(
            self.snapshot_a, self.snapshot_b,
            filter_type=filter_type,
            stride=stride,
            ignore_noise=self.noise_chk.isChecked()
        )
        self._worker.finished.connect(self._on_diff_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_diff_done(self, diffs: List[SnapshotDiffItem]):
        self.diff_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.current_diffs = diffs
        self.count_lbl.setText(f"{len(diffs)} differences found")
        self.add_table_btn.setEnabled(len(diffs) > 0)
        self.jump_hex_btn.setEnabled(len(diffs) > 0)

        self.diff_table.setRowCount(len(diffs))

        for row, d in enumerate(diffs):
            # 0: Address
            addr_item = QTableWidgetItem(f"0x{d.address:X}")
            addr_item.setData(Qt.UserRole, d.address)
            addr_item.setForeground(Qt.yellow)

            # 1: Location
            loc_str = f"{d.module_name} + 0x{d.offset:X}" if d.module_name else "-"
            loc_item = QTableWidgetItem(loc_str)
            loc_item.setForeground(Qt.cyan)

            # 2: Type
            type_item = QTableWidgetItem(d.diff_type)
            if d.diff_type == "INCREASED":
                type_item.setForeground(Qt.green)
            elif d.diff_type == "DECREASED":
                type_item.setForeground(Qt.red)
            else:
                type_item.setForeground(Qt.magenta)

            # 3: Old Value
            old_item = QTableWidgetItem(f"{d.old_int32}")

            # 4: New Value
            new_item = QTableWidgetItem(f"{d.new_int32}")

            # 5: Delta
            delta_val = d.new_int32 - d.old_int32
            delta_str = f"{delta_val:+d}"
            delta_item = QTableWidgetItem(delta_str)
            if delta_val > 0:
                delta_item.setForeground(Qt.green)
            elif delta_val < 0:
                delta_item.setForeground(Qt.red)

            # 6: Old Hex -> New Hex
            old_hex = " ".join(f"{b:02X}" for b in d.old_bytes)
            new_hex = " ".join(f"{b:02X}" for b in d.new_bytes)
            hex_item = QTableWidgetItem(f"{old_hex}  ->  {new_hex}")
            hex_item.setForeground(Qt.gray)

            self.diff_table.setItem(row, 0, addr_item)
            self.diff_table.setItem(row, 1, loc_item)
            self.diff_table.setItem(row, 2, type_item)
            self.diff_table.setItem(row, 3, old_item)
            self.diff_table.setItem(row, 4, new_item)
            self.diff_table.setItem(row, 5, delta_item)
            self.diff_table.setItem(row, 6, hex_item)

    def _add_selected_to_table(self):
        selected_rows = sorted(set(idx.row() for idx in self.diff_table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select one or more diff items first.")
            return

        for row in selected_rows:
            if row < len(self.current_diffs):
                d = self.current_diffs[row]
                desc = f"Diff ({d.diff_type}) @ {d.module_name or 'mem'}"
                self.add_to_cheat_table.emit(d.address, TypeFormat.INT32, desc)

        QMessageBox.information(self, "Added", f"Added {len(selected_rows)} address(es) to the Address Table.")

    def _jump_selected_to_hex(self):
        row = self.diff_table.currentRow()
        if row < 0 or row >= len(self.current_diffs):
            return
        addr = self.current_diffs[row].address
        self.jump_to_hex.emit(addr)
