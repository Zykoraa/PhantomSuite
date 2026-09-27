"""
PhantomSuite AOB Pattern Scanner & SigMaker
High-speed memory scanning with wildcards and automatic unique signature generation.
"""

import os
import re
from typing import List, Tuple, Optional
from dataclasses import dataclass
from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion
from phantom_suite.core.table_serializer import TableSerializer


@dataclass
class PatternMatch:
    address: int
    module_name: str
    offset: int


class PatternScanner:
    """Pattern scanner supporting byte masks and automatic unique signature generation."""

    @classmethod
    def parse_pattern(cls, pattern_str: str) -> Tuple[bytes, str]:
        """
        Parses pattern string like "48 8B 05 ?? ?? ?? ?? 48 85"
        into (pattern_bytes, mask_string) where mask has 'x' for exact and '?' for wildcard.
        """
        tokens = pattern_str.strip().replace("0x", "").split()
        b_list = []
        m_list = []

        for t in tokens:
            if t in ("?", "??", "*"):
                b_list.append(0)
                m_list.append("?")
            else:
                b_list.append(int(t, 16))
                m_list.append("x")

        return bytes(b_list), "".join(m_list)

    @classmethod
    def scan_pattern(
        cls,
        pid: int,
        pattern_str: str,
        module_only: Optional[str] = None,
        max_matches: int = 50
    ) -> List[PatternMatch]:
        """
        Scans process memory for an AOB pattern with wildcards.
        Returns list of PatternMatch items.
        """
        matches: List[PatternMatch] = []
        if not pid or pid <= 0 or not pattern_str.strip():
            return matches

        target_bytes, mask = cls.parse_pattern(pattern_str)
        pat_len = len(target_bytes)
        if pat_len == 0:
            return matches

        regions = MemoryEngine.get_maps(pid)
        candidate_regions: List[Tuple[str, MemoryRegion]] = []

        for r in regions:
            if not r.is_readable:
                continue
            if r.pathname.startswith(("/dev/", "[vsyscall]", "[vvar]")):
                continue
            mod_name = os.path.basename(r.pathname) if r.pathname and r.pathname.startswith("/") else ""
            if module_only and mod_name != module_only:
                continue
            candidate_regions.append((mod_name, r))

        # Check if pure exact bytes (no wildcards) for fast bytes.find
        has_wildcard = "?" in mask

        for mod_name, reg in candidate_regions:
            chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
            if not chunk or len(chunk) < pat_len:
                continue

            chunk_len = len(chunk)

            if not has_wildcard:
                idx = 0
                while True:
                    pos = chunk.find(target_bytes, idx)
                    if pos == -1:
                        break
                    match_addr = reg.start + pos
                    base = TableSerializer.get_module_base(pid, mod_name) if mod_name else None
                    off = match_addr - base if base is not None else match_addr
                    matches.append(PatternMatch(match_addr, mod_name, off))
                    if len(matches) >= max_matches:
                        return matches
                    idx = pos + 1
            else:
                # Sliding window with wildcard mask
                limit = chunk_len - pat_len + 1
                for pos in range(limit):
                    match = True
                    for i in range(pat_len):
                        if mask[i] == "x" and chunk[pos + i] != target_bytes[i]:
                            match = False
                            break
                    if match:
                        match_addr = reg.start + pos
                        base = TableSerializer.get_module_base(pid, mod_name) if mod_name else None
                        off = match_addr - base if base is not None else match_addr
                        matches.append(PatternMatch(match_addr, mod_name, off))
                        if len(matches) >= max_matches:
                            return matches

        return matches

    @classmethod
    def generate_unique_signature(
        cls,
        pid: int,
        address: int,
        module_name: Optional[str] = None,
        max_length: int = 48
    ) -> Tuple[Optional[str], int]:
        """
        Automatically generates the shortest unique AOB signature for the instruction/bytes
        at address within target module. Returns (signature_string, signature_length).
        """
        raw = MemoryEngine.read_bytes(pid, address, max_length)
        if not raw or len(raw) < 4:
            return None, 0

        # Try increasing lengths starting from 5 bytes up to max_length
        for length in range(5, len(raw) + 1):
            chunk = raw[:length]
            hex_pattern = " ".join(f"{b:02X}" for b in chunk)
            matches = cls.scan_pattern(pid, hex_pattern, module_only=module_name, max_matches=2)
            if len(matches) == 1 and matches[0].address == address:
                return hex_pattern, length

        # If not unique without wildcards, return full hex string
        return " ".join(f"{b:02X}" for b in raw[:max_length]), max_length
