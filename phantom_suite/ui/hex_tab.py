"""
PhantomSuite Memory Hex Viewer & In-Place Patcher Tab
Live interactive memory inspection with hex, ASCII, and byte-patching.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox, QGroupBox, QInputDialog, QAbstractItemView
)
from PySide6.QtCore import Qt, QTimer
from phantom_suite.core.hex_viewer import HexViewer, HexLine


class HexTab(QWidget):
    """Live Memory Hex Viewer and In-Place Patcher."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.current_address: int = 0
        self.bytes_per_page: int = 256

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

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.goto_btn.setEnabled(False)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.patch_btn.setEnabled(False)
        self.hex_table.setRowCount(0)
        self._timer.stop()
        self.auto_refresh_chk.setChecked(False)

    def navigate_to_address(self, address: int):
        self.current_address = address
        self.addr_input.setText(f"0x{address:X}")
        self.refresh_hex()

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
        nav_group = QGroupBox("Memory Navigation")
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

        nav_layout.addWidget(addr_lbl)
        nav_layout.addWidget(self.addr_input, 2)
        nav_layout.addWidget(self.goto_btn)
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addWidget(self.auto_refresh_chk)
        nav_layout.addWidget(self.patch_btn)
        layout.addWidget(nav_group)

        # Hex Display Grid
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

        layout.addWidget(self.hex_table, 1)

    def _on_goto_clicked(self):
        raw = self.addr_input.text().strip()
        if not raw:
            return
        try:
            self.current_address = int(raw, 16) if raw.startswith(("0x", "0X")) else int(raw)
            self.refresh_hex()
        except ValueError:
            QMessageBox.warning(self, "Invalid Address", "Address must be a valid hex or integer.")

    def _on_prev_page(self):
        self.current_address = max(0, self.current_address - self.bytes_per_page)
        self.addr_input.setText(f"0x{self.current_address:X}")
        self.refresh_hex()

    def _on_next_page(self):
        self.current_address += self.bytes_per_page
        self.addr_input.setText(f"0x{self.current_address:X}")
        self.refresh_hex()

    def _on_auto_refresh_toggled(self, checked: bool):
        if checked:
            self._timer.start()
        else:
            self._timer.stop()

    def _on_timer_refresh(self):
        if self.target_pid and self.current_address > 0:
            self.refresh_hex()

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
                self.refresh_hex()
                QMessageBox.information(self, "Success", msg)
            else:
                QMessageBox.critical(self, "Patch Failed", msg)
