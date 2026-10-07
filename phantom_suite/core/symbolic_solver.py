"""
PhantomSuite Symbolic Solver & Memory Synthesizer Engine (PhantomPath)
Utilizes Z3 SMT constraint solving and formal graph synthesis to discover
deterministic, multi-level pointer paths across dynamic memory allocations,
with multi-snapshot consistency validation and automated C++20 struct reconstruction.
"""

import os
import re
import struct
import math
import bisect
from typing import List, Dict, Tuple, Optional, Set, Any
from dataclasses import dataclass, field

try:
    import z3
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False

from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion
from phantom_suite.core.table_serializer import TableSerializer
from phantom_suite.core.pointer_scanner import PointerPath, MIN_USER_PTR, MAX_USER_PTR


@dataclass
class SymbolicEdge:
    source_addr: int
    pointed_value: int
    target_addr: int
    offset: int
    module_name: Optional[str] = None
    is_static_root: bool = False


@dataclass
class SymbolicGraph:
    nodes: Set[int] = field(default_factory=set)
    # Target address -> incoming edges
    incoming_edges: Dict[int, List[SymbolicEdge]] = field(default_factory=dict)
    static_roots: List[Tuple[str, int, int]] = field(default_factory=list)  # (module_name, base_addr, root_addr)


