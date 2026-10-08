"""
PhantomSuite IL2CPP Metadata & Klass Explorer Tab
Visual hierarchy browser, field/method introspector, instance value resolver,
and C#/C++20 struct header generator for Unity IL2CPP processes.
"""

from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QGroupBox, QTextEdit, QTabWidget, QMessageBox,
    QApplication, QMenu
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, Signal

from phantom_suite.core.il2cpp_inspector import (
    Il2CppInspector, Il2CppClassDef, Il2CppFieldDef, Il2CppMethodDef, Il2CppObjectDump
)


class Il2CppTab(QWidget):
    """Visual IL2CPP Metadata and Klass Layout Explorer Tab."""

    jump_to_hex = Signal(object)
    add_to_cheat_table = Signal(object, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.current_class: Optional[Il2CppClassDef] = None
        self.current_object: Optional[Il2CppObjectDump] = None

        self._init_ui()
        self.clear_target()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        is_il2cpp = Il2CppInspector.detect_il2cpp(pid)
        status_text = "IL2CPP Runtime Detected" if is_il2cpp else "IL2CPP Not Detected (Manual Inspect Available)"
        status_color = "#00ff9d" if is_il2cpp else "#ffb86c"

        self.target_lbl.setText(f"Target: [{pid}] {name}  |  <span style='color: {status_color};'>{status_text}</span>")
        self.inspect_btn.setEnabled(True)
        self.inspect_obj_btn.setEnabled(True)

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.current_class = None
        self.current_object = None
        self.target_lbl.setText("No Target Attached")
        self.inspect_btn.setEnabled(False)
        self.inspect_obj_btn.setEnabled(False)
        self._clear_displays()

    def _clear_displays(self):
        self.info_lbl.setText("Enter a 64-bit Il2CppClass or instance address to inspect.")
        self.fields_table.setRowCount(0)
        self.methods_table.setRowCount(0)
        self.code_preview.clear()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target & Status Banner
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        layout.addWidget(self.target_lbl)

        # Top Control Bar
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Address (Hex):"))

        self.addr_input = QLineEdit()
        self.addr_input.setPlaceholderText("0x5555A000 (Class pointer) or 0x7FFF... (Instance)")
        self.addr_input.setFont(QFont("Monospace", 10))
        self.addr_input.setFixedWidth(240)
        self.addr_input.returnPressed.connect(self._inspect_address)
        ctrl_layout.addWidget(self.addr_input)

        self.inspect_btn = QPushButton("🔍 Inspect Class")
        self.inspect_btn.setObjectName("accent_btn")
        self.inspect_btn.clicked.connect(self._inspect_address)
        ctrl_layout.addWidget(self.inspect_btn)

        self.inspect_obj_btn = QPushButton("🎯 Inspect Object")
        self.inspect_obj_btn.clicked.connect(self._inspect_object_address)
        ctrl_layout.addWidget(self.inspect_obj_btn)

        ctrl_layout.addSpacing(15)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter fields or methods...")
        self.filter_input.textChanged.connect(self._filter_tables)
        ctrl_layout.addWidget(self.filter_input, 1)

        layout.addLayout(ctrl_layout)

        # Class Info Banner
        self.info_lbl = QLabel("Enter a 64-bit Il2CppClass or instance address to inspect.")
        self.info_lbl.setStyleSheet(
            "background-color: #121824; border: 1px solid #1a2436; border-radius: 4px; "
            "padding: 8px 12px; color: #a9b7d0; font-family: Monospace;"
        )
        layout.addWidget(self.info_lbl)

        # Tabbed Viewer: Fields / Methods / Code Synthesizer
        self.tabs = QTabWidget()

        # Tab 1: Fields Table
        self.fields_table = QTableWidget()
        self.fields_table.setColumnCount(5)
        self.fields_table.setHorizontalHeaderLabels(["Offset", "Field Name", "Type", "Flags", "Instance Value (Hex / Ptr)"])
        self.fields_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.fields_table.horizontalHeader().setStretchLastSection(True)
        self.fields_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.fields_table.customContextMenuRequested.connect(self._show_field_context_menu)
        self.tabs.addTab(self.fields_table, "📋 Fields")

        # Tab 2: Methods Table
        self.methods_table = QTableWidget()
        self.methods_table.setColumnCount(4)
        self.methods_table.setHorizontalHeaderLabels(["VA Address", "Method Name", "Return Type", "Signature"])
        self.methods_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.methods_table.horizontalHeader().setStretchLastSection(True)
        self.methods_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.methods_table.customContextMenuRequested.connect(self._show_method_context_menu)
        self.tabs.addTab(self.methods_table, "⚡ Methods (VTable)")

        # Tab 3: Generated Code Synthesizer
        code_widget = QWidget()
        code_layout = QVBoxLayout(code_widget)
        code_btn_bar = QHBoxLayout()

        self.export_cs_btn = QPushButton("📄 C# Class Header")
        self.export_cs_btn.clicked.connect(self._export_csharp)
        code_btn_bar.addWidget(self.export_cs_btn)

        self.export_cpp_btn = QPushButton("⚙️ C++20 Struct")
        self.export_cpp_btn.clicked.connect(self._export_cpp)
        code_btn_bar.addWidget(self.export_cpp_btn)

        self.copy_code_btn = QPushButton("📋 Copy Code")
        self.copy_code_btn.clicked.connect(self._copy_code)
        code_btn_bar.addWidget(self.copy_code_btn)
        code_btn_bar.addStretch()

        code_layout.addLayout(code_btn_bar)

        self.code_preview = QTextEdit()
        self.code_preview.setFont(QFont("Monospace", 10))
        self.code_preview.setReadOnly(True)
        self.code_preview.setStyleSheet("background-color: #0b0f17; color: #00ff9d;")
        code_layout.addWidget(self.code_preview)

        self.tabs.addTab(code_widget, "🧬 Synthesized Header")

        layout.addWidget(self.tabs, 1)

    def _parse_addr_input(self) -> Optional[int]:
        text = self.addr_input.text().strip()
        if not text:
            return None
        try:
            return int(text, 16) if text.startswith("0x") or text.startswith("0X") else int(text)
        except ValueError:
            QMessageBox.warning(self, "Invalid Address", "Please enter a valid hexadecimal or integer address.")
            return None

    def _inspect_address(self):
        if not self.target_pid:
            QMessageBox.information(self, "No Target", "Please attach to a process first.")
            return

        addr = self._parse_addr_input()
        if not addr or addr <= 0:
            return

        klass = Il2CppInspector.inspect_class(self.target_pid, addr)
        if not klass:
            QMessageBox.warning(self, "Inspection Failed", f"No valid Il2CppClass metadata resolved at 0x{addr:X}.")
            return

        self.current_class = klass
        self.current_object = None
        self._populate_class_view(klass)

    def _inspect_object_address(self):
        if not self.target_pid:
            QMessageBox.information(self, "No Target", "Please attach to a process first.")
            return

        addr = self._parse_addr_input()
        if not addr or addr <= 0:
            return

        obj_dump = Il2CppInspector.inspect_object(self.target_pid, addr)
        if not obj_dump:
            QMessageBox.warning(self, "Inspection Failed", f"No valid Il2CppObject resolved at 0x{addr:X}.")
            return

        self.current_class = obj_dump.klass
        self.current_object = obj_dump
        self._populate_class_view(obj_dump.klass, obj_dump)

    def _populate_class_view(self, klass: Il2CppClassDef, obj: Optional[Il2CppObjectDump] = None):
        self.current_class = klass
        self.current_object = obj

        # Update Info Banner
        parent_str = f" : {klass.parent_name}" if klass.parent_name else ""
        obj_str = f" | Object: 0x{obj.object_address:X}" if obj else ""
        self.info_lbl.setText(
            f"<b>{klass.full_name}{parent_str}</b> | Klass: 0x{klass.klass_address:016X} "
            f"| Size: 0x{klass.instance_size:X} ({klass.instance_size} B) "
            f"| Fields: {len(klass.fields)} | Methods: {len(klass.methods)}{obj_str}"
        )

        # Populate Fields
        self.fields_table.setRowCount(0)
        sorted_fields = sorted(klass.fields, key=lambda f: f.offset)
        for row_idx, f in enumerate(sorted_fields):
            self.fields_table.insertRow(row_idx)

            off_str = f"+0x{abs(f.offset):02X}" if f.offset >= 0 else f"Static (0x{f.offset:X})"
            item_off = QTableWidgetItem(off_str)
            item_off.setFont(QFont("Monospace", 9))
            self.fields_table.setItem(row_idx, 0, item_off)

            item_name = QTableWidgetItem(f.name)
            item_name.setForeground(QColor("#00f0ff"))
            self.fields_table.setItem(row_idx, 1, item_name)

            item_type = QTableWidgetItem(f.type_name)
            self.fields_table.setItem(row_idx, 2, item_type)

            flag_str = "Static" if f.is_static else "Instance"
            item_flags = QTableWidgetItem(flag_str)
            item_flags.setForeground(QColor("#ffb86c" if f.is_static else "#7d90b3"))
            self.fields_table.setItem(row_idx, 3, item_flags)

            val_str = ""
            if obj and f.name in obj.field_values:
                val = obj.field_values[f.name]
                val_str = f"0x{val:016X} ({val})"

            item_val = QTableWidgetItem(val_str)
            item_val.setFont(QFont("Monospace", 9))
            item_val.setForeground(QColor("#00ff9d"))
            self.fields_table.setItem(row_idx, 4, item_val)

        # Populate Methods
        self.methods_table.setRowCount(0)
        for row_idx, m in enumerate(klass.methods):
            self.methods_table.insertRow(row_idx)

            va_str = f"0x{m.method_pointer:016X}"
            item_va = QTableWidgetItem(va_str)
            item_va.setFont(QFont("Monospace", 9))
            item_va.setForeground(QColor("#00ff9d"))
            self.methods_table.setItem(row_idx, 0, item_va)

            item_name = QTableWidgetItem(m.name)
            item_name.setForeground(QColor("#ffffff"))
            self.methods_table.setItem(row_idx, 1, item_name)

            item_ret = QTableWidgetItem(m.return_type)
            self.methods_table.setItem(row_idx, 2, item_ret)

            sig = f"{m.return_type} {m.name}();"
            item_sig = QTableWidgetItem(sig)
            item_sig.setFont(QFont("Monospace", 9))
            self.methods_table.setItem(row_idx, 3, item_sig)

        # Generate default C# code
        self._export_csharp()

    def _export_csharp(self):
        if not self.current_class:
            return
        cs = Il2CppInspector.generate_csharp_header(self.current_class)
        self.code_preview.setPlainText(cs)

    def _export_cpp(self):
        if not self.current_class:
            return
        cpp = Il2CppInspector.generate_cpp_struct(self.current_class)
        self.code_preview.setPlainText(cpp)

    def _copy_code(self):
        text = self.code_preview.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            QMessageBox.information(self, "Copied", "Synthesized code copied to clipboard.")

    def _filter_tables(self, query: str):
        q = query.lower().strip()
        # Filter Fields
        for row in range(self.fields_table.rowCount()):
            name = self.fields_table.item(row, 1).text().lower() if self.fields_table.item(row, 1) else ""
            type_str = self.fields_table.item(row, 2).text().lower() if self.fields_table.item(row, 2) else ""
            visible = (q in name) or (q in type_str) if q else True
            self.fields_table.setRowHidden(row, not visible)

        # Filter Methods
        for row in range(self.methods_table.rowCount()):
            name = self.methods_table.item(row, 1).text().lower() if self.methods_table.item(row, 1) else ""
            visible = (q in name) if q else True
            self.methods_table.setRowHidden(row, not visible)

    def _show_field_context_menu(self, pos):
        item = self.fields_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        f_name = self.fields_table.item(row, 1).text()

        menu = QMenu(self)
        if self.current_object and f_name in self.current_object.field_values:
            val = self.current_object.field_values[f_name]
            act_jump = menu.addAction(f"Jump to Field Value in Hex Tab (0x{val:X})")
            act_jump.triggered.connect(lambda: self.jump_to_hex.emit(val))

            act_add = menu.addAction(f"Add Field to Cheat Table")
            f_off = next((f.offset for f in self.current_class.fields if f.name == f_name), 0)
            target_addr = self.current_object.object_address + f_off
            act_add.triggered.connect(lambda: self.add_to_cheat_table.emit(target_addr, "int32", f"{self.current_class.name}.{f_name}"))

        menu.exec(self.fields_table.viewport().mapToGlobal(pos))

    def _show_method_context_menu(self, pos):
        item = self.methods_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        va_str = self.methods_table.item(row, 0).text()
        try:
            va = int(va_str, 16)
        except ValueError:
            return

        menu = QMenu(self)
        act_jump = menu.addAction(f"Disassemble Method in Hex Tab ({va_str})")
        act_jump.triggered.connect(lambda: self.jump_to_hex.emit(va))
        menu.exec(self.methods_table.viewport().mapToGlobal(pos))
