"""
Unit tests for PhantomSuite Virtual Address Space Analyzer.
"""

import os
import subprocess
import time
import unittest
from phantom_suite.core.memory_map import MemoryMapAnalyzer, VisualMemoryBlock, MapCategoryStats


class TestMemoryMapAnalyzer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_src = os.path.join(os.path.dirname(__file__), "test_target.c")
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        if not os.path.exists(target_bin):
            subprocess.run(["gcc", "-O0", "-g", target_src, "-o", target_bin, "-lpthread"], check=True)

        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.2)
        cls.pid = cls.proc.pid

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_analyze_process_maps(self):
        blocks, stats = MemoryMapAnalyzer.analyze_process_maps(self.pid)
        self.assertGreater(len(blocks), 0)
        self.assertEqual(stats.region_count, len(blocks))
        self.assertGreater(stats.total_virt_bytes, 0)
        self.assertGreater(stats.executable_bytes, 0)
        self.assertGreater(stats.writable_bytes, 0)

        # Check block categories
        categories = {b.category for b in blocks}
        self.assertIn("CODE", categories)
        self.assertIn("WRITABLE", categories)


if __name__ == "__main__":
    unittest.main()