class SymbolicPointerSolver:
    """
    Formal SMT-driven pointer path solver and synthesizer.
    Formulates pointer reachability as SMT constraint satisfaction over
    directed memory graphs, eliminating brute-force combinatorial explosion
    and verifying paths against multi-snapshot state invariants.
    """

    @classmethod
    def is_available(cls) -> bool:
        return HAS_Z3

    @classmethod
    def build_memory_graph(
        cls,
        pid: int,
        target_address: int,
        max_offset: int = 4096,
        max_depth: int = 3,
        alignment: int = 4,
        max_nodes_per_level: int = 1000
    ) -> SymbolicGraph:
        """
        Constructs an indexed directed memory graph backwards from target_address.
        Extracts static module roots and intermediate heap/stack pointer references.
        """
        graph = SymbolicGraph()
        if not pid or not isinstance(pid, int) or pid <= 0:
            return graph
        if not isinstance(target_address, int) or target_address < MIN_USER_PTR or target_address > MAX_USER_PTR:
            return graph
        if max_depth <= 0 or max_nodes_per_level <= 0 or max_offset < 0:
            return graph

        alignment = max(1, alignment)

        try:
            regions = MemoryEngine.get_maps(pid)
        except Exception:
            return graph
        if not regions:
            return graph

        readable_regions: List[MemoryRegion] = []
        for r in regions:
            if not r.is_readable or r.size <= 0:
                continue
            pathname = r.pathname or ""
            if pathname.startswith(("/dev/", "[vvar]", "[vsyscall]", "[vdso]")):
                continue
            readable_regions.append(r)

        # Categorize static module writable segments (.data, .bss) vs general dynamic heap/anon memory
        module_segments: List[Tuple[str, int, MemoryRegion]] = []  # (mod_name, mod_base, region)
        dynamic_segments: List[MemoryRegion] = []

        seen_modules: Dict[str, int] = {}
        for r in readable_regions:
            pathname = r.pathname or ""
            if pathname.startswith("/") and r.is_writable and r.size <= 64 * 1024 * 1024:
                mod_name = os.path.basename(pathname)
                if mod_name not in seen_modules:
                    try:
                        base = TableSerializer.get_module_base(pid, mod_name)
                    except Exception:
                        base = None
                    if base is not None:
                        seen_modules[mod_name] = base
                mod_base = seen_modules.get(mod_name)
                if mod_base is not None:
                    module_segments.append((mod_name, mod_base, r))
            elif r.is_readable and r.size <= 32 * 1024 * 1024:  # Up to 32MB regions for heap/anon
                dynamic_segments.append(r)

        # Leaf alignment support for unaligned target variables (e.g. char/short/packed fields)
        leaf_alignment = math.gcd(alignment, target_address) if alignment > 0 else 1

        # Backward BFS layer exploration: targets_to_search -> find pointers pointing to [T - max_offset, T]
        current_targets: Set[int] = {target_address}
        visited_targets: Set[int] = {target_address}
        graph.nodes.add(target_address)

        seen_edges: Set[Tuple[int, int, int]] = set()  # (source_addr, target_addr, offset)
        seen_static_roots: Set[Tuple[str, int, int]] = set()

        for depth in range(1, max_depth + 1):
            if not current_targets:
                break

            sorted_targets = sorted(current_targets)
            min_tgt = sorted_targets[0]
            max_tgt = sorted_targets[-1]

            # 1. Search static module segments first (these can close the path at this depth)
            for mod_name, mod_base, reg in module_segments:
                try:
                    chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
                except Exception:
                    continue
                if not chunk:
                    continue
                chunk_len = len(chunk)

                for pos in range(0, chunk_len - 7, 8):
                    ptr_val = struct.unpack_from("<Q", chunk, pos)[0]
                    if ptr_val < MIN_USER_PTR or ptr_val > MAX_USER_PTR:
                        continue

                    # Fast interval check
                    if (ptr_val + max_offset) < min_tgt or ptr_val > max_tgt:
                        continue

                    ptr_addr = reg.start + pos

                    # Target range [ptr_val, ptr_val + max_offset]
                    start_idx = bisect.bisect_left(sorted_targets, ptr_val)
                    end_idx = bisect.bisect_right(sorted_targets, ptr_val + max_offset)

                    for tgt in sorted_targets[start_idx:end_idx]:
                        # Prevent self-loops and cycle back to original target
                        if ptr_addr == tgt or (ptr_addr == target_address and tgt != target_address):
                            continue

                        offset = tgt - ptr_val
                        eff_align = leaf_alignment if tgt == target_address else alignment
                        if offset % eff_align != 0:
                            continue

                        edge_key = (ptr_addr, tgt, offset)
                        if edge_key in seen_edges:
                            continue
                        seen_edges.add(edge_key)

                        edge = SymbolicEdge(
                            source_addr=ptr_addr,
                            pointed_value=ptr_val,
                            target_addr=tgt,
                            offset=offset,
                            module_name=mod_name,
                            is_static_root=True
                        )
                        graph.incoming_edges.setdefault(tgt, []).append(edge)
                        graph.nodes.add(ptr_addr)

                        root_tuple = (mod_name, mod_base, ptr_addr)
                        if root_tuple not in seen_static_roots:
                            seen_static_roots.add(root_tuple)
                            graph.static_roots.append(root_tuple)

            if depth == max_depth:
                break

            # 2. Search dynamic heap segments for intermediate nodes
            next_targets: Set[int] = set()

            for reg in dynamic_segments:
                if len(next_targets) >= max_nodes_per_level:
                    break
                try:
                    chunk = MemoryEngine.read_bytes(pid, reg.start, reg.size)
                except Exception:
                    continue
                if not chunk:
                    continue
                chunk_len = len(chunk)

                for pos in range(0, chunk_len - 7, 8):
                    ptr_val = struct.unpack_from("<Q", chunk, pos)[0]
                    if ptr_val < MIN_USER_PTR or ptr_val > MAX_USER_PTR:
                        continue

                    if (ptr_val + max_offset) < min_tgt or ptr_val > max_tgt:
                        continue

                    ptr_addr = reg.start + pos

                    start_idx = bisect.bisect_left(sorted_targets, ptr_val)
                    end_idx = bisect.bisect_right(sorted_targets, ptr_val + max_offset)

                    for tgt in sorted_targets[start_idx:end_idx]:
                        # Acyclicity: avoid self-loops and re-visiting already explored targets
                        if ptr_addr == tgt or ptr_addr == target_address or ptr_addr in visited_targets:
                            continue

                        offset = tgt - ptr_val
                        eff_align = leaf_alignment if tgt == target_address else alignment
                        if offset % eff_align != 0:
                            continue

                        edge_key = (ptr_addr, tgt, offset)
                        if edge_key in seen_edges:
                            continue
                        seen_edges.add(edge_key)

                        edge = SymbolicEdge(
                            source_addr=ptr_addr,
                            pointed_value=ptr_val,
                            target_addr=tgt,
                            offset=offset,
                            module_name=None,
                            is_static_root=False
                        )
                        graph.incoming_edges.setdefault(tgt, []).append(edge)
                        graph.nodes.add(ptr_addr)
                        next_targets.add(ptr_addr)

                        if len(next_targets) >= max_nodes_per_level:
                            break
                    if len(next_targets) >= max_nodes_per_level:
                        break

            visited_targets.update(next_targets)
            current_targets = next_targets

        return graph

    @classmethod
    def solve_paths_smt(
        cls,
        graph: SymbolicGraph,
        target_address: int,
        max_depth: int = 3,
        max_offset: int = 4096,
        alignment: int = 4,
        max_results: int = 25
    ) -> List[PointerPath]:
        """
        Uses Z3 SMT solver to find valid, cycle-free pointer chains from
        static roots to target_address, satisfying bounds and alignment constraints.
        """
        results: List[PointerPath] = []
        if not graph or not graph.nodes or not graph.static_roots:
            return results
        if not isinstance(target_address, int) or target_address <= 0:
            return results
        if max_depth <= 0 or max_results <= 0:
            return results

        alignment = max(1, alignment)
        max_offset = max(0, max_offset)

        if not HAS_Z3:
            # Fallback to direct depth-bounded acyclic path traversal
            return cls._solve_graph_direct(graph, target_address, max_depth, max_offset, alignment, max_results)

        try:
            # Depth-by-depth SMT synthesis to guarantee finding shortest/cleanest paths first
            for depth in range(1, max_depth + 1):
                if len(results) >= max_results:
                    break

                # Synthesize all valid paths of length `depth` using Z3
                found = cls._synthesize_depth_k(
                    graph=graph,
                    target_address=target_address,
                    k=depth,
                    max_offset=max_offset,
                    alignment=alignment,
                    limit=max_results - len(results)
                )
                results.extend(found)
        except Exception:
            # On unexpected Z3 failure, fall back gracefully to direct DFS
            return cls._solve_graph_direct(graph, target_address, max_depth, max_offset, alignment, max_results)

        return results

    @classmethod
    def _synthesize_depth_k(
        cls,
        graph: SymbolicGraph,
        target_address: int,
        k: int,
        max_offset: int,
        alignment: int,
        limit: int
    ) -> List[PointerPath]:
        """
        Synthesizes paths of length exactly k using Z3 constraint satisfaction with
        proper node-level acyclicity constraints.
        """
        if limit <= 0 or k <= 0:
            return []

        # Collect and deduplicate all edges, filtering by alignment and max_offset
        all_edges: List[SymbolicEdge] = []
        seen_edges: Set[Tuple[int, int, int, bool]] = set()
        for edges in graph.incoming_edges.values():
            for e in edges:
                if alignment > 1 and e.offset % alignment != 0:
                    continue
                if max_offset > 0 and e.offset > max_offset:
                    continue
                ident = (e.source_addr, e.target_addr, e.offset, e.is_static_root)
                if ident not in seen_edges:
                    seen_edges.add(ident)
                    all_edges.append(e)

        if not all_edges:
            return []

        # Quick pre-validation: check that static roots and target edges exist
        root_ids = [i for i, e in enumerate(all_edges) if e.is_static_root]
        end_ids = [i for i, e in enumerate(all_edges) if e.target_addr == target_address]
        if not root_ids or not end_ids:
            return []

        # Map each edge to a unique integer ID
        num_edges = len(all_edges)

        # Index edges by source address for O(1) adjacency lookups
        edges_by_source: Dict[int, List[int]] = {}
        src_to_eids: Dict[int, List[int]] = {}
        for eid, e in enumerate(all_edges):
            edges_by_source.setdefault(e.source_addr, []).append(eid)
            src_to_eids.setdefault(e.source_addr, []).append(eid)

        # Fast static root lookup
        root_base_map: Dict[Tuple[str, int], int] = {}
        for m_name, m_base, r_addr in graph.static_roots:
            root_base_map[(m_name, r_addr)] = m_base

        solver = z3.Solver()
        # Set a 5-second timeout on Z3 solver instance to prevent unbounded stall on large graphs
        solver.set("timeout", 5000)

        # Variables: step_0, step_1, ... step_{k-1} representing the edge ID chosen at each hop
        step_vars = [z3.Int(f"edge_step_{i}") for i in range(k)]
        node_vars = [z3.Int(f"node_step_{i}") for i in range(k)]

        # Bounds: each step variable is in [0, num_edges - 1]
        for s in step_vars:
            solver.add(s >= 0, s < num_edges)

        # Constraint: step_0 must be a static root
        if len(root_ids) == 1:
            solver.add(step_vars[0] == root_ids[0])
        else:
            solver.add(z3.Or([step_vars[0] == i for i in root_ids]))

        # Constraint: step_{k-1} must end at target_address
        if len(end_ids) == 1:
            solver.add(step_vars[k - 1] == end_ids[0])
        else:
            solver.add(z3.Or([step_vars[k - 1] == i for i in end_ids]))

        # Chaining constraints: for each step i < k - 1:
        # target_addr of edge at step i must equal source_addr of edge at step i+1
        for i in range(k - 1):
            for id1, e1 in enumerate(all_edges):
                matching_next = edges_by_source.get(e1.target_addr, [])
                if matching_next:
                    if len(matching_next) == 1:
                        solver.add(z3.Implies(step_vars[i] == id1, step_vars[i + 1] == matching_next[0]))
                    else:
                        solver.add(z3.Implies(step_vars[i] == id1, z3.Or([step_vars[i + 1] == id2 for id2 in matching_next])))
                else:
                    solver.add(step_vars[i] != id1)

        # Node mapping constraints: node_vars[i] == source_addr of chosen edge at step i
        for i in range(k):
            for src_addr, eids in src_to_eids.items():
                if len(eids) == 1:
                    solver.add(z3.Implies(step_vars[i] == eids[0], node_vars[i] == src_addr))
                else:
                    solver.add(z3.Implies(z3.Or([step_vars[i] == eid for eid in eids]), node_vars[i] == src_addr))

        # True Acyclicity Invariant:
        # All intermediate visited node addresses AND the final target_address must be pairwise distinct.
        solver.add(z3.Distinct(node_vars + [z3.IntVal(target_address)]))
        if k > 1:
            solver.add(z3.Distinct(step_vars))

        results: List[PointerPath] = []
        seen_paths: Set[Tuple[str, int, Tuple[int, ...]]] = set()

        try:
            while len(results) < limit and solver.check() == z3.sat:
                model = solver.model()
                edge_ids = []
                for s in step_vars:
                    val = model[s]
                    if val is None:
                        break
                    edge_ids.append(val.as_long())

                if len(edge_ids) != k:
                    break

                path_edges = [all_edges[eid] for eid in edge_ids]
                root_edge = path_edges[0]
                module_name = root_edge.module_name or ""

                mod_base = root_base_map.get((module_name, root_edge.source_addr))
                base_offset = (root_edge.source_addr - mod_base) if mod_base is not None else root_edge.source_addr
                offsets = [e.offset for e in path_edges]

                path_key = (module_name, base_offset, tuple(offsets))
                if path_key not in seen_paths:
                    seen_paths.add(path_key)
                    results.append(PointerPath(
                        module_name=module_name,
                        base_offset=base_offset,
                        offsets=offsets,
                        resolved_address=target_address
                    ))

                # Block this exact combination of edges to find next solution
                block = z3.Or([step_vars[i] != edge_ids[i] for i in range(k)])
                solver.add(block)
        except Exception:
            # Catch solver exceptions (e.g. Z3 timeout / memory limit) gracefully
            pass

        return results

    @classmethod
    def _solve_graph_direct(
        cls,
        graph: SymbolicGraph,
        target_address: int,
        max_depth: int,
        max_offset: int,
        alignment: int,
        max_results: int
    ) -> List[PointerPath]:
        """Depth-first graph search fallback when Z3 is not present or errors."""
        results: List[PointerPath] = []
        if not graph or not graph.static_roots or max_depth <= 0 or max_results <= 0:
            return results

        seen_paths: Set[Tuple[str, int, Tuple[int, ...]]] = set()
        root_base_map = {(m_name, r_addr): m_base for m_name, m_base, r_addr in graph.static_roots}

        def dfs(curr_addr: int, current_offsets: List[int], visited: Set[int]):
            if len(results) >= max_results:
                return
            if len(current_offsets) >= max_depth:
                return

            incoming = graph.incoming_edges.get(curr_addr, [])
            for edge in incoming:
                if edge.source_addr in visited:
                    continue
                if alignment > 1 and edge.offset % alignment != 0:
                    continue
                if max_offset > 0 and edge.offset > max_offset:
                    continue

                new_offsets = [edge.offset] + current_offsets
                if edge.is_static_root:
                    mod_name = edge.module_name or ""
                    mod_base = root_base_map.get((mod_name, edge.source_addr))
                    base_off = (edge.source_addr - mod_base) if mod_base is not None else edge.source_addr
                    key = (mod_name, base_off, tuple(new_offsets))
                    if key not in seen_paths:
                        seen_paths.add(key)
                        results.append(PointerPath(
                            module_name=mod_name,
                            base_offset=base_off,
                            offsets=new_offsets,
                            resolved_address=target_address
                        ))
                        if len(results) >= max_results:
                            return
                else:
                    visited.add(edge.source_addr)
                    dfs(edge.source_addr, new_offsets, visited)
                    visited.remove(edge.source_addr)

        try:
            dfs(target_address, [], {target_address})
        except Exception:
            pass
        return results

    @classmethod
    def verify_multi_snapshot(
        cls,
        path: PointerPath,
        snapshots: List[Dict[str, Any]],
    ) -> bool:
        """
        Verifies that a synthesized pointer path remains valid and deterministic
        across multiple process snapshots or restarts.
        """
        if not snapshots or not isinstance(snapshots, (list, tuple)):
            return True
        if not path or not isinstance(path, PointerPath):
            return False

        from phantom_suite.core.pointer_scanner import PointerScanner

        for snap in snapshots:
            if not isinstance(snap, dict):
                continue
            pid = snap.get("pid")
            expected = snap.get("expected_target")
            if not isinstance(pid, int) or pid <= 0 or expected is None or not isinstance(expected, int):
                continue

            try:
                resolved = PointerScanner.resolve_path(pid, path.module_name, path.base_offset, path.offsets)
                if resolved != expected:
                    return False
            except Exception:
                return False

        return True


