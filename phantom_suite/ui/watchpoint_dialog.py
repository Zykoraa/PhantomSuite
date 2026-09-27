"""
PhantomSuite Hardware Watchpoint Dialog
"Find What Writes / Accesses This Address" - interactive hardware debug register tracing.
"""

from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QGroupBox, QAbstractItemView,
    QProgressBar, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from phantom_suite.core.watchpoint_tracer import WatchpointTracer, WatchpointHit
from phantom_suite.core.disassembler import Disassembler


class WatchpointWorker(QThread):
    finished = Signal(list) # List[WatchpointHit]
    error = Signal(str)

    def __init__(self, pid: int, address: int, watch_type: str, timeout_sec: float):
        super().__init__()
        self.pid = pid
        self.address = address
        self.watch_type = watch_type
        self.timeout_sec = timeout_sec

    def run(self):
        try:
            hits = WatchpointTracer.trace_address(
                self.pid, self.address, self.watch_type, self.timeout_sec
            )
            self.finished.emit(hits)
        except Exception as e:
            self.error.emit(str(e))


class WatchpointDialog(QDialog):
    """Dialog finding instructions that write to or access a specific memory address."""

    jump_to_disasm = Signal(int)

    def __init__(self, pid: int, address: int, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.address = address
        self.hits: List[WatchpointHit] = []
        self._worker: Optional[WatchpointWorker] = None

        self.setWindowTitle(f"Hardware Watchpoint // Find Accesses to 0x{address:X}")
        self.resize(750, 480)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header Info
        header_box = QGroupBox("Target Memory Address")
        h_layout = QHBoxLayout(header_box)

        addr_lbl = QLabel(f"Watching Address: <font color='#00f0ff'><b>0x{self.address:X}</b></font>")
        addr_lbl.setStyleSheet("font-size: 14px;")

        type_lbl = QLabel("Mode:")
        type_lbl.setStyleSheet("color: #7d90b3;")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Writes Only (watch)", "Reads & Writes (awatch)"])

        self.start_btn = QPushButton("🎯 Start Trace (3s)")
        self.start_btn.setObjectName("accent_btn")
        self.start_btn.clicked.connect(self._start_trace)

        h_layout.addWidget(addr_lbl)
        h_layout.addStretch()
        h_layout.addWidget(type_lbl)
        h_layout.addWidget(self.mode_combo)
        h_layout.addWidget(self.start_btn)
        layout.addWidget(header_box)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        # Hits Table
        self.hits_table = QTableWidget()
        self.hits_table.setColumnCount(5)
        self.hits_table.setHorizontalHeaderLabels([
            "Instruction Address", "Module / Location", "Values", "Instruction Disassembly", "Function"
        ])
        self.hits_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.hits_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.hits_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.hits_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.hits_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.hits_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hits_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.hits_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hits_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        layout.addWidget(self.hits_table, 1)

        # Bottom Buttons
        btn_box = QHBoxLayout()
        self.jump_btn = QPushButton("🔬 Jump to Disassembly")
        self.jump_btn.setEnabled(False)
        self.jump_btn.clicked.connect(self._jump_selected)

        self.nop_btn = QPushButton("🚫 NOP Instruction (0x90)")
        self.nop_btn.setEnabled(False)
        self.nop_btn.clicked.connect(self._nop_selected)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_box.addWidget(self.jump_btn)
        btn_box.addWidget(self.nop_btn)
        btn_box.addStretch()
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

    def _start_trace(self):
        w_mode = "write" if "Writes" in self.mode_combo.currentText() else "access"
        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)

        self._worker = WatchpointWorker(self.pid, self.address, w_mode, timeout_sec=3.0)
        self._worker.finished.connect(self._on_trace_done)
        self._worker.error.connect(self._on_trace_error)
        self._worker.start()

    def _on_trace_done(self, hits: List[WatchpointHit]):
        self.start_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.hits = hits

        self.hits_table.setRowCount(len(hits))
        for row, h in enumerate(hits):
            addr_item = QTableWidgetItem(f"0x{h.instruction_address:X}")
            addr_item.setData(Qt.UserRole, h.instruction_address)
            addr_item.setForeground(Qt.yellow)

            loc_str = f"{h.module_name} + 0x{h.offset:X}" if h.module_name else "-"
            loc_item = QTableWidgetItem(loc_str)
            loc_item.setForeground(Qt.cyan)

            val_item = QTableWidgetItem(f"{h.old_value} -> {h.new_value}")
            inst_item = QTableWidgetItem(h.instruction_text)
            inst_item.setForeground(Qt.green)

            fn_item = QTableWidgetItem(h.function_name)

            self.hits_table.setItem(row, 0, addr_item)
            self.hits_table.setItem(row, 1, loc_item)
            self.hits_table.setItem(row, 2, val_item)
            self.hits_table.setItem(row, 3, inst_item)
            self.hits_table.setItem(row, 4, fn_item)

        has_hits = len(hits) > 0
        self.jump_btn.setEnabled(has_hits)
        self.nop_btn.setEnabled(has_hits)

        if not has_hits:
            QMessageBox.information(
                self, "No Hits Detected",
                "No instructions wrote to or accessed this address during the 3-second trace window."
            )

    def _on_trace_error(self, err: str):
        self.start_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Trace Error", f"Watchpoint failed: {err}")

    def _jump_selected(self):
        row = self.hits_table.currentRow()
        if row < 0 or row >= len(self.hits):
            return
        addr = self.hits[row].instruction_address
        self.jump_to_disasm.emit(addr)
        self.accept()

    def _nop_selected(self):
        row = self.hits_table.currentRow()
        if row < 0 or row >= len(self.hits):
            return
        hit = self.hits[row]
        # Disassemble instruction to find its exact size
        instructions = Disassembler.disassemble(self.pid, hit.instruction_address, length=16)
        if not instructions:
            QMessageBox.critical(self, "NOP Failed", "Could not disassemble instruction.")
            return

        target_inst = instructions[0]
        ok, msg, _ = Disassembler.nop_instruction(self.pid, target_inst.address, target_inst.size)
        if ok:
            QMessageBox.information(self, "Success", f"Instruction at 0x{target_inst.address:X} replaced with NOPs ({target_inst.size} bytes).")
        else:
            QMessageBox.critical(self, "NOP Failed", msg)
