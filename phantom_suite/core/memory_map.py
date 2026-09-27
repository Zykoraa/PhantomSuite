"""
PhantomSuite Virtual Address Space Analyzer
Parses and categorizes virtual memory mappings, permissions, and segment statistics.
"""

import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion


@dataclass
class MapCategoryStats:
    executable_bytes: int = 0
    writable_bytes: int = 0
    readonly_bytes: int = 0
    shared_bytes: int = 0
    heap_bytes: int = 0
    stack_bytes: int = 0
    total_virt_bytes: int = 0
    region_count: int = 0


@dataclass
class VisualMemoryBlock:
    start: int
    end: int
    size: int
    perms: str
    category: str # "CODE", "HEAP", "STACK", "WRITABLE", "READONLY", "SHARED", "GUARD"
    label: str
    color_hex: str


class MemoryMapAnalyzer:
    """Analyzes and aggregates process virtual address space mappings."""

    COLOR_MAP = {
        "CODE": "#00f0ff",      # Neon Cyan
        "HEAP": "#00ff9d",      # Neon Emerald Green
        "STACK": "#ffb700",     # Neon Amber
        "WRITABLE": "#ff007f",  # Neon Magenta
        "READONLY": "#7d90b3",  # Slate Blue
        "SHARED": "#b537f2",    # Neon Purple
        "GUARD": "#1c2638"      # Dark Muted
    }

    @classmethod
    def analyze_process_maps(cls, pid: int) -> Tuple[List[VisualMemoryBlock], MapCategoryStats]:
        """
        Parses all memory regions of target PID, categorizes each segment,
        and computes memory distribution statistics.
        """
        blocks: List[VisualMemoryBlock] = []
        stats = MapCategoryStats()

        if not pid or pid <= 0:
            return blocks, stats

        regions = MemoryEngine.get_maps(pid)
        stats.region_count = len(regions)

        for r in regions:
            sz = r.size
            stats.total_virt_bytes += sz

            # Categorize
            p = r.pathname
            perms = r.perms

            if 'x' in perms:
                cat = "CODE"
                stats.executable_bytes += sz
            elif p == "[heap]":
                cat = "HEAP"
                stats.heap_bytes += sz
                stats.writable_bytes += sz
            elif p.startswith("[stack"):
                cat = "STACK"
                stats.stack_bytes += sz
                stats.writable_bytes += sz
            elif 's' in perms:
                cat = "SHARED"
                stats.shared_bytes += sz
            elif 'w' in perms:
                cat = "WRITABLE"
                stats.writable_bytes += sz
            elif 'r' in perms:
                cat = "READONLY"
                stats.readonly_bytes += sz
            else:
                cat = "GUARD"

            label = os.path.basename(p) if p.startswith("/") else (p if p else "[anon]")
            color = cls.COLOR_MAP.get(cat, "#7d90b3")

            blocks.append(VisualMemoryBlock(
                start=r.start,
                end=r.end,
                size=sz,
                perms=perms,
                category=cat,
                label=label,
                color_hex=color
            ))

        return blocks, stats
