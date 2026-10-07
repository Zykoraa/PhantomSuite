"""
Automated Unit Tests for PhantomSuite Mid-Function Detour & Trampoline Hook Engine
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.detour_engine import DetourEngine, DetourHook


class TestDetourEngine(unittest.TestCase):
    def test_capstone_available(self):
        self.assertTrue(DetourEngine.is_available(), "Capstone should be available for detour engine")

    def test_calculate_stolen_boundary(self):
        # 14 bytes target, assembly instructions:
        # push rbp (1)
        # mov rbp, rsp (3)
        # sub rsp, 0x20 (4)
        # mov dword ptr [rbp-4], 0 (7)
        # Total = 1 + 3 + 4 + 7 = 15 bytes
        raw_code = b"\x55\x48\x89\xE5\x48\x83\xEC\x20\xC7\x45\xFC\x00\x00\x00\x00"
        res = DetourEngine.calculate_stolen_boundary(raw_code, 0x1000, 14)
        self.assertIsNotNone(res)
        stolen_len, stolen_bytes, insns = res
        self.assertEqual(stolen_len, 15)
        self.assertEqual(len(insns), 4)

    def test_build_detour_jump_relative(self):
        src = 0x1000
        dst = 0x2000
        payload, is_abs = DetourEngine.build_detour_jump(src, dst)
        self.assertFalse(is_abs)
        self.assertEqual(len(payload), 5)
        self.assertEqual(payload[0], 0xE9)

    def test_build_detour_jump_absolute(self):
        src = 0x1000
        dst = 0x7FFFFFFF1000 # > 2GB away
        payload, is_abs = DetourEngine.build_detour_jump(src, dst)
        self.assertTrue(is_abs)
        self.assertEqual(len(payload), 14)
        self.assertTrue(payload.startswith(b"\xFF\x25\x00\x00\x00\x00"))

    def test_create_trampoline(self):
        stolen = b"\x55\x48\x89\xE5" # 4 bytes
        tramp = DetourEngine.create_trampoline(0x1000, 0x5000, stolen, 4)
        self.assertTrue(tramp.startswith(stolen))
        self.assertEqual(len(tramp), len(stolen) + 14)


if __name__ == "__main__":
    unittest.main()