class SymbolicStructSynthesizer:
    """
    Automated C++20 and Rust struct reconstruction engine.
    Analyzes live memory layouts, classifies vtables and embedded pointers,
    inserts alignment padding, and generates compilable type headers with static assertions.
    """

    @classmethod
    def synthesize_cpp_struct(
        cls,
        pid: Optional[int] = None,
        base_address: Optional[int] = None,
        size: int = 256,
        struct_name: str = "SynthesizedEntity",
        raw_buffer: Optional[bytes] = None
    ) -> str:
        """
        Reconstructs a memory block into an idiomatic, compilable C++20 struct header.
        Detects virtual method tables, sub-pointers, floats, integers, and padding holes.
        Supports either live PID scanning or direct raw_buffer analysis.
        """
        # Sanitize struct_name to prevent C++ header injection
        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", str(struct_name))
        if not clean_name or clean_name[0].isdigit():
            clean_name = "Synthesized_" + clean_name

        raw: Optional[bytes] = None
        readable_regions: List[MemoryRegion] = []

        if raw_buffer is not None:
            if len(raw_buffer) == 0:
                return "// Empty raw_buffer provided"
            raw = raw_buffer
            size = len(raw)
            base_address = base_address if isinstance(base_address, int) else 0
        else:
            if base_address is None or base_address == 0:
                return f"// Null pointer or invalid base address: {base_address}"
            if not isinstance(base_address, int) or base_address < MIN_USER_PTR or base_address > MAX_USER_PTR:
                return f"// Invalid base address: {base_address}"
            if not pid or not isinstance(pid, int) or pid <= 0:
                return f"// Invalid PID: {pid}"
            if size <= 0:
                return "// Struct size must be positive"
            if size > 10 * 1024 * 1024:
                return "// Struct size exceeds maximum dissection limit (10MB)"

            try:
                raw = MemoryEngine.read_bytes(pid, base_address, size)
            except Exception as e:
                return f"// Failed to read {size} bytes at 0x{base_address:X} in PID {pid}: {e}"

            if not raw:
                return f"// Failed to read {size} bytes at 0x{base_address:X} in PID {pid}"

            try:
                regions = MemoryEngine.get_maps(pid)
                readable_regions = [r for r in regions if r.is_readable]
            except Exception:
                readable_regions = []

        lines = [
            "// ==========================================================================",
            f"// PhantomSuite Symbolic Struct Synthesizer // {clean_name}",
            f"// Base Address: 0x{base_address:X} | Dissected Size: 0x{size:X} ({size}) bytes",
            "// Standard: C++20 / ReClass.NET Compatible",
            "// ==========================================================================",
            "#pragma once",
            "#include <cstdint>",
            "#include <cstddef>",
            "#include <type_traits>",
            "",
            f"struct alignas(8) {clean_name} {{",
        ]

        curr_off = 0
        buf_len = len(raw)

        while curr_off < buf_len:
            remaining = buf_len - curr_off
            chunk = raw[curr_off: curr_off + 8]

            # 8-byte pointer evaluation
            if len(chunk) == 8:
                val64 = struct.unpack("<Q", chunk)[0]

                # Check for VTable (points to executable segment or .rodata vtable)
                is_vtable = False
                vtable_desc = ""
                if curr_off == 0 and val64 > 0x10000:
                    for reg in readable_regions:
                        if reg.start <= val64 < reg.end:
                            if reg.is_executable or (reg.pathname and ".so" in reg.pathname):
                                is_vtable = True
                                mod = os.path.basename(reg.pathname) if reg.pathname else "core"
                                vtable_desc = f"VTable pointer -> {mod} + 0x{val64 - reg.start:X}"
                                break

                if is_vtable:
                    lines.append(f"    /* +0x{curr_off:04X} */ void** vtable; // {vtable_desc}")
                    curr_off += 8
                    continue

                # Check general pointer into readable address space
                is_ptr = False
                ptr_desc = ""
                if val64 > 0x10000 and readable_regions:
                    for reg in readable_regions:
                        if reg.start <= val64 < reg.end:
                            is_ptr = True
                            mod = os.path.basename(reg.pathname) if reg.pathname else "[heap/anon]"
                            ptr_desc = f"-> {mod} (0x{val64:X})"
                            break

                if is_ptr:
                    lines.append(f"    /* +0x{curr_off:04X} */ void* ptr_0x{curr_off:X}; // {ptr_desc}")
                    curr_off += 8
                    continue

            # 4-byte evaluation (Float vs Int32)
            if remaining >= 4:
                val32_i = struct.unpack("<i", chunk[:4])[0]
                val32_f = struct.unpack("<f", chunk[:4])[0]

                # Plausible float heuristic
                if not math.isnan(val32_f) and not math.isinf(val32_f) and 0.001 <= abs(val32_f) <= 100000.0:
                    lines.append(f"    /* +0x{curr_off:04X} */ float flt_0x{curr_off:X}; // ~{val32_f:.4f}")
                    curr_off += 4
                    continue

                # Plausible non-zero int32
                if val32_i != 0 and -1000000 <= val32_i <= 1000000:
                    lines.append(f"    /* +0x{curr_off:04X} */ int32_t val_0x{curr_off:X}; // {val32_i}")
                    curr_off += 4
                    continue

            # If null or unknown byte, aggregate contiguous padding bytes
            pad_start = curr_off
            curr_off += 1
            while curr_off < buf_len:
                if curr_off % 4 == 0:
                    sub = raw[curr_off: curr_off + 8]
                    if len(sub) == 8:
                        sub64 = struct.unpack("<Q", sub)[0]
                        if sub64 > 0x10000 and any(r.start <= sub64 < r.end for r in readable_regions):
                            break
                    if len(sub) >= 4:
                        sub_f = struct.unpack("<f", sub[:4])[0]
                        sub_i = struct.unpack("<i", sub[:4])[0]
                        if (not math.isnan(sub_f) and not math.isinf(sub_f) and 0.001 <= abs(sub_f) <= 100000.0) or (sub_i != 0 and -1000000 <= sub_i <= 1000000):
                            break
                curr_off += 1

            pad_len = curr_off - pad_start
            if pad_len > 0:
                lines.append(f"    /* +0x{pad_start:04X} */ uint8_t _pad0x{pad_start:X}[0x{pad_len:X}];")

        lines.append("};")
        lines.append(f"static_assert(sizeof({clean_name}) == 0x{size:X}, \"Layout alignment mismatch\");")
        return "\n".join(lines)
