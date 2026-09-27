"""
PhantomSuite Cheat Table Serializer
Saves and loads .phantom cheat table files with module relative offset resolution
to ensure addresses survive ASLR and process restarts.
"""

import json
import os
from typing import List, Dict, Any, Optional, Tuple
from phantom_suite.core.memory_engine import MemoryEngine, TypeFormat


class TableSerializer:
    """Serializes and deserializes cheat tables to and from JSON (.phantom)."""

    VERSION = "1.0"

    @classmethod
    def get_module_base(cls, pid: int, module_name: str) -> Optional[int]:
        """Finds the base load address (lowest start address) of a module in PID."""
        regions = MemoryEngine.get_maps(pid)
        bases = [r.start for r in regions if r.pathname and os.path.basename(r.pathname) == module_name]
        return min(bases) if bases else None

    @classmethod
    def resolve_module_offset(cls, pid: int, address: int) -> Tuple[str, int]:
        """
        Finds the base module containing address and computes the relative offset
        from the module's base load address. Returns (module_name, offset).
        """
        regions = MemoryEngine.get_maps(pid)
        target_mod = ""
        for r in regions:
            if r.start <= address < r.end:
                if r.pathname and r.pathname.startswith("/"):
                    target_mod = os.path.basename(r.pathname)
                    break

        if target_mod:
            base = cls.get_module_base(pid, target_mod)
            if base is not None:
                return target_mod, address - base

        return "", address

    @classmethod
    def resolve_absolute_address(cls, pid: int, module_name: str, offset: int) -> Optional[int]:
        """Calculates absolute address given module base + offset."""
        if not module_name:
            return offset

        base = cls.get_module_base(pid, module_name)
        if base is not None:
            return base + offset
        return None

    @classmethod
    def save_table(
        cls,
        filepath: str,
        pid: Optional[int],
        entries: List[Dict[str, Any]],
        target_name: str = ""
    ) -> Tuple[bool, str]:
        """
        Saves cheat table entries to filepath (.phantom).
        Each entry has: {description, address, type, value, frozen}
        """
        try:
            records = []
            for e in entries:
                addr = int(e.get("address", 0))
                mod_name = ""
                offset = addr

                if pid and pid > 0:
                    mod_name, offset = cls.resolve_module_offset(pid, addr)

                records.append({
                    "description": e.get("description", "Untitled"),
                    "type": e.get("type", TypeFormat.INT32),
                    "value": str(e.get("value", "")),
                    "frozen": bool(e.get("frozen", False)),
                    "module": mod_name,
                    "offset": f"0x{offset:X}",
                    "static_address": f"0x{addr:X}"
                })

            data = {
                "format": "phantom-table",
                "version": cls.VERSION,
                "target_name": target_name,
                "entries": records
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            return True, f"Saved {len(records)} entries to {os.path.basename(filepath)}."
        except Exception as e:
            return False, f"Failed to save table: {str(e)}"

    @classmethod
    def load_table(
        cls,
        filepath: str,
        pid: Optional[int]
    ) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """
        Loads cheat table from filepath (.phantom) and re-resolves addresses if target PID is provided.
        Returns (entries, status_message).
        """
        if not os.path.exists(filepath):
            return None, f"File not found: {filepath}"

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("format") != "phantom-table":
                return None, "Invalid format: Not a PhantomSuite table (.phantom)."

            raw_entries = data.get("entries", [])
            resolved_entries = []

            for r in raw_entries:
                mod_name = r.get("module", "")
                offset_str = r.get("offset", "0x0")
                offset = int(offset_str, 16) if offset_str.startswith("0x") else int(offset_str)
                static_addr_str = r.get("static_address", "0x0")
                static_addr = int(static_addr_str, 16) if static_addr_str.startswith("0x") else int(static_addr_str)

                final_addr = static_addr
                if pid and pid > 0 and mod_name:
                    dyn_addr = cls.resolve_absolute_address(pid, mod_name, offset)
                    if dyn_addr is not None:
                        final_addr = dyn_addr

                resolved_entries.append({
                    "description": r.get("description", "Untitled"),
                    "type": r.get("type", TypeFormat.INT32),
                    "value": r.get("value", "0"),
                    "frozen": r.get("frozen", False),
                    "address": final_addr,
                    "module": mod_name
                })

            return resolved_entries, f"Loaded {len(resolved_entries)} entries successfully."
        except Exception as e:
            return None, f"Failed to load table: {str(e)}"
