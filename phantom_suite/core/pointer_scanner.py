"""
PhantomSuite Pointer Scanner Engine
Discovers single-level and multi-level pointer chains to resolve dynamically
allocated heap variables across process restarts and map loads.
"""

import os
import struct
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion
from phantom_suite.core.table_serializer import TableSerializer


@dataclass
class PointerPath:
    module_name: str
    base_offset: int
    offsets: List[int]
    resolved_address: int

    def to_string(self) -> str:
        base = f"[{self.module_name} + 0x{self.base_offset:X}]" if self.module_name else f"[0x{self.base_offset:X}]"
        if not self.offsets:
            return base
        offs = " -> ".join(f"+ 0x{o:X}" for o in self.offsets)
        return f"{base} -> {offs}"


class PointerScanner:
    """Finds and evaluates pointer chains pointing to target memory addresses."""

    @classmethod
    def resolve_path(cls, pid: int, module_name: str, base_offset: int, offsets: List[int]) -> Optional[int]:
        """Evaluates a pointer chain in live PID memory to compute target address."""
        if not pid or pid <= 0:
            return None

        # 1. Resolve base address
        if module_name:
            base = TableSerializer.get_module_base(pid, module_name)
            if base is None:
                return None
            curr_addr = base + base_offset
        else:
            curr_addr = base_offset

        # 2. Dereference pointers across chain
        for idx, off in enumerate(offsets):
            # Read 8-byte pointer (64-bit x86_64 pointer)
            raw = MemoryEngine.read_bytes(pid, curr_addr, 8)
            if not raw or len(raw) != 8:
                return None
            ptr_val = struct.unpack("<Q", raw)[0]
            if ptr_val == 0:
                return None
            curr_addr = ptr_val + off

        return curr_addr

    @classmethod
    def scan_for_pointers(
        cls,
        pid: int,
        target_address: int,
        max_offset: int = 4096,
        max_depth: int = 2,
        max_results: int = 50
    ) -> List[PointerPath]:
        """
        Scans readable memory for pointers pointing within max_offset of target_address.
        Supports single-level (depth 1) and multi-level (depth 2) chains rooted in named modules.
        """
        results: List[PointerPath] = []
        regions = MemoryEngine.get_maps(pid)
        if not regions:
            return results

        # Identify named module regions (.data / .bss / static segments)
        module_regions: List[Tuple[str, MemoryRegion]] = []
        all_readable: List[MemoryRegion] = []

        for r in regions:
            if not r.is_readable:
                continue
            if r.pathname.startswith(("/dev/", "[vsyscall]", "[vvar]")):
                continue
            all_readable.append(r)
            if r.pathname and r.pathname.startswith("/") and r.is_writable:
                mod_name = os.path.basename(r.pathname)
                module_regions.append((mod_name, r))

        # Level 1: Find all pointers in readable memory pointing to [target - max_offset, target]
        # Pointers in memory are 8-byte aligned on 64-bit
        level1_candidates: List[Tuple[int, int]] = [] # (ptr_address, offset_to_target)

        # Search module static writable regions first
        for mod_name, reg in module_regions:
            chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
            if not chunk:
                continue

            for pos in range(0, len(chunk) - 7, 8):
                val = struct.unpack_from("<Q", chunk, pos)[0]
                if target_address - max_offset <= val <= target_address:
                    offset = target_address - val
                    ptr_addr = reg.start + pos
                    base = TableSerializer.get_module_base(pid, mod_name)
                    if base is not None:
                        base_off = ptr_addr - base
                        results.append(PointerPath(
                            module_name=mod_name,
                            base_offset=base_off,
                            offsets=[offset],
                            resolved_address=target_address
                        ))
                        if len(results) >= max_results:
                            return results

        if max_depth <= 1:
            return results

        # If needed, search heap / anonymous readable regions for multi-level paths
        for reg in all_readable:
            if reg.size > 8 * 1024 * 1024: # Skip massive mappings for speed
                continue
            chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
            if not chunk:
                continue

            for pos in range(0, len(chunk) - 7, 8):
                val = struct.unpack_from("<Q", chunk, pos)[0]
                if target_address - max_offset <= val <= target_address:
                    offset = target_address - val
                    level1_candidates.append((reg.start + pos, offset))
                    if len(level1_candidates) >= 500:
                        break
            if len(level1_candidates) >= 500:
                break

        # Level 2: Search module static regions for pointers pointing to level1 candidate addresses
        for l1_addr, l1_off in level1_candidates:
            for mod_name, reg in module_regions:
                chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
                if not chunk:
                    continue

                for pos in range(0, len(chunk) - 7, 8):
                    val = struct.unpack_from("<Q", chunk, pos)[0]
                    if l1_addr - max_offset <= val <= l1_addr:
                        l2_off = l1_addr - val
                        base = TableSerializer.get_module_base(pid, mod_name)
                        if base is not None:
                            results.append(PointerPath(
                                module_name=mod_name,
                                base_offset=(reg.start + pos) - base,
                                offsets=[l2_off, l1_off],
                                resolved_address=target_address
                            ))
                            if len(results) >= max_results:
                                return results

        return results
