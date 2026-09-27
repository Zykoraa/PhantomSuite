"""
PhantomSuite Memory Scanner Tab
Cheat Engine style memory scanning, filtering, and live address freezing.
"""

from typing import List, Optional, Any, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QCheckBox, QProgressBar, QMessageBox, QAbstractItemView,
    QGroupBox, QInputDialog, QFileDialog
)
from PySide6.QtCore import Qt, QThread, Signal
from phantom_suite.core.memory_engine import (
    MemoryEngine, TypeFormat, ScanType, ScanResult, FreezeManager
)
from phantom_suite.core.table_serializer import TableSerializer
from phantom_suite.core.pattern_scanner import PatternScanner
from phantom_suite.ui.pointer_dialog import PointerDialog
from phantom_suite.ui.watchpoint_dialog import WatchpointDialog


class ScanWorker(QThread):
    progress = Signal(float, str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, pid: int, val_type: str, scan_type: str, target_val: Any,
                 is_first: bool, previous_results: Optional[List[ScanResult]] = None,
                 writable_only: bool = True, alignment: int = 4):
        super().__init__()
        self.pid = pid
        self.val_type = val_type
        self.scan_type = scan_type
        self.target_val = target_val
        self.is_first = is_first
        self.previous_results = previous_results or []
        self.writable_only = writable_only
        self.alignment = alignment

    def run(self):
        try:
            if self.val_type == TypeFormat.AOB:
                self.progress.emit(0.2, "Scanning memory regions for AOB pattern...")
                matches = PatternScanner.scan_pattern(
                    pid=self.pid,
                    pattern_str=str(self.target_val),
                    max_matches=500
                )
                res = []
                for m in matches:
                    val_str = f"{m.module_name} + 0x{m.offset:X}" if m.module_name else f"0x{m.address:X}"
                    res.append(ScanResult(address=m.address, value=val_str))
                self.progress.emit(1.0, f"Found {len(res)} matches.")
                self.finished.emit(res)
                return

            if self.is_first:
                res = MemoryEngine.first_scan(
                    pid=self.pid,
                    val_type=self.val_type,
                    scan_type=self.scan_type,
                    target_value=self.target_val,
                    writable_only=self.writable_only,
                    alignment=self.alignment,
                    progress_callback=lambda pct, msg: self.progress.emit(pct, msg)
                )
            else:
                res = MemoryEngine.next_scan(
                    pid=self.pid,
                    val_type=self.val_type,
                    scan_type=self.scan_type,
                    target_value=self.target_val,
                    previous_results=self.previous_results,
                    progress_callback=lambda pct, msg: self.progress.emit(pct, msg)
                )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class ScannerTab(QWidget):
    """Memory Scanner and Cheat Table interface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.scan_results: List[ScanResult] = []
        self.saved_entries: List[Dict[str, Any]] = [] # address, type, desc, frozen
        self.freezer = FreezeManager(interval_sec=0.05)
        self._scan_worker: Optional[ScanWorker] = None

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.first_scan_btn.setEnabled(True)
        self.new_scan()

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.first_scan_btn.setEnabled(False)
        self.next_scan_btn.setEnabled(False)
        self.new_scan()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target Banner
        banner_layout = QHBoxLayout()
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.results_count_lbl = QLabel("0 addresses found")
        self.results_count_lbl.setStyleSheet("color: #a0aec0;")
        banner_layout.addWidget(self.target_lbl)
        banner_layout.addStretch()
        banner_layout.addWidget(self.results_count_lbl)
        layout.addLayout(banner_layout)

        # Parameters & Controls Box
        controls_group = QGroupBox("Scan Configuration")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setSpacing(8)

        row1 = QHBoxLayout()
        val_lbl = QLabel("Value:")
        val_lbl.setStyleSheet("color: #7d90b3;")
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Enter value to search...")
        self.value_input.returnPressed.connect(self._on_enter_pressed)

        type_lbl = QLabel("Type:")
        type_lbl.setStyleSheet("color: #7d90b3;")
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "4 Bytes (int32)",
            "8 Bytes (int64)",
            "2 Bytes (int16)",
            "1 Byte (int8)",
            "Float",
            "Double",
            "String / Text",
            "Hex Byte Array",
            "AOB / Pattern (with ??)"
        ])

        scan_type_lbl = QLabel("Scan Type:")
        scan_type_lbl.setStyleSheet("color: #7d90b3;")
        self.scan_type_combo = QComboBox()
        self.scan_type_combo.addItems([
            ScanType.EXACT,
            ScanType.INCREASED,
            ScanType.DECREASED,
            ScanType.CHANGED,
            ScanType.UNCHANGED,
            ScanType.BIGGER_THAN,
            ScanType.SMALLER_THAN
        ])

        row1.addWidget(val_lbl)
        row1.addWidget(self.value_input, 2)
        row1.addWidget(type_lbl)
        row1.addWidget(self.type_combo)
        row1.addWidget(scan_type_lbl)
        row1.addWidget(self.scan_type_combo)
        controls_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.writable_check = QCheckBox("Writable Memory Only (rw-p)")
        self.writable_check.setChecked(True)

        self.first_scan_btn = QPushButton("⚡ First Scan")
        self.first_scan_btn.setEnabled(False)
        self.first_scan_btn.clicked.connect(self.start_first_scan)

        self.next_scan_btn = QPushButton("🔍 Next Scan")
        self.next_scan_btn.setEnabled(False)
        self.next_scan_btn.clicked.connect(self.start_next_scan)

        self.new_scan_btn = QPushButton("⟳ New Scan")
        self.new_scan_btn.clicked.connect(self.new_scan)

        row2.addWidget(self.writable_check)
        row2.addStretch()
        row2.addWidget(self.first_scan_btn)
        row2.addWidget(self.next_scan_btn)
        row2.addWidget(self.new_scan_btn)
        controls_layout.addLayout(row2)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        controls_layout.addWidget(self.progress_bar)

        layout.addWidget(controls_group)

        # Middle: Found Addresses Table
        results_group = QGroupBox("Scan Results")
        results_layout = QVBoxLayout(results_group)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Address", "Value", "Previous"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.doubleClicked.connect(self._add_selected_to_cheat_table)
        results_layout.addWidget(self.results_table)

        results_btn_layout = QHBoxLayout()
        add_to_table_btn = QPushButton("⬇ Add Selected to Address Table")
        add_to_table_btn.clicked.connect(self._add_selected_to_cheat_table)
        results_btn_layout.addStretch()
        results_btn_layout.addWidget(add_to_table_btn)
        results_layout.addLayout(results_btn_layout)

        layout.addWidget(results_group, 1)

        # Bottom: Saved / Cheat Address Table
        cheat_group = QGroupBox("Saved Address Table & Value Freezer")
        cheat_layout = QVBoxLayout(cheat_group)

        self.cheat_table = QTableWidget()
        self.cheat_table.setColumnCount(5)
        self.cheat_table.setHorizontalHeaderLabels([
            "Active", "Description", "Address", "Type", "Value"
        ])
        self.cheat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.cheat_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.cheat_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.cheat_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.cheat_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.cheat_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cheat_table.doubleClicked.connect(self._on_cheat_table_double_click)
        cheat_layout.addWidget(self.cheat_table)

        cheat_btn_layout = QHBoxLayout()
        manual_add_btn = QPushButton("+ Add Custom Address")
        manual_add_btn.clicked.connect(self._add_manual_address)
        change_val_btn = QPushButton("✏ Change Value")
        change_val_btn.clicked.connect(self._change_selected_val)
        remove_btn = QPushButton("🗑 Remove Selected")
        remove_btn.clicked.connect(self._remove_selected_cheat)

        pointer_btn = QPushButton("🔍 Pointer Scan")
        pointer_btn.clicked.connect(self._open_pointer_scanner)

        watchpoint_btn = QPushButton("🎯 Find Accesses")
        watchpoint_btn.setToolTip("Hardware watchpoint: Find which instructions write to or access this address")
        watchpoint_btn.clicked.connect(self._open_watchpoint_dialog)

        save_table_btn = QPushButton("💾 Save Table")
        save_table_btn.clicked.connect(self._save_table)
        load_table_btn = QPushButton("📂 Load Table")
        load_table_btn.clicked.connect(self._load_table)

        cheat_btn_layout.addWidget(manual_add_btn)
        cheat_btn_layout.addWidget(change_val_btn)
        cheat_btn_layout.addWidget(remove_btn)
        cheat_btn_layout.addWidget(pointer_btn)
        cheat_btn_layout.addWidget(watchpoint_btn)
        cheat_btn_layout.addSpacing(15)
        cheat_btn_layout.addWidget(save_table_btn)
        cheat_btn_layout.addWidget(load_table_btn)
        cheat_btn_layout.addStretch()
        cheat_layout.addLayout(cheat_btn_layout)

        layout.addWidget(cheat_group, 1)

    def _get_val_type_key(self) -> str:
        idx = self.type_combo.currentIndex()
        mapping = [
            TypeFormat.INT32,
            TypeFormat.INT64,
            TypeFormat.INT16,
            TypeFormat.INT8,
            TypeFormat.FLOAT,
            TypeFormat.DOUBLE,
            TypeFormat.STRING,
            TypeFormat.BYTES,
            TypeFormat.AOB
        ]
        return mapping[idx]

    def _parse_input_val(self) -> Any:
        raw = self.value_input.text().strip()
        val_type = self._get_val_type_key()
        if not raw and self.scan_type_combo.currentText() in (ScanType.EXACT, ScanType.BIGGER_THAN, ScanType.SMALLER_THAN):
            return None
        try:
            if val_type in (TypeFormat.FLOAT, TypeFormat.DOUBLE):
                return float(raw)
            elif val_type in (TypeFormat.INT8, TypeFormat.UINT8, TypeFormat.INT16, TypeFormat.UINT16,
                              TypeFormat.INT32, TypeFormat.UINT32, TypeFormat.INT64, TypeFormat.UINT64):
                return int(raw, 0)
            elif val_type == TypeFormat.STRING:
                return raw
            elif val_type in (TypeFormat.BYTES, TypeFormat.AOB):
                return raw
        except ValueError:
            return None
        return raw

    def _on_enter_pressed(self):
        if self.next_scan_btn.isEnabled():
            self.start_next_scan()
        elif self.first_scan_btn.isEnabled():
            self.start_first_scan()

    def start_first_scan(self):
        if not self.target_pid:
            return
        target_val = self._parse_input_val()
        scan_type = self.scan_type_combo.currentText()
        if scan_type == ScanType.EXACT and target_val is None:
            QMessageBox.warning(self, "Invalid Value", "Please enter a valid value for an Exact scan.")
            return

        val_type = self._get_val_type_key()
        align = 1 if val_type in (TypeFormat.STRING, TypeFormat.BYTES, TypeFormat.AOB) else 4

        self.first_scan_btn.setEnabled(False)
        self.next_scan_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self._scan_worker = ScanWorker(
            pid=self.target_pid,
            val_type=val_type,
            scan_type=scan_type,
            target_val=target_val,
            is_first=True,
            writable_only=self.writable_check.isChecked(),
            alignment=align
        )
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def start_next_scan(self):
        if not self.target_pid or not self.scan_results:
            return
        target_val = self._parse_input_val()
        scan_type = self.scan_type_combo.currentText()
        if scan_type in (ScanType.EXACT, ScanType.BIGGER_THAN, ScanType.SMALLER_THAN) and target_val is None:
            QMessageBox.warning(self, "Invalid Value", "Please enter a valid value to compare.")
            return

        val_type = self._get_val_type_key()

        self.first_scan_btn.setEnabled(False)
        self.next_scan_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self._scan_worker = ScanWorker(
            pid=self.target_pid,
            val_type=val_type,
            scan_type=scan_type,
            target_val=target_val,
            is_first=False,
            previous_results=self.scan_results
        )
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_progress(self, pct: float, msg: str):
        self.progress_bar.setValue(int(pct * 100))
        self.results_count_lbl.setText(msg)

    def _on_scan_finished(self, results: List[ScanResult]):
        self.scan_results = results
        self.progress_bar.setVisible(False)
        self.first_scan_btn.setEnabled(True)
        self.next_scan_btn.setEnabled(len(results) > 0)
        self.results_count_lbl.setText(f"{len(results):,} addresses found")
        self._populate_results_table()

    def _on_scan_error(self, err: str):
        self.progress_bar.setVisible(False)
        self.first_scan_btn.setEnabled(True)
        QMessageBox.critical(self, "Scan Error", f"Memory scan failed:\n{err}")

    def _populate_results_table(self):
        # Display up to 1000 items in table for UI fluidity
        disp_limit = min(1000, len(self.scan_results))
        self.results_table.setRowCount(disp_limit)

        for row in range(disp_limit):
            res = self.scan_results[row]
            addr_item = QTableWidgetItem(f"0x{res.address:X}")
            addr_item.setData(Qt.UserRole, res.address)
            addr_item.setForeground(Qt.cyan)

            val_item = QTableWidgetItem(str(res.value))
            prev_str = str(res.previous_value) if res.previous_value is not None else "-"
            prev_item = QTableWidgetItem(prev_str)
            prev_item.setForeground(Qt.gray)

            self.results_table.setItem(row, 0, addr_item)
            self.results_table.setItem(row, 1, val_item)
            self.results_table.setItem(row, 2, prev_item)

    def new_scan(self):
        self.scan_results = []
        self.results_table.setRowCount(0)
        self.results_count_lbl.setText("0 addresses found")
        self.first_scan_btn.setEnabled(self.target_pid is not None)
        self.next_scan_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

    def _add_selected_to_cheat_table(self):
        selected_rows = self.results_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        val_type = self._get_val_type_key()
        for idx in selected_rows:
            row = idx.row()
            addr_item = self.results_table.item(row, 0)
            val_item = self.results_table.item(row, 1)
            if not addr_item:
                continue
            addr = addr_item.data(Qt.UserRole)
            val = val_item.text()

            self._insert_cheat_entry(addr, val_type, "No description", val)

    def _insert_cheat_entry(self, address: int, val_type: str, desc: str, val: Any):
        row = self.cheat_table.rowCount()
        self.cheat_table.insertRow(row)

        chk_widget = QWidget()
        chk_layout = QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(4, 0, 0, 0)
        chk = QCheckBox()
        chk.toggled.connect(lambda checked, a=address, t=val_type, r=row: self._toggle_freeze(checked, a, t, r))
        chk_layout.addWidget(chk)

        desc_item = QTableWidgetItem(desc)
        addr_item = QTableWidgetItem(f"0x{address:X}")
        addr_item.setData(Qt.UserRole, address)
        addr_item.setForeground(Qt.cyan)

        type_item = QTableWidgetItem(val_type)
        val_item = QTableWidgetItem(str(val))

        self.cheat_table.setCellWidget(row, 0, chk_widget)
        self.cheat_table.setItem(row, 1, desc_item)
        self.cheat_table.setItem(row, 2, addr_item)
        self.cheat_table.setItem(row, 3, type_item)
        self.cheat_table.setItem(row, 4, val_item)

    def add_cheat_entry(self, address: int, val_type: str, desc: str):
        """Public method to programmatically add an entry to the saved Cheat Table."""
        curr_val = "?"
        if self.target_pid:
            curr_val = str(MemoryEngine.read_typed(self.target_pid, address, val_type) or "?")
        self._insert_cheat_entry(address, val_type, desc, curr_val)

    def _toggle_freeze(self, checked: bool, address: int, val_type: str, row: int):
        if not self.target_pid:
            return
        if checked:
            val_item = self.cheat_table.item(row, 4)
            val = val_item.text() if val_item else "0"
            self.freezer.add(self.target_pid, address, val_type, val)
        else:
            self.freezer.remove(self.target_pid, address)

    def _on_cheat_table_double_click(self, index):
        col = index.column()
        row = index.row()
        if col == 4: # Value column
            self._change_selected_val()
        elif col == 1: # Description column
            desc_item = self.cheat_table.item(row, 1)
            current = desc_item.text() if desc_item else ""
            new_desc, ok = QInputDialog.getText(self, "Edit Description", "Description:", text=current)
            if ok and desc_item:
                desc_item.setText(new_desc)

    def _change_selected_val(self):
        row = self.cheat_table.currentRow()
        if row < 0 or not self.target_pid:
            return

        addr_item = self.cheat_table.item(row, 2)
        type_item = self.cheat_table.item(row, 3)
        val_item = self.cheat_table.item(row, 4)
        if not addr_item or not type_item or not val_item:
            return

        addr = addr_item.data(Qt.UserRole)
        v_type = type_item.text()
        current_val = val_item.text()

        new_val, ok = QInputDialog.getText(
            self, "Change Memory Value",
            f"Enter new {v_type} value for 0x{addr:X}:",
            text=current_val
        )
        if ok and new_val:
            success = MemoryEngine.write_typed(self.target_pid, addr, v_type, new_val)
            if success:
                val_item.setText(new_val)
                # If frozen, update freezer value
                if self.freezer.is_frozen(self.target_pid, addr):
                    self.freezer.add(self.target_pid, addr, v_type, new_val)
            else:
                QMessageBox.critical(self, "Write Failed", f"Could not write to address 0x{addr:X}.")

    def _add_manual_address(self):
        addr_str, ok = QInputDialog.getText(self, "Add Address Manually", "Hex Address (e.g. 0x55d6...):")
        if not ok or not addr_str:
            return
        try:
            addr = int(addr_str, 16)
        except ValueError:
            QMessageBox.warning(self, "Invalid Address", "Address must be a valid hex number.")
            return

        val_type = self._get_val_type_key()
        curr_val = "?"
        if self.target_pid:
            curr_val = str(MemoryEngine.read_typed(self.target_pid, addr, val_type) or "?")

        self._insert_cheat_entry(addr, val_type, "Manual Address", curr_val)

    def _remove_selected_cheat(self):
        row = self.cheat_table.currentRow()
        if row < 0:
            return
        addr_item = self.cheat_table.item(row, 2)
        if addr_item and self.target_pid:
            addr = addr_item.data(Qt.UserRole)
            self.freezer.remove(self.target_pid, addr)
        self.cheat_table.removeRow(row)

    def _save_table(self):
        count = self.cheat_table.rowCount()
        if count == 0:
            QMessageBox.information(self, "Empty Table", "No saved addresses to export.")
            return

        entries = []
        for row in range(count):
            desc_item = self.cheat_table.item(row, 1)
            addr_item = self.cheat_table.item(row, 2)
            type_item = self.cheat_table.item(row, 3)
            val_item = self.cheat_table.item(row, 4)
            chk_widget = self.cheat_table.cellWidget(row, 0)
            is_frozen = False
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk:
                    is_frozen = chk.isChecked()

            entries.append({
                "description": desc_item.text() if desc_item else "",
                "address": addr_item.data(Qt.UserRole) if addr_item else 0,
                "type": type_item.text() if type_item else TypeFormat.INT32,
                "value": val_item.text() if val_item else "",
                "frozen": is_frozen
            })

        default_name = f"{self.target_name.replace(' ', '_')}.phantom" if self.target_name else "table.phantom"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Cheat Table", default_name, "Phantom Tables (*.phantom);;All Files (*)"
        )
        if path:
            ok, msg = TableSerializer.save_table(path, self.target_pid, entries, self.target_name)
            if ok:
                QMessageBox.information(self, "Table Saved", msg)
            else:
                QMessageBox.critical(self, "Save Error", msg)

    def _load_table(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Cheat Table", "", "Phantom Tables (*.phantom);;All Files (*)"
        )
        if not path:
            return

        entries, msg = TableSerializer.load_table(path, self.target_pid)
        if entries is None:
            QMessageBox.critical(self, "Load Error", msg)
            return

        for e in entries:
            addr = e["address"]
            v_type = e["type"]
            desc = e["description"]
            val = e["value"]
            is_frozen = e.get("frozen", False)

            # If attached, read live value
            if self.target_pid:
                live_val = MemoryEngine.read_typed(self.target_pid, addr, v_type)
                if live_val is not None:
                    val = str(live_val)

            self._insert_cheat_entry(addr, v_type, desc, val)
            if is_frozen and self.target_pid:
                # Toggle freeze on loaded entry
                row = self.cheat_table.rowCount() - 1
                chk_widget = self.cheat_table.cellWidget(row, 0)
                if chk_widget:
                    chk = chk_widget.findChild(QCheckBox)
                    if chk:
                        chk.setChecked(True)

        QMessageBox.information(self, "Table Loaded", msg)

    def _open_pointer_scanner(self):
        if not self.target_pid:
            QMessageBox.warning(self, "No Target", "Attach to a process first before scanning for pointers.")
            return

        row = self.cheat_table.currentRow()
        target_addr = None

        if row >= 0:
            addr_item = self.cheat_table.item(row, 2)
            if addr_item:
                target_addr = addr_item.data(Qt.UserRole)
        elif self.results_table.currentRow() >= 0:
            res_row = self.results_table.currentRow()
            addr_item = self.results_table.item(res_row, 0)
            if addr_item:
                target_addr = addr_item.data(Qt.UserRole)

        if not target_addr:
            addr_str, ok = QInputDialog.getText(
                self, "Pointer Scanner Target", "Enter hex address to find pointers for:"
            )
            if not ok or not addr_str:
                return
            try:
                target_addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
            except ValueError:
                QMessageBox.warning(self, "Invalid Address", "Address must be a valid hex or integer.")
                return

        dialog = PointerDialog(self.target_pid, target_addr, self)
        dialog.pointer_selected.connect(
            lambda desc, path: self._insert_cheat_entry(target_addr, TypeFormat.INT32, f"{desc} [{path}]", "?")
        )
        dialog.exec()

    def _open_watchpoint_dialog(self):
        row = self.cheat_table.currentRow()
        if row < 0 or not self.target_pid:
            QMessageBox.information(self, "No Selection", "Please select an entry from the address table first.")
            return

        addr_item = self.cheat_table.item(row, 2)
        if not addr_item:
            return

        addr = addr_item.data(Qt.UserRole)
        dialog = WatchpointDialog(self.target_pid, addr, self)
        dialog.exec()

    def get_saved_entries(self) -> List[Dict[str, Any]]:
        """Returns current cheat table entries for HUD overlay."""
        entries = []
        for row in range(self.cheat_table.rowCount()):
            desc_item = self.cheat_table.item(row, 1)
            addr_item = self.cheat_table.item(row, 2)
            type_item = self.cheat_table.item(row, 3)
            if addr_item and type_item:
                entries.append({
                    "address": addr_item.data(Qt.UserRole),
                    "type": type_item.text(),
                    "desc": desc_item.text() if desc_item else "Var"
                })
        return entries

