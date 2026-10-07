"""
Unit tests for PhantomSuite In-Memory IL2CPP Introspector.
"""

import unittest
from unittest.mock import patch
import struct
from phantom_suite.core.il2cpp_inspector import (
    Il2CppInspector, Il2CppClassDef, Il2CppFieldDef, Il2CppMethodDef,
    Il2CppLayoutOffsets
)


class TestIl2CppInspector(unittest.TestCase):

    def test_detect_il2cpp_negative(self):
        # PID 0 or negative
        self.assertFalse(Il2CppInspector.detect_il2cpp(0))
        self.assertFalse(Il2CppInspector.detect_il2cpp(-1))

    def test_csharp_header_generation(self):
        fields = [
            Il2CppFieldDef(name="health", type_name="System.Int32", offset=0x18),
            Il2CppFieldDef(name="speed", type_name="System.Single", offset=0x1C),
            Il2CppFieldDef(name="playerName", type_name="System.String", offset=0x20),
        ]
        methods = [
            Il2CppMethodDef(name="TakeDamage", method_pointer=0x7FFF12345678, return_type="void"),
            Il2CppMethodDef(name="GetScore", method_pointer=0x7FFF12345690, return_type="System.Int32")
        ]
        klass = Il2CppClassDef(
            klass_address=0x5555A000,
            name="PlayerController",
            namespace="VRC.SDKBase",
            full_name="VRC.SDKBase.PlayerController",
            parent_name="MonoBehaviour",
            instance_size=0x40,
            fields=fields,
            methods=methods
        )

        header = Il2CppInspector.generate_csharp_header(klass)
        self.assertIn("namespace VRC.SDKBase", header)
        self.assertIn("public class PlayerController : MonoBehaviour", header)
        self.assertIn("[FieldOffset(0x18)] public System.Int32 health;", header)
        self.assertIn("// VA: 0x00007FFF12345678", header)
        self.assertIn("public void TakeDamage();", header)

    def test_cpp_struct_generation(self):
        fields = [
            Il2CppFieldDef(name="health", type_name="uint64_t", offset=0x10),
            Il2CppFieldDef(name="gold", type_name="uint64_t", offset=0x20),
        ]
        klass = Il2CppClassDef(
            klass_address=0x5555A000,
            name="Player",
            namespace="",
            full_name="Player",
            instance_size=0x28,
            fields=fields
        )

        cpp = Il2CppInspector.generate_cpp_struct(klass)
        self.assertIn("struct Player {", cpp)
        self.assertIn("void* klass;", cpp)
        self.assertIn("uint64_t health; // +0x10", cpp)
        self.assertIn("_pad_0x18[0x8];", cpp)
        self.assertIn("uint64_t gold; // +0x20", cpp)

    @patch("phantom_suite.core.memory_engine.MemoryEngine.read_bytes")
    def test_read_il2cpp_string(self, mock_read):
        # Mock reading a string object
        # Length at +0x10 = 5
        # Chars at +0x14 = "Hello" in utf-16-le
        test_str = "Hello"
        encoded_chars = test_str.encode("utf-16-le")

        def side_effect(pid, addr, size):
            if addr == 0x1000 + Il2CppLayoutOffsets.STRING_LENGTH:
                return struct.pack("<i", len(test_str))
            elif addr == 0x1000 + Il2CppLayoutOffsets.STRING_CHARS:
                return encoded_chars
            return b""

        mock_read.side_effect = side_effect
        result = Il2CppInspector.read_il2cpp_string(1234, 0x1000)
        self.assertEqual(result, "Hello")

    @patch("phantom_suite.core.memory_engine.MemoryEngine.read_bytes")
    def test_inspect_class_mock(self, mock_read):
        klass_addr = 0x2000
        name_ptr = 0x3000
        ns_ptr = 0x3020
        fields_ptr = 0x4000
        methods_ptr = 0x5000

        field_name_ptr = 0x6000
        method_name_ptr = 0x7000
        method_info_ptr = 0x8000

        # Memory mapping
        mem_map = {
            klass_addr + Il2CppLayoutOffsets.CLASS_NAME: struct.pack("<Q", name_ptr),
            klass_addr + Il2CppLayoutOffsets.CLASS_NAMESPAZE: struct.pack("<Q", ns_ptr),
            klass_addr + Il2CppLayoutOffsets.CLASS_PARENT: struct.pack("<Q", 0),
            klass_addr + Il2CppLayoutOffsets.CLASS_FIELDS: struct.pack("<Q", fields_ptr),
            klass_addr + Il2CppLayoutOffsets.CLASS_METHODS: struct.pack("<Q", methods_ptr),
            klass_addr + Il2CppLayoutOffsets.CLASS_FIELD_COUNT: struct.pack("<H", 1),
            klass_addr + Il2CppLayoutOffsets.CLASS_METHOD_COUNT: struct.pack("<H", 1),
            klass_addr + Il2CppLayoutOffsets.CLASS_INSTANCE_SIZE: struct.pack("<i", 0x30),
            name_ptr: b"Hero\x00",
            ns_ptr: b"Game\x00",
            # Field 0
            fields_ptr + Il2CppLayoutOffsets.FIELD_NAME: struct.pack("<Q", field_name_ptr),
            fields_ptr + Il2CppLayoutOffsets.FIELD_OFFSET: struct.pack("<i", 0x18),
            fields_ptr + Il2CppLayoutOffsets.FIELD_TOKEN: struct.pack("<i", 101),
            field_name_ptr: b"currentHealth\x00",
            # Method 0
            methods_ptr: struct.pack("<Q", method_info_ptr),
            method_info_ptr + Il2CppLayoutOffsets.METHOD_PTR: struct.pack("<Q", 0x7FFF99990000),
            method_info_ptr + Il2CppLayoutOffsets.METHOD_NAME_2020: struct.pack("<Q", method_name_ptr),
            method_name_ptr: b"Attack\x00"
        }

        def side_effect(pid, addr, size):
            for k, val in mem_map.items():
                if k <= addr < k + len(val):
                    offset = addr - k
                    return val[offset:offset + size]
            return b"\x00" * size

        mock_read.side_effect = side_effect

        klass_def = Il2CppInspector.inspect_class(1234, klass_addr)
        self.assertIsNotNone(klass_def)
        self.assertEqual(klass_def.name, "Hero")
        self.assertEqual(klass_def.namespace, "Game")
        self.assertEqual(klass_def.full_name, "Game.Hero")
        self.assertEqual(len(klass_def.fields), 1)
        self.assertEqual(klass_def.fields[0].name, "currentHealth")
        self.assertEqual(klass_def.fields[0].offset, 0x18)
        self.assertEqual(len(klass_def.methods), 1)
        self.assertEqual(klass_def.methods[0].name, "Attack")
        self.assertEqual(klass_def.methods[0].method_pointer, 0x7FFF99990000)


if __name__ == "__main__":
    unittest.main()
