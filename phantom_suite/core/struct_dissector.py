"""
PhantomSuite Live Struct Dissector & Data Analyzer
Inspects structured memory layout, auto-detects types (pointers, floats, integers, strings),
and tracks runtime delta changes (heatmaps).
"""

import math
import struct
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion


@dataclass
class DissectedField:
    offset: int
    address: int
    raw_bytes: bytes
    int32_val: int
    uint32_val: int
    int64_val: int
    float_val: float
    double_val: float
    is_pointer: bool
    pointer_target: Optional[int]
    pointer_desc: str
    ascii_repr: str
    suggested_type: str
    name: str = ""
    changed: bool = False


class StructDissector:
    """Dissects memory at an address into structured fields with type guessing and heatmaps."""

    @classmethod
    def dissect(
        cls,
        pid: int,
        base_address: int,
        size: int = 256,
        stride: int = 4,
        previous_fields: Optional[Dict[int, bytes]] = None,
        maps: Optional[List[MemoryRegion]] = None
    ) -> List[DissectedField]:
        """
        Reads `size` bytes starting from `base_address` and interprets fields every `stride` bytes.
        Detects pointers, floats, integers, and delta changes from previous_fields.
        """
        if not pid or pid <= 0 or base_address <= 0 or size <= 0:
            return []

        stride = 4 if stride not in (4, 8) else stride
        raw_buffer = MemoryEngine.read_bytes(pid, base_address, size)
        if not raw_buffer:
            return []

        if maps is None:
            maps = MemoryEngine.get_maps(pid)

        # Build readable region index for fast pointer resolution
        readable_regions = [r for r in maps if r.is_readable]

        fields: List[DissectedField] = []
        buf_len = len(raw_buffer)

        for off in range(0, buf_len, stride):
            field_addr = base_address + off
            chunk = raw_buffer[off: off + 8]
            if len(chunk) < 4:
                break

            # 4-byte values
            int32_val = struct.unpack("<i", chunk[:4])[0]
            uint32_val = struct.unpack("<I", chunk[:4])[0]
            float_val = struct.unpack("<f", chunk[:4])[0]

            # 8-byte values (if available)
            if len(chunk) >= 8:
                int64_val = struct.unpack("<q", chunk[:8])[0]
                uint64_val = struct.unpack("<Q", chunk[:8])[0]
                double_val = struct.unpack("<d", chunk[:8])[0]
            else:
                int64_val = int32_val
                uint64_val = uint32_val
                double_val = 0.0

            # Pointer resolution: check if uint64_val falls in readable process region
            is_pointer = False
            ptr_target = None
            ptr_desc = ""

            if len(chunk) >= 8 and uint64_val > 0x10000:
                for reg in readable_regions:
                    if reg.start <= uint64_val < reg.end:
                        is_pointer = True
                        ptr_target = uint64_val
                        mod_name = reg.pathname.split("/")[-1] if reg.pathname else "[anon]"
                        offset_in_reg = uint64_val - reg.start
                        ptr_desc = f"-> {mod_name} + 0x{offset_in_reg:X}"
                        break

            # ASCII string representation of 4 bytes
            ascii_chars = []
            for b in chunk[:4]:
                if 32 <= b <= 126:
                    ascii_chars.append(chr(b))
                else:
                    ascii_chars.append(".")
            ascii_repr = "".join(ascii_chars)

            # Type suggestion heuristic
            suggested_type = cls._guess_type(
                is_pointer=is_pointer,
                int32_val=int32_val,
                uint32_val=uint32_val,
                float_val=float_val,
                ascii_chars=ascii_chars,
                stride=stride
            )

            # Change detection (heatmap)
            cur_bytes = chunk[:stride]
            has_changed = False
            if previous_fields is not None and off in previous_fields:
                if previous_fields[off] != cur_bytes:
                    has_changed = True

            field_obj = DissectedField(
                offset=off,
                address=field_addr,
                raw_bytes=cur_bytes,
                int32_val=int32_val,
                uint32_val=uint32_val,
                int64_val=int64_val,
                float_val=float_val,
                double_val=double_val,
                is_pointer=is_pointer,
                pointer_target=ptr_target,
                pointer_desc=ptr_desc,
                ascii_repr=ascii_repr,
                suggested_type=suggested_type,
                name=f"field_0x{off:02X}",
                changed=has_changed
            )
            fields.append(field_obj)

        return fields

    @staticmethod
    def _guess_type(
        is_pointer: bool,
        int32_val: int,
        uint32_val: int,
        float_val: float,
        ascii_chars: List[str],
        stride: int
    ) -> str:
        """Heuristically determines the most probable semantic data type."""
        if is_pointer:
            return "Pointer (ptr64)"

        # Check if printable ASCII text (at least 3 valid printable characters)
        printable_count = sum(1 for c in ascii_chars if c != ".")
        if printable_count >= 3:
            return "String / ASCII"

        # Check for plausible floating point number (coordinates, health, speed)
        if not math.isnan(float_val) and not math.isinf(float_val):
            abs_f = abs(float_val)
            if 0.001 <= abs_f <= 100000.0:
                # Check that exponent is not weirdly small or extreme
                return "Float"

        # Check for small integer or counter
        if -100000 <= int32_val <= 100000:
            return "4 Bytes (int32)"

        if stride == 8:
            return "8 Bytes (int64)"

        return "Hex Bytes"

    @classmethod
    def export_c_struct(cls, fields: List[DissectedField], struct_name: str = "DissectedEntity") -> str:
        """Generates a compilable C struct definition matching the dissected memory."""
        lines = [
            f"// PhantomSuite Auto-Generated Struct: {struct_name}",
            f"// Total Size: {fields[-1].offset + len(fields[-1].raw_bytes) if fields else 0} bytes",
            "#include <stdint.h>",
            "",
            f"typedef struct {struct_name} {{",
        ]

        type_map = {
            "Pointer (ptr64)": "void*",
            "Float": "float",
            "4 Bytes (int32)": "int32_t",
            "8 Bytes (int64)": "int64_t",
            "String / ASCII": "char",
            "Hex Bytes": "uint8_t"
        }

        for f in fields:
            c_type = type_map.get(f.suggested_type, "uint32_t")
            if f.suggested_type == "String / ASCII":
                decl = f"char {f.name}[4];"
            elif f.suggested_type == "Hex Bytes":
                decl = f"uint8_t {f.name}[{len(f.raw_bytes)}];"
            else:
                decl = f"{c_type} {f.name};"

            ptr_comment = f" // {f.pointer_desc}" if f.is_pointer else ""
            lines.append(f"    /* +0x{f.offset:03X} */ {decl:<28}{ptr_comment}")

        lines.append(f"}} {struct_name};")
        return "\n".join(lines)
