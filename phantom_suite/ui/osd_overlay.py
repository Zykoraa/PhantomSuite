"""
PhantomSuite On-Screen Display (OSD) Overlay
Lightweight, translucent floating HUD window displaying pinned memory values,
speedhack multipliers, and process telemetry over games and applications.
"""

from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QSlider
)
from PySide6.QtCore import Qt, QPoint, QTimer
from phantom_suite.core.memory_engine import MemoryEngine
from phantom_suite.core.speedhack_controller import SpeedhackController


class OsdOverlay(QWidget):
    """Floating Cyberpunk HUD Overlay Widget."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(320, 220)

        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.pinned_entries: List[Dict[str, Any]] = [] # address, type, desc
        self._drag_pos: Optional[QPoint] = None

        self._timer = QTimer(self)
        self._timer.setInterval(100) # 100ms live HUD refresh
        self._timer.timeout.connect(self._on_timer_refresh)

        self._init_ui()

    def set_target(self, pid: int, name: str):
        self.target_pid = pid
        self.target_name = name
        self.title_lbl.setText(f"HUD // [{pid}] {name}")
        self._timer.start()

    def clear_target(self):
        self.target_pid = None
        self.target_name = ""
        self.title_lbl.setText("HUD // NO TARGET")
        self._timer.stop()
        self.values_table.setRowCount(0)

    def set_pinned_entries(self, entries: List[Dict[str, Any]]):
        """Updates list of addresses displayed on the HUD."""
        self.pinned_entries = entries
        self.values_table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            d_item = QTableWidgetItem(e.get("desc", "Variable"))
            d_item.setForeground(Qt.white)
            v_item = QTableWidgetItem("...")
            v_item.setForeground(Qt.cyan)
            self.values_table.setItem(row, 0, d_item)
            self.values_table.setItem(row, 1, v_item)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Container Frame
        self.frame = QFrame()
        self.frame.setStyleSheet(
            "background-color: rgba(10, 16, 26, 0.88); "
            "border: 1px solid #00f0ff; "
            "border-radius: 8px;"
        )
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(10, 8, 10, 8)
        frame_layout.setSpacing(6)

        # Title / Drag Bar
        title_bar = QHBoxLayout()
        self.title_lbl = QLabel("HUD // NO TARGET")
        self.title_lbl.setStyleSheet("color: #00f0ff; font-weight: bold; font-size: 12px; letter-spacing: 1px;")

        self.speed_badge = QLabel("1.0x")
        self.speed_badge.setStyleSheet("color: #ff007f; font-weight: bold; font-size: 11px;")

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(18, 18)
        close_btn.setStyleSheet(
            "background-color: transparent; color: #7d90b3; border: none; font-size: 12px; font-weight: bold;"
        )
        close_btn.clicked.connect(self.hide)

        title_bar.addWidget(self.title_lbl)
        title_bar.addStretch()
        title_bar.addWidget(self.speed_badge)
        title_bar.addSpacing(6)
        title_bar.addWidget(close_btn)
        frame_layout.addLayout(title_bar)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #1c2638; max-height: 1px;")
        frame_layout.addWidget(line)

        # Values Table
        self.values_table = QTableWidget()
        self.values_table.setColumnCount(2)
        self.values_table.setHorizontalHeaderLabels(["Pinned Watch", "Live Value"])
        self.values_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.values_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.values_table.verticalHeader().setVisible(False)
        self.values_table.setShowGrid(False)
        self.values_table.setStyleSheet(
            "background-color: transparent; border: none; font-family: monospace; font-size: 12px;"
        )
        frame_layout.addWidget(self.values_table, 1)

        # Opacity slider
        bot_bar = QHBoxLayout()
        op_lbl = QLabel("Opacity:")
        op_lbl.setStyleSheet("color: #7d90b3; font-size: 10px;")

        self.op_slider = QSlider(Qt.Horizontal)
        self.op_slider.setRange(30, 100)
        self.op_slider.setValue(88)
        self.op_slider.setFixedHeight(12)
        self.op_slider.valueChanged.connect(self._on_opacity_changed)

        bot_bar.addWidget(op_lbl)
        bot_bar.addWidget(self.op_slider)
        frame_layout.addLayout(bot_bar)

        main_layout.addWidget(self.frame)

    def _on_opacity_changed(self, val: int):
        alpha = val / 100.0
        self.frame.setStyleSheet(
            f"background-color: rgba(10, 16, 26, {alpha:.2f}); "
            f"border: 1px solid #00f0ff; "
            f"border-radius: 8px;"
        )

    def _on_timer_refresh(self):
        if not self.target_pid or not self.isVisible():
            return

        # Update speedhack badge
        is_inj = SpeedhackController.is_injected(self.target_pid)
        if is_inj:
            spd, en = SpeedhackController.get_speed(self.target_pid)
            self.speed_badge.setText(f"{spd:.1f}x {'ON' if en else 'OFF'}")
        else:
            self.speed_badge.setText("")

        # Update pinned values
        for row, entry in enumerate(self.pinned_entries):
            addr = entry.get("address", 0)
            v_type = entry.get("type", "int32")
            if addr > 0:
                val = MemoryEngine.read_typed(self.target_pid, addr, v_type)
                val_str = f"{val:.2f}" if isinstance(val, float) else str(val if val is not None else "?")
                item = self.values_table.item(row, 1)
                if item:
                    item.setText(val_str)

    # Window Dragging support for frameless overlay
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
