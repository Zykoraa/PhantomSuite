"""
PhantomSuite Shannon Entropy & Cryptographic Primitive Scanner Tab
Interactive visual scanner for identifying AES/SHA/ChaCha20 constants,
cryptographic S-boxes, compressed payload boundaries, and high-entropy packed code.
"""

from typing import Optional, List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QGroupBox, QMessageBox, QApplication, QMenu,
    QAbstractItemView, QDoubleSpinBox, QProgressBar
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, Signal

from phantom_suite.core.memory_engine import MemoryEngine
from phantom_suite.core.entropy_crypto_scanner import (
    EntropyCryptoScanner, EntropyBlock, CryptoMatch
)


class CryptoTab(QWidget):
    """Visual scanner for cryptographic primitives and Shannon entropy profiling."""

    jump_to_hex = Signal(object)
    add_to_cheat_table = Signal(object, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.cached_entropy_blocks: List[EntropyBlock] = []
        self.cached_crypto_matches: List[CryptoMatch] = []

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}  |  <span style='color: #00ff9d;'>Ready for Cryptographic & Entropy Scan</span>")
        self.scan_proc_btn.setEnabled(True)
        self.scan_range_btn.setEnabled(True)

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.cached_entropy_blocks.clear()
        self.cached_crypto_matches.clear()
        self.target_lbl.setText("No Target Attached")
        self.scan_proc_btn.setEnabled(False)
        self.scan_range_btn.setEnabled(False)
        self._clear_displays()

    def _clear_displays(self):
        self.crypto_table.setRowCount(0)
        self.entropy_table.setRowCount(0)
        self.status_lbl.setText("Ready. Attach to target process to scan memory.")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Target Banner
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        layout.addWidget(self.target_lbl)

        # 2. Control Toolbar
        ctrl_layout = QHBoxLayout()

        self.scan_proc_btn = QPushButton("🔐 Scan Process Memory")
        self.scan_proc_btn.setObjectName("accent_btn")
        self.scan_proc_btn.setEnabled(False)
        self.scan_proc_btn.setToolTip("Scan process memory maps for cryptographic constants and high entropy (H >= 7.5)")
        self.scan_proc_btn.clicked.connect(self._scan_process)
        ctrl_layout.addWidget(self.scan_proc_btn)

        ctrl_layout.addSpacing(15)

        ctrl_layout.addWidget(QLabel("Range (Hex):"))
        self.addr_input = QLineEdit()
        self.addr_input.setPlaceholderText("0x7FFF0000")
        self.addr_input.setFont(QFont("Monospace", 10))
        self.addr_input.setFixedWidth(130)
        ctrl_layout.addWidget(self.addr_input)

        ctrl_layout.addWidget(QLabel("Size:"))
        self.size_input = QLineEdit()
        self.size_input.setPlaceholderText("0x10000")
        self.size_input.setFont(QFont("Monospace", 10))
        self.size_input.setFixedWidth(100)
        ctrl_layout.addWidget(self.size_input)

        self.scan_range_btn = QPushButton("🎯 Scan Range")
        self.scan_range_btn.setEnabled(False)
        self.scan_range_btn.clicked.connect(self._scan_custom_range)
        ctrl_layout.addWidget(self.scan_range_btn)

        ctrl_layout.addSpacing(15)

        ctrl_layout.addWidget(QLabel("Min Entropy:"))
        self.entropy_spin = QDoubleSpinBox()
        self.entropy_spin.setRange(0.0, 8.0)
        self.entropy_spin.setSingleStep(0.25)
        self.entropy_spin.setValue(7.5)
        self.entropy_spin.setFixedWidth(70)
        self.entropy_spin.valueChanged.connect(self._apply_filter)
        ctrl_layout.addWidget(self.entropy_spin)

        ctrl_layout.addSpacing(10)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter primitives or algorithms...")
        self.filter_input.textChanged.connect(self._apply_filter)
        ctrl_layout.addWidget(self.filter_input, 1)

        layout.addLayout(ctrl_layout)

        # 3. Main Splitter: Top (Cryptographic Primitives), Bottom (Shannon Entropy Map)
        main_splitter = QSplitter(Qt.Vertical)

        # 3a. Cryptographic Primitives Table
        crypto_box = QGroupBox("Detected Cryptographic Constants & Primitives (AES, SHA, ChaCha20, MD5, CRC)")
        crypto_layout = QVBoxLayout(crypto_box)
        crypto_layout.setContentsMargins(6, 6, 6, 6)

        self.crypto_table = QTableWidget(0, 6)
        self.crypto_table.setHorizontalHeaderLabels([
            "Algorithm", "Primitive Name", "Address", "Confidence", "Sample Hex", "Description"
        ])
        self.crypto_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.crypto_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.crypto_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.crypto_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.crypto_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.crypto_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.crypto_table.setFont(QFont("Monospace", 9))
        self.crypto_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.crypto_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.crypto_table.customContextMenuRequested.connect(self._show_crypto_context_menu)
        self.crypto_table.itemDoubleClicked.connect(self._on_crypto_double_clicked)
        crypto_layout.addWidget(self.crypto_table)

        main_splitter.addWidget(crypto_box)

        # 3b. Shannon Entropy Profile Table
        entropy_box = QGroupBox("Shannon Information Entropy Profile (H ∈ [0.0, 8.0 bits/byte])")
        entropy_layout = QVBoxLayout(entropy_box)
        entropy_layout.setContentsMargins(6, 6, 6, 6)

        self.entropy_table = QTableWidget(0, 5)
        self.entropy_table.setHorizontalHeaderLabels([
            "Memory Range", "Block Size", "Entropy (bits/byte)", "Classification", "Visual Density"
        ])
        self.entropy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.entropy_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.entropy_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.entropy_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.entropy_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.entropy_table.setFont(QFont("Monospace", 9))
        self.entropy_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.entropy_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.entropy_table.customContextMenuRequested.connect(self._show_entropy_context_menu)
        self.entropy_table.itemDoubleClicked.connect(self._on_entropy_double_clicked)
        entropy_layout.addWidget(self.entropy_table)

        main_splitter.addWidget(entropy_box)
        main_splitter.setSizes([320, 320])
        layout.addWidget(main_splitter, 1)

        # 4. Status Strip
        self.status_lbl = QLabel("Ready. Attach to target process to scan memory.")
        self.status_lbl.setStyleSheet("color: #7d90b3; font-size: 11px;")
        layout.addWidget(self.status_lbl)

    def _scan_process(self):
        if not self.target_pid:
            return

        self.status_lbl.setText("Scanning process memory maps for cryptographic primitives and entropy...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            entropy_blocks, crypto_matches = EntropyCryptoScanner.scan_process(self.target_pid, max_regions=100)
            self.cached_entropy_blocks = entropy_blocks
            self.cached_crypto_matches = crypto_matches
            self._render_results()
            self.status_lbl.setText(
                f"Scan complete. Found {len(crypto_matches)} cryptographic constants, "
                f"{len(entropy_blocks)} high-entropy blocks (H >= 7.5)."
            )
        except Exception as e:
            QMessageBox.critical(self, "Scan Error", f"Failed to scan target process: {e}")
            self.status_lbl.setText("Scan failed.")
        finally:
            QApplication.restoreOverrideCursor()

    def _scan_custom_range(self):
        if not self.target_pid:
            return

        addr_txt = self.addr_input.text().strip()
        size_txt = self.size_input.text().strip()

        if not addr_txt or not size_txt:
            QMessageBox.warning(self, "Missing Parameters", "Please enter starting address and size in hex.")
            return

        try:
            addr = int(addr_txt, 16)
            size = int(size_txt, 16)
        except ValueError:
            QMessageBox.warning(self, "Invalid Hex", "Address and size must be valid hexadecimal numbers.")
            return

        data = MemoryEngine.read_bytes(self.target_pid, addr, size)
        if not data:
            QMessageBox.warning(self, "Read Error", f"Could not read {size} bytes from 0x{addr:X}.")
            return

        blocks = EntropyCryptoScanner.scan_entropy_blocks(data, block_size=min(4096, len(data)), base_address=addr)
        matches = EntropyCryptoScanner.scan_buffer_for_crypto(data, base_address=addr)

        self.cached_entropy_blocks = blocks
        self.cached_crypto_matches = matches
        self._render_results()
        self.status_lbl.setText(f"Range scan at 0x{addr:X} complete: {len(matches)} crypto matches, {len(blocks)} entropy blocks.")

    def _render_results(self):
        self._apply_filter()

    def _apply_filter(self):
        term = self.filter_input.text().strip().lower()
        min_entropy = self.entropy_spin.value()

        # 1. Filter & Render Crypto Table
        filtered_crypto = [
            m for m in self.cached_crypto_matches
            if not term or term in m.algorithm.lower() or term in m.name.lower() or term in m.description.lower()
        ]

        self.crypto_table.setRowCount(0)
        self.crypto_table.setRowCount(len(filtered_crypto))

        for row, m in enumerate(filtered_crypto):
            algo_item = QTableWidgetItem(m.algorithm)
            algo_item.setForeground(QColor("#00f0ff"))
            algo_item.setFont(QFont("Monospace", 9, QFont.Bold))

            name_item = QTableWidgetItem(m.name)
            name_item.setForeground(QColor("#f8f8f2"))

            addr_item = QTableWidgetItem(f"0x{m.address:016X}")
            addr_item.setForeground(QColor("#50fa7b"))

            conf_item = QTableWidgetItem(f"{m.confidence * 100:.0f}%")
            conf_item.setForeground(QColor("#ffb86c"))

            sample_item = QTableWidgetItem(m.sample_hex)
            sample_item.setForeground(QColor("#bd93f9"))

            desc_item = QTableWidgetItem(m.description)
            desc_item.setForeground(QColor("#8fa0c0"))

            self.crypto_table.setItem(row, 0, algo_item)
            self.crypto_table.setItem(row, 1, name_item)
            self.crypto_table.setItem(row, 2, addr_item)
            self.crypto_table.setItem(row, 3, conf_item)
            self.crypto_table.setItem(row, 4, sample_item)
            self.crypto_table.setItem(row, 5, desc_item)

        # 2. Filter & Render Entropy Table
        filtered_entropy = [
            b for b in self.cached_entropy_blocks
            if b.entropy >= min_entropy and (not term or term in b.classification.lower())
        ]

        self.entropy_table.setRowCount(0)
        self.entropy_table.setRowCount(len(filtered_entropy))

        for row, b in enumerate(filtered_entropy):
            range_str = f"0x{b.address:016X} - 0x{b.address + b.size:016X}"
            range_item = QTableWidgetItem(range_str)
            range_item.setForeground(QColor("#00f0ff"))

            size_item = QTableWidgetItem(f"{b.size} B")
            size_item.setForeground(QColor("#7d90b3"))

            ent_item = QTableWidgetItem(f"{b.entropy:.4f} / 8.0000")
            if b.entropy >= 7.5:
                ent_item.setForeground(QColor("#ff5555"))  # Red/Pink high entropy
                ent_item.setFont(QFont("Monospace", 9, QFont.Bold))
            elif b.entropy >= 5.0:
                ent_item.setForeground(QColor("#00f0ff"))
            else:
                ent_item.setForeground(QColor("#50fa7b"))

            class_item = QTableWidgetItem(b.classification)
            if b.classification == "Encrypted/Packed":
                class_item.setForeground(QColor("#ff79c6"))
            elif b.classification == "Code/Structured":
                class_item.setForeground(QColor("#8be9fd"))
            else:
                class_item.setForeground(QColor("#6272a4"))

            # Visual meter
            bar_len = int((b.entropy / 8.0) * 20)
            bar_visual = "█" * bar_len + "░" * (20 - bar_len)
            meter_item = QTableWidgetItem(bar_visual)
            meter_item.setForeground(QColor("#ff5555" if b.entropy >= 7.5 else "#00f0ff"))

            self.entropy_table.setItem(row, 0, range_item)
            self.entropy_table.setItem(row, 1, size_item)
            self.entropy_table.setItem(row, 2, ent_item)
            self.entropy_table.setItem(row, 3, class_item)
            self.entropy_table.setItem(row, 4, meter_item)

    # --- Double-Click & Context Menus ---

    def _on_crypto_double_clicked(self, item):
        row = item.row()
        addr_item = self.crypto_table.item(row, 2)
        if addr_item:
            addr = int(addr_item.text(), 16)
            self.jump_to_hex.emit(addr)

    def _on_entropy_double_clicked(self, item):
        row = item.row()
        range_item = self.entropy_table.item(row, 0)
        if range_item:
            start_addr = int(range_item.text().split(" - ")[0], 16)
            self.jump_to_hex.emit(start_addr)

    def _show_crypto_context_menu(self, pos):
        item = self.crypto_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        algo = self.crypto_table.item(row, 0).text()
        name = self.crypto_table.item(row, 1).text()
        addr = int(self.crypto_table.item(row, 2).text(), 16)
        sample = self.crypto_table.item(row, 4).text()

        menu = QMenu(self)

        act_hex = menu.addAction(f"🧬 Jump to Hex @ 0x{addr:X}")
        act_hex.triggered.connect(lambda: self.jump_to_hex.emit(addr))

        act_cheat = menu.addAction(f"➕ Add '{name}' to Cheat Table")
        act_cheat.triggered.connect(lambda: self.add_to_cheat_table.emit(addr, "bytes", f"Crypto_{algo}_{name}"))

        act_copy_addr = menu.addAction("📋 Copy Address")
        act_copy_addr.triggered.connect(lambda: QApplication.clipboard().setText(f"0x{addr:X}"))

        act_copy_hex = menu.addAction("📋 Copy Pattern Hex")
        act_copy_hex.triggered.connect(lambda: QApplication.clipboard().setText(sample))

        menu.exec(self.crypto_table.viewport().mapToGlobal(pos))

    def _show_entropy_context_menu(self, pos):
        item = self.entropy_table.itemAt(pos)
        if not item:
            return

        row = item.row()
        range_str = self.entropy_table.item(row, 0).text()
        start_addr = int(range_str.split(" - ")[0], 16)

        menu = QMenu(self)
        act_hex = menu.addAction(f"🧬 Jump to Hex @ 0x{start_addr:X}")
        act_hex.triggered.connect(lambda: self.jump_to_hex.emit(start_addr))

        act_copy = menu.addAction("📋 Copy Address Range")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(range_str))

        menu.exec(self.entropy_table.viewport().mapToGlobal(pos))
