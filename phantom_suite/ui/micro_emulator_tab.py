"""
PhantomSuite Micro-Execution & Sub-Function Emulation Tab
Interactive visual cockpit for sandboxed x86_64 CPU emulation, step-by-step
instruction tracing, delta register inspection, shadow stack examination,
and non-destructive snapshot rollbacks.
"""

from typing import Optional, Dict, List, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QGroupBox, QTextEdit, QTabWidget, QMessageBox,
    QApplication, QMenu, QSpinBox, QAbstractItemView
)
from PySide6.QtGui import QFont, QColor, QKeySequence, QShortcut
from PySide6.QtCore import Qt, Signal

from phantom_suite.core.micro_emulator import MicroEmulator, StepTrace, EmulationResult


class MicroEmulatorTab(QWidget):
    """Visual cockpit for sandboxed x86_64 sub-routine micro-execution."""

    jump_to_hex = Signal(object)
    add_to_cheat_table = Signal(object, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.emulator: Optional[MicroEmulator] = None
        self.last_regs: Dict[str, int] = {}
        self.snapshot_depth: int = 0

        self._init_ui()
        self._setup_shortcuts()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}  |  <span style='color: #00ff9d;'>Process Memory Paging Ready</span>")
        self.init_btn.setEnabled(True)

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.emulator = None
        self.last_regs.clear()
        self.snapshot_depth = 0
        self.target_lbl.setText("No Target Attached (Standalone CPU Emulation Mode)")
        self.init_btn.setEnabled(True)
        self._clear_displays()

    def _setup_shortcuts(self):
        # Local shortcuts when tab has focus
        QShortcut(QKeySequence("F7"), self, self._step_instruction)
        QShortcut(QKeySequence("F8"), self, self._step_over_instruction)
        QShortcut(QKeySequence("F9"), self, self._run_execution)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Target & Mode Banner
        self.target_lbl = QLabel("No Target Attached (Standalone CPU Emulation Mode)")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        layout.addWidget(self.target_lbl)

        # 2. Control & Address Toolbar
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Entry RIP:"))

        self.addr_input = QLineEdit()
        self.addr_input.setPlaceholderText("0x401000 or function address")
        self.addr_input.setFont(QFont("Monospace", 10))
        self.addr_input.setFixedWidth(200)
        self.addr_input.returnPressed.connect(self._init_or_reset_emulator)
        ctrl_layout.addWidget(self.addr_input)

        self.init_btn = QPushButton("⚙️ Init CPU")
        self.init_btn.setObjectName("accent_btn")
        self.init_btn.setToolTip("Initialize x86_64 CPU state and bind shadow memory")
        self.init_btn.clicked.connect(self._init_or_reset_emulator)
        ctrl_layout.addWidget(self.init_btn)

        ctrl_layout.addSpacing(10)

        # Stepping Controls
        self.step_btn = QPushButton("▶ Step (F7)")
        self.step_btn.setEnabled(False)
        self.step_btn.clicked.connect(self._step_instruction)
        ctrl_layout.addWidget(self.step_btn)

        self.step_over_btn = QPushButton("⏭ Step Over (F8)")
        self.step_over_btn.setEnabled(False)
        self.step_over_btn.clicked.connect(self._step_over_instruction)
        ctrl_layout.addWidget(self.step_over_btn)

        ctrl_layout.addWidget(QLabel("Max Steps:"))
        self.max_steps_spin = QSpinBox()
        self.max_steps_spin.setRange(1, 100000)
        self.max_steps_spin.setValue(100)
        self.max_steps_spin.setFixedWidth(80)
        ctrl_layout.addWidget(self.max_steps_spin)

        self.run_btn = QPushButton("🚀 Run (F9)")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._run_execution)
        ctrl_layout.addWidget(self.run_btn)

        ctrl_layout.addSpacing(10)

        # Snapshot Controls
        self.snapshot_btn = QPushButton("💾 Snapshot")
        self.snapshot_btn.setEnabled(False)
        self.snapshot_btn.setToolTip("Save CPU registers and shadow pages to undo stack")
        self.snapshot_btn.clicked.connect(self._save_snapshot)
        ctrl_layout.addWidget(self.snapshot_btn)

        self.rollback_btn = QPushButton("⏪ Rollback")
        self.rollback_btn.setEnabled(False)
        self.rollback_btn.setToolTip("Restore CPU state from last snapshot")
        self.rollback_btn.clicked.connect(self._rollback_snapshot)
        ctrl_layout.addWidget(self.rollback_btn)

        self.reset_btn = QPushButton("🔄 Reset")
        self.reset_btn.setEnabled(False)
        self.reset_btn.clicked.connect(self._reset_emulator)
        ctrl_layout.addWidget(self.reset_btn)

        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # 3. Main Splitter: Left (Trace & Code), Right (Registers & Stack)
        main_splitter = QSplitter(Qt.Horizontal)

        # Left Container: Disassembly & Instruction Execution Trace
        trace_box = QGroupBox("Execution Trace & Sub-Routine Steps")
        trace_layout = QVBoxLayout(trace_box)
        trace_layout.setContentsMargins(6, 6, 6, 6)

        self.trace_table = QTableWidget(0, 5)
        self.trace_table.setHorizontalHeaderLabels(["Address", "Bytes", "Mnemonic", "Operands", "Delta / Memory Access"])
        self.trace_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.trace_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.trace_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.trace_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.trace_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.trace_table.setFont(QFont("Monospace", 9))
        self.trace_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.trace_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.trace_table.customContextMenuRequested.connect(self._show_trace_context_menu)
        trace_layout.addWidget(self.trace_table)

        main_splitter.addWidget(trace_box)

        # Right Container: Registers, Flags & Shadow Stack
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 3a. Registers Box
        reg_box = QGroupBox("64-Bit General Purpose Registers (Editable)")
        reg_layout = QVBoxLayout(reg_box)
        reg_layout.setContentsMargins(6, 6, 6, 6)

        self.reg_table = QTableWidget(17, 2)
        self.reg_table.setHorizontalHeaderLabels(["Register", "Value (Hex)"])
        self.reg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.reg_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.reg_table.setFont(QFont("Monospace", 9))
        self.reg_table.cellChanged.connect(self._on_register_edited)
        self.reg_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.reg_table.customContextMenuRequested.connect(self._show_reg_context_menu)

        self._populate_initial_reg_table()
        reg_layout.addWidget(self.reg_table)

        # CPU Flags Banner
        self.flags_lbl = QLabel("Flags: CF=0  ZF=0  SF=0  OF=0  PF=0")
        self.flags_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #7d90b3; font-weight: bold;")
        reg_layout.addWidget(self.flags_lbl)

        right_layout.addWidget(reg_box, 1)

        # 3b. Shadow Stack Box
        stack_box = QGroupBox("Shadow Stack (RSP Window)")
        stack_layout = QVBoxLayout(stack_box)
        stack_layout.setContentsMargins(6, 6, 6, 6)

        self.stack_table = QTableWidget(16, 3)
        self.stack_table.setHorizontalHeaderLabels(["Offset", "Address", "QWORD Value"])
        self.stack_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.stack_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.stack_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.stack_table.setFont(QFont("Monospace", 9))
        self.stack_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.stack_table.customContextMenuRequested.connect(self._show_stack_context_menu)
        stack_layout.addWidget(self.stack_table)

        right_layout.addWidget(stack_box, 1)

        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([600, 380])
        layout.addWidget(main_splitter, 1)

        # 4. Status Strip
        self.status_lbl = QLabel("Micro-Emulator ready. Specify entry RIP and initialize CPU.")
        self.status_lbl.setStyleSheet("color: #7d90b3; font-size: 11px;")
        layout.addWidget(self.status_lbl)

    def _populate_initial_reg_table(self):
        self.reg_table.blockSignals(True)
        reg_names = MicroEmulator.REG_64_NAMES
        for row, name in enumerate(reg_names):
            name_item = QTableWidgetItem(name.upper())
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            name_item.setForeground(QColor("#00f0ff"))

            val_item = QTableWidgetItem("0x0000000000000000")
            val_item.setForeground(QColor("#f8f8f2"))
            self.reg_table.setItem(row, 0, name_item)
            self.reg_table.setItem(row, 1, val_item)
        self.reg_table.blockSignals(False)

    def _init_or_reset_emulator(self):
        addr_text = self.addr_input.text().strip()
        if not addr_text:
            QMessageBox.warning(self, "Invalid Address", "Please provide a starting RIP address in hex (e.g. 0x401000).")
            return

        try:
            addr = int(addr_text, 16)
        except ValueError:
            QMessageBox.warning(self, "Invalid Address", f"'{addr_text}' is not a valid hexadecimal address.")
            return

        self.emulator = MicroEmulator(target_pid=self.target_pid)
        self.emulator.set_reg("rip", addr)
        self.last_regs = dict(self.emulator.regs)
        self.snapshot_depth = 0

        self.step_btn.setEnabled(True)
        self.step_over_btn.setEnabled(True)
        self.run_btn.setEnabled(True)
        self.snapshot_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        self.rollback_btn.setEnabled(False)

        self.trace_table.setRowCount(0)
        self._update_views()
        self.status_lbl.setText(f"Initialized MicroEmulator at RIP: 0x{addr:016X}. Ready for execution.")

    def _step_instruction(self):
        if not self.emulator:
            return

        success, trace, reason = self.emulator.step()
        self._on_execution_step(success, trace, reason)

    def _step_over_instruction(self):
        if not self.emulator:
            return

        # Read instruction at current RIP to check if it's a call
        rip = self.emulator.get_reg("rip")
        data = self.emulator.read_mem(rip, 15)
        is_call = False
        ins_size = 5

        if self.emulator._cs:
            insns = list(self.emulator._cs.disasm(data, rip, count=1))
            if insns:
                ins = insns[0]
                ins_size = ins.size
                if ins.mnemonic == "call":
                    is_call = True

        if is_call:
            next_rip = (rip + ins_size) & 0xFFFFFFFFFFFFFFFF
            res = self.emulator.run(max_steps=5000, stop_at=next_rip)
            self._update_views()
            self.status_lbl.setText(f"Stepped over call to 0x{self.emulator.get_reg('rip'):016X} ({res.steps_executed} steps).")
        else:
            self._step_instruction()

    def _run_execution(self):
        if not self.emulator:
            return

        max_steps = self.max_steps_spin.value()
        res = self.emulator.run(max_steps=max_steps)

        # Populate trace table with newly executed steps
        self._render_full_trace(self.emulator.trace)
        self._update_views()

        status_text = f"Execution stopped: {res.halt_reason} | Executed: {res.steps_executed} steps | Final RIP: 0x{res.final_rip:016X}"
        self.status_lbl.setText(status_text)

    def _on_execution_step(self, success: bool, trace: Optional[StepTrace], reason: str):
        if not success or not trace:
            self.status_lbl.setText(f"Execution halted/faulted: {reason}")
            self._update_views()
            return

        # Append row to trace table
        row = self.trace_table.rowCount()
        self.trace_table.insertRow(row)

        addr_item = QTableWidgetItem(f"0x{trace.address:016X}")
        addr_item.setForeground(QColor("#00f0ff"))

        bytes_item = QTableWidgetItem(trace.raw_bytes.hex().upper())
        bytes_item.setForeground(QColor("#7d90b3"))

        mnem_item = QTableWidgetItem(trace.mnemonic)
        mnem_item.setForeground(QColor("#ff79c6"))
        mnem_item.setFont(QFont("Monospace", 9, QFont.Bold))

        ops_item = QTableWidgetItem(trace.op_str)
        ops_item.setForeground(QColor("#f8f8f2"))

        delta_parts = []
        if trace.regs_delta:
            delta_str = ", ".join(f"{k.upper()}: 0x{v[0]:X}->0x{v[1]:X}" for k, v in trace.regs_delta.items())
            delta_parts.append(delta_str)
        if trace.mem_reads:
            reads_str = "R:[" + ", ".join(f"0x{a:X}" for a, _ in trace.mem_reads) + "]"
            delta_parts.append(reads_str)
        if trace.mem_writes:
            writes_str = "W:[" + ", ".join(f"0x{a:X}=0x{v:X}" for a, v in trace.mem_writes) + "]"
            delta_parts.append(writes_str)

        info_item = QTableWidgetItem(" | ".join(delta_parts) if delta_parts else "none")
        info_item.setForeground(QColor("#50fa7b"))

        self.trace_table.setItem(row, 0, addr_item)
        self.trace_table.setItem(row, 1, bytes_item)
        self.trace_table.setItem(row, 2, mnem_item)
        self.trace_table.setItem(row, 3, ops_item)
        self.trace_table.setItem(row, 4, info_item)

        self.trace_table.scrollToBottom()
        self._update_views()
        self.status_lbl.setText(f"Step executed at 0x{trace.address:016X}: {trace.mnemonic} {trace.op_str}")

    def _render_full_trace(self, traces: List[StepTrace]):
        self.trace_table.setRowCount(0)
        self.trace_table.setRowCount(len(traces))

        for row, trace in enumerate(traces):
            addr_item = QTableWidgetItem(f"0x{trace.address:016X}")
            addr_item.setForeground(QColor("#00f0ff"))

            bytes_item = QTableWidgetItem(trace.raw_bytes.hex().upper())
            bytes_item.setForeground(QColor("#7d90b3"))

            mnem_item = QTableWidgetItem(trace.mnemonic)
            mnem_item.setForeground(QColor("#ff79c6"))
            mnem_item.setFont(QFont("Monospace", 9, QFont.Bold))

            ops_item = QTableWidgetItem(trace.op_str)
            ops_item.setForeground(QColor("#f8f8f2"))

            delta_parts = []
            if trace.regs_delta:
                delta_str = ", ".join(f"{k.upper()}: 0x{v[0]:X}->0x{v[1]:X}" for k, v in trace.regs_delta.items())
                delta_parts.append(delta_str)
            if trace.mem_reads:
                delta_parts.append("R:[" + ", ".join(f"0x{a:X}" for a, _ in trace.mem_reads) + "]")
            if trace.mem_writes:
                delta_parts.append("W:[" + ", ".join(f"0x{a:X}=0x{v:X}" for a, v in trace.mem_writes) + "]")

            info_item = QTableWidgetItem(" | ".join(delta_parts) if delta_parts else "none")
            info_item.setForeground(QColor("#50fa7b"))

            self.trace_table.setItem(row, 0, addr_item)
            self.trace_table.setItem(row, 1, bytes_item)
            self.trace_table.setItem(row, 2, mnem_item)
            self.trace_table.setItem(row, 3, ops_item)
            self.trace_table.setItem(row, 4, info_item)

        self.trace_table.scrollToBottom()

    def _update_views(self):
        if not self.emulator:
            return

        # 1. Update Registers & Highlight Deltas
        self.reg_table.blockSignals(True)
        reg_names = MicroEmulator.REG_64_NAMES
        for row, name in enumerate(reg_names):
            val = self.emulator.regs.get(name, 0)
            old_val = self.last_regs.get(name, val)
            has_changed = (val != old_val)

            val_item = self.reg_table.item(row, 1)
            if not val_item:
                val_item = QTableWidgetItem()
                self.reg_table.setItem(row, 1, val_item)

            val_item.setText(f"0x{val:016X}")
            if has_changed:
                val_item.setForeground(QColor("#ffb86c"))  # Neon orange for delta
                val_item.setBackground(QColor("#2d2013"))
            else:
                val_item.setForeground(QColor("#f8f8f2"))
                val_item.setBackground(QColor(0, 0, 0, 0))

        self.reg_table.blockSignals(False)
        self.last_regs = dict(self.emulator.regs)

        # 2. Update Flags Banner
        f = self.emulator.flags
        cf = "1" if f.get("cf") else "0"
        zf = "1" if f.get("zf") else "0"
        sf = "1" if f.get("sf") else "0"
        of = "1" if f.get("of") else "0"
        pf = "1" if f.get("pf") else "0"
        self.flags_lbl.setText(f"Flags: CF={cf}  ZF={zf}  SF={sf}  OF={of}  PF={pf}")

        # 3. Update Shadow Stack Window
        rsp = self.emulator.get_reg("rsp")
        for i in range(16):
            offset = i * 8
            addr = (rsp + offset) & 0xFFFFFFFFFFFFFFFF
            val = self.emulator.read_u64(addr)

            off_item = QTableWidgetItem(f"+0x{offset:02X}")
            off_item.setForeground(QColor("#7d90b3"))

            addr_item = QTableWidgetItem(f"0x{addr:016X}")
            addr_item.setForeground(QColor("#00f0ff"))

            val_item = QTableWidgetItem(f"0x{val:016X}")
            val_item.setForeground(QColor("#50fa7b") if val != 0 else QColor("#6272a4"))

            self.stack_table.setItem(i, 0, off_item)
            self.stack_table.setItem(i, 1, addr_item)
            self.stack_table.setItem(i, 2, val_item)

    def _on_register_edited(self, row: int, col: int):
        if col != 1 or not self.emulator:
            return

        reg_name = MicroEmulator.REG_64_NAMES[row]
        item = self.reg_table.item(row, col)
        if not item:
            return

        text = item.text().strip()
        try:
            val = int(text, 16) & 0xFFFFFFFFFFFFFFFF
            self.emulator.set_reg(reg_name, val)
            self._update_views()
            self.status_lbl.setText(f"Set register {reg_name.upper()} = 0x{val:016X}")
        except ValueError:
            # Revert
            curr_val = self.emulator.get_reg(reg_name)
            self.reg_table.blockSignals(True)
            item.setText(f"0x{curr_val:016X}")
            self.reg_table.blockSignals(False)

    def _save_snapshot(self):
        if not self.emulator:
            return

        self.emulator.save_snapshot()
        self.snapshot_depth += 1
        self.rollback_btn.setEnabled(True)
        self.status_lbl.setText(f"Snapshot saved (depth: {self.snapshot_depth}).")

    def _rollback_snapshot(self):
        if not self.emulator or self.snapshot_depth == 0:
            return

        success = self.emulator.restore_snapshot()
        if success:
            self.snapshot_depth = max(0, self.snapshot_depth - 1)
            self.rollback_btn.setEnabled(self.snapshot_depth > 0)
            self.last_regs = dict(self.emulator.regs)
            self._update_views()
            self.status_lbl.setText(f"State rolled back to previous snapshot (depth: {self.snapshot_depth}).")
        else:
            self.rollback_btn.setEnabled(False)

    def _reset_emulator(self):
        self._init_or_reset_emulator()

    def _clear_displays(self):
        self.step_btn.setEnabled(False)
        self.step_over_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.snapshot_btn.setEnabled(False)
        self.rollback_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self.trace_table.setRowCount(0)
        self._populate_initial_reg_table()
        self.flags_lbl.setText("Flags: CF=0  ZF=0  SF=0  OF=0  PF=0")
        self.stack_table.clearContents()
        self.status_lbl.setText("Micro-Emulator cleared.")

    # --- Context Menus ---

    def _show_trace_context_menu(self, pos):
        item = self.trace_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        addr_item = self.trace_table.item(row, 0)
        if not addr_item:
            return

        addr = int(addr_item.text(), 16)
        menu = QMenu(self)

        act_hex = menu.addAction(f"🧬 Jump to Hex @ 0x{addr:X}")
        act_hex.triggered.connect(lambda: self.jump_to_hex.emit(addr))

        act_copy = menu.addAction("📋 Copy Instruction Line")
        act_copy.triggered.connect(lambda: self._copy_trace_row(row))

        menu.exec_(self.trace_table.viewport().mapToGlobal(pos))

    def _show_reg_context_menu(self, pos):
        item = self.reg_table.itemAt(pos)
        if not item or not self.emulator:
            return

        row = item.row()
        reg_name = MicroEmulator.REG_64_NAMES[row]
        val = self.emulator.get_reg(reg_name)

        menu = QMenu(self)
        if val > 0:
            act_hex = menu.addAction(f"🧬 Jump to Hex @ 0x{val:X}")
            act_hex.triggered.connect(lambda: self.jump_to_hex.emit(val))

            act_cheat = menu.addAction(f"➕ Add {reg_name.upper()} to Cheat Table")
            act_cheat.triggered.connect(lambda: self.add_to_cheat_table.emit(val, "qword", f"Reg_{reg_name.upper()}"))

        act_zero = menu.addAction(f"Zero Register {reg_name.upper()}")
        act_zero.triggered.connect(lambda: self._set_reg_direct(reg_name, 0))

        menu.exec(self.reg_table.viewport().mapToGlobal(pos))

    def _show_stack_context_menu(self, pos):
        item = self.stack_table.itemAt(pos)
        if not item or not self.emulator:
            return

        row = item.row()
        addr_item = self.stack_table.item(row, 1)
        val_item = self.stack_table.item(row, 2)
        if not addr_item or not val_item:
            return

        addr = int(addr_item.text(), 16)
        val = int(val_item.text(), 16)

        menu = QMenu(self)
        act_hex_stack = menu.addAction(f"🧬 Jump to Hex @ Stack 0x{addr:X}")
        act_hex_stack.triggered.connect(lambda: self.jump_to_hex.emit(addr))

        if val > 0:
            act_hex_val = menu.addAction(f"🧬 Dereference & Jump to Hex @ 0x{val:X}")
            act_hex_val.triggered.connect(lambda: self.jump_to_hex.emit(val))

            act_cheat = menu.addAction(f"➕ Add Stack Pointer to Cheat Table")
            act_cheat.triggered.connect(lambda: self.add_to_cheat_table.emit(val, "qword", f"Stack_0x{addr:X}"))

        menu.exec(self.stack_table.viewport().mapToGlobal(pos))

    def _set_reg_direct(self, name: str, val: int):
        if self.emulator:
            self.emulator.set_reg(name, val)
            self._update_views()

    def _copy_trace_row(self, row: int):
        cells = [self.trace_table.item(row, c).text() for c in range(self.trace_table.columnCount()) if self.trace_table.item(row, c)]
        QApplication.clipboard().setText(" | ".join(cells))
