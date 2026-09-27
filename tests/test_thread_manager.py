"""
Automated Unit Tests for PhantomSuite Thread Manager
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.thread_manager import ThreadManager


class TestThreadManager(unittest.TestCase):
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

    def test_list_and_affinity(self):
        threads = ThreadManager.list_threads(self.pid)
        self.assertGreater(len(threads), 0)

        main_thread = threads[0]
        self.assertEqual(main_thread.tid, self.pid)
        self.assertTrue(len(main_thread.affinity) > 0)

        # Set affinity to core 0
        ok = ThreadManager.set_thread_affinity(main_thread.tid, [0])
        self.assertTrue(ok)

        updated = ThreadManager.list_threads(self.pid)[0]
        self.assertEqual(updated.affinity, [0])


if __name__ == "__main__":
    unittest.main()
