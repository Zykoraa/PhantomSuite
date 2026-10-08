"""
PhantomSuite Dynamic Data Deserializer Tab
Decodes C++ STL containers (std::string, std::vector), embedded JSON, and string tables.
"""

import json
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QGroupBox, QAbstractItemView,
    QTextEdit, QSplitter
)
from PySide6.QtCore import Qt, Signal
from phantom_suite.core.data_deserializer import DataDeserializer, DecodedString, DecodedVector, DecodedJson
from phantom_suite.core.memory_engine import TypeFormat


class DeserializerTab(QWidget):
    """Dynamic Data Deserializer & C++ Container Inspector Tab."""

    add_to_cheat_table = Signal(object, str, str) # address, type, description
    jump_to_hex = Signal(object)                  # address

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.last_decoded_vector: Optional[DecodedVector] = None
        self.last_decoded_string: Optional[DecodedString] = None

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.analyze_btn.setEnabled(True)

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.analyze_btn.setEnabled(False)
        self.add_table_btn.setEnabled(False)
        self.jump_hex_btn.setEnabled(False)
        self.details_edit.clear()
        self.elements_table.setRowCount(0)

    def set_address(self, address: int):
        self.addr_input.setText(f"0x{address:X}")
        self.analyze_memory()

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

        # Controls
        ctrl_group = QGroupBox("Container & Structure Configuration")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(10)

        addr_lbl = QLabel("Address:")
        addr_lbl.setStyleSheet("color: #7d90b3;")
        self.addr_input = QLineEdit()
        self.addr_input.setPlaceholderText("Hex address (e.g. 0x55d6...)")
        self.addr_input.returnPressed.connect(self.analyze_memory)

        type_lbl = QLabel("Structure Type:")
        type_lbl.setStyleSheet("color: #7d90b3;")
        self.struct_combo = QComboBox()
        self.struct_combo.addItems([
            "std::string (C++ SSO / Heap)",
            "std::vector<int32>",
            "std::vector<float>",
            "std::vector<int64>",
            "Embedded JSON Buffer",
            "Null-Terminated String Table"
        ])

        self.analyze_btn = QPushButton("🔬 Analyze & Decode")
        self.analyze_btn.setObjectName("accent_btn")
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.clicked.connect(self.analyze_memory)

        self.add_table_btn = QPushButton("⬇ Add to Address Table")
        self.add_table_btn.setEnabled(False)
        self.add_table_btn.clicked.connect(self._add_to_table)

        self.jump_hex_btn = QPushButton("🧬 Jump to Hex")
        self.jump_hex_btn.setEnabled(False)
        self.jump_hex_btn.clicked.connect(self._jump_to_hex)

        ctrl_layout.addWidget(addr_lbl)
        ctrl_layout.addWidget(self.addr_input, 2)
        ctrl_layout.addWidget(type_lbl)
        ctrl_layout.addWidget(self.struct_combo)
        ctrl_layout.addWidget(self.analyze_btn)
        ctrl_layout.addWidget(self.add_table_btn)
        ctrl_layout.addWidget(self.jump_hex_btn)
        layout.addWidget(ctrl_group)

        # Display Splitter: Container Metadata / JSON on left, Elements Table on right
        splitter = QSplitter(Qt.Horizontal)

        left_box = QGroupBox("Deserialized Container Metadata / JSON")
        left_layout = QVBoxLayout(left_box)
        self.details_edit = QTextEdit()
        self.details_edit.setReadOnly(True)
        self.details_edit.setStyleSheet("font-family: monospace; font-size: 13px; color: #00f0ff;")
        left_layout.addWidget(self.details_edit)
        splitter.addWidget(left_box)

        right_box = QGroupBox("Elements / Strings Table")
        right_layout = QVBoxLayout(right_box)
        self.elements_table = QTableWidget()
        self.elements_table.setColumnCount(3)
        self.elements_table.setHorizontalHeaderLabels(["Index / Offset", "Address", "Value"])
        self.elements_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.elements_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.elements_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.elements_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.elements_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.elements_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        right_layout.addWidget(self.elements_table)
        splitter.addWidget(right_box)

        layout.addWidget(splitter, 1)

    def analyze_memory(self):
        if not self.target_pid:
            return

        raw_addr = self.addr_input.text().strip()
        if not raw_addr:
            return

        try:
            addr = int(raw_addr, 16) if raw_addr.startswith(("0x", "0X")) else int(raw_addr)
        except ValueError:
            QMessageBox.warning(self, "Invalid Address", "Address must be a valid hex or integer.")
            return

        stype = self.struct_combo.currentText()
        self.details_edit.clear()
        self.elements_table.setRowCount(0)
        self.last_decoded_vector = None
        self.last_decoded_string = None

        if "std::string" in stype:
            res = DataDeserializer.decode_std_string(self.target_pid, addr)
            if res:
                self.last_decoded_string = res
                info = (
                    f"=== C++ std::string ===\n"
                    f"Address:        0x{res.address:X}\n"
                    f"Storage Mode:   {'SSO (Internal Buffer)' if res.is_sso else 'Heap Allocated'}\n"
                    f"Data Address:   0x{res.data_address:X}\n"
                    f"Length:         {res.length} characters\n"
                    f"Capacity:       {res.capacity} bytes\n\n"
                    f"Decoded String:\n\"{res.text}\""
                )
                self.details_edit.setPlainText(info)
                self.add_table_btn.setEnabled(True)
                self.jump_hex_btn.setEnabled(True)
            else:
                self.details_edit.setPlainText("Could not decode valid std::string at this address.")

        elif "std::vector" in stype:
            elem_sz = 8 if "int64" in stype else 4
            elem_type = "float" if "float" in stype else ("int64" if "int64" in stype else "int32")
            res_vec = DataDeserializer.decode_std_vector(self.target_pid, addr, element_size=elem_sz, element_type=elem_type)
            if res_vec:
                self.last_decoded_vector = res_vec
                info = (
                    f"=== C++ std::vector<{elem_type}> ===\n"
                    f"Address:        0x{res_vec.address:X}\n"
                    f"Elements Count: {res_vec.count}\n"
                    f"Capacity:       {res_vec.capacity}\n"
                    f"Start Buffer:   0x{res_vec.start_address:X}\n"
                    f"Element Size:   {res_vec.element_size} bytes\n"
                )
                self.details_edit.setPlainText(info)

                self.elements_table.setRowCount(len(res_vec.elements))
                for i, val in enumerate(res_vec.elements):
                    elem_addr = res_vec.start_address + (i * res_vec.element_size)
                    idx_item = QTableWidgetItem(f"[{i}]")
                    idx_item.setForeground(Qt.cyan)

                    addr_item = QTableWidgetItem(f"0x{elem_addr:X}")
                    addr_item.setData(Qt.UserRole, elem_addr)
                    addr_item.setForeground(Qt.yellow)

                    val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
                    val_item = QTableWidgetItem(val_str)
                    val_item.setForeground(Qt.green)

                    self.elements_table.setItem(i, 0, idx_item)
                    self.elements_table.setItem(i, 1, addr_item)
                    self.elements_table.setItem(i, 2, val_item)

                self.add_table_btn.setEnabled(True)
                self.jump_hex_btn.setEnabled(True)
            else:
                self.details_edit.setPlainText("Could not decode valid std::vector layout at this address.")

        elif "JSON" in stype:
            json_list = DataDeserializer.find_embedded_json(self.target_pid, addr)
            if json_list:
                formatted_blocks = []
                for j_item in json_list:
                    formatted_blocks.append(f"// Match at +0x{j_item.offset:X} (0x{j_item.address:X}):\n" + json.dumps(j_item.parsed, indent=2))
                self.details_edit.setPlainText("\n\n".join(formatted_blocks))
                self.jump_hex_btn.setEnabled(True)
            else:
                self.details_edit.setPlainText("No valid JSON objects or arrays found in this buffer.")

        elif "String Table" in stype:
            str_list = DataDeserializer.decode_string_table(self.target_pid, addr)
            self.elements_table.setRowCount(len(str_list))
            for i, (str_addr, txt) in enumerate(str_list):
                off_item = QTableWidgetItem(f"+0x{str_addr - addr:X}")
                off_item.setForeground(Qt.cyan)

                addr_item = QTableWidgetItem(f"0x{str_addr:X}")
                addr_item.setData(Qt.UserRole, str_addr)
                addr_item.setForeground(Qt.yellow)

                txt_item = QTableWidgetItem(f'"{txt}"')
                txt_item.setForeground(Qt.green)

                self.elements_table.setItem(i, 0, off_item)
                self.elements_table.setItem(i, 1, addr_item)
                self.elements_table.setItem(i, 2, txt_item)

            self.details_edit.setPlainText(f"Decoded {len(str_list)} null-terminated strings.")
            self.jump_hex_btn.setEnabled(True)

    def _add_to_table(self):
        if self.last_decoded_string:
            s = self.last_decoded_string
            self.add_to_cheat_table.emit(s.data_address, TypeFormat.STRING, f"std::string ({s.length} chars)")
            QMessageBox.information(self, "Added", "std::string data pointer added to Address Table.")
        elif self.last_decoded_vector:
            v = self.last_decoded_vector
            t = TypeFormat.FLOAT if v.element_type == "float" else (TypeFormat.INT64 if v.element_size == 8 else TypeFormat.INT32)
            self.add_to_cheat_table.emit(v.start_address, t, f"vector[0] (size {v.count})")
            QMessageBox.information(self, "Added", "Vector buffer added to Address Table.")

    def _jump_to_hex(self):
        raw = self.addr_input.text().strip()
        if raw:
            try:
                addr = int(raw, 16) if raw.startswith(("0x", "0X")) else int(raw)
                self.jump_to_hex.emit(addr)
            except ValueError:
                pass
