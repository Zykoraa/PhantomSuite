"""
PhantomSuite Struct Dissector Tab
Interactive memory structure dissection, heuristic type analysis,
live heatmap delta tracking, and C struct definition export.
"""

from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox, QGroupBox, QComboBox, QAbstractItemView,
    QDialog, QTextEdit, QDialogButtonBox, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal
from phantom_suite.core.struct_dissector import StructDissector, DissectedField
from phantom_suite.core.memory_engine import TypeFormat


class StructExportDialog(QDialog):
    """Dialog showing auto-generated C struct header."""

    def __init__(self, c_code: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exported C Struct Definition")
        self.resize(600, 450)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info_lbl = QLabel("Compilable C header definition based on live dissected memory:")
        info_lbl.setStyleSheet("color: #7d90b3;")
        layout.addWidget(info_lbl)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(c_code)
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("font-family: monospace; font-size: 13px;")
        layout.addWidget(self.text_edit)

        btn_box = QHBoxLayout()
        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.setObjectName("accent_btn")
        copy_btn.clicked.connect(self._copy_to_clipboard)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_box.addStretch()
        btn_box.addWidget(copy_btn)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

    def _copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())
        QMessageBox.information(self, "Copied", "Struct definition copied to clipboard.")


class StructTab(QWidget):
    """Live Struct Dissector and Heatmap Tab."""

    # Signal to request adding fields to the Cheat Table in ScannerTab
    add_to_cheat_table = Signal(object, str, str) # address, type, description
    jump_to_hex = Signal(object)                  # address

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.current_base_addr: int = 0
        self.current_fields: List[DissectedField] = []
        self.previous_byte_snapshots: Dict[int, bytes] = {} # offset -> bytes
        self.custom_field_names: Dict[int, str] = {}         # offset -> custom name

        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._on_timer_refresh)

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.dissect_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.add_table_btn.setEnabled(True)

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.dissect_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.add_table_btn.setEnabled(False)
        self.struct_table.setRowCount(0)
        self._timer.stop()
        self.auto_refresh_chk.setChecked(False)
        self.previous_byte_snapshots.clear()
        self.custom_field_names.clear()

    def set_base_address(self, address: int):
        self.current_base_addr = address
        self.addr_input.setText(f"0x{address:X}")
        self.dissect_memory()

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

        # Control Panel
        ctrl_group = QGroupBox("Struct Dissector Configuration")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(10)

        addr_lbl = QLabel("Base Address:")
        addr_lbl.setStyleSheet("color: #7d90b3;")
        self.addr_input = QLineEdit()
        self.addr_input.setPlaceholderText("Hex address (e.g. 0x55af...)")
        self.addr_input.returnPressed.connect(self.dissect_memory)

        size_lbl = QLabel("Size:")
        size_lbl.setStyleSheet("color: #7d90b3;")
        self.size_combo = QComboBox()
        self.size_combo.addItems(["128 Bytes", "256 Bytes", "512 Bytes", "1024 Bytes", "2048 Bytes"])
        self.size_combo.setCurrentIndex(1) # 256

        stride_lbl = QLabel("Stride:")
        stride_lbl.setStyleSheet("color: #7d90b3;")
        self.stride_combo = QComboBox()
        self.stride_combo.addItems(["4 Bytes (32-bit)", "8 Bytes (64-bit)"])

        self.dissect_btn = QPushButton("🔬 Dissect")
        self.dissect_btn.setObjectName("accent_btn")
        self.dissect_btn.setEnabled(False)
        self.dissect_btn.clicked.connect(self.dissect_memory)

        self.auto_refresh_chk = QCheckBox("🔥 Live Heatmap (300ms)")
        self.auto_refresh_chk.setToolTip("Periodically re-reads struct and highlights changed values in neon magenta")
        self.auto_refresh_chk.toggled.connect(self._on_auto_refresh_toggled)

        self.export_btn = QPushButton("📄 Export C Struct")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_c_struct)

        self.add_table_btn = QPushButton("⬇ Add to Address Table")
        self.add_table_btn.setEnabled(False)
        self.add_table_btn.clicked.connect(self._add_selected_to_table)

        ctrl_layout.addWidget(addr_lbl)
        ctrl_layout.addWidget(self.addr_input, 2)
        ctrl_layout.addWidget(size_lbl)
        ctrl_layout.addWidget(self.size_combo)
        ctrl_layout.addWidget(stride_lbl)
        ctrl_layout.addWidget(self.stride_combo)
        ctrl_layout.addWidget(self.dissect_btn)
        ctrl_layout.addWidget(self.auto_refresh_chk)
        ctrl_layout.addWidget(self.export_btn)
        ctrl_layout.addWidget(self.add_table_btn)
        layout.addWidget(ctrl_group)

        # Struct Table
        table_group = QGroupBox("Dissected Memory Structure")
        table_layout = QVBoxLayout(table_group)

        self.struct_table = QTableWidget()
        self.struct_table.setColumnCount(7)
        self.struct_table.setHorizontalHeaderLabels([
            "Offset", "Address", "Field Name", "Suggested Type", "Value", "Hex Bytes", "Heatmap"
        ])
        self.struct_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.struct_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.struct_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.struct_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.struct_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.struct_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.struct_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.struct_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.struct_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self.struct_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        self.struct_table.cellChanged.connect(self._on_cell_changed)
        self.struct_table.itemDoubleClicked.connect(self._on_item_double_clicked)
        table_layout.addWidget(self.struct_table)

        layout.addWidget(table_group, 1)

    def _get_selected_size(self) -> int:
        txt = self.size_combo.currentText().split()[0]
        return int(txt)

    def _get_selected_stride(self) -> int:
        return 8 if "8" in self.stride_combo.currentText() else 4

    def dissect_memory(self):
        if not self.target_pid:
            return

        raw_addr = self.addr_input.text().strip()
        if not raw_addr:
            return

        try:
            self.current_base_addr = int(raw_addr, 16) if raw_addr.startswith(("0x", "0X")) else int(raw_addr)
        except ValueError:
            QMessageBox.warning(self, "Invalid Address", "Address must be a valid hex or integer.")
            return

        size = self._get_selected_size()
        stride = self._get_selected_stride()

        fields = StructDissector.dissect(
            pid=self.target_pid,
            base_address=self.current_base_addr,
            size=size,
            stride=stride,
            previous_fields=self.previous_byte_snapshots
        )

        # Restore custom field names
        for f in fields:
            if f.offset in self.custom_field_names:
                f.name = self.custom_field_names[f.offset]

        self.current_fields = fields
        self._update_table(fields)

        # Update snapshot cache
        self.previous_byte_snapshots = {f.offset: f.raw_bytes for f in fields}

    def _update_table(self, fields: List[DissectedField]):
        self.struct_table.blockSignals(True)
        self.struct_table.setRowCount(len(fields))

        for row, f in enumerate(fields):
            # 0: Offset
            off_item = QTableWidgetItem(f"+0x{f.offset:03X}")
            off_item.setFlags(off_item.flags() & ~Qt.ItemIsEditable)
            off_item.setForeground(Qt.cyan)

            # 1: Address
            addr_item = QTableWidgetItem(f"0x{f.address:X}")
            addr_item.setData(Qt.UserRole, f.address)
            addr_item.setFlags(addr_item.flags() & ~Qt.ItemIsEditable)
            addr_item.setForeground(Qt.yellow)

            # 2: Field Name (Editable)
            name_item = QTableWidgetItem(f.name)
            name_item.setData(Qt.UserRole, f.offset)

            # 3: Suggested Type
            type_item = QTableWidgetItem(f.suggested_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            if "Pointer" in f.suggested_type:
                type_item.setForeground(Qt.magenta)
            elif "Float" in f.suggested_type:
                type_item.setForeground(Qt.green)
            else:
                type_item.setForeground(Qt.white)

            # 4: Formatted Value
            if f.is_pointer:
                val_str = f"0x{f.pointer_target:X} ({f.pointer_desc})"
            elif f.suggested_type == "Float":
                val_str = f"{f.float_val:.6f}"
            elif f.suggested_type == "String / ASCII":
                val_str = f"\"{f.ascii_repr}\""
            elif f.suggested_type == "8 Bytes (int64)":
                val_str = f"{f.int64_val} (0x{f.int64_val:X})"
            else:
                val_str = f"{f.int32_val} (0x{f.int32_val:X})"

            val_item = QTableWidgetItem(val_str)
            val_item.setFlags(val_item.flags() & ~Qt.ItemIsEditable)

            # 5: Hex Bytes
            hex_str = " ".join(f"{b:02X}" for b in f.raw_bytes)
            hex_item = QTableWidgetItem(hex_str)
            hex_item.setFlags(hex_item.flags() & ~Qt.ItemIsEditable)
            hex_item.setForeground(Qt.cyan)

            # 6: Heatmap Status
            heat_item = QTableWidgetItem("● DIFF" if f.changed else "-")
            heat_item.setFlags(heat_item.flags() & ~Qt.ItemIsEditable)
            if f.changed:
                heat_item.setForeground(Qt.red)
                val_item.setForeground(Qt.red)
                off_item.setForeground(Qt.red)
            else:
                heat_item.setForeground(Qt.darkGray)

            self.struct_table.setItem(row, 0, off_item)
            self.struct_table.setItem(row, 1, addr_item)
            self.struct_table.setItem(row, 2, name_item)
            self.struct_table.setItem(row, 3, type_item)
            self.struct_table.setItem(row, 4, val_item)
            self.struct_table.setItem(row, 5, hex_item)
            self.struct_table.setItem(row, 6, heat_item)

        self.struct_table.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int):
        if col == 2: # Field Name edited
            item = self.struct_table.item(row, col)
            if item:
                off = item.data(Qt.UserRole)
                if off is not None:
                    self.custom_field_names[off] = item.text().strip()
                    if row < len(self.current_fields):
                        self.current_fields[row].name = item.text().strip()

    def _on_item_double_clicked(self, item: QTableWidgetItem):
        if item.column() == 1: # Double clicked Address column -> jump to Hex/Disasm
            addr = item.data(Qt.UserRole)
            if addr:
                self.jump_to_hex.emit(addr)

    def _on_auto_refresh_toggled(self, checked: bool):
        if checked:
            self._timer.start()
        else:
            self._timer.stop()

    def _on_timer_refresh(self):
        if self.target_pid and self.current_base_addr > 0:
            self.dissect_memory()

    def _export_c_struct(self):
        if not self.current_fields:
            QMessageBox.information(self, "No Struct", "Dissect memory first to export struct.")
            return

        c_code = StructDissector.export_c_struct(self.current_fields, struct_name=f"Entity_{self.current_base_addr:X}")
        dlg = StructExportDialog(c_code, self)
        dlg.exec()

    def _add_selected_to_table(self):
        selected_rows = sorted(set(idx.row() for idx in self.struct_table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Select one or more fields from the table first.")
            return

        for row in selected_rows:
            if row < len(self.current_fields):
                f = self.current_fields[row]
                # Map suggested type to TypeFormat
                if f.suggested_type == "Float":
                    t = TypeFormat.FLOAT
                elif f.suggested_type == "8 Bytes (int64)" or f.is_pointer:
                    t = TypeFormat.INT64
                elif f.suggested_type == "String / ASCII":
                    t = TypeFormat.STRING
                else:
                    t = TypeFormat.INT32

                desc = f"{f.name} (+0x{f.offset:X})"
                self.add_to_cheat_table.emit(f.address, t, desc)

        QMessageBox.information(
            self, "Added",
            f"Added {len(selected_rows)} field(s) to the Address Table in the Memory Scanner tab."
        )
