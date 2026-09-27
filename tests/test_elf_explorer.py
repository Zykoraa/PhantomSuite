"""
Unit tests for PhantomSuite ELF Symbol & Module Explorer.
"""

import os
import subprocess
import time
import unittest
from phantom_suite.core.elf_explorer import ElfExplorer, LoadedModule, ElfSymbol, ElfSection


class TestElfExplorer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_src = os.path.join(os.path.dirname(__file__), "test_target.c")
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        if not os.path.exists(target_bin):
            subprocess.run(["gcc", "-O0", "-g", target_src, "-o", target_bin, "-lpthread"], check=True)

        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.2)
        cls.pid = cls.proc.pid
        cls.target_bin = target_bin

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_get_loaded_modules(self):
        modules = ElfExplorer.get_loaded_modules(self.pid)
        self.assertGreater(len(modules), 0)
        mod_names = [m.name for m in modules]
        self.assertTrue(any("test_target" in n for n in mod_names))
        self.assertTrue(any("libc" in n for n in mod_names))

    def test_parse_symbols(self):
        symbols = ElfExplorer.parse_symbols(self.target_bin, base_address=0x555555554000)
        self.assertGreater(len(symbols), 0)

        sym_names = {s.name: s for s in symbols}
        self.assertIn("target_health", sym_names)
        self.assertIn("target_score", sym_names)
        self.assertIn("target_speed", sym_names)
        self.assertIn("target_banner", sym_names)

        health = sym_names["target_health"]
        self.assertEqual(health.symbol_type, "OBJECT")
        self.assertIsNotNone(health.runtime_address)
        self.assertGreater(health.runtime_address, 0x555555554000)

    def test_parse_sections(self):
        sections = ElfExplorer.parse_sections(self.target_bin, base_address=0x555555554000)
        self.assertGreater(len(sections), 0)
        sec_names = [s.name for s in sections]
        self.assertIn(".text", sec_names)
        self.assertIn(".data", sec_names)


if __name__ == "__main__":
    unittest.main()
