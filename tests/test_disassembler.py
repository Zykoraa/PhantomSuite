"""
Automated Unit Tests for PhantomSuite Disassembler & NOP Patcher
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.disassembler import Disassembler
from phantom_suite.core.memory_engine import MemoryEngine


class TestDisassembler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid

        # Find code address in maps
        regions = MemoryEngine.get_maps(cls.pid)
        exec_regions = [r for r in regions if r.is_executable and r.pathname.endswith("test_target")]
        assert len(exec_regions) > 0
        cls.code_addr = exec_regions[0].start

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_disassemble_and_nop(self):
        instructions = Disassembler.disassemble(self.pid, self.code_addr, length=32)
        self.assertGreater(len(instructions), 0)

        inst = instructions[0]
        self.assertGreater(inst.size, 0)
        self.assertTrue(inst.mnemonic)

        # NOP patch
        ok, msg, orig_bytes = Disassembler.nop_instruction(self.pid, inst.address, inst.size)
        self.assertTrue(ok)
        self.assertIsNotNone(orig_bytes)

        # Verify NOPs in memory
        mem = MemoryEngine.read_bytes(self.pid, inst.address, inst.size)
        self.assertEqual(mem, b"\x90" * inst.size)

        # Restore
        ok_res, msg_res = Disassembler.restore_instruction(self.pid, inst.address, orig_bytes)
        self.assertTrue(ok_res)
        restored = MemoryEngine.read_bytes(self.pid, inst.address, inst.size)
        self.assertEqual(restored, orig_bytes)


if __name__ == "__main__":
    unittest.main()
