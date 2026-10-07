"""
PhantomSuite In-Memory IL2CPP Metadata & Klass Layout Introspector
Provides memory-walking capabilities for Unity IL2CPP runtimes, parsing
Il2CppClass (klass) descriptors, FieldInfo arrays, MethodInfo tables,
dynamic instance field values, and synthesizes C# / C++ type headers.
"""

import struct
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from phantom_suite.core.memory_engine import MemoryEngine
from phantom_suite.core.elf_explorer import ElfExplorer


@dataclass
class Il2CppFieldDef:
    """Represents a C# field defined on an Il2CppClass."""
    name: str
    type_name: str
    offset: int
    token: int = 0
    is_static: bool = False
    raw_value: Optional[Any] = None


@dataclass
class Il2CppMethodDef:
    """Represents a C# method defined on an Il2CppClass."""
    name: str
    method_pointer: int
    invoker_pointer: int = 0
    return_type: str = "void"
    param_count: int = 0
    flags: int = 0
    token: int = 0
    rva: int = 0


@dataclass
class Il2CppClassDef:
    """Represents an introspected Il2CppClass (klass) descriptor."""
    klass_address: int
    name: str
    namespace: str
    full_name: str
    parent_address: int = 0
    parent_name: str = ""
    instance_size: int = 0
    actual_size: int = 0
    field_count: int = 0
    method_count: int = 0
    fields: List[Il2CppFieldDef] = field(default_factory=list)
    methods: List[Il2CppMethodDef] = field(default_factory=list)
    is_value_type: bool = False
    is_enum: bool = False


@dataclass
class Il2CppObjectDump:
    """Represents a live instance of an Il2CppObject with resolved field values."""
    object_address: int
    klass: Il2CppClassDef
    field_values: Dict[str, Any] = field(default_factory=dict)


class Il2CppLayoutOffsets:
    """
    Standard 64-bit Unity IL2CPP struct offsets.
    Handles 16-byte Il2CppType sizing and adapts across Unity versions.
    """
    # Il2CppObject
    OBJ_KLASS = 0x00
    OBJ_MONITOR = 0x08
    OBJ_DATA_START = 0x10

    # Il2CppClass (64-bit)
    CLASS_IMAGE = 0x00
    CLASS_NAME = 0x10
    CLASS_NAMESPAZE = 0x18
    CLASS_BYVAL_ARG = 0x20
    # sizeof(Il2CppType) is 16 bytes on 64-bit:
    CLASS_THIS_ARG = 0x30
    CLASS_ELEMENT_CLASS = 0x40
    CLASS_CAST_CLASS = 0x48
    CLASS_DECLARING_TYPE = 0x50
    CLASS_PARENT = 0x58

    # Unity 2020-2022+ default offsets (with dynamic fallback to 2019)
    CLASS_FIELDS = 0x80
    CLASS_FIELDS_FALLBACK = 0x70
    CLASS_METHODS = 0x98
    CLASS_METHODS_FALLBACK = 0x88

    CLASS_INSTANCE_SIZE = 0xF8
    CLASS_ACTUAL_SIZE = 0x100
    CLASS_FIELD_COUNT = 0x124
    CLASS_METHOD_COUNT = 0x120

    # FieldInfo (64-bit)
    FIELD_SIZE = 0x20
    FIELD_NAME = 0x00
    FIELD_TYPE = 0x08
    FIELD_OFFSET = 0x18
    FIELD_TOKEN = 0x1C

    # MethodInfo (64-bit)
    METHOD_PTR = 0x00
    METHOD_INVOKER_2019 = 0x08
    METHOD_NAME_2019 = 0x10
    METHOD_INVOKER_2020 = 0x10
    METHOD_NAME_2020 = 0x18

    # String object
    STRING_LENGTH = 0x10
    STRING_CHARS = 0x14


