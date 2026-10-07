"""
PhantomSuite Command Palette (Ctrl+K / Ctrl+P)
Instant keyboard-driven fuzzy search launcher for tabs, tools, actions, and addresses.
"""

from typing import List, Dict, Any, Callable, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QWidget, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QFont


class CommandAction:
    def __init__(
        self,
        action_id: str,
        title: str,
        category: str,
        description: str = "",
        shortcut: str = "",
        callback: Optional[Callable[[], None]] = None
    ):
        self.action_id = action_id
        self.title = title
        self.category = category
        self.description = description
        self.shortcut = shortcut
        self.callback = callback


class CommandPaletteDialog(QDialog):
    """Floating modal command palette for instant navigation and tool execution."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(560)
        self.setFixedHeight(380)

        self.actions: List[CommandAction] = []
        self.filtered_actions: List[CommandAction] = []
        self.address_jump_callback: Optional[Callable[[str, int], None]] = None

        self._init_ui()

    def _init_ui(self):
        container = QFrame(self)
        container.setObjectName("palette_container")
        container.setGeometry(0, 0, 560, 380)
        container.setStyleSheet(
            "#palette_container {"
            "  background-color: #0b0e14;"
            "  border: 1px solid #00f0ff;"
            "  border-radius: 8px;"
            "}"
        )

        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header Search Box
        search_box = QHBoxLayout()
        search_box.setSpacing(8)

        icon_lbl = QLabel("⌘")
        icon_lbl.setStyleSheet("color: #00f0ff; font-size: 16px; font-weight: bold;")
        search_box.addWidget(icon_lbl)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type a command, tool, action, or address (e.g. 'scan', 'attach', '0x1000')...")
        self.search_input.setStyleSheet(
            "QLineEdit {"
            "  background-color: #121824;"
            "  color: #ffffff;"
            "  border: 1px solid #23314d;"
            "  border-radius: 4px;"
            "  padding: 8px 12px;"
            "  font-size: 14px;"
            "}"
            "QLineEdit:focus {"
            "  border: 1px solid #00f0ff;"
            "}"
        )
        self.search_input.textChanged.connect(self._on_text_changed)
        search_box.addWidget(self.search_input)

        hint_lbl = QLabel("[ESC to Close]")
        hint_lbl.setStyleSheet("color: #5d6f8f; font-size: 11px;")
        search_box.addWidget(hint_lbl)

        layout.addLayout(search_box)

        # Actions List
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget {"
            "  background-color: #0e121a;"
            "  border: 1px solid #1a2233;"
            "  border-radius: 4px;"
            "  padding: 4px;"
            "}"
            "QListWidget::item {"
            "  padding: 8px 10px;"
            "  border-radius: 4px;"
            "  margin-bottom: 2px;"
            "}"
            "QListWidget::item:selected {"
            "  background-color: #16253b;"
            "  border-left: 3px solid #00f0ff;"
            "  color: #00f0ff;"
            "}"
            "QListWidget::item:hover:!selected {"
            "  background-color: #121824;"
            "}"
        )
        self.list_widget.itemActivated.connect(self._on_item_activated)
        self.list_widget.itemClicked.connect(self._on_item_activated)
        layout.addWidget(self.list_widget)

    def register_action(self, action: CommandAction):
        self.actions.append(action)

    def register_actions(self, actions: List[CommandAction]):
        self.actions.extend(actions)

    def set_address_jump_callback(self, cb: Callable[[str, int], None]):
        """Callback(target_tab: 'hex' | 'struct', address: int)"""
        self.address_jump_callback = cb

    def show_palette(self):
        """Shows palette, resets input, centers over parent."""
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + 80
            self.move(x, y)

        self.search_input.clear()
        self.search_input.setFocus()
        self._filter_actions("")
        self.exec_()

    def _on_text_changed(self, text: str):
        self._filter_actions(text.strip())

    def _filter_actions(self, query: str):
        self.list_widget.clear()
        self.filtered_actions = []

        q_lower = query.lower()

        # Check if query is a hex or decimal memory address
        addr_val: Optional[int] = None
        if query.startswith("0x") or query.startswith("0X"):
            try:
                addr_val = int(query, 16)
            except ValueError:
                pass
        elif query.isdigit() and len(query) >= 4:
            try:
                addr_val = int(query)
            except ValueError:
                pass

        if addr_val is not None:
            # Add dynamic address jump actions at top
            hex_str = f"0x{addr_val:X}"
            hex_act = CommandAction(
                action_id=f"jump_hex_{addr_val}",
                title=f"🧬 Jump to Hex Editor at {hex_str}",
                category="JUMP",
                description=f"Inspect memory bytes and disassembly at {hex_str}",
                callback=lambda a=addr_val: self.address_jump_callback("hex", a) if self.address_jump_callback else None
            )
            struct_act = CommandAction(
                action_id=f"jump_struct_{addr_val}",
                title=f"🔬 Dissect Struct at {hex_str}",
                category="JUMP",
                description=f"Heuristically dissect memory structure at {hex_str}",
                callback=lambda a=addr_val: self.address_jump_callback("struct", a) if self.address_jump_callback else None
            )
            ptr_act = CommandAction(
                action_id=f"jump_ptr_{addr_val}",
                title=f"⚡ SMT Pointer Solver & Synthesizer at {hex_str}",
                category="JUMP",
                description=f"Synthesize Z3 pointer chains & C++ struct for {hex_str}",
                callback=lambda a=addr_val: self.address_jump_callback("pointer", a) if self.address_jump_callback else None
            )
            self._add_list_item(hex_act)
            self._add_list_item(struct_act)
            self._add_list_item(ptr_act)
            self.filtered_actions.extend([hex_act, struct_act, ptr_act])

        # Filter registered actions
        for act in self.actions:
            match = False
            if not q_lower:
                match = True
            elif (
                q_lower in act.title.lower()
                or q_lower in act.category.lower()
                or q_lower in act.description.lower()
            ):
                match = True

            if match:
                self._add_list_item(act)
                self.filtered_actions.append(act)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _add_list_item(self, act: CommandAction):
        item = QListWidgetItem()
        shortcut_text = f"[{act.shortcut}]" if act.shortcut else ""
        item.setText(f"{act.title}   —   {act.category}  {shortcut_text}\n    {act.description}")
        self.list_widget.addItem(item)

    def _on_item_activated(self, item: QListWidgetItem):
        row = self.list_widget.row(item)
        if 0 <= row < len(self.filtered_actions):
            act = self.filtered_actions[row]
            self.accept()
            if act.callback:
                act.callback()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_Escape:
            self.reject()
        elif key in (Qt.Key_Down, Qt.Key_Up):
            curr = self.list_widget.currentRow()
            total = self.list_widget.count()
            if total > 0:
                if key == Qt.Key_Down:
                    next_row = (curr + 1) % total
                else:
                    next_row = (curr - 1 + total) % total
                self.list_widget.setCurrentRow(next_row)
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            curr_item = self.list_widget.currentItem()
            if curr_item:
                self._on_item_activated(curr_item)
            elif self.list_widget.count() > 0:
                self._on_item_activated(self.list_widget.item(0))
        else:
            super().keyPressEvent(event)
