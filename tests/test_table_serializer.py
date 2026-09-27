"""
Automated Unit Tests for PhantomSuite Table Serializer
"""

import unittest
import subprocess
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.table_serializer import TableSerializer
from phantom_suite.core.memory_engine import MemoryEngine, TypeFormat, ScanType


class TestTableSerializer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target_bin = os.path.join(os.path.dirname(__file__), "test_target")
        cls.proc = subprocess.Popen([target_bin], stdout=subprocess.PIPE, text=True)
        cls.proc.stdout.readline()
        cls.pid = cls.proc.pid

        # Find target address
        results = MemoryEngine.first_scan(cls.pid, TypeFormat.INT32, ScanType.EXACT, 1337)
        assert len(results) > 0
        cls.addr = results[0].address

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait()

    def test_save_and_load_table(self):
        entries = [
            {
                "description": "Score",
                "type": TypeFormat.INT32,
                "address": self.addr,
                "value": "1337",
                "frozen": True
            }
        ]

        with tempfile.NamedTemporaryFile(suffix=".phantom", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Save
            ok_save, msg_save = TableSerializer.save_table(tmp_path, self.pid, entries, "test_target")
            self.assertTrue(ok_save, msg_save)

            # Load
            loaded_entries, msg_load = TableSerializer.load_table(tmp_path, self.pid)
            self.assertIsNotNone(loaded_entries, msg_load)
            self.assertEqual(len(loaded_entries), 1)

            entry = loaded_entries[0]
            self.assertEqual(entry["description"], "Score")
            self.assertEqual(entry["address"], self.addr)
            self.assertEqual(entry["type"], TypeFormat.INT32)
            self.assertTrue(entry["frozen"])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
