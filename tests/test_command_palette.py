"""
Unit tests for PhantomSuite Command Palette.
"""

import unittest
from PySide6.QtWidgets import QApplication
from phantom_suite.ui.command_palette import CommandPaletteDialog, CommandAction

app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class TestCommandPalette(unittest.TestCase):
    def setUp(self):
        self.palette = CommandPaletteDialog()
        self.callback_fired = False

    def _dummy_callback(self):
        self.callback_fired = True

    def test_register_and_filter_actions(self):
        act1 = CommandAction("act1", "Memory Scanner", "NAVIGATION", "Scan memory", "Ctrl+2", self._dummy_callback)
        act2 = CommandAction("act2", "Attach Active Window", "ACTION", "Attach to Hyprland window", "", None)
        self.palette.register_actions([act1, act2])

        # Filter by 'scan'
        self.palette._filter_actions("scan")
        self.assertEqual(len(self.palette.filtered_actions), 1)
        self.assertEqual(self.palette.filtered_actions[0].action_id, "act1")

        # Filter by 'attach'
        self.palette._filter_actions("attach")
        self.assertEqual(len(self.palette.filtered_actions), 1)
        self.assertEqual(self.palette.filtered_actions[0].action_id, "act2")

        # Empty filter returns all
        self.palette._filter_actions("")
        self.assertEqual(len(self.palette.filtered_actions), 2)

    def test_address_jump_detection(self):
        jump_targets = []
        def on_jump(target, addr):
            jump_targets.append((target, addr))

        self.palette.set_address_jump_callback(on_jump)
        self.palette._filter_actions("0x55AFC0A4A080")

        # Should generate 2 address jump actions (hex and struct)
        self.assertGreaterEqual(len(self.palette.filtered_actions), 2)
        hex_act = self.palette.filtered_actions[0]
        self.assertIn("Jump to Hex Editor", hex_act.title)
        self.assertIn("0x55AFC0A4A080", hex_act.title)

        # Execute hex action
        hex_act.callback()
        self.assertEqual(len(jump_targets), 1)
        self.assertEqual(jump_targets[0], ("hex", 0x55AFC0A4A080))

    def test_action_execution(self):
        act = CommandAction("test_act", "Test Action", "TEST", "Desc", "", self._dummy_callback)
        self.palette.register_action(act)
        self.palette._filter_actions("Test")
        self.assertEqual(len(self.palette.filtered_actions), 1)

        # Trigger activation
        item = self.palette.list_widget.item(0)
        self.palette._on_item_activated(item)
        self.assertTrue(self.callback_fired)


if __name__ == "__main__":
    unittest.main()
