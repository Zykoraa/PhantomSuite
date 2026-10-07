"""
PhantomSuite Anti-Debug & PMU Timing Anomaly Dialog
Visualizes ptrace telemetry, kernel wchan status, and RDTSC timing delta loops.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from phantom_suite.core.pmu_profiler import PmuProfiler, TimingProfileReport, AntiDebugIndicator


class PmuDialog(QDialog):
    """Dialog displaying anti-debug threats, timing loops, and tracer telemetry."""

    def __init__(self, pid: int, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.report: Optional[TimingProfileReport] = None

        self.setWindowTitle(f"Anti-Debug & PMU Profiler // PID: {pid}")
        self.resize(850, 520)
        self._init_ui()
        self._refresh_profile()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Threat Score & Telemetry Header
        header = QHBoxLayout()

        score_lbl = QLabel("Threat Score:")
        score_lbl.setStyleSheet("color: #7d90b3; font-weight: bold;")
        self.score_bar = QProgressBar()
        self.score_bar.setRange(0, 100)
        self.score_bar.setFixedWidth(200)

        self.tracer_lbl = QLabel("TracerPid: 0")
        self.tracer_lbl.setStyleSheet("color: #00ff9d; font-weight: bold;")
        self.wchan_lbl = QLabel("wchan: -")
        self.wchan_lbl.setStyleSheet("color: #7d90b3;")
        self.rdtsc_lbl = QLabel("RDTSC Count: 0")
        self.rdtsc_lbl.setStyleSheet("color: #ffb700;")

        header.addWidget(score_lbl)
        header.addWidget(self.score_bar)
        header.addWidget(self.tracer_lbl)
        header.addWidget(self.wchan_lbl)
        header.addWidget(self.rdtsc_lbl)
        header.addStretch()

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setObjectName("accent_btn")
        refresh_btn.clicked.connect(self._refresh_profile)
        header.addWidget(refresh_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)

        layout.addLayout(header)

        # Indicators Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Category", "Severity", "Description", "Technical Details"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)

    def _refresh_profile(self):
        self.report = PmuProfiler.audit_process(self.pid, scan_executable_memory=True)
        if not self.report:
            QMessageBox.warning(self, "Audit Error", f"Could not inspect PID {self.pid}")
            return

        self.score_bar.setValue(self.report.threat_score)
        if self.report.threat_score < 25:
            bar_color = "#00ff9d" # Low threat
        elif self.report.threat_score < 60:
            bar_color = "#ffb700" # Medium threat
        else:
            bar_color = "#ff0055" # High threat

        self.score_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {bar_color}; }}")

        if self.report.is_ptraced:
            self.tracer_lbl.setText(f"TracerPid: {self.report.tracer_pid} (TRACED)")
            self.tracer_lbl.setStyleSheet("color: #ff0055; font-weight: bold;")
        else:
            self.tracer_lbl.setText("TracerPid: 0 (Clean)")
            self.tracer_lbl.setStyleSheet("color: #00ff9d; font-weight: bold;")

        self.wchan_lbl.setText(f"wchan: {self.report.wchan_state or 'running'}")
        self.rdtsc_lbl.setText(f"RDTSC Count: {self.report.rdtsc_instruction_count}")

        self.table.setRowCount(len(self.report.indicators))
        for row, ind in enumerate(self.report.indicators):
            cat_item = QTableWidgetItem(ind.category)
            cat_item.setForeground(QColor("#00f0ff"))

            sev_item = QTableWidgetItem(ind.severity)
            if ind.severity == "HIGH":
                sev_item.setForeground(QColor("#ff0055"))
            elif ind.severity == "MEDIUM":
                sev_item.setForeground(QColor("#ffb700"))
            else:
                sev_item.setForeground(QColor("#00ff9d"))

            desc_item = QTableWidgetItem(ind.description)
            det_item = QTableWidgetItem(ind.details)

            self.table.setItem(row, 0, cat_item)
            self.table.setItem(row, 1, sev_item)
            self.table.setItem(row, 2, desc_item)
            self.table.setItem(row, 3, det_item)
