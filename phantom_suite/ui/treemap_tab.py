"""
PhantomSuite Virtual Address Space & Treemap Visualizer Tab
Interactive visualization of virtual memory segments, permissions, heap/stack boundaries,
and segment-to-hex/struct navigation.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QGroupBox, QAbstractItemView, QFrame
)
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
from PySide6.QtCore import Qt, Signal
from phantom_suite.core.memory_map import MemoryMapAnalyzer, VisualMemoryBlock, MapCategoryStats


class MemoryBarWidget(QFrame):
    """Visual proportional bar showing distribution of memory categories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #0b1118; border: 1px solid #1c2638; border-radius: 4px;")
        self.stats: Optional[MapCategoryStats] = None

    def set_stats(self, stats: MapCategoryStats):
        self.stats = stats
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.stats or self.stats.total_virt_bytes == 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width() - 2
        h = self.height() - 2
        total = self.stats.total_virt_bytes

        # Categories: Code, Heap, Stack, Writable, Readonly, Shared
        segments = [
            (self.stats.executable_bytes, QColor("#00f0ff")), # Code
            (self.stats.heap_bytes, QColor("#00ff9d")),       # Heap
            (self.stats.stack_bytes, QColor("#ffb700")),      # Stack
            (self.stats.writable_bytes - self.stats.heap_bytes - self.stats.stack_bytes, QColor("#ff007f")), # Writable
            (self.stats.readonly_bytes, QColor("#7d90b3")),   # Readonly
            (self.stats.shared_bytes, QColor("#b537f2"))      # Shared
        ]

        x_cursor = 1
        for num_bytes, color in segments:
            if num_bytes <= 0:
                continue
            seg_width = max(2, int((num_bytes / total) * w))
            if x_cursor + seg_width > w + 1:
                seg_width = (w + 1) - x_cursor
            if seg_width <= 0:
                break
            painter.fillRect(x_cursor, 1, seg_width, h, QBrush(color))
            x_cursor += seg_width


