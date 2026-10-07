"""
Automated Unit Tests for PhantomSuite PMU & Anti-Debug Timing Profiler
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.pmu_profiler import PmuProfiler, TimingProfileReport, AntiDebugIndicator


class TestPmuProfiler(unittest.TestCase):
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

    def test_audit_process_live(self):
        report = PmuProfiler.audit_process(self.pid, scan_executable_memory=True)
        self.assertIsNotNone(report)
        self.assertIsInstance(report, TimingProfileReport)
        self.assertEqual(report.pid, self.pid)
        self.assertFalse(report.is_ptraced) # Not currently ptraced
        self.assertEqual(report.tracer_pid, 0)
        self.assertGreaterEqual(report.threat_score, 0)
        self.assertLessEqual(report.threat_score, 100)

    def test_audit_invalid_pid(self):
        self.assertIsNone(PmuProfiler.audit_process(-1))
        self.assertIsNone(PmuProfiler.audit_process(9999999))


if __name__ == "__main__":
    unittest.main()
