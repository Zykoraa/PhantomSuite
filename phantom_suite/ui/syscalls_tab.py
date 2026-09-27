"""
PhantomSuite Syscall Telemetry Monitor Tab
Real-time process system call streaming, filtering, search, and telemetry export.
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QCheckBox, QMessageBox, QGroupBox, QAbstractItemView,
    QFileDialog, QApplication
)
from PySide6.QtCore import Qt, QObject, Signal
from phantom_suite.core.syscall_tracer import SyscallTracer, SyscallEvent


class SyscallSignalBridge(QObject):
    event_received = Signal(object) # SyscallEvent


class SyscallsTab(QWidget):
    """Real-Time Syscall Telemetry Monitor Tab."""

    CATEGORY_COLORS = {
        "FILE": "#00f0ff",
        "NET": "#00ff9d",
        "MEM": "#ffb700",
        "PROC": "#ff007f",
        "IPC": "#b537f2",
        "OTHER": "#7d90b3"
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_pid: Optional[int] = None
        self.target_name: str = ""
        self.tracer = SyscallTracer()
        self.bridge = SyscallSignalBridge()
        self.bridge.event_received.connect(self._on_event_received)

        self.events: List[SyscallEvent] = []
        self.start_time: float = 0.0

        self._init_ui()

    def set_target(self, pid: int, name: str):
        if self.tracer.is_tracing:
            self.tracer.stop()

        self.target_pid = pid
        self.target_name = name
        self.target_lbl.setText(f"Target: [{pid}] {name}")
        self.target_lbl.setStyleSheet("color: #00f0ff; font-weight: bold;")
        self.toggle_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.toggle_btn.setText("▶ Start Tracing")
        self.toggle_btn.setStyleSheet("")

    def clear_target(self):
        if self.tracer.is_tracing:
            self.tracer.stop()

        self.target_pid = None
        self.target_name = ""
        self.target_lbl.setText("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.toggle_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.toggle_btn.setText("▶ Start Tracing")
        self.toggle_btn.setStyleSheet("")
        self.events.clear()
        self.syscall_table.setRowCount(0)
        self.count_lbl.setText("0 events")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target Banner
        banner_layout = QHBoxLayout()
        self.target_lbl = QLabel("No Target Attached")
        self.target_lbl.setStyleSheet("color: #7d90b3; font-style: italic;")
        self.count_lbl = QLabel("0 events")
        self.count_lbl.setStyleSheet("color: #7d90b3;")
        banner_layout.addWidget(self.target_lbl)
        banner_layout.addStretch()
        banner_layout.addWidget(self.count_lbl)
        layout.addLayout(banner_layout)

        # Controls Bar
        ctrl_group = QGroupBox("Syscall Stream Controls & Filters")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(10)

        self.toggle_btn = QPushButton("▶ Start Tracing")
        self.toggle_btn.setObjectName("accent_btn")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self._toggle_tracing)

        self.clear_btn = QPushButton("🗑 Clear")
        self.clear_btn.setEnabled(False)
        self.clear_btn.clicked.connect(self._clear_events)

        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet("color: #7d90b3;")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter syscall, path, IP, or arg...")
        self.filter_input.textChanged.connect(self._refresh_table)

        cat_lbl = QLabel("Category:")
        cat_lbl.setStyleSheet("color: #7d90b3;")
        self.cat_combo = QComboBox()
        self.cat_combo.addItems([
            "ALL Categories",
            "FILE (I/O & Descriptors)",
            "NET (Sockets & Network)",
            "MEM (Alloc & Protect)",
            "PROC (Threads & Execution)",
            "IPC (Pipes & Poll)"
        ])
        self.cat_combo.currentIndexChanged.connect(self._refresh_table)

        self.autoscroll_chk = QCheckBox("Auto-Scroll")
        self.autoscroll_chk.setChecked(True)

        self.export_btn = QPushButton("💾 Export Log")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_log)

        ctrl_layout.addWidget(self.toggle_btn)
        ctrl_layout.addWidget(self.clear_btn)
        ctrl_layout.addWidget(filter_lbl)
        ctrl_layout.addWidget(self.filter_input, 2)
        ctrl_layout.addWidget(cat_lbl)
        ctrl_layout.addWidget(self.cat_combo)
        ctrl_layout.addWidget(self.autoscroll_chk)
        ctrl_layout.addWidget(self.export_btn)
        layout.addWidget(ctrl_group)

        # Syscall Stream Table
        self.syscall_table = QTableWidget()
        self.syscall_table.setColumnCount(7)
        self.syscall_table.setHorizontalHeaderLabels([
            "Time (rel)", "PID/TID", "Category", "Syscall", "Arguments", "Result", "Duration"
        ])
        self.syscall_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.syscall_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.syscall_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.syscall_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.syscall_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.syscall_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.syscall_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.syscall_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.syscall_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.syscall_table.setStyleSheet("font-family: monospace; font-size: 13px;")
        self.syscall_table.doubleClicked.connect(self._copy_selected_raw)
        layout.addWidget(self.syscall_table, 1)

    def _toggle_tracing(self):
        if not self.target_pid:
            return

        if not self.tracer.is_tracing:
            self.start_time = self.start_time or time.time()
            ok = self.tracer.start(self.target_pid, lambda ev: self.bridge.event_received.emit(ev))
            if ok:
                self.toggle_btn.setText("⏹ Stop Tracing")
                self.toggle_btn.setStyleSheet("color: #ff007f; border-color: #ff007f;")
            else:
                QMessageBox.critical(self, "Trace Failed", "Could not start strace. Please check permissions / ptrace.")
        else:
            self.tracer.stop()
            self.toggle_btn.setText("▶ Start Tracing")
            self.toggle_btn.setStyleSheet("")

    def _clear_events(self):
        self.events.clear()
        self.syscall_table.setRowCount(0)
        self.count_lbl.setText("0 events")

    def _on_event_received(self, event: SyscallEvent):
        # Bound event history to 10,000 items
        if len(self.events) >= 10000:
            self.events.pop(0)

        self.events.append(event)
        self.count_lbl.setText(f"{len(self.events)} events")

        if self._matches_filter(event):
            self._insert_table_row(event)

    def _matches_filter(self, ev: SyscallEvent) -> bool:
        search = self.filter_input.text().strip().lower()
        if search:
            if search not in ev.syscall.lower() and search not in ev.args.lower() and search not in ev.result.lower():
                return False

        cat_sel = self.cat_combo.currentText().split()[0]
        if cat_sel != "ALL" and ev.category != cat_sel:
            return False

        return True

    def _insert_table_row(self, ev: SyscallEvent):
        row = self.syscall_table.rowCount()
        self.syscall_table.insertRow(row)

        rel_time = ev.timestamp - (self.start_time or ev.timestamp)
        time_item = QTableWidgetItem(f"+{rel_time:.4f}s")
        time_item.setForeground(Qt.gray)

        pid_item = QTableWidgetItem(str(ev.pid) if ev.pid > 0 else "-")
        pid_item.setForeground(Qt.yellow)

        cat_color = self.CATEGORY_COLORS.get(ev.category, "#7d90b3")
        cat_item = QTableWidgetItem(ev.category)
        cat_item.setForeground(QColor(cat_color))

        sys_item = QTableWidgetItem(ev.syscall)
        sys_item.setForeground(Qt.cyan)

        args_item = QTableWidgetItem(ev.args)

        res_item = QTableWidgetItem(ev.result)
        if ev.result.startswith("-1"):
            res_item.setForeground(Qt.red)
        else:
            res_item.setForeground(Qt.green)

        dur_item = QTableWidgetItem(f"{ev.duration * 1000:.3f} ms" if ev.duration > 0 else "<0.001 ms")
        dur_item.setForeground(Qt.gray)

        self.syscall_table.setItem(row, 0, time_item)
        self.syscall_table.setItem(row, 1, pid_item)
        self.syscall_table.setItem(row, 2, cat_item)
        self.syscall_table.setItem(row, 3, sys_item)
        self.syscall_table.setItem(row, 4, args_item)
        self.syscall_table.setItem(row, 5, res_item)
        self.syscall_table.setItem(row, 6, dur_item)

        if self.autoscroll_chk.isChecked():
            self.syscall_table.scrollToBottom()

    def _refresh_table(self):
        self.syscall_table.setRowCount(0)
        filtered = [e for e in self.events if self._matches_filter(e)]
        for e in filtered[-500:]: # Keep view fast on refresh
            self._insert_table_row(e)

    def _copy_selected_raw(self):
        row = self.syscall_table.currentRow()
        if row < 0 or row >= len(self.events):
            return
        ev = self.events[row]
        QApplication.clipboard().setText(ev.raw)
        QMessageBox.information(self, "Copied", f"Copied syscall line: {ev.raw}")

    def _export_log(self):
        if not self.events:
            QMessageBox.information(self, "No Events", "No captured syscalls to export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export Syscall Log", "syscalls.csv", "CSV Files (*.csv);;Text (*.txt)")
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Time_Rel,PID,Category,Syscall,Args,Result,Duration\n")
                for e in self.events:
                    rel = e.timestamp - (self.start_time or e.timestamp)
                    clean_args = e.args.replace('"', '""')
                    f.write(f'{rel:.6f},{e.pid},{e.category},{e.syscall},"{clean_args}",{e.result},{e.duration}\n')
            QMessageBox.information(self, "Exported", f"Successfully exported {len(self.events)} events to {path}.")
        except Exception as err:
            QMessageBox.critical(self, "Export Error", str(err))