class TreemapTab(QWidget):
    """Virtual Address Space & Memory Map Visualizer Tab."""

    jump_to_hex = Signal(int)     # address
    jump_to_struct = Signal(int)  # address

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.current_blocks: List[VisualMemoryBlock] = []
        self.filtered_blocks: List[VisualMemoryBlock] = []

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.refresh_btn.setEnabled(True)
        self.refresh_map()

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.refresh_btn.setEnabled(False)
        self.jump_hex_btn.setEnabled(False)
        self.dissect_btn.setEnabled(False)
        self.map_table.setRowCount(0)
        self.bar_widget.set_stats(None)
        self.stat_virt.setText("-")
        self.stat_code.setText("-")
        self.stat_heap.setText("-")
        self.stat_regions.setText("-")

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

        # KPI Stats Summary
        kpi_group = QGroupBox("Virtual Address Space Summary")
        kpi_layout = QHBoxLayout(kpi_group)
        kpi_layout.setSpacing(15)

        self.stat_virt = self._create_kpi_card("Total VIRT", "-", "#00f0ff", kpi_layout)
        self.stat_code = self._create_kpi_card("Executable Code", "-", "#00f0ff", kpi_layout)
        self.stat_heap = self._create_kpi_card("Writable / Heap", "-", "#00ff9d", kpi_layout)
        self.stat_regions = self._create_kpi_card("Total Regions", "-", "#ffb700", kpi_layout)
        layout.addWidget(kpi_group)

        # Visual Proportion Bar
        bar_group = QGroupBox("Memory Segment Proportion")
        bar_layout = QVBoxLayout(bar_group)
        self.bar_widget = MemoryBarWidget()
        bar_layout.addWidget(self.bar_widget)

        # Legend
        legend_layout = QHBoxLayout()
        self._add_legend_item("■ Code (r-xp)", "#00f0ff", legend_layout)
        self._add_legend_item("■ Heap", "#00ff9d", legend_layout)
        self._add_legend_item("■ Stack", "#ffb700", legend_layout)
        self._add_legend_item("■ Writable Data", "#ff007f", legend_layout)
        self._add_legend_item("■ Read-Only", "#7d90b3", legend_layout)
        self._add_legend_item("■ Shared", "#b537f2", legend_layout)
        legend_layout.addStretch()
        bar_layout.addLayout(legend_layout)
        layout.addWidget(bar_group)

        # Filter & Action Controls
        ctrl_layout = QHBoxLayout()
        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet("color: #7d90b3;")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by path, library, or category...")
        self.filter_input.textChanged.connect(self._apply_filter)

        perm_lbl = QLabel("Perms:")
        perm_lbl.setStyleSheet("color: #7d90b3;")
        self.perm_combo = QComboBox()
        self.perm_combo.addItems(["All Segments", "Executable (r-xp)", "Writable (rw-p)", "Read-Only (r--p)", "Heap & Stack"])
        self.perm_combo.currentIndexChanged.connect(self._apply_filter)

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.clicked.connect(self.refresh_map)

        self.jump_hex_btn = QPushButton("🧬 Jump to Hex")
        self.jump_hex_btn.setObjectName("accent_btn")
        self.jump_hex_btn.setEnabled(False)
        self.jump_hex_btn.clicked.connect(self._jump_selected_to_hex)

        self.dissect_btn = QPushButton("🔬 Dissect Region")
        self.dissect_btn.setEnabled(False)
        self.dissect_btn.clicked.connect(self._dissect_selected_region)

        ctrl_layout.addWidget(filter_lbl)
        ctrl_layout.addWidget(self.filter_input, 2)
        ctrl_layout.addWidget(perm_lbl)
        ctrl_layout.addWidget(self.perm_combo)
        ctrl_layout.addWidget(self.refresh_btn)
        ctrl_layout.addWidget(self.jump_hex_btn)
        ctrl_layout.addWidget(self.dissect_btn)
        layout.addLayout(ctrl_layout)

        # Memory Regions Table
        self.map_table = QTableWidget()
        self.map_table.setColumnCount(6)
        self.map_table.setHorizontalHeaderLabels([
            "Start Address", "End Address", "Size", "Perms", "Category", "Mapping / Path"
        ])
        self.map_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.map_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.map_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.map_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.map_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.map_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.map_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.map_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.map_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.map_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        self.map_table.doubleClicked.connect(self._jump_selected_to_hex)
        layout.addWidget(self.map_table, 1)

    def _create_kpi_card(self, label: str, init_val: str, color_hex: str, parent_layout) -> QLabel:
        card = QFrame()
        card.setStyleSheet("background-color: #0d141e; border: 1px solid #1c2638; border-radius: 4px; padding: 6px 12px;")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(4, 4, 4, 4)
        c_layout.setSpacing(2)

        lbl = QLabel(label)
        lbl.setStyleSheet("color: #7d90b3; font-size: 11px;")
        val_lbl = QLabel(init_val)
        val_lbl.setStyleSheet(f"color: {color_hex}; font-size: 15px; font-weight: bold;")

        c_layout.addWidget(lbl)
        c_layout.addWidget(val_lbl)
        parent_layout.addWidget(card)
        return val_lbl

    def _add_legend_item(self, text: str, color_hex: str, parent_layout):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {color_hex}; font-size: 11px; font-weight: bold; margin-right: 12px;")
        parent_layout.addWidget(lbl)

    def refresh_map(self):
        if not self.target_pid:
            return

        blocks, stats = MemoryMapAnalyzer.analyze_process_maps(self.target_pid)
        self.current_blocks = blocks
        self.bar_widget.set_stats(stats)

        # Update KPI cards
        self.stat_virt.setText(f"{stats.total_virt_bytes / (1024*1024):.1f} MB")
        self.stat_code.setText(f"{stats.executable_bytes / (1024*1024):.1f} MB")
        self.stat_heap.setText(f"{stats.writable_bytes / (1024*1024):.1f} MB")
        self.stat_regions.setText(f"{stats.region_count}")

        self._apply_filter()

    def _apply_filter(self):
        search_txt = self.filter_input.text().strip().lower()
        perm_filter = self.perm_combo.currentText()

        results: List[VisualMemoryBlock] = []
        for b in self.current_blocks:
            if search_txt and (search_txt not in b.label.lower() and search_txt not in b.category.lower()):
                continue

            if perm_filter == "Executable (r-xp)" and "x" not in b.perms:
                continue
            elif perm_filter == "Writable (rw-p)" and "w" not in b.perms:
                continue
            elif perm_filter == "Read-Only (r--p)" and ("w" in b.perms or "x" in b.perms):
                continue
            elif perm_filter == "Heap & Stack" and b.category not in ("HEAP", "STACK"):
                continue

            results.append(b)

        self.filtered_blocks = results
        self.map_table.setRowCount(len(results))

        for row, b in enumerate(results):
            start_item = QTableWidgetItem(f"0x{b.start:012X}")
            start_item.setData(Qt.UserRole, b.start)
            start_item.setForeground(Qt.yellow)

            end_item = QTableWidgetItem(f"0x{b.end:012X}")
            end_item.setForeground(Qt.gray)

            # Format size (KB or MB)
            sz_kb = b.size // 1024
            sz_str = f"{sz_kb / 1024:.2f} MB" if sz_kb >= 1024 else f"{sz_kb} KB"
            size_item = QTableWidgetItem(sz_str)

            perm_item = QTableWidgetItem(b.perms)
            if "x" in b.perms:
                perm_item.setForeground(Qt.cyan)
            elif "w" in b.perms:
                perm_item.setForeground(Qt.magenta)
            else:
                perm_item.setForeground(Qt.gray)

            cat_item = QTableWidgetItem(b.category)
            cat_item.setForeground(QColor(b.color_hex))

            label_item = QTableWidgetItem(b.label)
            label_item.setForeground(Qt.white)

            self.map_table.setItem(row, 0, start_item)
            self.map_table.setItem(row, 1, end_item)
            self.map_table.setItem(row, 2, size_item)
            self.map_table.setItem(row, 3, perm_item)
            self.map_table.setItem(row, 4, cat_item)
            self.map_table.setItem(row, 5, label_item)

        has_rows = len(results) > 0
        self.jump_hex_btn.setEnabled(has_rows)
        self.dissect_btn.setEnabled(has_rows)

    def _get_selected_address(self) -> Optional[int]:
        row = self.map_table.currentRow()
        if row < 0 or row >= len(self.filtered_blocks):
            return None
        return self.filtered_blocks[row].start

    def _jump_selected_to_hex(self):
        addr = self._get_selected_address()
        if addr is not None:
            self.jump_to_hex.emit(addr)

    def _dissect_selected_region(self):
        addr = self._get_selected_address()
        if addr is not None:
            self.jump_to_struct.emit(addr)
