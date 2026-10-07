"""
Automated Unit Tests for PhantomSuite Glibc Heap Chunk Introspector
"""

import unittest
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.heap_inspector import HeapInspector, HeapSnapshot, HeapChunk


class TestHeapInspector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_get_heap_region(self):
        reg = HeapInspector.get_heap_region(self.pid)
        self.assertIsNotNone(reg)
        self.assertGreater(reg.size, 0)

    def test_audit_heap_live(self):
        snap = HeapInspector.audit_heap(self.pid, max_chunks=20)
        self.assertIsNotNone(snap)
        self.assertIsInstance(snap, HeapSnapshot)
        self.assertEqual(snap.pid, self.pid)
        self.assertGreater(len(snap.chunks), 0)

        first_chunk = snap.chunks[0]
        self.assertIsInstance(first_chunk, HeapChunk)
        self.assertGreater(first_chunk.chunk_size, 0)
        self.assertIn(first_chunk.state, ("allocated", "freed", "top_chunk", "corrupted"))

    def test_invalid_pid(self):
        self.assertIsNone(HeapInspector.audit_heap(-1))
        self.assertIsNone(HeapInspector.get_heap_region(-1))


if __name__ == "__main__":
    unittest.main()
