"""
PhantomSuite Glibc Heap Chunk Introspector & Allocator Visualizer
Traverses Linux process heap memory (ptmalloc / tcache), validates chunk headers,
identifies allocated vs freed blocks, and detects heap corruption anomalies.
"""

import struct
from typing import List, Dict, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion


PREV_INUSE = 0x1
IS_MMAPPED = 0x2
NON_MAIN_ARENA = 0x4
SIZE_BITS = ~(PREV_INUSE | IS_MMAPPED | NON_MAIN_ARENA)

MIN_CHUNK_SIZE = 0x20 # 32 bytes on x86_64
MALLOC_ALIGNMENT = 0x10 # 16 bytes


@dataclass
class HeapChunk:
    address: int
    prev_size: int
    raw_size: int
    chunk_size: int
    is_prev_inuse: bool
    is_mmapped: bool
    is_non_main_arena: bool
    user_data_addr: int
    user_data_size: int
    state: str = "allocated" # "allocated", "freed", "top_chunk", "corrupted"
    anomaly: Optional[str] = None


@dataclass
class HeapSnapshot:
    pid: int
    heap_base: int
    heap_end: int
    total_size: int
    chunks: List[HeapChunk] = field(default_factory=list)
    allocated_count: int = 0
    freed_count: int = 0
    corrupted_count: int = 0
    top_chunk_addr: Optional[int] = None
    fragmentation_ratio: float = 0.0


class HeapInspector:
    """Introspects and audits glibc heap allocations in running target processes."""

    @classmethod
    def get_heap_region(cls, pid: int) -> Optional[MemoryRegion]:
        """Finds the primary [heap] region for the target PID."""
        if not pid or pid <= 0:
            return None

        regions = MemoryEngine.get_maps(pid)
        for r in regions:
            if r.pathname == "[heap]":
                return r

        # Fallback: find primary anonymous writable region following main executable .bss
        for r in regions:
            if r.is_readable and r.is_writable and not r.is_executable and not r.pathname:
                if 0x10000 <= r.size <= 64 * 1024 * 1024:
                    return r

        return None

    @classmethod
    def audit_heap(
        cls,
        pid: int,
        max_chunks: int = 500,
        sample_bytes: Optional[int] = None
    ) -> Optional[HeapSnapshot]:
        """
        Parses and audits heap chunks starting at heap base.
        Validates chunk alignment, header integrity, and flags.
        """
        heap_reg = cls.get_heap_region(pid)
        if not heap_reg:
            return None

        read_size = min(heap_reg.size, sample_bytes if sample_bytes else 4 * 1024 * 1024)
        raw_heap = MemoryEngine.read_bytes(pid, heap_reg.start, read_size)
        if not raw_heap or len(raw_heap) < 32:
            return None

        snapshot = HeapSnapshot(
            pid=pid,
            heap_base=heap_reg.start,
            heap_end=heap_reg.end,
            total_size=heap_reg.size
        )

        curr_off = 0
        buf_len = len(raw_heap)
        seen_addresses: Set[int] = set()

        while curr_off + 16 <= buf_len and len(snapshot.chunks) < max_chunks:
            chunk_addr = heap_reg.start + curr_off
            if chunk_addr in seen_addresses:
                # Cycle detected
                break
            seen_addresses.add(chunk_addr)

            header_bytes = raw_heap[curr_off: curr_off + 16]
            prev_sz, raw_sz = struct.unpack("<QQ", header_bytes)

            chunk_sz = raw_sz & SIZE_BITS
            prev_inuse = bool(raw_sz & PREV_INUSE)
            mmapped = bool(raw_sz & IS_MMAPPED)
            non_main = bool(raw_sz & NON_MAIN_ARENA)

            anomaly = None
            state = "allocated"

            # Check for top chunk (wilderness)
            if curr_off + chunk_sz >= heap_reg.size:
                state = "top_chunk"
                snapshot.top_chunk_addr = chunk_addr

            # Integrity checks
            elif chunk_sz < MIN_CHUNK_SIZE:
                anomaly = f"Invalid chunk size: 0x{chunk_sz:X} < min (0x{MIN_CHUNK_SIZE:X})"
                state = "corrupted"

            elif chunk_sz % MALLOC_ALIGNMENT != 0:
                anomaly = f"Unaligned chunk size: 0x{chunk_sz:X} not 16-byte aligned"
                state = "corrupted"

            elif chunk_sz > heap_reg.size:
                anomaly = f"Chunk size exceeds total heap: 0x{chunk_sz:X}"
                state = "corrupted"

            # Check next chunk's PREV_INUSE flag to deduce if this chunk is freed
            elif curr_off + chunk_sz + 16 <= buf_len:
                next_header = raw_heap[curr_off + chunk_sz: curr_off + chunk_sz + 16]
                _, next_raw_sz = struct.unpack("<QQ", next_header)
                next_prev_inuse = bool(next_raw_sz & PREV_INUSE)
                if not next_prev_inuse:
                    state = "freed"

            user_data_addr = chunk_addr + 16
            user_data_size = max(0, chunk_sz - 16) if state != "top_chunk" else 0

            chunk_obj = HeapChunk(
                address=chunk_addr,
                prev_size=prev_sz,
                raw_size=raw_sz,
                chunk_size=chunk_sz,
                is_prev_inuse=prev_inuse,
                is_mmapped=mmapped,
                is_non_main_arena=non_main,
                user_data_addr=user_data_addr,
                user_data_size=user_data_size,
                state=state,
                anomaly=anomaly
            )
            snapshot.chunks.append(chunk_obj)

            if state == "allocated":
                snapshot.allocated_count += 1
            elif state == "freed":
                snapshot.freed_count += 1
            elif state == "corrupted":
                snapshot.corrupted_count += 1

            if state in ("corrupted", "top_chunk") or chunk_sz == 0:
                break

            curr_off += chunk_sz

        # Compute fragmentation ratio (freed / total chunks)
        total_counted = snapshot.allocated_count + snapshot.freed_count
        if total_counted > 0:
            snapshot.fragmentation_ratio = snapshot.freed_count / float(total_counted)

        return snapshot