class Il2CppInspector:
    """
    In-memory IL2CPP Introspector for process reverse engineering and modding.
    Inspects live class layouts, virtual method tables, and object instances.
    """

    @classmethod
    def detect_il2cpp(cls, pid: int) -> bool:
        """Checks if IL2CPP runtime is loaded in the target process."""
        if not pid or pid <= 0:
            return False
        mods = ElfExplorer.get_loaded_modules(pid)
        for m in mods:
            low_name = m.name.lower()
            if "libil2cpp" in low_name or "gameassembly" in low_name:
                return True
        return False

    @classmethod
    def read_c_string(cls, pid: int, addr: int, max_len: int = 128) -> str:
        """Safely reads a null-terminated UTF-8 / ASCII string from target memory."""
        if not addr or addr <= 0:
            return ""
        raw = MemoryEngine.read_bytes(pid, addr, max_len)
        if not raw:
            return ""
        null_idx = raw.find(b"\x00")
        if null_idx != -1:
            raw = raw[:null_idx]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin1", errors="replace")

    @classmethod
    def read_il2cpp_string(cls, pid: int, string_addr: int) -> str:
        """
        Reads a managed System.String object from memory.
        Layout: [0x00: klass] [0x08: monitor] [0x10: int32 length] [0x14: utf16 characters]
        """
        if not string_addr or string_addr <= 0:
            return ""
        len_bytes = MemoryEngine.read_bytes(pid, string_addr + Il2CppLayoutOffsets.STRING_LENGTH, 4)
        if not len_bytes or len(len_bytes) < 4:
            return ""
        length = struct.unpack("<i", len_bytes)[0]
        if length <= 0 or length > 65536:
            return ""

        char_bytes = MemoryEngine.read_bytes(pid, string_addr + Il2CppLayoutOffsets.STRING_CHARS, length * 2)
        if not char_bytes:
            return ""
        return char_bytes.decode("utf-16-le", errors="replace")

    @classmethod
    def read_pointer(cls, pid: int, addr: int) -> int:
        """Reads a 64-bit pointer from process memory."""
        if not addr or addr <= 0:
            return 0
        raw = MemoryEngine.read_bytes(pid, addr, 8)
        if raw and len(raw) == 8:
            return struct.unpack("<Q", raw)[0]
        return 0

    @classmethod
    def read_u16(cls, pid: int, addr: int) -> int:
        """Reads a 16-bit unsigned integer from process memory."""
        raw = MemoryEngine.read_bytes(pid, addr, 2)
        return struct.unpack("<H", raw)[0] if raw and len(raw) == 2 else 0

    @classmethod
    def read_i32(cls, pid: int, addr: int) -> int:
        """Reads a 32-bit signed integer from process memory."""
        raw = MemoryEngine.read_bytes(pid, addr, 4)
        return struct.unpack("<i", raw)[0] if raw and len(raw) == 4 else 0

    @classmethod
    def inspect_class(cls, pid: int, klass_addr: int, max_fields: int = 128, max_methods: int = 128) -> Optional[Il2CppClassDef]:
        """
        Walks an Il2CppClass memory structure and resolves all fields and methods.
        Supports both modern Unity 2020-2022 and legacy 2019 layouts dynamically.
        """
        if not klass_addr or klass_addr <= 0:
            return None

        # Read class name & namespace pointers
        name_ptr = cls.read_pointer(pid, klass_addr + Il2CppLayoutOffsets.CLASS_NAME)
        ns_ptr = cls.read_pointer(pid, klass_addr + Il2CppLayoutOffsets.CLASS_NAMESPAZE)
        parent_ptr = cls.read_pointer(pid, klass_addr + Il2CppLayoutOffsets.CLASS_PARENT)

        name = cls.read_c_string(pid, name_ptr)
        if not name:
            return None

        namespace = cls.read_c_string(pid, ns_ptr)
        full_name = f"{namespace}.{name}" if namespace else name

        parent_name = ""
        if parent_ptr:
            p_name_ptr = cls.read_pointer(pid, parent_ptr + Il2CppLayoutOffsets.CLASS_NAME)
            parent_name = cls.read_c_string(pid, p_name_ptr)

        # Dynamic layout resolution for fields & methods
        fields_ptr = cls.read_pointer(pid, klass_addr + Il2CppLayoutOffsets.CLASS_FIELDS)
        if not fields_ptr:
            fields_ptr = cls.read_pointer(pid, klass_addr + Il2CppLayoutOffsets.CLASS_FIELDS_FALLBACK)

        methods_ptr = cls.read_pointer(pid, klass_addr + Il2CppLayoutOffsets.CLASS_METHODS)
        if not methods_ptr:
            methods_ptr = cls.read_pointer(pid, klass_addr + Il2CppLayoutOffsets.CLASS_METHODS_FALLBACK)

        # Read counts (check 2020-2022 offsets, fallback to legacy)
        raw_field_count = cls.read_u16(pid, klass_addr + Il2CppLayoutOffsets.CLASS_FIELD_COUNT)
        if raw_field_count == 0 or raw_field_count > 4096:
            raw_field_count = cls.read_u16(pid, klass_addr + 0x114)

        raw_method_count = cls.read_u16(pid, klass_addr + Il2CppLayoutOffsets.CLASS_METHOD_COUNT)
        if raw_method_count == 0 or raw_method_count > 4096:
            raw_method_count = cls.read_u16(pid, klass_addr + 0x116)

        field_count = min(raw_field_count, max_fields)
        method_count = min(raw_method_count, max_methods)

        # Parse Fields
        fields: List[Il2CppFieldDef] = []
        if fields_ptr and field_count > 0:
            for i in range(field_count):
                f_entry = fields_ptr + (i * Il2CppLayoutOffsets.FIELD_SIZE)
                f_name_ptr = cls.read_pointer(pid, f_entry + Il2CppLayoutOffsets.FIELD_NAME)
                f_name = cls.read_c_string(pid, f_name_ptr)
                f_offset = cls.read_i32(pid, f_entry + Il2CppLayoutOffsets.FIELD_OFFSET)
                f_token = cls.read_i32(pid, f_entry + Il2CppLayoutOffsets.FIELD_TOKEN)

                if f_name:
                    # In IL2CPP, thread-static or static fields without instance layout have negative offset
                    is_static = (f_offset < 0)
                    fields.append(Il2CppFieldDef(
                        name=f_name,
                        type_name="System.Object",
                        offset=f_offset,
                        token=f_token,
                        is_static=is_static
                    ))

        # Parse Methods
        methods: List[Il2CppMethodDef] = []
        if methods_ptr and method_count > 0:
            for i in range(method_count):
                m_info_ptr = cls.read_pointer(pid, methods_ptr + (i * 8))
                if not m_info_ptr:
                    continue
                m_fn_ptr = cls.read_pointer(pid, m_info_ptr + Il2CppLayoutOffsets.METHOD_PTR)

                # Check 2020+ method name offset (0x18), fallback to 2019 (0x10)
                m_name_ptr = cls.read_pointer(pid, m_info_ptr + Il2CppLayoutOffsets.METHOD_NAME_2020)
                m_name = cls.read_c_string(pid, m_name_ptr)
                if not m_name or not m_name.isprintable():
                    m_name_ptr = cls.read_pointer(pid, m_info_ptr + Il2CppLayoutOffsets.METHOD_NAME_2019)
                    m_name = cls.read_c_string(pid, m_name_ptr)

                if m_name and m_fn_ptr:
                    methods.append(Il2CppMethodDef(
                        name=m_name,
                        method_pointer=m_fn_ptr,
                        return_type="void"
                    ))

        instance_size = cls.read_i32(pid, klass_addr + Il2CppLayoutOffsets.CLASS_INSTANCE_SIZE)
        if instance_size <= 0:
            instance_size = cls.read_i32(pid, klass_addr + 0xD4)

        return Il2CppClassDef(
            klass_address=klass_addr,
            name=name,
            namespace=namespace,
            full_name=full_name,
            parent_address=parent_ptr,
            parent_name=parent_name,
            instance_size=max(0, instance_size),
            field_count=raw_field_count,
            method_count=raw_method_count,
            fields=fields,
            methods=methods
        )

    @classmethod
    def inspect_object(cls, pid: int, obj_addr: int) -> Optional[Il2CppObjectDump]:
        """
        Inspects an instantiated Il2CppObject pointer in memory.
        Dereferences klass at +0x00 and extracts non-static field values.
        """
        if not obj_addr or obj_addr <= 0:
            return None

        klass_ptr = cls.read_pointer(pid, obj_addr + Il2CppLayoutOffsets.OBJ_KLASS)
        if not klass_ptr:
            return None

        klass_def = cls.inspect_class(pid, klass_ptr)
        if not klass_def:
            return None

        field_vals: Dict[str, Any] = {}
        for f in klass_def.fields:
            if f.offset > 0 and not f.is_static:
                target_field_addr = obj_addr + f.offset
                val = cls.read_pointer(pid, target_field_addr)
                field_vals[f.name] = val

        return Il2CppObjectDump(
            object_address=obj_addr,
            klass=klass_def,
            field_values=field_vals
        )

    @classmethod
    def generate_csharp_header(cls, klass: Il2CppClassDef) -> str:
        """Synthesizes a clean C# class header with offsets and method signatures."""
        lines = []
        if klass.namespace:
            lines.append(f"namespace {klass.namespace}")
            lines.append("{")
            indent = "    "
        else:
            indent = ""

        parent_clause = f" : {klass.parent_name}" if klass.parent_name else ""
        lines.append(f"{indent}// [Il2CppClass] Address: 0x{klass.klass_address:016X} | Size: 0x{klass.instance_size:X}")
        lines.append(f"{indent}public class {klass.name}{parent_clause}")
        lines.append(f"{indent}{{")

        if klass.fields:
            lines.append(f"{indent}    // --- Fields ---")
            for f in sorted(klass.fields, key=lambda x: x.offset):
                static_mod = "static " if f.is_static else ""
                lines.append(f"{indent}    [FieldOffset(0x{abs(f.offset):02X})] public {static_mod}{f.type_name} {f.name};")

        if klass.methods:
            lines.append(f"{indent}    // --- Methods ---")
            for m in klass.methods:
                lines.append(f"{indent}    // VA: 0x{m.method_pointer:016X}")
                lines.append(f"{indent}    public {m.return_type} {m.name}();")

        lines.append(f"{indent}}}")
        if klass.namespace:
            lines.append("}")
        return "\n".join(lines)

    @classmethod
    def generate_cpp_struct(cls, klass: Il2CppClassDef) -> str:
        """
        Synthesizes a C++20 representation of the class layout with accurate
        member sizing and padding bytes.
        """
        lines = [
            f"// Il2Cpp Klass: 0x{klass.klass_address:016X}",
            f"struct {klass.name} {{",
            "    void* klass;   // +0x00",
            "    void* monitor; // +0x08"
        ]

        current_offset = 0x10
        sorted_fields = [f for f in klass.fields if not f.is_static and f.offset >= 0x10]
        sorted_fields.sort(key=lambda x: x.offset)

        for i, f in enumerate(sorted_fields):
            if f.offset > current_offset:
                pad = f.offset - current_offset
                lines.append(f"    uint8_t _pad_0x{current_offset:X}[0x{pad:X}];")
                current_offset = f.offset

            # Determine field size from interval to next field
            if i + 1 < len(sorted_fields):
                next_offset = sorted_fields[i + 1].offset
                field_size = max(1, min(8, next_offset - f.offset))
            else:
                field_size = 8

            if field_size == 1:
                type_str = "uint8_t"
            elif field_size == 2:
                type_str = "uint16_t"
            elif field_size == 4:
                type_str = "uint32_t"
            else:
                type_str = "uint64_t"
                field_size = 8

            lines.append(f"    {type_str} {f.name}; // +0x{f.offset:02X}")
            current_offset += field_size

        lines.append("};")
        return "\n".join(lines)
