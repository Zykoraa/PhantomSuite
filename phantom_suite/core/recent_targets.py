"""
PhantomSuite Recent Targets Manager
Persists and retrieves recently attached processes across sessions.
"""

import json
import os
import time
from typing import List, Dict, Any, Optional

CONFIG_DIR = os.path.expanduser("~/.config/phantom-suite")
HISTORY_FILE = os.path.join(CONFIG_DIR, "recent_targets.json")
MAX_RECENT_TARGETS = 8


class RecentTargetsManager:
    """Manages history of attached target processes."""

    @classmethod
    def _ensure_dir(cls):
        os.makedirs(CONFIG_DIR, exist_ok=True)

    @classmethod
    def get_recents(cls) -> List[Dict[str, Any]]:
        """Returns list of recent target dictionaries ordered by newest first."""
        if not os.path.exists(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    @classmethod
    def add_target(cls, pid: int, name: str, exe_path: str = "") -> List[Dict[str, Any]]:
        """Adds a target to the recent history, deduplicating by executable name or path."""
        cls._ensure_dir()
        recents = cls.get_recents()

        entry = {
            "pid": pid,
            "name": name,
            "exe_path": exe_path,
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # Filter out duplicates by name or path
        recents = [r for r in recents if r.get("name") != name and (not exe_path or r.get("exe_path") != exe_path)]
        recents.insert(0, entry)
        recents = recents[:MAX_RECENT_TARGETS]

        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump(recents, f, indent=2)
        except Exception:
            pass

        return recents

    @classmethod
    def clear(cls):
        """Clears target history."""
        if os.path.exists(HISTORY_FILE):
            try:
                os.remove(HISTORY_FILE)
            except Exception:
                pass
