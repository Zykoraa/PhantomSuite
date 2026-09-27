"""
PhantomSuite Dynamic Data Deserializer & Type Inferer
Discovers and reconstructs high-level data structures from raw memory:
std::string, std::vector, embedded JSON objects, and string tables.
"""

import json
import struct
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from phantom_suite.core.memory_engine import MemoryEngine


@dataclass
class DecodedString:
    address: int
    text: str
    length: int
    capacity: int
    is_sso: bool
    data_address: int


@dataclass
class DecodedVector:
    address: int
    count: int
    capacity: int
    element_size: int
    element_type: str
    start_address: int
    elements: List[Any]


@dataclass
class DecodedJson:
    address: int
    offset: int
    raw_text: str
    parsed: Any


class DataDeserializer:
    """Decodes C++ STL containers and structured data formats from raw process memory."""

    @classmethod
    def decode_std_string(cls, pid: int, address: int) -> Optional[DecodedString]:
        """
        Decodes a libstdc++ 64-bit std::string at address.
        Memory layout (32 bytes):
        [0x00] pointer _M_p (8 bytes)
        [0x08] size_t _M_string_length (8 bytes)
        [0x10] union { char _M_local_buf[16]; size_t _M_allocated_capacity; } (16 bytes)
        """
        raw = MemoryEngine.read_bytes(pid, address, 32)
        if not raw or len(raw) < 32:
            return None

        ptr = struct.unpack("<Q", raw[:8])[0]
        length = struct.unpack("<Q", raw[8:16])[0]

        # Sanity check: length should be plausible (< 10 MB)
        if length > 10 * 1024 * 1024:
            return None

        is_sso = (length < 16)
        if is_sso:
            capacity = 15
            data_addr = address + 16
            str_bytes = raw[16: 16 + length]
        else:
            capacity = struct.unpack("<Q", raw[16:24])[0]
            data_addr = ptr
            str_bytes = MemoryEngine.read_bytes(pid, ptr, min(length, 1024)) or b""

        try:
            text = str_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = str(str_bytes)

        return DecodedString(
            address=address,
            text=text,
            length=length,
            capacity=capacity,
            is_sso=is_sso,
            data_address=data_addr
        )

    @classmethod
    def decode_std_vector(
        cls,
        pid: int,
        address: int,
        element_size: int = 4,
        element_type: str = "int32",
        max_elements: int = 100
    ) -> Optional[DecodedVector]:
        """
        Decodes a 64-bit std::vector at address.
        Memory layout (24 bytes):
        [0x00] T* _M_start (8 bytes)
        [0x08] T* _M_finish (8 bytes)
        [0x10] T* _M_end_of_storage (8 bytes)
        """
        raw = MemoryEngine.read_bytes(pid, address, 24)
        if not raw or len(raw) < 24:
            return None

        start_ptr = struct.unpack("<Q", raw[0:8])[0]
        finish_ptr = struct.unpack("<Q", raw[8:16])[0]
        end_ptr = struct.unpack("<Q", raw[16:24])[0]

        if start_ptr == 0 and finish_ptr == 0:
            return DecodedVector(address, 0, 0, element_size, element_type, 0, [])

        # Sanity checks: start <= finish <= end
        if not (start_ptr <= finish_ptr <= end_ptr) or element_size <= 0:
            return None

        byte_count = finish_ptr - start_ptr
        byte_cap = end_ptr - start_ptr
        if byte_count % element_size != 0 or byte_cap % element_size != 0:
            return None

        count = byte_count // element_size
        capacity = byte_cap // element_size

        if count > 1000000 or capacity > 2000000:
            return None

        # Read sample elements up to max_elements
        elements: List[Any] = []
        read_len = min(count, max_elements) * element_size
        if read_len > 0:
            elem_bytes = MemoryEngine.read_bytes(pid, start_ptr, read_len)
            if elem_bytes:
                fmt_map = {1: "<b", 2: "<h", 4: "<i", 8: "<q"}
                if element_type == "float" and element_size == 4:
                    fmt = "<f"
                elif element_type == "double" and element_size == 8:
                    fmt = "<d"
                else:
                    fmt = fmt_map.get(element_size, "<i")

                stride = struct.calcsize(fmt)
                for off in range(0, len(elem_bytes) - stride + 1, stride):
                    val = struct.unpack(fmt, elem_bytes[off:off+stride])[0]
                    elements.append(val)

        return DecodedVector(
            address=address,
            count=count,
            capacity=capacity,
            element_size=element_size,
            element_type=element_type,
            start_address=start_ptr,
            elements=elements
        )

    @classmethod
    def find_embedded_json(cls, pid: int, address: int, search_size: int = 4096) -> List[DecodedJson]:
        """Scans memory starting at address for valid embedded JSON objects or arrays."""
        results: List[DecodedJson] = []
        raw = MemoryEngine.read_bytes(pid, address, search_size)
        if not raw:
            return results

        text = raw.decode("utf-8", errors="ignore")
        text_len = len(text)

        # Look for '{' or '[' characters
        idx = 0
        while idx < text_len:
            char = text[idx]
            if char in ("{", "["):
                close_char = "}" if char == "{" else "]"
                # Try finding matching closing character with valid json parse
                for end_idx in range(idx + 2, min(idx + 1024, text_len)):
                    if text[end_idx] == close_char:
                        candidate = text[idx:end_idx + 1]
                        try:
                            parsed_obj = json.loads(candidate)
                            results.append(DecodedJson(
                                address=address + idx,
                                offset=idx,
                                raw_text=candidate,
                                parsed=parsed_obj
                            ))
                            idx = end_idx
                            break
                        except Exception:
                            continue
            idx += 1

        return results

    @classmethod
    def decode_string_table(cls, pid: int, address: int, search_size: int = 1024) -> List[Tuple[int, str]]:
        """Parses contiguous null-terminated C-strings from a buffer."""
        results: List[Tuple[int, str]] = []
        raw = MemoryEngine.read_bytes(pid, address, search_size)
        if not raw:
            return results

        strings = raw.split(b"\x00")
        offset = 0
        for s in strings:
            if len(s) >= 3:
                try:
                    txt = s.decode("utf-8", errors="strict")
                    if all(32 <= ord(c) <= 126 for c in txt):
                        results.append((address + offset, txt))
                except Exception:
                    pass
            offset += len(s) + 1

        return results
