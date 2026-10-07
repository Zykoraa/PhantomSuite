"""
PhantomSuite Pointer Scanner & Symbolic Solver Dialog
Allows users to discover pointer paths and multi-level offsets for dynamic variables
using formal Z3 SMT constraint solving or standard scanning, plus C++20 struct synthesis.
"""

import re
from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QProgressBar, QMessageBox, QAbstractItemView,
    QComboBox, QTextEdit, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor

from phantom_suite.core.pointer_scanner import PointerScanner, PointerPath
from phantom_suite.core.symbolic_solver import SymbolicPointerSolver, SymbolicStructSynthesizer


class PointerScanWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        pid: int,
        target_addr: int,
        max_offset: int,
        max_depth: int,
        use_smt: bool = True,
        alignment: int = 4,
        parent=None
    ):
        super().__init__(parent)
        self.pid = pid
        self.target_addr = target_addr
        self.max_offset = max_offset
        self.max_depth = max_depth
        self.use_smt = use_smt
        self.alignment = alignment

    def run(self):
        try:
            if self.isInterruptionRequested():
                return

            if self.use_smt:
                results = PointerScanner.symbolic_solve(
                    pid=self.pid,
                    target_address=self.target_addr,
                    max_offset=self.max_offset,
                    max_depth=self.max_depth,
                    alignment=self.alignment,
                    max_results=30
                )
            else:
                results = PointerScanner.scan_for_pointers(
                    self.pid, self.target_addr, self.max_offset, self.max_depth
                )

            if not self.isInterruptionRequested():
                self.finished.emit(results)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


