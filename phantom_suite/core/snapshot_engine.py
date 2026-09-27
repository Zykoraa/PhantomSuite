"""
PhantomSuite Memory Snapshot & Differential Comparison Engine
Captures full-process writable memory states and computes deltas across snapshots
to discover unknown variables and track state transitions.
"""

import os
import time
import struct
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion
from phantom_suite.core.table_serializer import TableSerializer


@dataclass
class SnapshotRegion:
    start: int
    end: int
    pathname: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class MemorySnapshot:
    pid: int
    timestamp: float
    regions: Dict[int, SnapshotRegion] = field(default_factory=dict) # start_addr -> SnapshotRegion
    total_bytes: int = 0


@dataclass
class SnapshotDiffItem:
    address: int
    module_name: str
    offset: int
    old_bytes: bytes
    new_bytes: bytes
    diff_type: str      # "INCREASED", "DECREASED", "CHANGED", "NEW_REGION"
    old_int32: int
    new_int32: int
    old_float: float
    new_float: float


class SnapshotEngine:
    """Captures memory snapshots of a process and computes differential deltas."""

    @classmethod
    def take_snapshot(
        cls,
        pid: int,
        writable_only: bool = True,
        max_region_size: int = 64 * 1024 * 1024 # 64MB limit per region to avoid huge dumps
    ) -> MemorySnapshot:
        """
        Dumps memory of readable (and optionally writable) regions into a MemorySnapshot object.
        """
        snapshot = MemorySnapshot(pid=pid, timestamp=time.time())
        if not pid or pid <= 0:
            return snapshot

        regions = MemoryEngine.get_maps(pid)
        total = 0

        for r in regions:
            if not r.is_readable:
                continue
            if writable_only and not r.is_writable:
                continue
            if r.pathname.startswith(("/dev/", "[vsyscall]", "[vvar]")):
                continue
            if r.size > max_region_size:
                continue

            chunk = MemoryEngine.read_bytes(pid, r.start, r.size)
            if chunk:
                snapshot.regions[r.start] = SnapshotRegion(
                    start=r.start,
                    end=r.end,
                    pathname=r.pathname,
                    data=chunk
                )
                total += len(chunk)

        snapshot.total_bytes = total
        return snapshot

    @classmethod
    def compute_diff(
        cls,
        snapshot_a: MemorySnapshot,
        snapshot_b: MemorySnapshot,
        filter_type: str = "all",       # "all", "increased", "decreased", "changed"
        stride: int = 4,
        max_results: int = 5000,
        ignore_high_noise: bool = True  # Ignore regions where > 40% of bytes changed
    ) -> List[SnapshotDiffItem]:
        """
        Compares Snapshot A against Snapshot B.
        Returns a list of SnapshotDiffItem records matching filter_type.
        """
        diffs: List[SnapshotDiffItem] = []
        if not snapshot_a or not snapshot_b or snapshot_a.pid != snapshot_b.pid:
            return diffs

        pid = snapshot_a.pid
        stride = 4 if stride not in (1, 2, 4, 8) else stride

        for start_addr, reg_a in snapshot_a.regions.items():
            reg_b = snapshot_b.regions.get(start_addr)
            if not reg_b:
                continue

            bytes_a = reg_a.data
            bytes_b = reg_b.data
            common_len = min(len(bytes_a), len(bytes_b))
            if common_len < stride:
                continue

            # Check noise threshold
            if ignore_high_noise and common_len > 1024:
                # Fast sample noise check
                diff_count = sum(1 for i in range(0, min(1000, common_len), stride) if bytes_a[i:i+stride] != bytes_b[i:i+stride])
                sample_count = min(1000, common_len) // stride
                if sample_count > 0 and (diff_count / sample_count) > 0.40:
                    continue # High noise region (likely framebuffer, decompression scratchbuffer)

            mod_name = os.path.basename(reg_a.pathname) if reg_a.pathname and reg_a.pathname.startswith("/") else ""
            base = TableSerializer.get_module_base(pid, mod_name) if mod_name else None

            for i in range(0, common_len - stride + 1, stride):
                chunk_a = bytes_a[i:i+stride]
                chunk_b = bytes_b[i:i+stride]

                if chunk_a == chunk_b:
                    continue

                curr_addr = start_addr + i
                off = (curr_addr - base) if base is not None else curr_addr

                # Unpack int32 & float if 4-byte stride
                old_i32, new_i32 = 0, 0
                old_flt, new_flt = 0.0, 0.0

                if stride == 4:
                    old_i32 = struct.unpack("<i", chunk_a)[0]
                    new_i32 = struct.unpack("<i", chunk_b)[0]
                    old_flt = struct.unpack("<f", chunk_a)[0]
                    new_flt = struct.unpack("<f", chunk_b)[0]

                if new_i32 > old_i32:
                    delta_type = "INCREASED"
                elif new_i32 < old_i32:
                    delta_type = "DECREASED"
                else:
                    delta_type = "CHANGED"

                if filter_type == "increased" and delta_type != "INCREASED":
                    continue
                elif filter_type == "decreased" and delta_type != "DECREASED":
                    continue

                diffs.append(SnapshotDiffItem(
                    address=curr_addr,
                    module_name=mod_name,
                    offset=off,
                    old_bytes=chunk_a,
                    new_bytes=chunk_b,
                    diff_type=delta_type,
                    old_int32=old_i32,
                    new_int32=new_i32,
                    old_float=old_flt,
                    new_float=new_flt
                ))

                if len(diffs) >= max_results:
                    return diffs

        return diffs
