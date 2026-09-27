"""
Unit tests for PhantomSuite AOB Pattern Scanner & SigMaker.
"""

import os
import subprocess
import time
import unittest
from phantom_suite.core.pattern_scanner import PatternScanner, PatternMatch
from phantom_suite.core.memory_engine import MemoryEngine


class TestPatternScanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Build test target if needed
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

    def test_parse_pattern(self):
        b, m = PatternScanner.parse_pattern("48 89 5C ?? ?? 48 83 * 20")
        self.assertEqual(len(b), len(m))
        self.assertEqual(m, "xxx??xx?x")
        self.assertEqual(b[0], 0x48)
        self.assertEqual(b[1], 0x89)
        self.assertEqual(b[2], 0x5C)
        self.assertEqual(b[3], 0x00)
        self.assertEqual(b[4], 0x00)
        self.assertEqual(b[8], 0x20)

    def test_scan_pattern_exact(self):
        # Scan for banner string "PhantomTarget_Active"
        hex_pat = " ".join(f"{b:02X}" for b in b"PhantomTarget")
        matches = PatternScanner.scan_pattern(self.pid, hex_pat, max_matches=10)
        self.assertGreaterEqual(len(matches), 1)
        # Read back at match address
        read_back = MemoryEngine.read_bytes(self.pid, matches[0].address, 13)
        self.assertEqual(read_back, b"PhantomTarget")

    def test_scan_pattern_wildcard(self):
        # "PhantomTarget" with wildcards in the middle
        # 'P' 'h' 'a' 'n' '?' '?' 'm' 'T' 'a' 'r' 'g' 'e' 't'
        parts = []
        for i, b in enumerate(b"PhantomTarget"):
            if i in (4, 5):
                parts.append("??")
            else:
                parts.append(f"{b:02X}")
        pattern_str = " ".join(parts)

        matches = PatternScanner.scan_pattern(self.pid, pattern_str, max_matches=10)
        self.assertGreaterEqual(len(matches), 1)
        read_back = MemoryEngine.read_bytes(self.pid, matches[0].address, 13)
        self.assertEqual(read_back, b"PhantomTarget")

    def test_generate_unique_signature(self):
        # Pick address of banner
        hex_pat = " ".join(f"{b:02X}" for b in b"PhantomTarget")
        matches = PatternScanner.scan_pattern(self.pid, hex_pat, max_matches=1)
        self.assertTrue(len(matches) > 0)
        target_addr = matches[0].address

        sig, length = PatternScanner.generate_unique_signature(self.pid, target_addr, max_length=32)
        self.assertIsNotNone(sig)
        self.assertGreaterEqual(length, 5)

        # Re-scan generated signature to verify uniqueness
        verify_matches = PatternScanner.scan_pattern(self.pid, sig, max_matches=2)
        self.assertEqual(len(verify_matches), 1)
        self.assertEqual(verify_matches[0].address, target_addr)


if __name__ == "__main__":
    unittest.main()
