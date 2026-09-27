"""
Automated Unit Tests for PhantomSuite Speedhack Engine
"""

import unittest
import subprocess
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.speedhack_controller import SpeedhackController


class TestSpeedhack(unittest.TestCase):
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

    def test_speedhack_lifecycle(self):
        # 1. Inject speedhack
        ok, msg = SpeedhackController.inject(self.pid)
        self.assertTrue(ok, f"Speedhack injection failed: {msg}")

        # 2. Check injected
        is_inj = SpeedhackController.is_injected(self.pid)
        self.assertTrue(is_inj)

        # 3. Check initial speed
        speed, enabled = SpeedhackController.get_speed(self.pid)
        self.assertEqual(speed, 1.0)
        self.assertTrue(enabled)

        # 4. Update speed multiplier to 2.5x
        ok_set = SpeedhackController.set_speed(self.pid, 2.5, enabled=True)
        self.assertTrue(ok_set)

        # 5. Verify speed is 2.5x
        speed_new, enabled_new = SpeedhackController.get_speed(self.pid)
        self.assertEqual(speed_new, 2.5)
        self.assertTrue(enabled_new)


if __name__ == "__main__":
    unittest.main()
