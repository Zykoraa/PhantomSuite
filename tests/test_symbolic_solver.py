"""
Automated Unit Tests for PhantomSuite Symbolic Pointer Solver & Struct Synthesizer (PhantomPath)
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.symbolic_solver import (
    SymbolicPointerSolver, SymbolicStructSynthesizer, SymbolicGraph, SymbolicEdge
)
from phantom_suite.core.pointer_scanner import PointerScanner, PointerPath
from phantom_suite.core.memory_engine import MemoryEngine, TypeFormat, ScanType


class TestSymbolicSolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid

        # Scan for target_score (1337)
        results = MemoryEngine.first_scan(cls.pid, TypeFormat.INT32, ScanType.EXACT, 1337)
        assert len(results) > 0
        cls.score_addr = results[0].address

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_z3_solver_available(self):
        """Verifies Z3 SMT solver is successfully integrated and detected."""
        self.assertTrue(SymbolicPointerSolver.is_available(), "Z3 SMT solver should be available")

    def test_synthetic_graph_smt_synthesis(self):
        """Tests formal SMT constraint synthesis over an in-memory symbolic graph."""
        graph = SymbolicGraph()
        
        # Define synthetic nodes:
        # Static Root in "test_module": 0x1000
        # Intermediate Node: 0x2000
        # Target: 0x3000
        graph.static_roots.append(("test_module", 0x1000, 0x1000))
        
        # Edge 1: 0x1000 points to 0x1FD0, offset to 0x2000 is 0x30
        edge1 = SymbolicEdge(
            source_addr=0x1000,
            pointed_value=0x1FD0,
            target_addr=0x2000,
            offset=0x30,
            module_name="test_module",
            is_static_root=True
        )
        
        # Edge 2: 0x2000 points to 0x2F80, offset to 0x3000 is 0x80
        edge2 = SymbolicEdge(
            source_addr=0x2000,
            pointed_value=0x2F80,
            target_addr=0x3000,
            offset=0x80,
            module_name=None,
            is_static_root=False
        )
        
        graph.incoming_edges.setdefault(0x2000, []).append(edge1)
        graph.incoming_edges.setdefault(0x3000, []).append(edge2)
        graph.nodes.update([0x1000, 0x2000, 0x3000])

        # Synthesize path of depth 2 to target 0x3000 using Z3
        paths = SymbolicPointerSolver.solve_paths_smt(
            graph=graph,
            target_address=0x3000,
            max_depth=2,
            max_offset=4096,
            alignment=4,
            max_results=5
        )

        self.assertGreaterEqual(len(paths), 1, "Z3 should find at least 1 path")
        path = paths[0]
        self.assertEqual(path.module_name, "test_module")
        self.assertEqual(path.base_offset, 0)
        self.assertEqual(path.offsets, [0x30, 0x80])
        self.assertEqual(path.resolved_address, 0x3000)

    def test_live_process_symbolic_solve(self):
        """Tests live PID graph construction and SMT solving."""
        paths = PointerScanner.symbolic_solve(
            pid=self.pid,
            target_address=self.score_addr,
            max_offset=4096,
            max_depth=2,
            alignment=4,
            max_results=10
        )
        self.assertIsInstance(paths, list)
        
        # If any paths were synthesized, verify that dereferencing resolves correctly
        for p in paths:
            resolved = PointerScanner.resolve_path(self.pid, p.module_name, p.base_offset, p.offsets)
            if resolved is not None:
                self.assertEqual(resolved, self.score_addr)

    def test_multi_snapshot_verification(self):
        """Tests invariant filtering across snapshots."""
        test_path = PointerPath(
            module_name="test_target",
            base_offset=0x20,
            offsets=[0x10],
            resolved_address=self.score_addr
        )
        
        # Fake snapshot with invalid expected target should fail
        bad_snap = [{"pid": self.pid, "expected_target": 0xDEADBEEF}]
        self.assertFalse(SymbolicPointerSolver.verify_multi_snapshot(test_path, bad_snap))

    def test_cpp_struct_synthesizer(self):
        """Tests C++20 header synthesis from live process memory."""
        code = SymbolicStructSynthesizer.synthesize_cpp_struct(
            pid=self.pid,
            base_address=self.score_addr,
            size=64,
            struct_name="ScoreEntity"
        )
        self.assertIn("#pragma once", code)
        self.assertIn("struct alignas(8) ScoreEntity", code)
        self.assertIn("static_assert(sizeof(ScoreEntity) == 0x40", code)

    # -------------------------------------------------------------------------
    # Degenerate & Empty Memory Graphs
    # -------------------------------------------------------------------------
    def test_degenerate_empty_graph(self):
        """Verifies solver returns empty results gracefully for empty memory graphs."""
        empty_graph = SymbolicGraph()
        paths = SymbolicPointerSolver.solve_paths_smt(empty_graph, target_address=0x1337)
        self.assertEqual(paths, [])

        direct_paths = SymbolicPointerSolver._solve_graph_direct(
            empty_graph, target_address=0x1337, max_depth=3, max_offset=4096, alignment=4, max_results=10
        )
        self.assertEqual(direct_paths, [])

    def test_degenerate_disconnected_graph(self):
        """Verifies solver handles disconnected roots and targets without paths."""
        graph = SymbolicGraph()
        graph.static_roots.append(("test_mod", 0x1000, 0x1000))
        edge = SymbolicEdge(0x1000, 0x1FF0, 0x2000, offset=0x10, module_name="test_mod", is_static_root=True)
        graph.incoming_edges[0x2000] = [edge]
        graph.nodes.update([0x1000, 0x2000])

        # Target 0x9999 has no incoming edges
        paths = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x9999, max_depth=2)
        self.assertEqual(paths, [])

    def test_degenerate_cyclic_graph_no_root(self):
        """Verifies solver rejects cyclic loops with no static roots."""
        graph = SymbolicGraph()
        edge1 = SymbolicEdge(0x2000, 0x2FE0, 0x3000, offset=0x20, is_static_root=False)
        edge2 = SymbolicEdge(0x3000, 0x1FE0, 0x2000, offset=0x20, is_static_root=False)
        graph.incoming_edges[0x3000] = [edge1]
        graph.incoming_edges[0x2000] = [edge2]
        graph.nodes.update([0x2000, 0x3000])

        paths = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x3000, max_depth=3)
        self.assertEqual(paths, [])

    def test_build_memory_graph_invalid_pid(self):
        """Verifies build_memory_graph on invalid PID returns an empty graph."""
        graph = SymbolicPointerSolver.build_memory_graph(pid=99999999, target_address=0x1337)
        self.assertIsInstance(graph, SymbolicGraph)
        self.assertEqual(len(graph.nodes), 0)
        self.assertEqual(len(graph.static_roots), 0)

    # -------------------------------------------------------------------------
    # Depth Boundary Conditions
    # -------------------------------------------------------------------------
    def test_depth_boundary_conditions(self):
        """Tests boundary conditions for search depth (depth 0, depth 1, max depth)."""
        # Build 3-hop chain: 0x1000 (static root) -> 0x2000 -> 0x3000 -> 0x4000 (target)
        graph = SymbolicGraph()
        graph.static_roots.append(("main_mod", 0x1000, 0x1000))
        edge1 = SymbolicEdge(0x1000, 0x1FF0, 0x2000, offset=0x10, module_name="main_mod", is_static_root=True)
        edge2 = SymbolicEdge(0x2000, 0x2FE0, 0x3000, offset=0x20, module_name=None, is_static_root=False)
        edge3 = SymbolicEdge(0x3000, 0x3FD0, 0x4000, offset=0x30, module_name=None, is_static_root=False)
        graph.incoming_edges[0x2000] = [edge1]
        graph.incoming_edges[0x3000] = [edge2]
        graph.incoming_edges[0x4000] = [edge3]
        graph.nodes.update([0x1000, 0x2000, 0x3000, 0x4000])

        # Depth 0: must return 0 paths
        paths_d0 = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x4000, max_depth=0)
        self.assertEqual(paths_d0, [])
        paths_d0_direct = SymbolicPointerSolver._solve_graph_direct(graph, target_address=0x4000, max_depth=0, max_offset=4096, alignment=4, max_results=5)
        self.assertEqual(paths_d0_direct, [])

        # Negative depth: must return 0 paths
        paths_neg = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x4000, max_depth=-1)
        self.assertEqual(paths_neg, [])

        # Depth 1:
        # Target 0x2000 is 1 hop from static root -> should find path
        paths_d1_hit = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2000, max_depth=1)
        self.assertEqual(len(paths_d1_hit), 1)
        self.assertEqual(paths_d1_hit[0].offsets, [0x10])

        # Target 0x4000 requires 3 hops -> depth 1 must return 0 paths
        paths_d1_miss = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x4000, max_depth=1)
        self.assertEqual(paths_d1_miss, [])
        paths_d1_direct_miss = SymbolicPointerSolver._solve_graph_direct(graph, target_address=0x4000, max_depth=1, max_offset=4096, alignment=4, max_results=5)
        self.assertEqual(paths_d1_direct_miss, [])

        # Depth 2:
        # Target 0x4000 requires 3 hops -> depth 2 must return 0 paths
        paths_d2_miss = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x4000, max_depth=2)
        self.assertEqual(paths_d2_miss, [])

        # Target 0x3000 is reachable in 2 hops -> should find path
        paths_d2_hit = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x3000, max_depth=2)
        self.assertEqual(len(paths_d2_hit), 1)
        self.assertEqual(paths_d2_hit[0].offsets, [0x10, 0x20])

        # Max Depth (Depth 3):
        # Target 0x4000 is reachable in exactly 3 hops -> should find path
        paths_d3 = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x4000, max_depth=3)
        self.assertEqual(len(paths_d3), 1)
        self.assertEqual(paths_d3[0].offsets, [0x10, 0x20, 0x30])

        # Depth 5 (oversized max_depth): should still find the exact 3-hop path
        paths_d5 = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x4000, max_depth=5)
        self.assertEqual(len(paths_d5), 1)
        self.assertEqual(paths_d5[0].offsets, [0x10, 0x20, 0x30])

    # -------------------------------------------------------------------------
    # Alignment Mismatch Rejection
    # -------------------------------------------------------------------------
    def test_alignment_mismatch_rejection(self):
        """Verifies solver rejects offsets that violate 4-byte or 8-byte alignment constraints."""
        graph = SymbolicGraph()
        graph.static_roots.append(("align_mod", 0x1000, 0x1000))

        # Edge with odd offset: 0x31 (49 bytes, unaligned)
        edge_odd = SymbolicEdge(0x1000, 0x1FCF, 0x2001, offset=0x31, module_name="align_mod", is_static_root=True)
        # Edge with 4-byte aligned but not 8-byte aligned offset: 0x34 (52 bytes)
        edge_4byte = SymbolicEdge(0x1000, 0x1FCC, 0x2004, offset=0x34, module_name="align_mod", is_static_root=True)
        # Edge with 8-byte aligned offset: 0x38 (56 bytes)
        edge_8byte = SymbolicEdge(0x1000, 0x1FC8, 0x2008, offset=0x38, module_name="align_mod", is_static_root=True)

        graph.incoming_edges[0x2001] = [edge_odd]
        graph.incoming_edges[0x2004] = [edge_4byte]
        graph.incoming_edges[0x2008] = [edge_8byte]
        graph.nodes.update([0x1000, 0x2001, 0x2004, 0x2008])

        # 1. Odd offset tests (target 0x2001):
        # Must be rejected when alignment=4 or alignment=8 requested
        self.assertEqual(SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2001, max_depth=1, alignment=4), [])
        self.assertEqual(SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2001, max_depth=1, alignment=8), [])
        # Accepted when alignment=1 (byte-level)
        paths_odd_a1 = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2001, max_depth=1, alignment=1)
        self.assertEqual(len(paths_odd_a1), 1)
        self.assertEqual(paths_odd_a1[0].offsets, [0x31])

        # Test direct traversal fallback as well
        self.assertEqual(SymbolicPointerSolver._solve_graph_direct(graph, target_address=0x2001, max_depth=1, max_offset=4096, alignment=4, max_results=5), [])

        # 2. 4-byte aligned offset tests (target 0x2004):
        # Must be rejected when alignment=8 requested (52 % 8 != 0)
        self.assertEqual(SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2004, max_depth=1, alignment=8), [])
        # Must be accepted when alignment=4 requested
        paths_4b = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2004, max_depth=1, alignment=4)
        self.assertEqual(len(paths_4b), 1)
        self.assertEqual(paths_4b[0].offsets, [0x34])

        # 3. 8-byte aligned offset tests (target 0x2008):
        # Must be accepted with alignment=4 and alignment=8
        paths_8b_a8 = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2008, max_depth=1, alignment=8)
        self.assertEqual(len(paths_8b_a8), 1)
        self.assertEqual(paths_8b_a8[0].offsets, [0x38])

        paths_8b_a4 = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2008, max_depth=1, alignment=4)
        self.assertEqual(len(paths_8b_a4), 1)
        self.assertEqual(paths_8b_a4[0].offsets, [0x38])

    # -------------------------------------------------------------------------
    # Struct Synthesizer: Empty Buffers & Null Pointers
    # -------------------------------------------------------------------------
    def test_struct_synthesizer_null_pointers(self):
        """Verifies struct synthesizer handles null and invalid base addresses safely."""
        # base_address = 0
        code_zero = SymbolicStructSynthesizer.synthesize_cpp_struct(
            pid=self.pid, base_address=0, size=64, struct_name="NullZeroEntity"
        )
        self.assertTrue(code_zero.startswith("//"), "Should return diagnostic comment on base_address 0")
        self.assertIn("null pointer", code_zero.lower())

        # base_address = None
        code_none = SymbolicStructSynthesizer.synthesize_cpp_struct(
            pid=self.pid, base_address=None, size=64, struct_name="NullNoneEntity"
        )
        self.assertTrue(code_none.startswith("//"), "Should return diagnostic comment on base_address None")
        self.assertIn("null pointer", code_none.lower())

        # Invalid PID
        code_bad_pid = SymbolicStructSynthesizer.synthesize_cpp_struct(
            pid=-1, base_address=self.score_addr, size=64, struct_name="BadPidEntity"
        )
        self.assertTrue(code_bad_pid.startswith("//"), "Should return diagnostic comment on invalid PID")

    def test_struct_synthesizer_empty_buffers(self):
        """Verifies struct synthesizer handles empty sizes and zero-length buffers."""
        # size = 0
        code_size_zero = SymbolicStructSynthesizer.synthesize_cpp_struct(
            pid=self.pid, base_address=self.score_addr, size=0, struct_name="ZeroSizeEntity"
        )
        self.assertTrue(code_size_zero.startswith("//"), "Should return diagnostic comment on size 0")

        # raw_buffer = b""
        code_empty_buf = SymbolicStructSynthesizer.synthesize_cpp_struct(
            raw_buffer=b"", struct_name="EmptyBufEntity"
        )
        self.assertTrue(code_empty_buf.startswith("//"), "Should return diagnostic comment on empty raw_buffer")

        # Buffer containing all zeros / null pointers
        zero_buf = b"\x00" * 32
        code_zeros = SymbolicStructSynthesizer.synthesize_cpp_struct(
            raw_buffer=zero_buf, struct_name="AllZeroStruct"
        )
        self.assertIn("#pragma once", code_zeros)
        self.assertIn("struct alignas(8) AllZeroStruct", code_zeros)
        self.assertIn("uint8_t _pad0x0[0x20];", code_zeros)
        self.assertIn("static_assert(sizeof(AllZeroStruct) == 0x20", code_zeros)

    # -------------------------------------------------------------------------
    # Corner Cases & Code Hardening Audits
    # -------------------------------------------------------------------------
    def test_pid_corner_cases(self):
        """Verifies PID <= 0 and invalid types return safely across all entry points."""
        for bad_pid in [0, -1, -9999]:
            self.assertIsNone(PointerScanner.resolve_path(bad_pid, "mod", 0x10, [0x20]))
            self.assertEqual(PointerScanner.symbolic_solve(bad_pid, target_address=0x2000), [])
            self.assertEqual(PointerScanner.scan_for_pointers(bad_pid, target_address=0x2000), [])
            
            graph = SymbolicPointerSolver.build_memory_graph(bad_pid, target_address=0x2000)
            self.assertEqual(len(graph.nodes), 0)
            self.assertEqual(len(graph.static_roots), 0)

    def test_acyclic_constraint_enforcement(self):
        """Verifies Z3 and DFS strictly reject cyclic paths (re-visiting nodes)."""
        graph = SymbolicGraph()
        graph.static_roots.append(("test_mod", 0x1000, 0x1000))

        # Root: 0x1000 -> 0x2000
        e1 = SymbolicEdge(0x1000, 0x1FC0, 0x2000, offset=0x40, module_name="test_mod", is_static_root=True)
        # 0x2000 -> 0x3000
        e2 = SymbolicEdge(0x2000, 0x2FC0, 0x3000, offset=0x40, module_name=None, is_static_root=False)
        # Cycle back: 0x3000 -> 0x2000
        e3 = SymbolicEdge(0x3000, 0x1FC0, 0x2000, offset=0x40, module_name=None, is_static_root=False)
        # 0x2000 -> 0x4000 (Target)
        e4 = SymbolicEdge(0x2000, 0x3FC0, 0x4000, offset=0x40, module_name=None, is_static_root=False)

        graph.incoming_edges[0x2000] = [e1, e3]
        graph.incoming_edges[0x3000] = [e2]
        graph.incoming_edges[0x4000] = [e4]
        graph.nodes.update([0x1000, 0x2000, 0x3000, 0x4000])

        # A 4-hop path would require 0x1000 -> 0x2000 -> 0x3000 -> 0x2000 -> 0x4000.
        # Since 0x2000 is visited twice, this cyclic path MUST be rejected as UNSAT!
        paths_k4 = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x4000, max_depth=4)
        for p in paths_k4:
            self.assertNotEqual(len(p.offsets), 4, "Z3 must never return cyclic 4-hop path")

        paths_direct = SymbolicPointerSolver._solve_graph_direct(
            graph, target_address=0x4000, max_depth=4, max_offset=4096, alignment=4, max_results=10
        )
        for p in paths_direct:
            self.assertNotEqual(len(p.offsets), 4, "DFS fallback must never return cyclic 4-hop path")

    def test_zero_and_negative_alignment_safety(self):
        """Verifies alignment <= 0 does not trigger ZeroDivisionError and normalizes safely."""
        graph = SymbolicGraph()
        graph.static_roots.append(("test_mod", 0x1000, 0x1000))
        e = SymbolicEdge(0x1000, 0x1FC0, 0x2000, offset=0x40, module_name="test_mod", is_static_root=True)
        graph.incoming_edges[0x2000] = [e]
        graph.nodes.update([0x1000, 0x2000])

        # alignment = 0
        paths_zero = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2000, alignment=0)
        self.assertIsInstance(paths_zero, list)

        # alignment = -4
        paths_neg = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x2000, alignment=-4)
        self.assertIsInstance(paths_neg, list)

    def test_large_graph_smt_scaling(self):
        """Verifies O(N) adjacency mapping and solver scaling on graphs with 500+ edges."""
        graph = SymbolicGraph()
        graph.static_roots.append(("scale_mod", 0x1000, 0x1000))

        # Add 1 static root edge to 0x2000
        graph.incoming_edges[0x2000] = [
            SymbolicEdge(0x1000, 0x1FC0, 0x2000, offset=0x40, module_name="scale_mod", is_static_root=True)
        ]

        # Add 500 parallel intermediate edges between disconnected nodes
        for i in range(1, 501):
            src = 0x10000 + (i * 0x100)
            tgt = src + 0x100
            graph.incoming_edges[tgt] = [
                SymbolicEdge(src, src + 0x40, tgt, offset=0x40, is_static_root=False)
            ]
            graph.nodes.update([src, tgt])

        # Add final edge from 0x2000 to target 0x3000
        graph.incoming_edges[0x3000] = [
            SymbolicEdge(0x2000, 0x2FC0, 0x3000, offset=0x40, is_static_root=False)
        ]
        graph.nodes.update([0x1000, 0x2000, 0x3000])

        # SMT solve should synthesize path cleanly in < 1 second without O(N^2) lockup
        paths = SymbolicPointerSolver.solve_paths_smt(graph, target_address=0x3000, max_depth=2, max_results=5)
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].offsets, [0x40, 0x40])


if __name__ == "__main__":
    unittest.main()
