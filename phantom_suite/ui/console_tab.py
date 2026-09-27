"""
PhantomSuite Python Scripting Console Tab
Interactive multi-line script editor, REPL output console, and automation templates.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QTextEdit, QComboBox,
    QMessageBox, QGroupBox, QFileDialog, QSplitter
)
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtCore import Qt
from phantom_suite.core.script_engine import ScriptEngine


EXAMPLES = {
    "Select Template...": "",
    "Read & Modify Value": (
        "# Read and modify a 32-bit integer at an address\n"
        "# Replace 0x55... with your target address\n"
        "addr = 0x555555558080\n"
        "val = read_i32(addr)\n"
        "print(f'Current Value: {val}')\n"
        "if val is not None:\n"
        "    write_i32(addr, val + 100)\n"
        "    print(f'New Value: {read_i32(addr)}')\n"
    ),
    "AOB Pattern Scan": (
        "# Scan process memory for an AOB pattern with wildcards\n"
        "pattern = '48 89 5C ?? ?? 48 83'\n"
        "matches = scan(pattern)\n"
        "print(f'Found {len(matches)} matches:')\n"
        "for m in matches[:10]:\n"
        "    print(f' -> 0x{m.address:X} ({m.module_name} + 0x{m.offset:X})')\n"
    ),
    "Enumerate Exported Symbols": (
        "# List all functions exported by the main executable\n"
        "modules = symbols()\n"
        "print(f'Loaded modules: {[m.name for m in modules]}')\n"
        "target_symbols = symbols(modules[0].name)\n"
        "print(f'Found {len(target_symbols)} symbols in {modules[0].name}:')\n"
        "for s in target_symbols[:15]:\n"
        "    print(f' [{s.symbol_type}] {s.name} -> 0x{s.runtime_address:X}' if s.runtime_address else f' [{s.symbol_type}] {s.name}')\n"
    ),
    "Dissect Entity Struct": (
        "# Dissect a 128-byte heap struct and print fields\n"
        "addr = 0x555555558080\n"
        "fields = dissect(addr, size=64)\n"
        "for f in fields:\n"
        "    print(f'+0x{f.offset:02X} | {f.suggested_type:<18} | {f.name:<12} | val: {f.int32_val}')\n"
    )
}


class ConsoleTab(QWidget):
    """Embedded Python Scripting Console and Automation Tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.engine = ScriptEngine()

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.engine.set_target(pid)

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.engine.set_target(0)

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

        # Controls Bar
        ctrl_layout = QHBoxLayout()
        self.run_btn = QPushButton("▶ Run Script (Ctrl+Enter)")
        self.run_btn.setObjectName("accent_btn")
        self.run_btn.clicked.connect(self._run_code)

        self.clear_out_btn = QPushButton("🗑 Clear Log")
        self.clear_out_btn.clicked.connect(self.output_edit_clear)

        self.template_combo = QComboBox()
        self.template_combo.addItems(list(EXAMPLES.keys()))
        self.template_combo.currentIndexChanged.connect(self._on_template_selected)

        self.open_btn = QPushButton("📂 Open...")
        self.open_btn.clicked.connect(self._open_script)

        self.save_btn = QPushButton("💾 Save...")
        self.save_btn.clicked.connect(self._save_script)

        ctrl_layout.addWidget(self.run_btn)
        ctrl_layout.addWidget(self.clear_out_btn)
        ctrl_layout.addSpacing(15)
        ctrl_layout.addWidget(QLabel("Templates:"))
        ctrl_layout.addWidget(self.template_combo)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.open_btn)
        ctrl_layout.addWidget(self.save_btn)
        layout.addLayout(ctrl_layout)

        # Splitter: Code Editor (top) & Console Log (bottom)
        splitter = QSplitter(Qt.Vertical)

        # Code Editor
        editor_group = QGroupBox("Python Automation Editor")
        editor_layout = QVBoxLayout(editor_group)
        self.code_edit = QPlainTextEdit()
        font = QFont("Monospace", 10)
        self.code_edit.setFont(font)
        self.code_edit.setPlaceholderText(
            "# Write Python code here to automate memory actions...\n"
            "# Helpers available: read(addr, sz), write(addr, bytes), read_i32(addr), write_i32(addr, val),\n"
            "# scan(pattern), disasm(addr), dissect(addr), symbols(mod), MemoryEngine, TableSerializer...\n"
        )
        self.code_edit.setPlainText(
            "# PhantomSuite Python Automation\n"
            "print(f'Connected to Target PID: {pid}')\n"
        )
        editor_layout.addWidget(self.code_edit)
        splitter.addWidget(editor_group)

        # Console Output
        out_group = QGroupBox("Interactive Console Output")
        out_layout = QVBoxLayout(out_group)
        self.out_edit = QTextEdit()
        self.out_edit.setFont(font)
        self.out_edit.setReadOnly(True)
        self.out_edit.setStyleSheet("background-color: #080c14; color: #00ff9d;")
        out_layout.addWidget(self.out_edit)
        splitter.addWidget(out_group)

        layout.addWidget(splitter, 1)

        # Keyboard Shortcut: Ctrl+Enter to run
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._run_code)

    def _run_code(self):
        code = self.code_edit.toPlainText().strip()
        if not code:
            return

        self.out_edit.append(f"<font color='#00f0ff'><b>&gt;&gt;&gt; Running script...</b></font>")
        success, output = self.engine.execute(code)
        if output.strip():
            color = "#00ff9d" if success else "#ff007f"
            clean_out = output.replace("\n", "<br>")
            self.out_edit.append(f"<font color='{color}'>{clean_out}</font>")
        else:
            self.out_edit.append("<font color='#7d90b3'>[Finished with no output]</font>")
        self.out_edit.append("<br>")

    def output_edit_clear(self):
        self.out_edit.clear()

    def _on_template_selected(self, index: int):
        key = self.template_combo.currentText()
        content = EXAMPLES.get(key, "")
        if content:
            self.code_edit.setPlainText(content)

    def _open_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Python Script", "", "Python Files (*.py);;All Files (*)")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.code_edit.setPlainText(f.read())
            except Exception as e:
                QMessageBox.critical(self, "Open Error", str(e))

    def _save_script(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Python Script", "automation.py", "Python Files (*.py);;All Files (*)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.code_edit.toPlainText())
                QMessageBox.information(self, "Saved", f"Script saved to {path}.")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", str(e))
