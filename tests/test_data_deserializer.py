"""
Unit tests for PhantomSuite Dynamic Data Deserializer & Type Inferer.
"""

import os
import struct
import subprocess
import time
import unittest
from phantom_suite.core.data_deserializer import (
    DataDeserializer, DecodedString, DecodedVector, DecodedJson
)
from phantom_suite.core.memory_engine import MemoryEngine
from phantom_suite.core.elf_explorer import ElfExplorer


class TestDataDeserializer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_src = os.path.join(os.path.dirname(__file__), "test_target.c")
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        if not os.path.exists(target_bin):
            subprocess.run(["gcc", "-O0", "-g", target_src, "-o", target_bin, "-lpthread"], check=True)

        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.2)
        cls.pid = cls.proc.pid

        # Find target_banner address in test_target
        mods = ElfExplorer.get_loaded_modules(cls.pid)
        target_mod = next(m for m in mods if "test_target" in m.name)
        syms = ElfExplorer.parse_symbols(target_mod.path, base_address=target_mod.base_address)
        cls.banner_sym = next(s for s in syms if s.name == "target_banner")
        cls.banner_addr = cls.banner_sym.runtime_address

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_decode_string_table(self):
        # Write null-delimited strings to banner
        test_data = b"PlayerOne\x00Cyberpunk\x00Phantom\x00"
        MemoryEngine.write_bytes(self.pid, self.banner_addr, test_data)

        strings = DataDeserializer.decode_string_table(self.pid, self.banner_addr, search_size=len(test_data))
        self.assertGreaterEqual(len(strings), 3)
        texts = [s[1] for s in strings]
        self.assertIn("PlayerOne", texts)
        self.assertIn("Cyberpunk", texts)
        self.assertIn("Phantom", texts)

    def test_find_embedded_json(self):
        # Write embedded JSON string
        json_data = b'{"name":"PhantomTarget","hp":100,"active":true}' + b"\x00"
        MemoryEngine.write_bytes(self.pid, self.banner_addr, json_data)

        results = DataDeserializer.find_embedded_json(self.pid, self.banner_addr, search_size=64)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].parsed.get("name"), "PhantomTarget")
        self.assertEqual(results[0].parsed.get("hp"), 100)
        self.assertTrue(results[0].parsed.get("active"))

    def test_decode_std_string_sso(self):
        # Construct SSO std::string (length < 16)
        # Layout: [0..7] ptr, [8..15] length, [16..31] local buffer
        sso_text = b"ShortStr"
        length = len(sso_text)
        ptr = self.banner_addr + 16  # In SSO, pointer points to local buffer
        local_buf = sso_text.ljust(16, b"\x00")
        raw_struct = struct.pack("<QQ16s", ptr, length, local_buf)

        MemoryEngine.write_bytes(self.pid, self.banner_addr, raw_struct)

        decoded = DataDeserializer.decode_std_string(self.pid, self.banner_addr)
        self.assertIsNotNone(decoded)
        self.assertTrue(decoded.is_sso)
        self.assertEqual(decoded.length, length)
        self.assertEqual(decoded.text, "ShortStr")
        self.assertEqual(decoded.data_address, self.banner_addr + 16)

    def test_decode_std_string_heap(self):
        # Construct heap std::string (length >= 16)
        # Place string contents at banner_addr + 32
        heap_text = b"LongHeapAllocatedString!"
        heap_data_addr = self.banner_addr + 32
        MemoryEngine.write_bytes(self.pid, heap_data_addr, heap_text + b"\x00")

        length = len(heap_text)
        capacity = 32
        # std::string struct at banner_addr: ptr, length, capacity
        raw_struct = struct.pack("<QQQ8s", heap_data_addr, length, capacity, b"\x00" * 8)
        MemoryEngine.write_bytes(self.pid, self.banner_addr, raw_struct)

        decoded = DataDeserializer.decode_std_string(self.pid, self.banner_addr)
        self.assertIsNotNone(decoded)
        self.assertFalse(decoded.is_sso)
        self.assertEqual(decoded.length, length)
        self.assertEqual(decoded.capacity, capacity)
        self.assertEqual(decoded.text, "LongHeapAllocatedString!")
        self.assertEqual(decoded.data_address, heap_data_addr)

    def test_decode_std_vector(self):
        # Construct std::vector<int32>
        # Elements at banner_addr + 24: [100, 200, 300] (12 bytes)
        elements_addr = self.banner_addr + 24
        elem_bytes = struct.pack("<iii", 100, 200, 300)
        MemoryEngine.write_bytes(self.pid, elements_addr, elem_bytes)

        start_ptr = elements_addr
        finish_ptr = elements_addr + 12
        end_ptr = elements_addr + 20  # capacity 5

        vector_struct = struct.pack("<QQQ", start_ptr, finish_ptr, end_ptr)
        MemoryEngine.write_bytes(self.pid, self.banner_addr, vector_struct)

        decoded = DataDeserializer.decode_std_vector(
            self.pid, self.banner_addr, element_size=4, element_type="int32"
        )
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.count, 3)
        self.assertEqual(decoded.capacity, 5)
        self.assertEqual(decoded.elements, [100, 200, 300])


if __name__ == "__main__":
    unittest.main()
