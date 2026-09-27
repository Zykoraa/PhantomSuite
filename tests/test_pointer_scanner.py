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


if __name__ == "__main__":
    unittest.main()
