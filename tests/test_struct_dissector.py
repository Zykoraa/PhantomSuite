"""
Unit tests for PhantomSuite Struct Dissector and Heatmaps.
"""

import os
import subprocess
import time
import unittest
from phantom_suite.core.struct_dissector import StructDissector, DissectedField
from phantom_suite.core.elf_explorer import ElfExplorer
from phantom_suite.core.memory_engine import MemoryEngine


class TestStructDissector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_src = os.path.join(os.path.dirname(__file__), "test_target.c")
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        if not os.path.exists(target_bin):
            subprocess.run(["gcc", "-O0", "-g", target_src, "-o", target_bin, "-lpthread"], check=True)

        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.2)
        cls.pid = cls.proc.pid

        # Find target_health address via ElfExplorer
        modules = ElfExplorer.get_loaded_modules(cls.pid)
        target_mod = next((m for m in modules if "test_target" in m.name), modules[0])
        syms = ElfExplorer.parse_symbols(target_mod.path, base_address=target_mod.base_address)
        health_sym = next(s for s in syms if s.name == "target_health")
        cls.health_addr = health_sym.runtime_address

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_dissect_fields(self):
        fields = StructDissector.dissect(
            pid=self.pid,
            base_address=self.health_addr,
            size=16,
            stride=4
        )
        self.assertGreaterEqual(len(fields), 3)

        # First field is target_health = 100
        f0 = fields[0]
        self.assertEqual(f0.offset, 0)
        self.assertEqual(f0.int32_val, 100)
        self.assertIn("int32", f0.suggested_type)

        # Second field is target_score = 1337
        f1 = fields[1]
        self.assertEqual(f1.offset, 4)
        self.assertEqual(f1.int32_val, 1337)

        # Third field is target_speed = 4.5f
        f2 = fields[2]
        self.assertEqual(f2.offset, 8)
        self.assertAlmostEqual(f2.float_val, 4.5, places=2)
        self.assertEqual(f2.suggested_type, "Float")

    def test_heatmap_change_detection(self):
        # Baseline snapshot
        fields1 = StructDissector.dissect(
            pid=self.pid,
            base_address=self.health_addr,
            size=16,
            stride=4
        )
        prev_cache = {f.offset: f.raw_bytes for f in fields1}

        # Modify memory at health_addr + 4 (target_score from 1337 to 9999)
        MemoryEngine.write_typed(self.pid, self.health_addr + 4, "int32", 9999)

        fields2 = StructDissector.dissect(
            pid=self.pid,
            base_address=self.health_addr,
            size=16,
            stride=4,
            previous_fields=prev_cache
        )

        # Check that field 0 is not changed, but field 1 is marked changed
        self.assertFalse(fields2[0].changed)
        self.assertTrue(fields2[1].changed)
        self.assertEqual(fields2[1].int32_val, 9999)

        # Revert change
        MemoryEngine.write_typed(self.pid, self.health_addr + 4, "int32", 1337)

    def test_export_c_struct(self):
        fields = StructDissector.dissect(
            pid=self.pid,
            base_address=self.health_addr,
            size=12,
            stride=4
        )
        c_code = StructDissector.export_c_struct(fields, struct_name="PlayerState")
        self.assertIn("typedef struct PlayerState {", c_code)
        self.assertIn("+0x000", c_code)
        self.assertIn("+0x004", c_code)
        self.assertIn("+0x008", c_code)
        self.assertIn("float", c_code)


if __name__ == "__main__":
    unittest.main()
