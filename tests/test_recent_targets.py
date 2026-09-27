"""
Unit tests for PhantomSuite Recent Targets Manager.
"""

import os
import shutil
import tempfile
import unittest
from phantom_suite.core.recent_targets import RecentTargetsManager
import phantom_suite.core.recent_targets as rt_module


class TestRecentTargets(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orig_config_dir = rt_module.CONFIG_DIR
        self.orig_history_file = rt_module.HISTORY_FILE
        rt_module.CONFIG_DIR = self.temp_dir
        rt_module.HISTORY_FILE = os.path.join(self.temp_dir, "recent_targets.json")

    def tearDown(self):
        rt_module.CONFIG_DIR = self.orig_config_dir
        rt_module.HISTORY_FILE = self.orig_history_file
        shutil.rmtree(self.temp_dir)

    def test_add_and_get_recents(self):
        self.assertEqual(RecentTargetsManager.get_recents(), [])

        RecentTargetsManager.add_target(1234, "game_binary", "/usr/bin/game_binary")
        recents = RecentTargetsManager.get_recents()
        self.assertEqual(len(recents), 1)
        self.assertEqual(recents[0]["name"], "game_binary")
        self.assertEqual(recents[0]["pid"], 1234)

        # Add second target
        RecentTargetsManager.add_target(5678, "steam_client", "/usr/bin/steam")
        recents = RecentTargetsManager.get_recents()
        self.assertEqual(len(recents), 2)
        self.assertEqual(recents[0]["name"], "steam_client")

        # Deduplication test: re-adding game_binary should move it to top
        RecentTargetsManager.add_target(9999, "game_binary", "/usr/bin/game_binary")
        recents = RecentTargetsManager.get_recents()
        self.assertEqual(len(recents), 2)
        self.assertEqual(recents[0]["name"], "game_binary")
        self.assertEqual(recents[0]["pid"], 9999)

    def test_clear_recents(self):
        RecentTargetsManager.add_target(111, "test_app")
        self.assertEqual(len(RecentTargetsManager.get_recents()), 1)
        RecentTargetsManager.clear()
        self.assertEqual(RecentTargetsManager.get_recents(), [])


if __name__ == "__main__":
    unittest.main()
