"""
Automated Unit Tests for PhantomSuite Memory Engine
"""

import unittest
import subprocess
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.memory_engine import (
    MemoryEngine, TypeFormat, ScanType, FreezeManager
)


class TestMemoryEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        # Wait for startup output
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid

        # Find the target address for target_score (1337)
        results = MemoryEngine.first_scan(cls.pid, TypeFormat.INT32, ScanType.EXACT, 1337)
        assert len(results) > 0, "Could not find score 1337 in test_target"
        cls.addr = results[0].address

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_01_first_scan_int32(self):
        results = MemoryEngine.first_scan(self.pid, TypeFormat.INT32, ScanType.EXACT, 1337)
        self.assertGreater(len(results), 0, "Expected at least 1 match for score=1337")
        self.assertEqual(results[0].address, self.addr)

    def test_02_read_typed_int32(self):
        val = MemoryEngine.read_typed(self.pid, self.addr, TypeFormat.INT32)
        self.assertEqual(val, 1337)

    def test_03_write_typed_int32(self):
        ok = MemoryEngine.write_typed(self.pid, self.addr, TypeFormat.INT32, 424242)
        self.assertTrue(ok)
        val = MemoryEngine.read_typed(self.pid, self.addr, TypeFormat.INT32)
        self.assertEqual(val, 424242)

    def test_04_next_scan_differential(self):
        initial_results = MemoryEngine.first_scan(self.pid, TypeFormat.INT32, ScanType.EXACT, 424242)
        self.assertTrue(any(r.address == self.addr for r in initial_results))

        # Change value in target
        MemoryEngine.write_typed(self.pid, self.addr, TypeFormat.INT32, 500000)

        # Differential next scan: INCREASED
        refined = MemoryEngine.next_scan(self.pid, TypeFormat.INT32, ScanType.INCREASED, None, initial_results)
        self.assertTrue(any(r.address == self.addr for r in refined))

    def test_05_string_scan_and_write(self):
        str_results = MemoryEngine.first_scan(self.pid, TypeFormat.STRING, ScanType.EXACT, "PhantomTarget_Active")
        self.assertGreater(len(str_results), 0)
        str_addr = str_results[0].address

        val = MemoryEngine.read_typed(self.pid, str_addr, TypeFormat.STRING, str_len=20)
        self.assertEqual(val, "PhantomTarget_Active")

        # Overwrite string
        ok = MemoryEngine.write_typed(self.pid, str_addr, TypeFormat.STRING, "PhantomPwned!")
        self.assertTrue(ok)
        new_val = MemoryEngine.read_typed(self.pid, str_addr, TypeFormat.STRING, str_len=20)
        self.assertEqual(new_val, "PhantomPwned!")

    def test_06_freeze_manager(self):
        freezer = FreezeManager(interval_sec=0.02)
        freezer.add(self.pid, self.addr, TypeFormat.INT32, 888888)
        time.sleep(0.06)

        val = MemoryEngine.read_typed(self.pid, self.addr, TypeFormat.INT32)
        self.assertEqual(val, 888888)

        # Attempt to change it externally; freezer should overwrite it back
        MemoryEngine.write_typed(self.pid, self.addr, TypeFormat.INT32, 111111)
        time.sleep(0.06)
        frozen_val = MemoryEngine.read_typed(self.pid, self.addr, TypeFormat.INT32)
        self.assertEqual(frozen_val, 888888)

        freezer.stop()


if __name__ == "__main__":
    unittest.main()
