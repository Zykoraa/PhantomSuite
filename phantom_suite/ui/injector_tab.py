"""
PhantomSuite Shared Object (.so) Injector Tab
Provides library injection via GDB dlopen, module mapping, and unloading.
"""

import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QTextEdit, QMessageBox, QGroupBox, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal
from phantom_suite.core.injector import Injector
from phantom_suite.core.memory_engine import MemoryRegion


class InjectWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, pid: int, so_path: str):
        super().__init__()
        self.pid = pid
        self.so_path = so_path

    def run(self):
        success, msg = Injector.inject(self.pid, self.so_path)
        self.finished.emit(success, msg)


class InjectorTab(QWidget):
    """Shared Object Injector and Loaded Module Explorer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.modules: List[MemoryRegion] = []
        self._inject_worker: Optional[InjectWorker] = None

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #ff007f; font-weight: bold;")
        self.inject_btn.setEnabled(True)
        self.refresh_modules()

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.inject_btn.setEnabled(False)
        self.modules_table.setRowCount(0)

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

        # Injection Control Box
        inject_group = QGroupBox("Payload Injection (.so)")
        inject_layout = QVBoxLayout(inject_group)
        inject_layout.setSpacing(8)

        row1 = QHBoxLayout()
        so_lbl = QLabel("Shared Object:")
        so_lbl.setStyleSheet("color: #7d90b3;")
        self.so_path_input = QLineEdit()
        self.so_path_input.setPlaceholderText("Select or enter path to .so payload...")
        browse_btn = QPushButton("📁 Browse...")
        browse_btn.clicked.connect(self._browse_so)

        row1.addWidget(so_lbl)
        row1.addWidget(self.so_path_input, 2)
        row1.addWidget(browse_btn)
        inject_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.inject_btn = QPushButton("💉 Inject Payload")
        self.inject_btn.setObjectName("accent_btn")
        self.inject_btn.setEnabled(False)
        self.inject_btn.clicked.connect(self._start_injection)

        self.unload_btn = QPushButton("⏏ Unload Selected")
        self.unload_btn.clicked.connect(self._unload_selected)

        row2.addStretch()
        row2.addWidget(self.inject_btn)
        row2.addWidget(self.unload_btn)
        inject_layout.addLayout(row2)

        layout.addWidget(inject_group)

        # Loaded Modules Explorer
        modules_group = QGroupBox("Loaded Dynamic Modules & Libraries")
        modules_layout = QVBoxLayout(modules_group)

        mod_top_bar = QHBoxLayout()
        self.mod_search = QLineEdit()
        self.mod_search.setPlaceholderText("Filter loaded modules...")
        self.mod_search.textChanged.connect(self._filter_modules)

        refresh_mod_btn = QPushButton("⟳ Refresh Modules")
        refresh_mod_btn.clicked.connect(self.refresh_modules)

        mod_top_bar.addWidget(self.mod_search, 2)
        mod_top_bar.addWidget(refresh_mod_btn)
        modules_layout.addLayout(mod_top_bar)

        self.modules_table = QTableWidget()
        self.modules_table.setColumnCount(4)
        self.modules_table.setHorizontalHeaderLabels([
            "Module Name", "Base Address", "Perms", "Full Path"
        ])
        self.modules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.modules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.modules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.modules_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.modules_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.modules_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.modules_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        modules_layout.addWidget(self.modules_table)

        layout.addWidget(modules_group, 2)

        # Log Console
        log_group = QGroupBox("Injection Logs")
        log_layout = QVBoxLayout(log_group)
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("background-color: #080a0f; color: #00ff9d; font-size: 11px;")
        log_layout.addWidget(self.log_console)
        layout.addWidget(log_group, 1)

    def _browse_so(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Shared Object (.so)", "", "Shared Libraries (*.so);;All Files (*)"
        )
        if path:
            self.so_path_input.setText(path)

    def _start_injection(self):
        if not self.target_pid:
            return
        so_path = self.so_path_input.text().strip()
        if not so_path:
            QMessageBox.warning(self, "No Payload", "Please select a .so payload file to inject.")
            return

        self.inject_btn.setEnabled(False)
        self.log_console.append(f"[*] Attaching to PID {self.target_pid} to inject: {so_path}")

        self._inject_worker = InjectWorker(self.target_pid, so_path)
        self._inject_worker.finished.connect(self._on_inject_finished)
        self._inject_worker.start()

    def _on_inject_finished(self, success: bool, msg: str):
        self.inject_btn.setEnabled(True)
        if success:
            self.log_console.append(f"[+] SUCCESS: {msg}")
            self.refresh_modules()
        else:
            self.log_console.append(f"[-] FAILED: {msg}")
            QMessageBox.critical(self, "Injection Failed", msg)

    def refresh_modules(self):
        if not self.target_pid:
            self.modules_table.setRowCount(0)
            return
        self.modules = Injector.get_loaded_modules(self.target_pid)
        self._filter_modules()

    def _filter_modules(self):
        query = self.mod_search.text().strip().lower()
        filtered = []
        for m in self.modules:
            if query:
                haystack = f"{m.pathname} {m.start:x}".lower()
                if query not in haystack:
                    continue
            filtered.append(m)

        self.modules_table.setRowCount(len(filtered))
        for row, m in enumerate(filtered):
            name = os.path.basename(m.pathname)
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, m.pathname)
            name_item.setForeground(Qt.cyan)

            base_item = QTableWidgetItem(f"0x{m.start:X}")
            base_item.setForeground(Qt.yellow)

            perm_item = QTableWidgetItem(m.perms)
            path_item = QTableWidgetItem(m.pathname)

            self.modules_table.setItem(row, 0, name_item)
            self.modules_table.setItem(row, 1, base_item)
            self.modules_table.setItem(row, 2, perm_item)
            self.modules_table.setItem(row, 3, path_item)

    def _unload_selected(self):
        row = self.modules_table.currentRow()
        if row < 0 or not self.target_pid:
            QMessageBox.warning(self, "No Module Selected", "Please select a loaded module to unload.")
            return

        name_item = self.modules_table.item(row, 0)
        if not name_item:
            return
        so_name = name_item.text()

        self.log_console.append(f"[*] Attempting to unload {so_name} from PID {self.target_pid}...")
        ok, msg = Injector.unload(self.target_pid, so_name)
        if ok:
            self.log_console.append(f"[+] {msg}")
            self.refresh_modules()
        else:
            self.log_console.append(f"[-] {msg}")
            QMessageBox.warning(self, "Unload", msg)
