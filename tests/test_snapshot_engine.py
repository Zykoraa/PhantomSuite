"""
Unit tests for PhantomSuite Memory Snapshot & Differential Comparison Engine.
"""

import os
import subprocess
import time
import unittest
from phantom_suite.core.snapshot_engine import SnapshotEngine, MemorySnapshot, SnapshotDiffItem
from phantom_suite.core.memory_engine import MemoryEngine
from phantom_suite.core.elf_explorer import ElfExplorer


class TestSnapshotEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_src = os.path.join(os.path.dirname(__file__), "test_target.c")
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        if not os.path.exists(target_bin):
            subprocess.run(["gcc", "-O0", "-g", target_src, "-o", target_bin, "-lpthread"], check=True)

        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.2)
        cls.pid = cls.proc.pid

        # Find health address
        mods = ElfExplorer.get_loaded_modules(cls.pid)
        target_mod = next(m for m in mods if "test_target" in m.name)
        syms = ElfExplorer.parse_symbols(target_mod.path, base_address=target_mod.base_address)
        cls.health_addr = next(s for s in syms if s.name == "target_health").runtime_address

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_take_snapshot(self):
        snap = SnapshotEngine.take_snapshot(self.pid, writable_only=True)
        self.assertEqual(snap.pid, self.pid)
        self.assertGreater(len(snap.regions), 0)
        self.assertGreater(snap.total_bytes, 0)

    def test_compute_diff(self):
        # Snapshot A
        snap_a = SnapshotEngine.take_snapshot(self.pid, writable_only=True)

        # Modify variable (target_health 100 -> 250)
        MemoryEngine.write_typed(self.pid, self.health_addr, "int32", 250)

        # Snapshot B
        snap_b = SnapshotEngine.take_snapshot(self.pid, writable_only=True)

        # Diff
        diffs = SnapshotEngine.compute_diff(snap_a, snap_b, filter_type="all")
        self.assertGreater(len(diffs), 0)

        # Look for health_addr in diffs
        health_diff = next((d for d in diffs if d.address == self.health_addr), None)
        self.assertIsNotNone(health_diff)
        self.assertEqual(health_diff.old_int32, 100)
        self.assertEqual(health_diff.new_int32, 250)
        self.assertEqual(health_diff.diff_type, "INCREASED")

        # Test filter "increased"
        inc_diffs = SnapshotEngine.compute_diff(snap_a, snap_b, filter_type="increased")
        self.assertTrue(any(d.address == self.health_addr for d in inc_diffs))

        # Revert change
        MemoryEngine.write_typed(self.pid, self.health_addr, "int32", 100)


if __name__ == "__main__":
    unittest.main()