class StructPreviewDialog(QDialog):
    """Modal displaying synthesized C++20 struct header."""

    def __init__(self, code: str, struct_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Synthesized Struct // {struct_name}")
        self.resize(700, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel(f"Generated C++20 Header for <b>{struct_name}</b> (ReClass.NET / PhantomSuite):")
        header.setStyleSheet("color: #00f0ff; font-size: 12px;")
        layout.addWidget(header)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(code)
        self.text_edit.setStyleSheet(
            "font-family: monospace; font-size: 11px; "
            "background-color: #080a0f; color: #c5d1eb; border: 1px solid #1c2333; "
            "selection-background-color: #00f0ff; selection-color: #000000;"
        )
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.setObjectName("accent_btn")
        copy_btn.clicked.connect(self._copy_code)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _copy_code(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())
        QMessageBox.information(self, "Copied", "Struct code copied to system clipboard!")


class PointerDialog(QDialog):
    """Dialog for running pointer scans and exporting pointer paths."""

    pointer_selected = Signal(str, str) # description, path_str

    def __init__(self, pid: int, target_address: int, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.target_address = target_address
        self.results: List[PointerPath] = []
        self._worker: Optional[PointerScanWorker] = None

        self.setWindowTitle(f"Symbolic Pointer Solver // Target: 0x{target_address:X}")
        self.resize(820, 520)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header info
        info_lbl = QLabel(f"Target Memory Address: <b>0x{self.target_address:X}</b>")
        info_lbl.setStyleSheet("color: #00f0ff; font-size: 13px;")
        layout.addWidget(info_lbl)

        # Settings
        settings_layout = QHBoxLayout()

        engine_lbl = QLabel("Engine:")
        engine_lbl.setStyleSheet("color: #7d90b3;")
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("⚡ Z3 SMT Symbolic Solver", True)
        self.engine_combo.addItem("Brute-Force Pointer Scanner", False)

        offset_lbl = QLabel("Max Offset:")
        offset_lbl.setStyleSheet("color: #7d90b3;")
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(64, 65536)
        self.offset_spin.setValue(4096)
        self.offset_spin.setSingleStep(256)

        depth_lbl = QLabel("Depth:")
        depth_lbl.setStyleSheet("color: #7d90b3;")
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(1, 5)
        self.depth_spin.setValue(2)

        align_lbl = QLabel("Align:")
        align_lbl.setStyleSheet("color: #7d90b3;")
        self.align_combo = QComboBox()
        self.align_combo.addItem("4 Bytes", 4)
        self.align_combo.addItem("8 Bytes", 8)
        self.align_combo.addItem("1 Byte (Any)", 1)

        self.scan_btn = QPushButton("🔍 Synthesize Paths")
        self.scan_btn.setObjectName("accent_btn")
        self.scan_btn.clicked.connect(self._start_scan)

        settings_layout.addWidget(engine_lbl)
        settings_layout.addWidget(self.engine_combo)
        settings_layout.addWidget(offset_lbl)
        settings_layout.addWidget(self.offset_spin)
        settings_layout.addWidget(depth_lbl)
        settings_layout.addWidget(self.depth_spin)
        settings_layout.addWidget(align_lbl)
        settings_layout.addWidget(self.align_combo)
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
        self.count_lbl = QLabel("0 pointer paths synthesized")
        self.count_lbl.setStyleSheet("color: #7d90b3;")

        self.struct_btn = QPushButton("🧬 Synthesize C++ Struct")
        self.struct_btn.setEnabled(False)
        self.struct_btn.clicked.connect(self._on_synthesize_struct_clicked)

        self.add_btn = QPushButton("⬇ Add to Address Table")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._on_add_clicked)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        bottom_layout.addWidget(self.count_lbl)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.struct_btn)
        bottom_layout.addWidget(self.add_btn)
        bottom_layout.addWidget(close_btn)
        layout.addLayout(bottom_layout)

    def _cleanup_worker(self):
        """Safely stops and disconnects worker thread to prevent QThread crashes."""
        if self._worker and self._worker.isRunning():
            try:
                self._worker.finished.disconnect()
                self._worker.error.disconnect()
            except RuntimeError:
                pass
            self._worker.requestInterruption()
            self._worker.wait(1000)

    def closeEvent(self, event):
        self._cleanup_worker()
        super().closeEvent(event)

    def reject(self):
        self._cleanup_worker()
        super().reject()

    def _start_scan(self):
        if self._worker and self._worker.isRunning():
            return

        self.scan_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        self.struct_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.count_lbl.setText("Running SMT constraint synthesis over memory graph...")

        use_smt = self.engine_combo.currentData()
        alignment = self.align_combo.currentData()

        self._worker = PointerScanWorker(
            pid=self.pid,
            target_addr=self.target_address,
            max_offset=self.offset_spin.value(),
            max_depth=self.depth_spin.value(),
            use_smt=use_smt,
            alignment=alignment,
            parent=self
        )
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()

    def _on_scan_finished(self, results: List[PointerPath]):
        self.results = results
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        has_results = len(results) > 0
        self.add_btn.setEnabled(has_results)
        self.struct_btn.setEnabled(has_results)
        self.count_lbl.setText(f"{len(results)} pointer paths synthesized")

        self.table.setRowCount(len(results))
        for row, p in enumerate(results):
            mod_item = QTableWidgetItem(p.module_name)
            mod_item.setForeground(QColor("#00f0ff"))

            base_item = QTableWidgetItem(f"0x{p.base_offset:X}")
            base_item.setForeground(QColor("#ffb700"))

            offs_str = ", ".join(f"0x{o:X}" for o in p.offsets)
            offs_item = QTableWidgetItem(offs_str)

            path_item = QTableWidgetItem(p.to_string())
            path_item.setForeground(QColor("#00ff9d"))

            self.table.setItem(row, 0, mod_item)
            self.table.setItem(row, 1, base_item)
            self.table.setItem(row, 2, offs_item)
            self.table.setItem(row, 3, path_item)

    def _on_scan_error(self, err: str):
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, "Pointer Synthesis Error", err)

    def _on_synthesize_struct_clicked(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.results):
            target_addr = self.target_address
            name = "TargetEntity"
        else:
            p = self.results[row]
            target_addr = p.resolved_address or self.target_address
            raw_name = p.module_name if p.module_name else "SynthesizedEntity"
            clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', raw_name)
            if clean_name and clean_name[0].isdigit():
                clean_name = f"Struct_{clean_name}"
            name = f"{clean_name}_Target"

        code = SymbolicStructSynthesizer.synthesize_cpp_struct(
            pid=self.pid,
            base_address=target_addr,
            size=256,
            struct_name=name
        )
        dialog = StructPreviewDialog(code, name, self)
        dialog.exec()

    def _on_add_clicked(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.results):
            QMessageBox.warning(self, "No Selection", "Please select a pointer path first.")
            return

        p = self.results[row]
        self.pointer_selected.emit(f"Ptr: {p.module_name}", p.to_string())
        self.close()
