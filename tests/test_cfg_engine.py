"""
Automated Unit Tests for PhantomSuite Control Flow Graph (CFG) Engine
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.cfg_engine import CFGEngine, ControlFlowGraph, BasicBlock, BRANCH_INVERSION_OPCODES
from phantom_suite.core.elf_explorer import ElfExplorer


class TestCFGEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid

        # Find main function symbol address
        symbols = ElfExplorer.parse_symbols(target_bin)
        main_sym = next((s for s in symbols if s.name == "main"), None)
        assert main_sym is not None
        
        # Get runtime base
        modules = ElfExplorer.get_loaded_modules(cls.pid)
        target_mod = next((m for m in modules if "test_target" in m.name), None)
        assert target_mod is not None
        cls.main_runtime_addr = target_mod.base_address + main_sym.file_offset

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_capstone_available(self):
        self.assertTrue(CFGEngine.is_available(), "Capstone disassembler should be available")

    def test_build_cfg_from_live_process(self):
        cfg = CFGEngine.build_cfg(self.pid, self.main_runtime_addr, max_bytes=512)
        self.assertIsNotNone(cfg)
        self.assertIsInstance(cfg, ControlFlowGraph)
        self.assertGreater(len(cfg.blocks), 0)
        
        entry_bb = cfg.get_entry_block()
        self.assertIsNotNone(entry_bb)
        self.assertGreater(len(entry_bb.instructions), 0)

        # Verify layout coordinates computed
        for bb in cfg.blocks.values():
            self.assertIsInstance(bb.x, float)
            self.assertIsInstance(bb.y, float)

    def test_branch_inversion_table(self):
        # 0x74 (JE) <-> 0x75 (JNE)
        self.assertEqual(BRANCH_INVERSION_OPCODES[0x74], 0x75)
        self.assertEqual(BRANCH_INVERSION_OPCODES[0x75], 0x74)


if __name__ == "__main__":
    unittest.main()
