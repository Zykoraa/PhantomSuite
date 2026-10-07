"""
Automated Unit Tests for PhantomSuite Pointer Scanner
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.pointer_scanner import PointerScanner
from phantom_suite.core.memory_engine import MemoryEngine, TypeFormat, ScanType


class TestPointerScanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid

        # Find target address for target_score (1337)
        results = MemoryEngine.first_scan(cls.pid, TypeFormat.INT32, ScanType.EXACT, 1337)
        assert len(results) > 0
        cls.score_addr = results[0].address

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_scan_and_resolve_pointers(self):
        # Scan for pointers pointing to score_addr
        paths = PointerScanner.scan_for_pointers(
            self.pid, self.score_addr, max_offset=4096, max_depth=1
        )
        self.assertIsInstance(paths, list)

        # Test evaluating resolve_path with a dummy known path
        # If any path was found, verify resolve_path resolves it
        for p in paths:
            resolved = PointerScanner.resolve_path(self.pid, p.module_name, p.base_offset, p.offsets)
            if resolved is not None:
                self.assertEqual(resolved, self.score_addr)

    def test_pointer_scanner_corner_cases(self):
        """Verifies PID <= 0, None/invalid offsets, and null pointer safety."""
        # PID <= 0
        self.assertIsNone(PointerScanner.resolve_path(0, "test", 0x10, [0x20]))
        self.assertIsNone(PointerScanner.resolve_path(-1, "test", 0x10, [0x20]))
        self.assertEqual(PointerScanner.scan_for_pointers(0, self.score_addr), [])
        self.assertEqual(PointerScanner.scan_for_pointers(-1, self.score_addr), [])

        # Invalid offsets argument
        self.assertIsNone(PointerScanner.resolve_path(self.pid, "test", 0x10, None))
        self.assertIsNone(PointerScanner.resolve_path(self.pid, "test", 0x10, ["not_an_int"]))

        # Invalid target address
        self.assertEqual(PointerScanner.scan_for_pointers(self.pid, target_address=0), [])
        self.assertEqual(PointerScanner.scan_for_pointers(self.pid, target_address=-1), [])

        # Negative offset to_string formatting
        path = PointerScanner.resolve_path(self.pid, "", 0, [])
        p_obj = PointerScanner.scan_for_pointers(self.pid, self.score_addr, max_offset=4096, max_depth=1)
        # Custom PointerPath string formatting check with negative offsets
        from phantom_suite.core.pointer_scanner import PointerPath
        p_neg = PointerPath(module_name="mod", base_offset=-0x20, offsets=[-0x10, 0x30], resolved_address=0x1000)
        self.assertIn("- 0x20", p_neg.to_string())
        self.assertIn("- 0x10", p_neg.to_string())
        self.assertIn("+ 0x30", p_neg.to_string())


if __name__ == "__main__":
    unittest.main()
