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


# Canonical x86_64 Linux user-space address bounds
MIN_USER_PTR = 0x1000
MAX_USER_PTR = 0x7FFFFFFFFFFF


@dataclass
class PointerPath:
    module_name: Optional[str]
    base_offset: int
    offsets: List[int]
    resolved_address: int

    def to_string(self) -> str:
        if self.module_name:
            if self.base_offset >= 0:
                base = f"[{self.module_name} + 0x{self.base_offset:X}]"
            else:
                base = f"[{self.module_name} - 0x{-self.base_offset:X}]"
        else:
            if self.base_offset >= 0:
                base = f"[0x{self.base_offset:X}]"
            else:
                base = f"[-0x{-self.base_offset:X}]"

        if not self.offsets:
            return base

        def _fmt_off(o: int) -> str:
            return f"+ 0x{o:X}" if o >= 0 else f"- 0x{-o:X}"

        offs = " -> ".join(_fmt_off(o) for o in self.offsets)
        return f"{base} -> {offs}"


class PointerScanner:
    """Finds and evaluates pointer chains pointing to target memory addresses."""

    @classmethod
    def resolve_path(
        cls,
        pid: int,
        module_name: Optional[str],
        base_offset: int,
        offsets: List[int]
    ) -> Optional[int]:
        """Evaluates a pointer chain in live PID memory to compute target address."""
        if not pid or not isinstance(pid, int) or pid <= 0:
            return None
        if not isinstance(offsets, (list, tuple)):
            return None

        try:
            # 1. Resolve base address
            if module_name:
                base = TableSerializer.get_module_base(pid, module_name)
                if base is None:
                    return None
                curr_addr = base + base_offset
            else:
                curr_addr = base_offset

            if curr_addr < MIN_USER_PTR or curr_addr > MAX_USER_PTR:
                return None

            # 2. Dereference pointers across chain
            for off in offsets:
                if not isinstance(off, int):
                    return None
                # Read 8-byte pointer (64-bit x86_64 pointer)
                raw = MemoryEngine.read_bytes(pid, curr_addr, 8)
                if not raw or len(raw) != 8:
                    return None
                ptr_val = struct.unpack("<Q", raw)[0]
                if ptr_val < MIN_USER_PTR or ptr_val > MAX_USER_PTR:
                    return None
                curr_addr = ptr_val + off
                if curr_addr < MIN_USER_PTR or curr_addr > MAX_USER_PTR:
                    return None

            return curr_addr
        except Exception:
            return None

    @classmethod
    def symbolic_solve(
        cls,
        pid: int,
        target_address: int,
        max_offset: int = 4096,
        max_depth: int = 3,
        alignment: int = 4,
        max_results: int = 25
    ) -> List[PointerPath]:
        """
        Uses PhantomPath Z3 SMT constraint solving to discover multi-level pointer chains
        satisfying offset bounds, stride alignment, and acyclic reachability invariants.
        """
        if not pid or not isinstance(pid, int) or pid <= 0:
            return []
        if not isinstance(target_address, int) or target_address < MIN_USER_PTR or target_address > MAX_USER_PTR:
            return []
        if max_depth <= 0 or max_results <= 0:
            return []

        try:
            from phantom_suite.core.symbolic_solver import SymbolicPointerSolver
            graph = SymbolicPointerSolver.build_memory_graph(
                pid=pid,
                target_address=target_address,
                max_offset=max(0, max_offset),
                max_depth=max_depth,
                alignment=max(1, alignment)
            )
            return SymbolicPointerSolver.solve_paths_smt(
                graph=graph,
                target_address=target_address,
                max_depth=max_depth,
                max_offset=max(0, max_offset),
                alignment=max(1, alignment),
                max_results=max_results
            )
        except Exception:
            return []

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
        if not pid or not isinstance(pid, int) or pid <= 0:
            return results
        if not isinstance(target_address, int) or target_address < MIN_USER_PTR or target_address > MAX_USER_PTR:
            return results
        if max_offset < 0 or max_depth <= 0 or max_results <= 0:
            return results

        try:
            regions = MemoryEngine.get_maps(pid)
        except Exception:
            return results
        if not regions:
            return results

        # Identify named module regions (.data / .bss / static segments)
        module_regions: List[Tuple[str, MemoryRegion]] = []
        all_readable: List[MemoryRegion] = []

        for r in regions:
            if not r.is_readable or r.size <= 0:
                continue
            pathname = r.pathname or ""
            if pathname.startswith(("/dev/", "[vsyscall]", "[vvar]", "[vdso]")):
                continue
            all_readable.append(r)
            if pathname.startswith("/") and r.is_writable and r.size <= 64 * 1024 * 1024:
                mod_name = os.path.basename(pathname)
                module_regions.append((mod_name, r))

        # Level 1: Find all pointers in readable memory pointing to [target - max_offset, target]
        # Pointers in memory are 8-byte aligned on 64-bit
        level1_candidates: List[Tuple[int, int]] = []  # (ptr_address, offset_to_target)

        # Search module static writable regions first
        for mod_name, reg in module_regions:
            try:
                chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
            except Exception:
                continue
            if not chunk:
                continue

            chunk_len = len(chunk)
            for pos in range(0, chunk_len - 7, 8):
                val = struct.unpack_from("<Q", chunk, pos)[0]
                if val < MIN_USER_PTR or val > MAX_USER_PTR:
                    continue
                if target_address - max_offset <= val <= target_address:
                    ptr_addr = reg.start + pos
                    if ptr_addr == target_address:
                        continue
                    offset = target_address - val
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
            if reg.size > 8 * 1024 * 1024:  # Skip massive mappings for speed
                continue
            try:
                chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
            except Exception:
                continue
            if not chunk:
                continue

            chunk_len = len(chunk)
            for pos in range(0, chunk_len - 7, 8):
                val = struct.unpack_from("<Q", chunk, pos)[0]
                if val < MIN_USER_PTR or val > MAX_USER_PTR:
                    continue
                if target_address - max_offset <= val <= target_address:
                    ptr_addr = reg.start + pos
                    if ptr_addr == target_address:
                        continue
                    offset = target_address - val
                    level1_candidates.append((ptr_addr, offset))
                    if len(level1_candidates) >= 500:
                        break
            if len(level1_candidates) >= 500:
                break

        # Level 2: Search module static regions for pointers pointing to level1 candidate addresses
        for l1_addr, l1_off in level1_candidates:
            for mod_name, reg in module_regions:
                try:
                    chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
                except Exception:
                    continue
                if not chunk:
                    continue

                chunk_len = len(chunk)
                for pos in range(0, chunk_len - 7, 8):
                    val = struct.unpack_from("<Q", chunk, pos)[0]
                    if val < MIN_USER_PTR or val > MAX_USER_PTR:
                        continue
                    if l1_addr - max_offset <= val <= l1_addr:
                        ptr_addr = reg.start + pos
                        if ptr_addr in (l1_addr, target_address):
                            continue
                        l2_off = l1_addr - val
                        base = TableSerializer.get_module_base(pid, mod_name)
                        if base is not None:
                            results.append(PointerPath(
                                module_name=mod_name,
                                base_offset=ptr_addr - base,
                                offsets=[l2_off, l1_off],
                                resolved_address=target_address
                            ))
                            if len(results) >= max_results:
                                return results

        return results
