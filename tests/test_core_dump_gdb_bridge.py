"""
Unit tests for PhantomSuite GDB/MI Debug Bridge & Core Dump Importer.
"""

import os
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from phantom_suite.core.core_dump_gdb_bridge import (
    CoreDumpReader, GdbMiBridge, SIGNAL_NAMES, X86_64_GREG_NAMES
)


class TestCoreDumpGdbBridge(unittest.TestCase):

    def _create_synthetic_core_dump(self) -> str:
        """Constructs a minimal valid 64-bit ELF core dump in a temp file."""
        # Note content: NT_PRSTATUS
        # 12B pr_info, 2B pr_cursig (11 = SIGSEGV), 2B pad, 16B sig masks, 16B pids, 64B timevals
        # 216B registers (27 * 8)
        prstatus_desc = bytearray(328)
        struct.pack_into("<H", prstatus_desc, 12, 11)  # SIGSEGV
        struct.pack_into("<i", prstatus_desc, 32, 4321)  # PID

        # Put dummy registers
        regs_start = 112
        struct.pack_into("<Q", prstatus_desc, regs_start + (16 * 8), 0x0000555555554000)  # RIP
        struct.pack_into("<Q", prstatus_desc, regs_start + (19 * 8), 0x00007FFFFFFFE000)  # RSP
        struct.pack_into("<Q", prstatus_desc, regs_start + (10 * 8), 0x42)  # RAX

        # Pack NT_PRSTATUS Note: namesz=5 ("CORE\0"), descsz=328, type=1
        note_name = b"CORE\x00\x00\x00\x00"  # 8 bytes padded
        note_prstatus = struct.pack("<III", 5, len(prstatus_desc), 1) + note_name + prstatus_desc

        # Note content: NT_PRPSINFO (64-bit Linux struct elf_prpsinfo: pr_fname at 40, pr_psargs at 56)
        prpsinfo_desc = bytearray(140)
        prpsinfo_desc[40:52] = b"crash_target\x00"
        prpsinfo_desc[56:72] = b"./crash_target\x00"
        note_prpsinfo = struct.pack("<III", 5, len(prpsinfo_desc), 3) + note_name + prpsinfo_desc

        notes_data = note_prstatus + note_prpsinfo

        # Memory payload for PT_LOAD
        load_data = b"PHANTOM_CORE_MEMORY_BYTES"

        # Offsets
        ehdr_size = 64
        phdr_size = 56
        num_phdrs = 2
        phdrs_offset = ehdr_size
        notes_offset = ehdr_size + (num_phdrs * phdr_size)
        load_offset = notes_offset + len(notes_data)

        # ELF Header (64-bit, ET_CORE = 4, EM_X86_64 = 62)
        # e_ident (16B): \x7fELF (4B), class 2 (64-bit), data 1 (LE), version 1, abi 0, pad 7
        e_ident = b"\x7fELF\x02\x01\x01\x00" + (b"\x00" * 8)
        ehdr = struct.pack(
            "<16sHHIQQQIHHHHHH",
            e_ident,
            4,    # e_type = ET_CORE
            62,   # e_machine = EM_X86_64
            1,    # e_version
            0,    # e_entry
            phdrs_offset,  # e_phoff
            0,    # e_shoff
            0,    # e_flags
            ehdr_size,     # e_ehsize
            phdr_size,     # e_phentsize
            num_phdrs,     # e_phnum
            0, 0, 0
        )

        # Phdr 0: PT_NOTE (type=7)
        phdr_note = struct.pack(
            "<IIQQQQQQ",
            7,     # p_type = PT_NOTE
            0,     # p_flags
            notes_offset,  # p_offset
            0,     # p_vaddr
            0,     # p_paddr
            len(notes_data),  # p_filesz
            0,     # p_memsz
            0      # p_align
        )

        # Phdr 1: PT_LOAD (type=1)
        phdr_load = struct.pack(
            "<IIQQQQQQ",
            1,     # p_type = PT_LOAD
            7,     # p_flags (rwx)
            load_offset,  # p_offset
            0x00400000,   # p_vaddr
            0,     # p_paddr
            len(load_data),   # p_filesz
            4096,             # p_memsz (26B initialized, remainder BSS)
            4096   # p_align
        )

        core_bytes = ehdr + phdr_note + phdr_load + notes_data + load_data

        fd, temp_path = tempfile.mkstemp(suffix=".core")
        with os.fdopen(fd, "wb") as f:
            f.write(core_bytes)

        return temp_path

    def test_core_dump_reader_parse_and_report(self):
        core_file = self._create_synthetic_core_dump()
        try:
            reader = CoreDumpReader(core_file)
            success = reader.load()
            self.assertTrue(success)
            self.assertIsNotNone(reader.metadata)

            meta = reader.metadata
            self.assertEqual(meta.pid, 4321)
            self.assertEqual(meta.signal_num, 11)
            self.assertEqual(meta.signal_name, "SIGSEGV")
            self.assertEqual(meta.exec_name, "crash_target")
            self.assertEqual(meta.registers["rip"], 0x0000555555554000)
            self.assertEqual(meta.registers["rsp"], 0x00007FFFFFFFE000)
            self.assertEqual(meta.registers["rax"], 0x42)

            # Test virtual memory read from PT_LOAD
            mem = reader.read_bytes(0x00400000, 12)
            self.assertEqual(mem, b"PHANTOM_CORE")

            # Test BSS zero padding when address is within memsz but beyond filesz
            bss_mem = reader.read_bytes(0x00400000 + 100, 8)
            self.assertEqual(bss_mem, b"\x00" * 8)

            # Test report generation
            report = reader.generate_report()
            self.assertIn("crash_target [PID: 4321]", report)
            self.assertIn("SIGSEGV", report)
            self.assertIn("0x0000555555554000", report)

            reader.close()
        finally:
            if os.path.exists(core_file):
                os.remove(core_file)

    def test_core_dump_invalid_file(self):
        reader = CoreDumpReader("/nonexistent/file.core")
        self.assertFalse(reader.load())

    def test_gdb_mi_bridge_mock(self):
        bridge = GdbMiBridge()
        # Mock process
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "101^done\n",
            "(gdb)\n"
        ]
        bridge.proc = mock_proc

        success, out = bridge.send_command("-data-evaluate-expression 1+1")
        self.assertTrue(success)
        self.assertIn("101^done", out)


if __name__ == "__main__":
    unittest.main()
