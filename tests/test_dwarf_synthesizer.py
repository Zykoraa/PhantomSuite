"""
Automated Unit Tests for PhantomSuite DWARF Type Synthesizer
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phantom_suite.core.dwarf_synthesizer import DwarfSynthesizer, DwarfStruct, DwarfMember


class TestDwarfSynthesizer(unittest.TestCase):
    def setUp(self):
        self.dwarf_bin = os.path.join(os.path.dirname(__file__), "test_dwarf_target")
        if not os.path.exists(self.dwarf_bin):
            src = os.path.join(os.path.dirname(__file__), "test_dwarf_target.c")
            import subprocess
            subprocess.run(["gcc", "-g", "-O0", src, "-o", self.dwarf_bin], check=True)

    def test_dwarf_available(self):
        self.assertTrue(DwarfSynthesizer.is_available(), "pyelftools should be available")

    def test_extract_structures(self):
        structs = DwarfSynthesizer.extract_structures_from_file(self.dwarf_bin)
        self.assertIn("PlayerData", structs)
        self.assertIn("GameSession", structs)

        player = structs["PlayerData"]
        self.assertEqual(player.name, "PlayerData")
        self.assertGreater(player.byte_size, 0)
        
        member_names = [m.name for m in player.members]
        self.assertIn("player_id", member_names)
        self.assertIn("health", member_names)
        self.assertIn("username", member_names)
        self.assertIn("inventory_ptr", member_names)

        # Verify C header emission
        header = player.to_c_header()
        self.assertIn("typedef struct PlayerData", header)
        self.assertIn("_Static_assert(sizeof(PlayerData)", header)

    def test_empty_or_missing_file(self):
        self.assertEqual(DwarfSynthesizer.extract_structures_from_file(""), {})
        self.assertEqual(DwarfSynthesizer.extract_structures_from_file("/nonexistent/bin"), {})


if __name__ == "__main__":
    unittest.main()
