"""
PhantomSuite Memory Hex Viewer & Editor
Live memory hex dumping, ASCII representation, in-place patching,
and change detection for target process memory.
"""

from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from phantom_suite.core.memory_engine import MemoryEngine


@dataclass
class HexLine:
    address: int
    hex_left: str
    hex_right: str
    ascii_repr: str
    raw_bytes: bytes


class HexViewer:
    """Provides formatted hex views and in-place memory editing."""

    BYTES_PER_ROW = 16

    @classmethod
    def read_hex_page(
        cls,
        pid: int,
        start_address: int,
        total_bytes: int = 256
    ) -> List[HexLine]:
        """
        Reads total_bytes starting from start_address,
        aligned to BYTES_PER_ROW, and formats them into HexLine items.
        """
        lines: List[HexLine] = []
        if total_bytes <= 0:
            return lines

        # Align start_address to 16 bytes
        aligned_start = start_address - (start_address % cls.BYTES_PER_ROW)
        raw = MemoryEngine.read_bytes(pid, aligned_start, total_bytes)

        if not raw:
            return lines

        for offset in range(0, len(raw), cls.BYTES_PER_ROW):
            row_addr = aligned_start + offset
            chunk = raw[offset:offset + cls.BYTES_PER_ROW]

            # Left 8 bytes, Right 8 bytes
            left_chunk = chunk[:8]
            right_chunk = chunk[8:]

            left_hex = " ".join(f"{b:02X}" for b in left_chunk)
            right_hex = " ".join(f"{b:02X}" for b in right_chunk)

            # Pad hex if row is shorter than 16 bytes
            if len(left_chunk) < 8:
                left_hex += "   " * (8 - len(left_chunk))
            if len(right_chunk) < 8:
                right_hex += "   " * (8 - len(right_chunk))

            # ASCII representation
            ascii_chars = []
            for b in chunk:
                if 32 <= b <= 126:
                    ascii_chars.append(chr(b))
                else:
                    ascii_chars.append("·")
            ascii_str = "".join(ascii_chars)

            lines.append(HexLine(
                address=row_addr,
                hex_left=left_hex,
                hex_right=right_hex,
                ascii_repr=ascii_str,
                raw_bytes=chunk
            ))

        return lines

    @classmethod
    def patch_bytes(cls, pid: int, address: int, new_hex: str) -> Tuple[bool, str]:
        """
        Writes a string of hex bytes (e.g. '90 90 90' or 'DEADBEEF') to address.
        """
        clean_hex = new_hex.replace(" ", "").replace("0x", "")
        if len(clean_hex) % 2 != 0:
            return False, "Hex string must have an even number of characters."
        try:
            data = bytes.fromhex(clean_hex)
        except ValueError:
            return False, "Invalid hexadecimal characters provided."

        ok = MemoryEngine.write_bytes(pid, address, data)
        if ok:
            return True, f"Successfully patched {len(data)} bytes at 0x{address:X}."
        return False, f"Failed to write bytes to address 0x{address:X}."
