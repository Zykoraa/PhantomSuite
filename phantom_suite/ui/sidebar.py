"""
PhantomSuite Modern Navigation Sidebar
Collapsible, categorized vertical navigation replacing overflowing tab headers.
"""

from typing import List, Dict, Tuple, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal


class SidebarButton(QPushButton):
    """Custom navigation item with icon, title, shortcut badge, and collapsed mode support."""

    def __init__(self, tool_id: str, icon_str: str, title: str, shortcut: str = "", tab_index: int = 0, parent=None):
        super().__init__(parent)
        self.tool_id = tool_id
        self.icon_str = icon_str
        self.title_str = title
        self.shortcut_str = shortcut
        self.tab_index = tab_index
        self.is_active = False
        self.is_collapsed = False

        self.setCheckable(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(36)
        self._update_display()

    def set_active(self, active: bool):
        self.is_active = active
        self._apply_style()

    def set_collapsed(self, collapsed: bool):
        self.is_collapsed = collapsed
        self._update_display()

    def _update_display(self):
        if self.is_collapsed:
            self.setText(self.icon_str)
            self.setToolTip(f"{self.icon_str} {self.title_str} ({self.shortcut_str})" if self.shortcut_str else f"{self.icon_str} {self.title_str}")
        else:
            sc_hint = f" [{self.shortcut_str}]" if self.shortcut_str else ""
            self.setText(f" {self.icon_str}  {self.title_str}{sc_hint}")
            self.setToolTip("")
        self._apply_style()

    def _apply_style(self):
        if self.is_active:
            self.setStyleSheet(
                "QPushButton {"
                "  background-color: #122438;"
                "  color: #00f0ff;"
                "  border: 1px solid #00f0ff;"
                "  border-left: 4px solid #00f0ff;"
                "  border-radius: 4px;"
                "  text-align: " + ("center;" if self.is_collapsed else "left;") +
                "  font-weight: bold;"
                "  padding: 4px 8px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QPushButton {"
                "  background-color: transparent;"
                "  color: #8fa0c0;"
                "  border: 1px solid transparent;"
                "  border-radius: 4px;"
                "  text-align: " + ("center;" if self.is_collapsed else "left;") +
                "  padding: 4px 8px;"
                "}"
                "QPushButton:hover {"
                "  background-color: #162033;"
                "  color: #00f0ff;"
                "  border: 1px solid #23344f;"
                "}"
            )


class SidebarWidget(QWidget):
    """Categorized collapsible navigation sidebar."""

    tab_requested = Signal(int)
    palette_requested = Signal()
    shortcuts_requested = Signal()

    GROUPS = [
        ("DASHBOARD", [
            ("welcome", "🚀", "Mission Control", "Ctrl+0", 13),
        ]),
        ("TARGET & SYSTEM", [
            ("process", "⚡", "Processes & Windows", "Ctrl+1", 0),
            ("threads", "🧵", "Threads & Affinity", "", 11),
            ("handles", "🌐", "Sockets & Handles", "", 12),
        ]),
        ("MEMORY & CHEATS", [
            ("scanner", "🔍", "Memory Scanner", "Ctrl+2", 1),
            ("snapshot", "📸", "Snapshot Diff", "Ctrl+3", 6),
            ("treemap", "🗺️", "Memory Treemap", "Ctrl+7", 7),
        ]),
        ("REVERSING & DISSECT", [
            ("hex", "🧬", "Hex & Disasm", "Ctrl+4", 3),
            ("struct", "🔬", "Struct Dissector", "Ctrl+5", 4),
            ("symbols", "📦", "ELF Symbols", "Ctrl+6", 5),
            ("deserializer", "🧩", "Data Deserializer", "", 9),
            ("il2cpp", "🎮", "IL2CPP Inspector", "", 14),
            ("micro_emu", "⚙️", "Micro-Emulator", "", 15),
            ("crypto", "🔐", "Entropy & Crypto", "", 16),
        ]),
        ("TOOLBOX & SCRIPTS", [
            ("injector", "💉", ".so Injector", "", 2),
            ("syscalls", "📡", "Syscall Monitor", "Ctrl+8", 8),
            ("console", "🐍", "Python Console", "Ctrl+9", 10),
        ]),
    ]

    MODES = {
        "All Tools": None, # All tools visible
        "Game Modding": {"welcome", "process", "scanner", "snapshot", "struct", "il2cpp"},
        "Binary Reversing": {"welcome", "process", "hex", "struct", "symbols", "deserializer", "console", "il2cpp", "micro_emu", "crypto"},
        "System Forensics": {"welcome", "process", "threads", "handles", "syscalls", "treemap"}
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_collapsed = False
        self.buttons: List[SidebarButton] = []
        self.category_labels: List[QLabel] = []
        self.current_tab_index = 0

        self._init_ui()

    def _init_ui(self):
        self.setObjectName("sidebar_root")
        self.setFixedWidth(210)
        self.setStyleSheet(
            "#sidebar_root {"
            "  background-color: #0d111a;"
            "  border-right: 1px solid #1a2233;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(6)

        # Top Bar: Collapse Toggle + Mode Dropdown
        top_bar = QHBoxLayout()
        top_bar.setSpacing(4)

        self.collapse_btn = QPushButton("◀")
        self.collapse_btn.setToolTip("Toggle Sidebar (Ctrl+B)")
        self.collapse_btn.setFixedSize(28, 26)
        self.collapse_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #121824;"
            "  color: #00f0ff;"
            "  border: 1px solid #1c2638;"
            "  border-radius: 4px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover {"
            "  background-color: #00f0ff;"
            "  color: #0c0e14;"
            "}"
        )
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        top_bar.addWidget(self.collapse_btn)

        self.mode_combo = QComboBox()
        for mode in self.MODES.keys():
            self.mode_combo.addItem(mode)
        self.mode_combo.setToolTip("Filter visible tools by workflow mode")
        self.mode_combo.setStyleSheet(
            "QComboBox {"
            "  background-color: #121824;"
            "  color: #00f0ff;"
            "  border: 1px solid #1c2638;"
            "  border-radius: 4px;"
            "  padding: 3px 6px;"
            "  font-size: 11px;"
            "  font-weight: bold;"
            "}"
        )
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        top_bar.addWidget(self.mode_combo, 1)

        layout.addLayout(top_bar)

        # Scrollable Tool Items
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        self.items_layout = QVBoxLayout(scroll_widget)
        self.items_layout.setContentsMargins(0, 4, 0, 4)
        self.items_layout.setSpacing(2)

        # Build categorized tool items
        for cat_title, items in self.GROUPS:
            cat_lbl = QLabel(cat_title)
            cat_lbl.setStyleSheet(
                "color: #4b5d7d; font-size: 10px; font-weight: bold; "
                "letter-spacing: 1px; padding: 6px 4px 2px 4px;"
            )
            self.category_labels.append(cat_lbl)
            self.items_layout.addWidget(cat_lbl)

            for tool_id, icon, title, shortcut, tab_idx in items:
                btn = SidebarButton(tool_id, icon, title, shortcut, tab_idx, self)
                btn.clicked.connect(lambda checked, idx=tab_idx: self._on_btn_clicked(idx))
                self.buttons.append(btn)
                self.items_layout.addWidget(btn)

        self.items_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        # Bottom Utilities: Command Palette & Shortcuts
        bottom_bar = QVBoxLayout()
        bottom_bar.setSpacing(4)

        self.palette_btn = QPushButton("⌘ Command Palette")
        self.palette_btn.setToolTip("Open Command Palette (Ctrl+K)")
        self.palette_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #121a28;"
            "  color: #00f0ff;"
            "  border: 1px solid #1f304d;"
            "  border-radius: 4px;"
            "  padding: 5px 8px;"
            "  font-size: 11px;"
            "  font-weight: bold;"
            "}"
            "QPushButton:hover {"
            "  background-color: #00f0ff;"
            "  color: #0b0e14;"
            "}"
        )
        self.palette_btn.clicked.connect(self.palette_requested.emit)
        bottom_bar.addWidget(self.palette_btn)

        self.shortcuts_btn = QPushButton("⌨ Shortcuts [?]")
        self.shortcuts_btn.setToolTip("View keyboard shortcuts and cheat sheet (F1 or ?)")
        self.shortcuts_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: transparent;"
            "  color: #5d6f8f;"
            "  border: 1px solid transparent;"
            "  border-radius: 4px;"
            "  padding: 4px;"
            "  font-size: 11px;"
            "}"
            "QPushButton:hover {"
            "  color: #00f0ff;"
            "}"
        )
        self.shortcuts_btn.clicked.connect(self.shortcuts_requested.emit)
        bottom_bar.addWidget(self.shortcuts_btn)

        layout.addLayout(bottom_bar)

        # Highlight default tab (0)
        self.set_active_tab(0)

    def toggle_collapsed(self):
        self.is_collapsed = not self.is_collapsed
        self.setFixedWidth(54 if self.is_collapsed else 210)
        self.collapse_btn.setText("▶" if self.is_collapsed else "◀")
        self.mode_combo.setVisible(not self.is_collapsed)
        self.palette_btn.setText("⌘" if self.is_collapsed else "⌘ Command Palette")
        self.shortcuts_btn.setText("⌨" if self.is_collapsed else "⌨ Shortcuts [?]")

        for lbl in self.category_labels:
            lbl.setVisible(not self.is_collapsed)

        for btn in self.buttons:
            btn.set_collapsed(self.is_collapsed)

    def _on_btn_clicked(self, tab_idx: int):
        self.set_active_tab(tab_idx)
        self.tab_requested.emit(tab_idx)

    def set_active_tab(self, tab_idx: int):
        self.current_tab_index = tab_idx
        for btn in self.buttons:
            btn.set_active(btn.tab_index == tab_idx)

    def _on_mode_changed(self, mode_name: str):
        allowed = self.MODES.get(mode_name)
        for btn in self.buttons:
            if allowed is None:
                btn.setVisible(True)
            else:
                btn.setVisible(btn.tool_id in allowed)
