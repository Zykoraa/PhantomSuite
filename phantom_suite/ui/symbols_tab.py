"""
PhantomSuite ELF Symbol & Module Explorer Tab
Interactive module inspection, exported/imported function and object browsing,
filtering, runtime address resolution, and 1-click jump to disassembly.
"""

from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QGroupBox, QAbstractItemView, QApplication
)
from PySide6.QtCore import Qt, Signal
from phantom_suite.core.elf_explorer import ElfExplorer, LoadedModule, ElfSymbol
from phantom_suite.core.memory_engine import TypeFormat


class SymbolsTab(QWidget):
    """ELF Module, Symbol & Section Explorer Tab."""

    jump_to_disasm = Signal(int)              # runtime address
    add_to_cheat_table = Signal(int, str, str) # address, type, description

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.loaded_modules: List[LoadedModule] = []
        self.current_symbols: List[ElfSymbol] = []
        self.filtered_symbols: List[ElfSymbol] = []

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.refresh_modules_btn.setEnabled(True)
        self.refresh_modules()

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.refresh_modules_btn.setEnabled(False)
        self.jump_disasm_btn.setEnabled(False)
        self.add_table_btn.setEnabled(False)
        self.copy_addr_btn.setEnabled(False)
        self.module_combo.clear()
        self.symbols_table.setRowCount(0)
        self.loaded_modules.clear()
        self.current_symbols.clear()
        self.filtered_symbols.clear()
        self.count_lbl.setText("0 symbols")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target Banner
        banner_layout = QHBoxLayout()
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.count_lbl = QLabel("0 symbols")
        self.count_lbl.setStyleSheet("color: #7d90b3;")
        banner_layout.addWidget(self.target_lbl)
        banner_layout.addStretch()
        banner_layout.addWidget(self.count_lbl)
        layout.addLayout(banner_layout)

        # Filter & Module Selection Panel
        ctrl_group = QGroupBox("ELF Module & Symbol Filter")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(10)

        mod_lbl = QLabel("Module:")
        mod_lbl.setStyleSheet("color: #7d90b3;")
        self.module_combo = QComboBox()
        self.module_combo.currentIndexChanged.connect(self._on_module_selected)

        self.refresh_modules_btn = QPushButton("⟳ Refresh")
        self.refresh_modules_btn.setEnabled(False)
        self.refresh_modules_btn.clicked.connect(self.refresh_modules)

        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet("color: #7d90b3;")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Search symbol name (e.g. main, health, socket)...")
        self.filter_input.textChanged.connect(self._apply_filter)

        type_lbl = QLabel("Type:")
        type_lbl.setStyleSheet("color: #7d90b3;")
        self.type_combo = QComboBox()
        self.type_combo.addItems(["All Symbols", "Functions (FUNC)", "Objects (OBJECT)", "Defined Only", "Imported Only"])
        self.type_combo.currentIndexChanged.connect(self._apply_filter)

        self.jump_disasm_btn = QPushButton("🔬 Disassemble")
        self.jump_disasm_btn.setObjectName("accent_btn")
        self.jump_disasm_btn.setEnabled(False)
        self.jump_disasm_btn.clicked.connect(self._jump_selected_to_disasm)

        self.add_table_btn = QPushButton("⬇ Add to Table")
        self.add_table_btn.setEnabled(False)
        self.add_table_btn.clicked.connect(self._add_selected_to_table)

        self.copy_addr_btn = QPushButton("📋 Copy Addr")
        self.copy_addr_btn.setEnabled(False)
        self.copy_addr_btn.clicked.connect(self._copy_selected_addr)

        ctrl_layout.addWidget(mod_lbl)
        ctrl_layout.addWidget(self.module_combo, 2)
        ctrl_layout.addWidget(self.refresh_modules_btn)
        ctrl_layout.addWidget(filter_lbl)
        ctrl_layout.addWidget(self.filter_input, 2)
        ctrl_layout.addWidget(type_lbl)
        ctrl_layout.addWidget(self.type_combo)
        ctrl_layout.addWidget(self.jump_disasm_btn)
        ctrl_layout.addWidget(self.add_table_btn)
        ctrl_layout.addWidget(self.copy_addr_btn)
        layout.addWidget(ctrl_group)

        # Symbols Table
        table_group = QGroupBox("Exported & Imported Symbols")
        table_layout = QVBoxLayout(table_group)

        self.symbols_table = QTableWidget()
        self.symbols_table.setColumnCount(7)
        self.symbols_table.setHorizontalHeaderLabels([
            "Symbol Name", "Type", "File Offset", "Runtime Address", "Size", "Binding", "Status"
        ])
        self.symbols_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.symbols_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.symbols_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.symbols_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.symbols_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.symbols_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.symbols_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.symbols_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.symbols_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.symbols_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.symbols_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        self.symbols_table.doubleClicked.connect(self._jump_selected_to_disasm)
        table_layout.addWidget(self.symbols_table)

        layout.addWidget(table_group, 1)

    def refresh_modules(self):
        if not self.target_pid:
            return

        self.module_combo.blockSignals(True)
        self.module_combo.clear()

        modules = ElfExplorer.get_loaded_modules(self.target_pid)
        self.loaded_modules = modules

        for m in modules:
            label = f"{m.name} (0x{m.base_address:X})"
            self.module_combo.addItem(label, m)

        self.module_combo.blockSignals(False)

        if modules:
            self._on_module_selected(0)
            self.jump_disasm_btn.setEnabled(True)
            self.add_table_btn.setEnabled(True)
            self.copy_addr_btn.setEnabled(True)

    def _on_module_selected(self, index: int):
        if index < 0 or index >= len(self.loaded_modules):
            return

        mod = self.loaded_modules[index]
        symbols = ElfExplorer.parse_symbols(mod.path, base_address=mod.base_address)
        self.current_symbols = symbols
        self._apply_filter()

    def _apply_filter(self):
        search_txt = self.filter_input.text().strip().lower()
        type_filter = self.type_combo.currentText()

        results: List[ElfSymbol] = []
        for s in self.current_symbols:
            if search_txt and search_txt not in s.name.lower():
                continue

            if type_filter == "Functions (FUNC)" and s.symbol_type != "FUNC":
                continue
            elif type_filter == "Objects (OBJECT)" and s.symbol_type != "OBJECT":
                continue
            elif type_filter == "Defined Only" and s.is_imported:
                continue
            elif type_filter == "Imported Only" and not s.is_imported:
                continue

            results.append(s)

        self.filtered_symbols = results
        self.count_lbl.setText(f"{len(results)} / {len(self.current_symbols)} symbols")
        self._populate_table(results)

    def _populate_table(self, symbols: List[ElfSymbol]):
        self.symbols_table.setRowCount(len(symbols))

        for row, s in enumerate(symbols):
            # 0: Name
            name_item = QTableWidgetItem(s.name)
            name_item.setForeground(Qt.cyan if s.symbol_type == "FUNC" else (Qt.yellow if s.symbol_type == "OBJECT" else Qt.white))

            # 1: Type
            type_item = QTableWidgetItem(s.symbol_type)

            # 2: File Offset
            off_item = QTableWidgetItem(f"0x{s.file_offset:X}" if s.file_offset > 0 else "-")
            off_item.setForeground(Qt.gray)

            # 3: Runtime Address
            if s.runtime_address is not None:
                addr_item = QTableWidgetItem(f"0x{s.runtime_address:012X}")
                addr_item.setData(Qt.UserRole, s.runtime_address)
                addr_item.setForeground(Qt.green)
            else:
                addr_item = QTableWidgetItem("[Import / Unresolved]")
                addr_item.setData(Qt.UserRole, 0)
                addr_item.setForeground(Qt.gray)

            # 4: Size
            size_item = QTableWidgetItem(str(s.size))

            # 5: Binding
            bind_item = QTableWidgetItem(s.bind)

            # 6: Status
            status_item = QTableWidgetItem("Imported" if s.is_imported else "Exported/Local")
            status_item.setForeground(Qt.magenta if s.is_imported else Qt.green)

            self.symbols_table.setItem(row, 0, name_item)
            self.symbols_table.setItem(row, 1, type_item)
            self.symbols_table.setItem(row, 2, off_item)
            self.symbols_table.setItem(row, 3, addr_item)
            self.symbols_table.setItem(row, 4, size_item)
            self.symbols_table.setItem(row, 5, bind_item)
            self.symbols_table.setItem(row, 6, status_item)

    def _get_selected_symbol(self) -> Optional[ElfSymbol]:
        row = self.symbols_table.currentRow()
        if row < 0 or row >= len(self.filtered_symbols):
            return None
        return self.filtered_symbols[row]

    def _jump_selected_to_disasm(self):
        sym = self._get_selected_symbol()
        if not sym:
            QMessageBox.information(self, "No Selection", "Please select a symbol first.")
            return

        if not sym.runtime_address or sym.runtime_address <= 0:
            QMessageBox.warning(self, "Unresolved Symbol", "This symbol is an external import and has no direct runtime address.")
            return

        self.jump_to_disasm.emit(sym.runtime_address)

    def _add_selected_to_table(self):
        sym = self._get_selected_symbol()
        if not sym:
            QMessageBox.information(self, "No Selection", "Please select a symbol first.")
            return

        if not sym.runtime_address or sym.runtime_address <= 0:
            QMessageBox.warning(self, "Cannot Add", "Cannot add unresolved import to address table.")
            return

        # Determine type
        val_type = TypeFormat.INT32
        if sym.symbol_type == "FUNC":
            val_type = TypeFormat.BYTES
        elif sym.size == 8:
            val_type = TypeFormat.INT64
        elif sym.size == 1:
            val_type = TypeFormat.INT8

        self.add_to_cheat_table.emit(sym.runtime_address, val_type, f"Symbol: {sym.name}")
        QMessageBox.information(self, "Added", f"Symbol '{sym.name}' added to Address Table.")

    def _copy_selected_addr(self):
        sym = self._get_selected_symbol()
        if not sym or not sym.runtime_address:
            return

        hex_addr = f"0x{sym.runtime_address:X}"
        clipboard = QApplication.clipboard()
        clipboard.setText(hex_addr)
        QMessageBox.information(self, "Copied", f"Address {hex_addr} copied to clipboard.")
