"""
Automated Unit Tests for PhantomSuite Process Manager
"""

import unittest
import subprocess
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.process_manager import ProcessManager


class TestProcessManager(unittest.TestCase):
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

    def test_01_list_processes(self):
        procs = ProcessManager.list_processes()
        self.assertGreater(len(procs), 0)
        found = any(p.pid == self.pid for p in procs)
        self.assertTrue(found, f"Process {self.pid} not found in process list")

    def test_02_pause_and_resume(self):
        # Pause process
        ok_pause = ProcessManager.pause_process(self.pid)
        self.assertTrue(ok_pause)
        time.sleep(0.05)

        # Check state in /proc/<pid>/status
        with open(f"/proc/{self.pid}/status") as f:
            status = f.read()
            self.assertIn("State:\tT", status) # T is Stopped / Paused

        # Resume process
        ok_resume = ProcessManager.resume_process(self.pid)
        self.assertTrue(ok_resume)
        time.sleep(0.05)

        with open(f"/proc/{self.pid}/status") as f:
            status = f.read()
            self.assertIn("State:\tS", status) # S is Sleeping (interruptible)

    def test_03_hyprland_windows(self):
        windows = ProcessManager.get_hyprland_windows()
        # Should be a dict (may have windows if in Hyprland session)
        self.assertIsInstance(windows, dict)


if __name__ == "__main__":
    unittest.main()
