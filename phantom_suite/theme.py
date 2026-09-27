"""
PhantomSuite Cyberpunk Dark Theme & Stylesheets
High-contrast neon styling with dark obsidian glass and cyberpunk accents.
"""

CYBERPUNK_QSS = """
/* Global Window & Typography */
QMainWindow, QDialog, QWidget {
    background-color: #0c0e14;
    color: #c5d1eb;
    font-family: 'JetBrains Mono', 'Fira Code', 'DejaVu Sans Mono', monospace;
    font-size: 13px;
    selection-background-color: #00f0ff;
    selection-color: #0c0e14;
}

/* Tab Bar Styling */
QTabWidget::pane {
    border: 1px solid #1f2738;
    background-color: #10141f;
    border-radius: 4px;
    top: -1px;
}

QTabBar::tab {
    background-color: #131824;
    color: #798aa8;
    padding: 8px 18px;
    margin-right: 3px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    border: 1px solid #1c2333;
    border-bottom: none;
    font-weight: bold;
}

QTabBar::tab:selected {
    background-color: #10141f;
    color: #00f0ff;
    border-top: 2px solid #00f0ff;
}

QTabBar::tab:hover:!selected {
    background-color: #192030;
    color: #00d2ff;
}

/* Buttons */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a2233, stop:1 #131926);
    color: #00f0ff;
    border: 1px solid #00f0ff;
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: bold;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #00f0ff;
    color: #0c0e14;
    border: 1px solid #70f7ff;
}

QPushButton:pressed {
    background-color: #00b3bf;
    color: #0c0e14;
}

QPushButton:disabled {
    border: 1px solid #283347;
    color: #4a5770;
    background-color: #10141d;
}

/* Secondary Action Button (Pink/Magenta Accent) */
QPushButton#accent_btn {
    color: #ff007f;
    border: 1px solid #ff007f;
}

QPushButton#accent_btn:hover {
    background-color: #ff007f;
    color: #0c0e14;
}

/* Danger Button (Red/Amber) */
QPushButton#danger_btn {
    color: #ff4757;
    border: 1px solid #ff4757;
}

QPushButton#danger_btn:hover {
    background-color: #ff4757;
    color: #0c0e14;
}

/* Input Fields & Combos */
QLineEdit, QComboBox, QSpinBox {
    background-color: #080a0f;
    border: 1px solid #242e42;
    border-radius: 4px;
    padding: 6px 10px;
    color: #e0e8ff;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #00f0ff;
    background-color: #0a0d14;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #101521;
    border: 1px solid #00f0ff;
    selection-background-color: #00f0ff;
    selection-color: #0c0e14;
    color: #e0e8ff;
}

/* Tables & Grids */
QTableWidget, QTableView {
    background-color: #090b10;
    border: 1px solid #1a2233;
    gridline-color: #161c2b;
    border-radius: 4px;
    color: #c9d6f0;
}

QTableWidget::item {
    padding: 4px 6px;
    border-bottom: 1px solid #121724;
}

QTableWidget::item:selected {
    background-color: #162438;
    color: #00f0ff;
}

QHeaderView::section {
    background-color: #131926;
    color: #7d90b3;
    padding: 6px;
    border: 1px solid #1c2436;
    font-weight: bold;
}

/* Checkboxes */
QCheckBox {
    spacing: 7px;
    color: #b0bfdb;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #2a364d;
    background-color: #0a0d14;
    border-radius: 3px;
}

QCheckBox::indicator:checked {
    background-color: #00f0ff;
    border: 1px solid #00f0ff;
}

/* Progress Bar */
QProgressBar {
    background-color: #0a0d14;
    border: 1px solid #1c2436;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-size: 11px;
    height: 16px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00b3bf, stop:1 #00f0ff);
    border-radius: 3px;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #0c0e14;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #1c2538;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #00f0ff;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Group Boxes & Frames */
QGroupBox {
    border: 1px solid #1c2436;
    border-radius: 5px;
    margin-top: 14px;
    padding-top: 14px;
    font-weight: bold;
    color: #00f0ff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}

/* Status Bar */
QStatusBar {
    background-color: #090b10;
    border-top: 1px solid #161c2b;
    color: #637599;
}
"""
