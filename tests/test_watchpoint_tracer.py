"""
Unit tests for PhantomSuite Hardware Watchpoint Tracer.
"""

import os
import subprocess
import time
import unittest
from phantom_suite.core.watchpoint_tracer import WatchpointTracer, WatchpointHit


class TestWatchpointTracer(unittest.TestCase):
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

    def test_regex_parsing_full(self):
        sample_output = (
            "Hardware watchpoint 1: *(int*)0x555555558028\n"
            "Old value = 100\n"
            "New value = 999\n"
            "0x0000555555555234 in main () from ./test_target\n"
        )
        matches = WatchpointTracer.HIT_REGEX.findall(sample_output)
        self.assertEqual(len(matches), 1)
        old_val, new_val, addr_hex, func_name = matches[0]
        self.assertEqual(old_val, "100")
        self.assertEqual(new_val, "999")
        self.assertEqual(addr_hex, "0x0000555555555234")
        self.assertEqual(func_name, "main")

    def test_regex_parsing_access_only(self):
        sample_output = (
            "Hardware access watchpoint 1: *(int*)0x555555558028\n"
            "Value = 100\n"
            "0x00005555555552a0 in compute_score () from ./test_target\n"
        )
        matches = WatchpointTracer.HIT_REGEX.findall(sample_output)
        self.assertEqual(len(matches), 1)
        old_val, new_val, addr_hex, func_name = matches[0]
        self.assertEqual(addr_hex, "0x00005555555552a0")
        self.assertEqual(func_name, "compute_score")

    def test_invalid_arguments(self):
        self.assertEqual(WatchpointTracer.trace_address(0, 0x1000), [])
        self.assertEqual(WatchpointTracer.trace_address(-1, 0x1000), [])
        self.assertEqual(WatchpointTracer.trace_address(self.pid, 0), [])

    def test_trace_timeout_clean(self):
        # Trace an address that is not written to, with a short timeout
        hits = WatchpointTracer.trace_address(self.pid, 0x555555558000, watch_type="write", timeout_sec=0.5)
        self.assertIsInstance(hits, list)


if __name__ == "__main__":
    unittest.main()
