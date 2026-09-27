"""
Automated Unit Tests for PhantomSuite Handle & Socket Tracer
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.handle_tracer import HandleTracer


class TestHandleTracer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_01_list_handles(self):
        handles = HandleTracer.list_handles(self.pid)
        self.assertGreater(len(handles), 0)

        # Target opens a listening TCP socket on 19876
        socket_handles = [h for h in handles if h.kind == "SOCKET"]
        self.assertGreater(len(socket_handles), 0)

        found_port = any("19876" in h.details for h in socket_handles)
        self.assertTrue(found_port, "Expected listening socket on port 19876")


if __name__ == "__main__":
    unittest.main()
