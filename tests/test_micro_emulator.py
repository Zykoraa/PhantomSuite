"""
Unit tests for PhantomSuite Micro-Execution & Sub-Function Emulation Engine.
"""

import unittest
from phantom_suite.core.micro_emulator import MicroEmulator, CAPSTONE_AVAILABLE


class TestMicroEmulator(unittest.TestCase):

    def setUp(self):
        self.emu = MicroEmulator()

    def test_register_get_set_64bit(self):
        self.emu.set_reg("rax", 0x1122334455667788)
        self.assertEqual(self.emu.get_reg("rax"), 0x1122334455667788)

    def test_register_32bit_clears_upper(self):
        self.emu.set_reg("rax", 0xFFFFFFFFFFFFFFFF)
        self.emu.set_reg("eax", 0x12345678)
        # Upper 32-bits must be cleared in x86_64
        self.assertEqual(self.emu.get_reg("rax"), 0x0000000012345678)
        self.assertEqual(self.emu.get_reg("eax"), 0x12345678)

    def test_register_16bit_preserves_upper(self):
        self.emu.set_reg("rax", 0x1122334455667788)
        self.emu.set_reg("ax", 0xAAAA)
        self.assertEqual(self.emu.get_reg("rax"), 0x112233445566AAAA)
        self.assertEqual(self.emu.get_reg("ax"), 0xAAAA)

    def test_memory_write_read_shadow(self):
        data = b"\x01\x02\x03\x04\x05"
        self.emu.write_mem(0x10000, data)
        read_back = self.emu.read_mem(0x10000, len(data))
        self.assertEqual(read_back, data)

    def test_push_pop_stack(self):
        init_rsp = self.emu.get_reg("rsp")
        self.emu.push(0xDEADBEEFCAFEBABE)
        self.assertEqual(self.emu.get_reg("rsp"), init_rsp - 8)
        popped = self.emu.pop()
        self.assertEqual(popped, 0xDEADBEEFCAFEBABE)
        self.assertEqual(self.emu.get_reg("rsp"), init_rsp)

    def test_snapshot_restore(self):
        self.emu.set_reg("rax", 100)
        self.emu.write_mem(0x2000, b"original")
        self.emu.save_snapshot()

        self.emu.set_reg("rax", 999)
        self.emu.write_mem(0x2000, b"modified")
        self.assertEqual(self.emu.get_reg("rax"), 999)
        self.assertEqual(self.emu.read_mem(0x2000, 8), b"modified")

        restored = self.emu.restore_snapshot()
        self.assertTrue(restored)
        self.assertEqual(self.emu.get_reg("rax"), 100)
        self.assertEqual(self.emu.read_mem(0x2000, 8), b"original")

    @unittest.skipUnless(CAPSTONE_AVAILABLE, "Capstone required for instruction emulation")
    def test_step_arithmetic_sequence(self):
        # 48 c7 c0 2a 00 00 00 -> mov rax, 42
        # 48 83 c0 08          -> add rax, 8
        # c3                   -> ret
        code = b"\x48\xc7\xc0\x2a\x00\x00\x00\x48\x83\xc0\x08\xc3"
        self.emu.write_mem(0x1000, code)
        self.emu.set_reg("rip", 0x1000)

        # Push dummy return address on stack
        self.emu.push(0x9999)

        res = self.emu.run(max_steps=10)
        self.assertTrue(res.terminated)
        self.assertEqual(res.halt_reason, "returned")
        self.assertEqual(res.steps_executed, 3)
        self.assertEqual(self.emu.get_reg("rax"), 50)
        self.assertEqual(self.emu.get_reg("rip"), 0x9999)

    @unittest.skipUnless(CAPSTONE_AVAILABLE, "Capstone required for instruction emulation")
    def test_step_branching(self):
        # 48 31 c0       -> xor rax, rax (sets ZF=1)
        # 74 03          -> je +3 (skip next instruction)
        # 48 ff c0       -> inc rax (skipped)
        # 48 83 c0 05    -> add rax, 5
        # c3             -> ret
        code = b"\x48\x31\xc0\x74\x03\x48\xff\xc0\x48\x83\xc0\x05\xc3"
        self.emu.write_mem(0x2000, code)
        self.emu.set_reg("rip", 0x2000)
        self.emu.push(0x8888)

        res = self.emu.run(max_steps=10)
        self.assertTrue(res.terminated)
        self.assertEqual(self.emu.get_reg("rax"), 5)

    @unittest.skipUnless(CAPSTONE_AVAILABLE, "Capstone required for instruction emulation")
    def test_step_memory_arithmetic_writeback(self):
        # 48 83 00 05 -> add qword ptr [rax], 5
        # c3          -> ret
        code = b"\x48\x83\x00\x05\xc3"
        self.emu.write_mem(0x2000, code)
        self.emu.set_reg("rip", 0x2000)

        # Buffer at 0x4000 has value 10
        self.emu.write_u64(0x4000, 10)
        self.emu.set_reg("rax", 0x4000)
        self.emu.push(0x7777)

        res = self.emu.run(max_steps=5)
        self.assertTrue(res.terminated)
        self.assertEqual(self.emu.read_u64(0x4000), 15)

    @unittest.skipUnless(CAPSTONE_AVAILABLE, "Capstone required for instruction emulation")
    def test_step_rip_relative_lea(self):
        # 48 8d 05 0a 00 00 00 -> lea rax, [rip + 0xa]
        # c3                   -> ret
        code = b"\x48\x8d\x05\x0a\x00\x00\x00\xc3"
        self.emu.write_mem(0x1000, code)
        self.emu.set_reg("rip", 0x1000)
        self.emu.push(0x5555)

        res = self.emu.run(max_steps=5)
        self.assertTrue(res.terminated)
        # Expected: rip (0x1000) + ins.size (7) + disp (0xa) = 0x1011
        self.assertEqual(self.emu.get_reg("rax"), 0x1011)


if __name__ == "__main__":
    unittest.main()
