"""
Automated Unit Tests for PhantomSuite Injector
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.injector import Injector


class TestInjector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid
        cls.so_path = os.path.join(os.path.dirname(__file__), "test_payload.so")

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_01_inject_payload(self):
        success, msg = Injector.inject(self.pid, self.so_path)
        self.assertTrue(success, f"Injection failed with message: {msg}")

        # Check constructor log
        log_file = "/tmp/phantom_injected_test.log"
        self.assertTrue(os.path.exists(log_file))

        # Check loaded modules in target maps
        is_loaded = Injector.is_module_loaded(self.pid, self.so_path)
        self.assertTrue(is_loaded)


if __name__ == "__main__":
    unittest.main()
