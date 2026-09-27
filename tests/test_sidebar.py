"""
Unit tests for PhantomSuite Modern Navigation Sidebar.
"""

import os
import unittest
from PySide6.QtWidgets import QApplication
from phantom_suite.ui.sidebar import SidebarWidget

# Ensure single QApplication exists for headless test
app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class TestSidebar(unittest.TestCase):
    def setUp(self):
        self.sidebar = SidebarWidget()

    def test_sidebar_initialization(self):
        self.assertEqual(self.sidebar.width(), 210)
        self.assertFalse(self.sidebar.is_collapsed)
        self.assertGreater(len(self.sidebar.buttons), 10)
        self.assertEqual(self.sidebar.current_tab_index, 0)

    def test_toggle_collapsed(self):
        # Collapse
        self.sidebar.toggle_collapsed()
        self.assertTrue(self.sidebar.is_collapsed)
        self.assertEqual(self.sidebar.width(), 54)
        self.assertEqual(self.sidebar.collapse_btn.text(), "▶")

        # Expand
        self.sidebar.toggle_collapsed()
        self.assertFalse(self.sidebar.is_collapsed)
        self.assertEqual(self.sidebar.width(), 210)
        self.assertEqual(self.sidebar.collapse_btn.text(), "◀")

    def test_set_active_tab(self):
        self.sidebar.set_active_tab(3) # Hex tab
        self.assertEqual(self.sidebar.current_tab_index, 3)

        hex_btn = next((b for b in self.sidebar.buttons if b.tab_index == 3), None)
        self.assertIsNotNone(hex_btn)
        self.assertTrue(hex_btn.is_active)

        # Other button should be inactive
        scan_btn = next((b for b in self.sidebar.buttons if b.tab_index == 1), None)
        self.assertIsNotNone(scan_btn)
        self.assertFalse(scan_btn.is_active)

    def test_mode_filtering(self):
        # Switch to Game Modding mode
        self.sidebar._on_mode_changed("Game Modding")

        scanner_btn = next(b for b in self.sidebar.buttons if b.tool_id == "scanner")
        syscall_btn = next(b for b in self.sidebar.buttons if b.tool_id == "syscalls")

        self.assertFalse(scanner_btn.isHidden())
        self.assertTrue(syscall_btn.isHidden())

        # Switch back to All Tools
        self.sidebar._on_mode_changed("All Tools")
        self.assertFalse(syscall_btn.isHidden())


if __name__ == "__main__":
    unittest.main()
