"""
PhantomSuite Memory Hex Viewer & Live Disassembler Tab
Interactive memory inspection with hex, ASCII, in-place byte patching,
and x86_64 disassembly with 1-click NOP patching & restoration.
"""

from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox, QGroupBox, QInputDialog, QAbstractItemView,
    QSplitter, QTabWidget, QDialog, QApplication
)
from PySide6.QtCore import Qt, QTimer
from phantom_suite.core.hex_viewer import HexViewer, HexLine
from phantom_suite.core.disassembler import Disassembler, Instruction
from phantom_suite.core.pattern_scanner import PatternScanner
from phantom_suite.core.table_serializer import TableSerializer
from phantom_suite.ui.watchpoint_dialog import WatchpointDialog


class SigMakerDialog(QDialog):
    """Dialog displaying generated unique AOB signature."""

    def __init__(self, address: int, signature: str, length: int, module_name: str, offset: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigMaker // Unique AOB Signature Generator")
        self.resize(560, 240)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl = QLabel("Generated shortest unique AOB signature for this instruction:")
        lbl.setStyleSheet("color: #7d90b3;")
        layout.addWidget(lbl)

        info_box = QGroupBox("Signature Details")
        info_layout = QVBoxLayout(info_box)

        addr_txt = f"Address: 0x{address:X}"
        if module_name:
            addr_txt += f"  ({module_name} + 0x{offset:X})"
        info_layout.addWidget(QLabel(addr_txt))
        info_layout.addWidget(QLabel(f"Length: {length} bytes"))

        self.sig_edit = QLineEdit(signature)
        self.sig_edit.setReadOnly(True)
        self.sig_edit.setStyleSheet("font-family: monospace; font-size: 13px; color: #00f0ff; font-weight: bold;")
        info_layout.addWidget(self.sig_edit)
        layout.addWidget(info_box)

        btn_box = QHBoxLayout()
        copy_btn = QPushButton("📋 Copy Signature")
        copy_btn.setObjectName("accent_btn")
        copy_btn.clicked.connect(self._copy_sig)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_box.addStretch()
        btn_box.addWidget(copy_btn)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

    def _copy_sig(self):
        QApplication.clipboard().setText(self.sig_edit.text())
        QMessageBox.information(self, "Copied", "AOB Signature copied to clipboard.")


class HexTab(QWidget):
    """Live Memory Hex Viewer, In-Place Patcher, and x86_64 Disassembler."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.current_address: int = 0
        self.bytes_per_page: int = 256
        self.original_bytes_cache: Dict[int, bytes] = {} # address -> original_bytes
        self.current_instructions: List[Instruction] = []

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._on_timer_refresh)

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.goto_btn.setEnabled(True)
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self.patch_btn.setEnabled(True)
        self.nop_btn.setEnabled(True)
        self.restore_btn.setEnabled(True)
        self.sigmaker_btn.setEnabled(True)
        self.watchpoint_btn.setEnabled(True)

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.goto_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.patch_btn.setEnabled(False)
        self.nop_btn.setEnabled(False)
        self.restore_btn.setEnabled(False)
        self.sigmaker_btn.setEnabled(False)
        self.watchpoint_btn.setEnabled(False)
        self.hex_table.setRowCount(0)
        self.disasm_table.setRowCount(0)
        self._timer.stop()
        self.auto_refresh_chk.setChecked(False)

    def navigate_to_address(self, address: int):
        self.current_address = address
        self.addr_input.setText(f"0x{address:X}")
        self.refresh_all()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target Banner
        banner_layout = QHBoxLayout()
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        banner_layout.addWidget(self.target_lbl)
        banner_layout.addStretch()
        layout.addLayout(banner_layout)

        # Navigation Bar
        nav_group = QGroupBox("Memory & Code Navigation")
        nav_layout = QHBoxLayout(nav_group)

        addr_lbl = QLabel("Address:")
        addr_lbl.setStyleSheet("color: #7d90b3;")
        self.addr_input = QLineEdit()
        self.addr_input.setPlaceholderText("Hex address (e.g. 0x55af...)")
        self.addr_input.returnPressed.connect(self._on_goto_clicked)

        self.goto_btn = QPushButton("Go")
        self.goto_btn.setEnabled(False)
        self.goto_btn.clicked.connect(self._on_goto_clicked)

        self.prev_btn = QPushButton("◀ Prev Page")
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._on_prev_page)

        self.next_btn = QPushButton("Next Page ▶")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self._on_next_page)

        self.auto_refresh_chk = QCheckBox("Live Auto-Refresh")
        self.auto_refresh_chk.toggled.connect(self._on_auto_refresh_toggled)

        self.patch_btn = QPushButton("✏ Patch Bytes")
        self.patch_btn.setObjectName("accent_btn")
        self.patch_btn.setEnabled(False)
        self.patch_btn.clicked.connect(self._on_patch_bytes)

        self.watchpoint_btn = QPushButton("🎯 Find Accesses")
        self.watchpoint_btn.setToolTip("Hardware Watchpoint: Find which instructions write to or access this address")
        self.watchpoint_btn.setEnabled(False)
        self.watchpoint_btn.clicked.connect(self._on_watchpoint_clicked)

        nav_layout.addWidget(addr_lbl)
        nav_layout.addWidget(self.addr_input, 2)
        nav_layout.addWidget(self.goto_btn)
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addWidget(self.auto_refresh_chk)
        nav_layout.addWidget(self.patch_btn)
        nav_layout.addWidget(self.watchpoint_btn)
        layout.addWidget(nav_group)

        # Splitter between Hex Dump and Disassembler
        splitter = QSplitter(Qt.Vertical)

        # 1. Hex Display Group
        hex_group = QGroupBox("Raw Memory Hex View")
        hex_layout = QVBoxLayout(hex_group)
        self.hex_table = QTableWidget()
        self.hex_table.setColumnCount(4)
        self.hex_table.setHorizontalHeaderLabels([
            "Address", "Bytes (0-7)", "Bytes (8-F)", "ASCII Preview"
        ])
        self.hex_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.hex_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.hex_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.hex_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.hex_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hex_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hex_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        hex_layout.addWidget(self.hex_table)
        splitter.addWidget(hex_group)

        # 2. Disassembler Group
        disasm_group = QGroupBox("Live x86_64 Disassembly & Code Patcher")
        disasm_layout = QVBoxLayout(disasm_group)

        disasm_top = QHBoxLayout()
        disasm_info = QLabel("Inspect instructions and patch logic (e.g. NOP out stat decreases):")
        disasm_info.setStyleSheet("color: #7d90b3; font-size: 12px;")

        self.nop_btn = QPushButton("🚫 Replace with NOPs (0x90)")
        self.nop_btn.setObjectName("accent_btn")
        self.nop_btn.setEnabled(False)
        self.nop_btn.clicked.connect(self._on_nop_selected)

        self.restore_btn = QPushButton("↺ Restore Original")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._on_restore_selected)

        self.sigmaker_btn = QPushButton("✨ SigMaker (AOB Sig)")
        self.sigmaker_btn.setEnabled(False)
        self.sigmaker_btn.clicked.connect(self._on_sigmaker_clicked)

        self.cfg_btn = QPushButton("🔀 CFG Graph")
        self.cfg_btn.setEnabled(False)
        self.cfg_btn.clicked.connect(self._on_cfg_clicked)

        disasm_top.addWidget(disasm_info)
        disasm_top.addStretch()
        disasm_top.addWidget(self.cfg_btn)
        disasm_top.addWidget(self.sigmaker_btn)
        disasm_top.addWidget(self.nop_btn)
        disasm_top.addWidget(self.restore_btn)
        disasm_layout.addLayout(disasm_top)

        self.disasm_table = QTableWidget()
        self.disasm_table.setColumnCount(4)
        self.disasm_table.setHorizontalHeaderLabels([
            "Address", "Hex Bytes", "Instruction", "Status"
        ])
        self.disasm_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.disasm_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.disasm_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.disasm_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.disasm_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.disasm_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.disasm_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.disasm_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        disasm_layout.addWidget(self.disasm_table)

        splitter.addWidget(disasm_group)
        layout.addWidget(splitter, 1)

    def _on_goto_clicked(self):
        raw = self.addr_input.text().strip()
        if not raw:
            return
        try:
            self.current_address = int(raw, 16) if raw.startswith(("0x", "0X")) else int(raw)
            self.refresh_all()
        except ValueError:
            QMessageBox.warning(self, "Invalid Address", "Address must be a valid hex or integer.")

    def _on_prev_page(self):
        self.current_address = max(0, self.current_address - self.bytes_per_page)
        self.addr_input.setText(f"0x{self.current_address:X}")
        self.refresh_all()

    def _on_next_page(self):
        self.current_address += self.bytes_per_page
        self.addr_input.setText(f"0x{self.current_address:X}")
        self.refresh_all()

    def _on_auto_refresh_toggled(self, checked: bool):
        if checked:
            self._timer.start()
        else:
            self._timer.stop()

    def _on_timer_refresh(self):
        if self.target_pid and self.current_address > 0:
            self.refresh_hex()

    def refresh_all(self):
        self.refresh_hex()
        self.refresh_disassembly()

    def refresh_hex(self):
        if not self.target_pid or self.current_address <= 0:
            return

        lines: List[HexLine] = HexViewer.read_hex_page(
            self.target_pid, self.current_address, self.bytes_per_page
        )
        self.hex_table.setRowCount(len(lines))

        for row, l in enumerate(lines):
            addr_item = QTableWidgetItem(f"0x{l.address:012X}")
            addr_item.setData(Qt.UserRole, l.address)
            addr_item.setForeground(Qt.yellow)

            left_item = QTableWidgetItem(l.hex_left)
            left_item.setForeground(Qt.cyan)

            right_item = QTableWidgetItem(l.hex_right)
            right_item.setForeground(Qt.cyan)

            ascii_item = QTableWidgetItem(l.ascii_repr)
            ascii_item.setForeground(Qt.green)

            self.hex_table.setItem(row, 0, addr_item)
            self.hex_table.setItem(row, 1, left_item)
            self.hex_table.setItem(row, 2, right_item)
            self.hex_table.setItem(row, 3, ascii_item)

    def refresh_disassembly(self):
        if not self.target_pid or self.current_address <= 0:
            self.disasm_table.setRowCount(0)
            return

        self.current_instructions = Disassembler.disassemble(
            self.target_pid, self.current_address, length=64
        )
        self.disasm_table.setRowCount(len(self.current_instructions))
        self.cfg_btn.setEnabled(len(self.current_instructions) > 0)

        for row, inst in enumerate(self.current_instructions):
            addr_item = QTableWidgetItem(f"0x{inst.address:X}")
            addr_item.setData(Qt.UserRole, inst.address)
            addr_item.setForeground(Qt.yellow)

            bytes_item = QTableWidgetItem(inst.hex_bytes)
            bytes_item.setForeground(Qt.cyan)

            text_item = QTableWidgetItem(inst.full_text)
            status_item = QTableWidgetItem("Active")

            if inst.is_nop:
                text_item.setForeground(Qt.magenta)
                status_item.setText("NOPed")
                status_item.setForeground(Qt.magenta)
            elif inst.address in self.original_bytes_cache:
                status_item.setText("Patched")
                status_item.setForeground(Qt.yellow)
            else:
                text_item.setForeground(Qt.green)
                status_item.setForeground(Qt.gray)

            self.disasm_table.setItem(row, 0, addr_item)
            self.disasm_table.setItem(row, 1, bytes_item)
            self.disasm_table.setItem(row, 2, text_item)
            self.disasm_table.setItem(row, 3, status_item)

    def _on_patch_bytes(self):
        if not self.target_pid:
            return
        addr_str = f"0x{self.current_address:X}"
        row = self.hex_table.currentRow()
        if row >= 0:
            addr_item = self.hex_table.item(row, 0)
            if addr_item:
                addr_str = addr_item.text()

        hex_str, ok = QInputDialog.getText(
            self, "Patch Memory Bytes",
            f"Enter hex bytes to write at {addr_str} (e.g. 90 90 90 or 41 42 43):"
        )
        if ok and hex_str.strip():
            addr = int(addr_str, 16)
            success, msg = HexViewer.patch_bytes(self.target_pid, addr, hex_str)
            if success:
                self.refresh_all()
                QMessageBox.information(self, "Success", msg)
            else:
                QMessageBox.critical(self, "Patch Failed", msg)

    def _on_nop_selected(self):
        row = self.disasm_table.currentRow()
        if row < 0 or not self.target_pid or row >= len(self.current_instructions):
            QMessageBox.warning(self, "No Selection", "Please select an instruction from the disassembly table first.")
            return

        inst = self.current_instructions[row]
        if inst.is_nop:
            QMessageBox.information(self, "Already NOP", "Instruction is already NOPed.")
            return

        ok, msg, orig_bytes = Disassembler.nop_instruction(self.target_pid, inst.address, inst.size)
        if ok and orig_bytes:
            if inst.address not in self.original_bytes_cache:
                self.original_bytes_cache[inst.address] = orig_bytes
            self.refresh_all()
        else:
            QMessageBox.critical(self, "NOP Failed", msg)

    def _on_restore_selected(self):
        row = self.disasm_table.currentRow()
        if row < 0 or not self.target_pid or row >= len(self.current_instructions):
            QMessageBox.warning(self, "No Selection", "Please select an instruction to restore.")
            return

        inst = self.current_instructions[row]
        orig_bytes = self.original_bytes_cache.get(inst.address)
        if not orig_bytes:
            QMessageBox.information(self, "No Cached Original", "No original bytes recorded for this instruction.")
            return

        ok, msg = Disassembler.restore_instruction(self.target_pid, inst.address, orig_bytes)
        if ok:
            del self.original_bytes_cache[inst.address]
            self.refresh_all()
            QMessageBox.information(self, "Restored", msg)
        else:
            QMessageBox.critical(self, "Restore Failed", msg)

    def _on_sigmaker_clicked(self):
        row = self.disasm_table.currentRow()
        if row < 0 or not self.target_pid or row >= len(self.current_instructions):
            QMessageBox.warning(self, "No Selection", "Please select an instruction from the disassembly table first.")
            return

        inst = self.current_instructions[row]
        module_name, offset = TableSerializer.resolve_runtime_address(self.target_pid, inst.address)
        sig, length = PatternScanner.generate_unique_signature(
            self.target_pid, inst.address, module_name=module_name
        )
        if not sig:
            QMessageBox.warning(self, "SigMaker", "Could not generate signature for this instruction.")
            return

        dlg = SigMakerDialog(inst.address, sig, length, module_name or "", offset, self)
        dlg.exec()

    def _on_watchpoint_clicked(self):
        if not self.target_pid or self.current_address <= 0:
            QMessageBox.information(self, "No Address", "Navigate to an address or enter one in the address box first.")
            return

        dlg = WatchpointDialog(self.target_pid, self.current_address, self)
        dlg.jump_to_disasm.connect(self.navigate_to_address)
        dlg.exec()

    def _on_cfg_clicked(self):
        if not self.target_pid or self.current_address <= 0:
            return
        from phantom_suite.ui.cfg_dialog import CFGDialog
        dlg = CFGDialog(self.target_pid, self.current_address, self)
        dlg.exec()


