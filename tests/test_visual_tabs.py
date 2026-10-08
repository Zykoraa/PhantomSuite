"""
Unit tests for PhantomSuite Visual RE Cockpit Tabs:
- Il2CppTab (Unity IL2CPP metadata & klass inspector)
- MicroEmulatorTab (sandboxed x86_64 micro-execution cockpit)
- CryptoTab (Shannon entropy spectrum & cryptographic primitive scanner)
- MainWindow tab navigation & lifecycle integration
"""

import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from phantom_suite.ui.il2cpp_tab import Il2CppTab
from phantom_suite.ui.micro_emulator_tab import MicroEmulatorTab
from phantom_suite.ui.crypto_tab import CryptoTab
from phantom_suite.ui.main_window import MainWindow
from phantom_suite.ui.sidebar import SidebarWidget
from phantom_suite.core.il2cpp_inspector import Il2CppClassDef, Il2CppFieldDef, Il2CppMethodDef
from phantom_suite.core.entropy_crypto_scanner import EntropyBlock, CryptoMatch
from phantom_suite.core.micro_emulator import MicroEmulator

# Ensure single offscreen QApplication instance
app = QApplication.instance() or QApplication(["-platform", "offscreen"])


class TestVisualTabs(unittest.TestCase):
    """Verifies UI component behavior, data population, lifecycle, and signal dispatch."""

    def setUp(self):
        self.il2cpp_tab = Il2CppTab()
        self.micro_emu_tab = MicroEmulatorTab()
        self.crypto_tab = CryptoTab()

    def test_il2cpp_tab_lifecycle_and_signals(self):
        # 1. Default state
        self.assertIsNone(self.il2cpp_tab.target_pid)
        self.assertFalse(self.il2cpp_tab.inspect_btn.isEnabled())

        # 2. Attach target
        self.il2cpp_tab.set_target(1337, "UnityGame.x86_64")
        self.assertEqual(self.il2cpp_tab.target_pid, 1337)
        self.assertTrue(self.il2cpp_tab.inspect_btn.isEnabled())
        self.assertIn("1337", self.il2cpp_tab.target_lbl.text())

        # 3. Populate synthetic class
        fields = [
            Il2CppFieldDef("health", "System.Int32", 0x20, is_static=False),
            Il2CppFieldDef("speed", "System.Single", 0x24, is_static=False),
            Il2CppFieldDef("instanceCount", "System.Int32", 0x00, is_static=True),
        ]
        methods = [
            Il2CppMethodDef("TakeDamage", method_pointer=0x140010000, return_type="System.Void", param_count=1),
            Il2CppMethodDef("Update", method_pointer=0x140010050, return_type="System.Void", param_count=0),
        ]
        klass = Il2CppClassDef(
            klass_address=0x55550000,
            name="PlayerController",
            namespace="Game.Entities",
            full_name="Game.Entities.PlayerController",
            instance_size=0x48,
            fields=fields,
            methods=methods
        )
        self.il2cpp_tab._populate_class_view(klass)

        self.assertEqual(self.il2cpp_tab.fields_table.rowCount(), 3)
        self.assertEqual(self.il2cpp_tab.methods_table.rowCount(), 2)
        self.assertIn("PlayerController", self.il2cpp_tab.code_preview.toPlainText())

        # 4. Filter testing
        self.il2cpp_tab.filter_input.setText("health")
        self.assertTrue(self.il2cpp_tab.fields_table.isRowHidden(0))   # instanceCount (offset 0) is hidden
        self.assertFalse(self.il2cpp_tab.fields_table.isRowHidden(1))  # health (offset 0x20) is visible

        # 5. Signal emission testing
        jumps = []
        cheats = []
        self.il2cpp_tab.jump_to_hex.connect(lambda a: jumps.append(a))
        self.il2cpp_tab.add_to_cheat_table.connect(lambda a, t, d: cheats.append((a, t, d)))

        self.il2cpp_tab.jump_to_hex.emit(0x140010000)
        self.assertEqual(jumps, [0x140010000])

        self.il2cpp_tab.add_to_cheat_table.emit(0x55550020, "int32", "Player_health")
        self.assertEqual(cheats, [(0x55550020, "int32", "Player_health")])

        # 6. Clear target
        self.il2cpp_tab.clear_target()
        self.assertIsNone(self.il2cpp_tab.target_pid)
        self.assertEqual(self.il2cpp_tab.fields_table.rowCount(), 0)

    def test_micro_emulator_tab_stepping_and_snapshots(self):
        # 1. Default state
        self.assertFalse(self.micro_emu_tab.step_btn.isEnabled())
        self.assertFalse(self.micro_emu_tab.run_btn.isEnabled())

        # 2. Initialize CPU at 0x401000
        self.micro_emu_tab.addr_input.setText("0x401000")
        self.micro_emu_tab._init_or_reset_emulator()

        self.assertIsNotNone(self.micro_emu_tab.emulator)
        self.assertEqual(self.micro_emu_tab.emulator.get_reg("rip"), 0x401000)
        self.assertTrue(self.micro_emu_tab.step_btn.isEnabled())
        self.assertTrue(self.micro_emu_tab.run_btn.isEnabled())

        # 3. Write instruction bytes into emulator shadow memory:
        # mov rax, 0x1234; add rax, 0x10; ret
        # 48 c7 c0 34 12 00 00  (mov rax, 0x1234)
        # 48 83 c0 10           (add rax, 0x10)
        # c3                    (ret)
        code = b"\x48\xc7\xc0\x34\x12\x00\x00\x48\x83\xc0\x10\xc3"
        self.micro_emu_tab.emulator.write_mem(0x401000, code)

        # 4. Step 1 (mov rax, 0x1234)
        self.micro_emu_tab._step_instruction()
        self.assertEqual(self.micro_emu_tab.emulator.get_reg("rax"), 0x1234)
        self.assertEqual(self.micro_emu_tab.trace_table.rowCount(), 1)

        # 5. Test Register Edit in GUI
        self.micro_emu_tab.reg_table.item(0, 1).setText("0x0000000000009999")
        self.micro_emu_tab._on_register_edited(0, 1)
        self.assertEqual(self.micro_emu_tab.emulator.get_reg("rax"), 0x9999)

        # 6. Snapshot & Rollback
        self.micro_emu_tab._save_snapshot()
        self.assertEqual(self.micro_emu_tab.snapshot_depth, 1)
        self.assertTrue(self.micro_emu_tab.rollback_btn.isEnabled())

        self.micro_emu_tab.emulator.set_reg("rax", 0xDEADBEEF)
        self.assertEqual(self.micro_emu_tab.emulator.get_reg("rax"), 0xDEADBEEF)

        self.micro_emu_tab._rollback_snapshot()
        self.assertEqual(self.micro_emu_tab.emulator.get_reg("rax"), 0x9999)
        self.assertEqual(self.micro_emu_tab.snapshot_depth, 0)
        self.assertFalse(self.micro_emu_tab.rollback_btn.isEnabled())

        # 7. Step remaining to ret
        self.micro_emu_tab._run_execution()
        self.assertGreater(self.micro_emu_tab.trace_table.rowCount(), 1)

        # 8. Reset & Clear
        self.micro_emu_tab.clear_target()
        self.assertFalse(self.micro_emu_tab.step_btn.isEnabled())

    def test_crypto_tab_rendering_and_filtering(self):
        # 1. Default state
        self.assertFalse(self.crypto_tab.scan_proc_btn.isEnabled())

        # 2. Attach target
        self.crypto_tab.set_target(4242, "TargetCryptoApp")
        self.assertTrue(self.crypto_tab.scan_proc_btn.isEnabled())

        # 3. Inject synthetic crypto & entropy results
        matches = [
            CryptoMatch("AES", "AES Forward S-Box", 0x7FFF1000, 1.0, "AES substitution table", "637C777BF26B6FC5"),
            CryptoMatch("SHA-256", "SHA-256 H0-H7", 0x7FFF2000, 1.0, "SHA initial vector", "6A09E667BB67AE85"),
        ]
        blocks = [
            EntropyBlock(0x7FFF5000, 4096, 7.92, "Encrypted/Packed", True),
            EntropyBlock(0x7FFF6000, 4096, 5.45, "Code/Structured", False),
            EntropyBlock(0x7FFF7000, 4096, 2.10, "Sparse/Text", False),
        ]

        self.crypto_tab.cached_crypto_matches = matches
        self.crypto_tab.cached_entropy_blocks = blocks
        self.crypto_tab._render_results()

        self.assertEqual(self.crypto_tab.crypto_table.rowCount(), 2)
        # Default min_entropy is 7.5, so only the block with 7.92 appears
        self.assertEqual(self.crypto_tab.entropy_table.rowCount(), 1)

        # 4. Lower min entropy threshold
        self.crypto_tab.entropy_spin.setValue(1.0)
        self.assertEqual(self.crypto_tab.entropy_table.rowCount(), 3)

        # 5. Filter by text "AES"
        self.crypto_tab.filter_input.setText("AES")
        self.assertEqual(self.crypto_tab.crypto_table.rowCount(), 1)

        # 6. Double click signal propagation
        jumps = []
        self.crypto_tab.jump_to_hex.connect(lambda a: jumps.append(a))
        item = self.crypto_tab.crypto_table.item(0, 2)
        self.crypto_tab._on_crypto_double_clicked(item)
        self.assertEqual(jumps, [0x7FFF1000])

        # 7. Clear
        self.crypto_tab.clear_target()
        self.assertEqual(self.crypto_tab.crypto_table.rowCount(), 0)
        self.assertEqual(self.crypto_tab.entropy_table.rowCount(), 0)

    def test_main_window_integration(self):
        win = MainWindow()
        # Verify 17 total tabs
        self.assertEqual(win.tabs.count(), 17)

        # Check dedicated tab indices
        self.assertIs(win.tabs.widget(14), win.il2cpp_tab)
        self.assertIs(win.tabs.widget(15), win.micro_emu_tab)
        self.assertIs(win.tabs.widget(16), win.crypto_tab)

        # Check navigation
        win.switch_to_tab(14)
        self.assertEqual(win.tabs.currentIndex(), 14)
        win.switch_to_tab(15)
        self.assertEqual(win.tabs.currentIndex(), 15)
        win.switch_to_tab(16)
        self.assertEqual(win.tabs.currentIndex(), 16)

        # Check lifecycle propagation
        win.attach_target(9999, "ProcTest")
        self.assertEqual(win.il2cpp_tab.target_pid, 9999)
        self.assertEqual(win.micro_emu_tab.target_pid, 9999)
        self.assertEqual(win.crypto_tab.target_pid, 9999)

        win.detach_target()
        self.assertIsNone(win.il2cpp_tab.target_pid)
        self.assertIsNone(win.micro_emu_tab.target_pid)
        self.assertIsNone(win.crypto_tab.target_pid)

        # Check sidebar buttons
        sidebar_tools = [b.tool_id for b in win.sidebar.buttons]
        self.assertIn("il2cpp", sidebar_tools)
        self.assertIn("micro_emu", sidebar_tools)
        self.assertIn("crypto", sidebar_tools)

        win.close()


if __name__ == "__main__":
    unittest.main()
