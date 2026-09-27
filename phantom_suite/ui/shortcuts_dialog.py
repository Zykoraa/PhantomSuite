"""
PhantomSuite Keyboard Shortcuts & Quick Guide Dialog
Displays essential hotkeys and workflows in a cyberpunk modal.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame
)
from PySide6.QtCore import Qt


class ShortcutsDialog(QDialog):
    """Cyberpunk modal dialog listing all global shortcuts and quick actions."""

    SHORTCUTS = [
        ("Ctrl + K / Ctrl + P", "Command Palette", "Global search launcher for tools, actions, and memory addresses"),
        ("Ctrl + B", "Toggle Sidebar", "Collapse sidebar to icon-only mode or expand"),
        ("Ctrl + 0", "Mission Control", "Switch to high-level dashboard & recent targets"),
        ("Ctrl + 1", "Processes & Windows", "Switch to Process Explorer"),
        ("Ctrl + 2", "Memory Scanner", "Switch to Memory Scanner & Cheat Table"),
        ("Ctrl + 3", "Snapshot Diff", "Switch to Full-Process Memory Snapshot Engine"),
        ("Ctrl + 4", "Hex & Disasm", "Switch to Hex Editor & Live x86_64 Disassembler"),
        ("Ctrl + 5", "Struct Dissector", "Switch to Live Struct Dissector & Heatmaps"),
        ("Ctrl + 6", "ELF Symbols", "Switch to Symbol & Module Explorer"),
        ("Ctrl + 7", "Memory Treemap", "Switch to Virtual Address Space Treemap"),
        ("Ctrl + 8", "Syscall Monitor", "Switch to Real-Time Syscall Telemetry Monitor"),
        ("Ctrl + 9", "Python Console", "Switch to Embedded Python Scripting Console"),
        ("F3", "Pause / Resume Process", "Sends SIGSTOP to freeze target or SIGCONT to resume"),
        ("F5", "Global Refresh", "Refreshes data in the active tool tab"),
        ("Ctrl + S", "Save Cheat Table", "Exports current address table to .phantom JSON"),
        ("Ctrl + O", "Load Cheat Table", "Imports saved .phantom cheat table"),
        ("?  /  F1", "Shortcuts Cheat Sheet", "Opens this shortcuts & quick help dialog"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PhantomSuite // Keyboard Shortcuts & Quick Reference")
        self.setFixedSize(680, 520)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Title
        title_box = QHBoxLayout()
        icon_lbl = QLabel("⌨")
        icon_lbl.setStyleSheet("color: #00f0ff; font-size: 20px; font-weight: bold;")
        title_box.addWidget(icon_lbl)

        title_lbl = QLabel("KEYBOARD SHORTCUTS & QUICK REFERENCE")
        title_lbl.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: bold; letter-spacing: 1px;")
        title_box.addWidget(title_lbl)
        title_box.addStretch()

        layout.addLayout(title_box)

        # Shortcuts Table
        self.table = QTableWidget(len(self.SHORTCUTS), 3)
        self.table.setHorizontalHeaderLabels(["Shortcut", "Action", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        for row, (sc, act, desc) in enumerate(self.SHORTCUTS):
            sc_item = QTableWidgetItem(sc)
            sc_item.setForeground(Qt.cyan)
            sc_item.setTextAlignment(Qt.AlignCenter)

            act_item = QTableWidgetItem(act)
            act_item.setForeground(Qt.white)

            desc_item = QTableWidgetItem(desc)
            desc_item.setForeground(Qt.lightGray)

            self.table.setItem(row, 0, sc_item)
            self.table.setItem(row, 1, act_item)
            self.table.setItem(row, 2, desc_item)

        layout.addWidget(self.table, 1)

        # Close button
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        close_btn = QPushButton("Close [ESC]")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)
