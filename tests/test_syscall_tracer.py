"""
Unit tests for PhantomSuite Syscall Telemetry Tracer.
"""

import unittest
from phantom_suite.core.syscall_tracer import SyscallTracer, SyscallEvent


class TestSyscallTracer(unittest.TestCase):
    def test_parse_line_with_duration(self):
        line = 'openat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 4 <0.000015>'
        ev = SyscallTracer.parse_line(line)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.syscall, "openat")
        self.assertEqual(ev.category, "FILE")
        self.assertEqual(ev.result, "4")
        self.assertAlmostEqual(ev.duration, 0.000015, places=6)

    def test_parse_line_with_pid(self):
        line = '[pid 45892] socket(AF_INET, SOCK_STREAM, IPPROTO_IP) = 3 <0.000020>'
        ev = SyscallTracer.parse_line(line)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.pid, 45892)
        self.assertEqual(ev.syscall, "socket")
        self.assertEqual(ev.category, "NET")
        self.assertEqual(ev.result, "3")

    def test_parse_memory_syscall(self):
        line = 'mmap(NULL, 206291, PROT_READ, MAP_PRIVATE, 4, 0) = 0x7f8199a55000 <0.000009>'
        ev = SyscallTracer.parse_line(line)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.syscall, "mmap")
        self.assertEqual(ev.category, "MEM")
        self.assertEqual(ev.result, "0x7f8199a55000")


if __name__ == "__main__":
    unittest.main()
