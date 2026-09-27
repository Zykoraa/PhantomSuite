"""
PhantomSuite Shared Library (.so) Injector
Injects and inspects shared objects into running Linux processes
using GDB dlopen with /proc/<pid>/maps verification.
"""

import os
import subprocess
from typing import Tuple, List, Optional
from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion


class Injector:
    """Manages .so injection and module verification for Linux processes."""

    @staticmethod
    def get_loaded_modules(pid: int) -> List[MemoryRegion]:
        """Returns all mapped .so libraries and binaries for the target process."""
        regions = MemoryEngine.get_maps(pid)
        seen_paths = set()
        modules = []
        for r in regions:
            if r.pathname and r.pathname.startswith("/") and r.pathname not in seen_paths:
                seen_paths.add(r.pathname)
                modules.append(r)
        return modules

    @staticmethod
    def is_module_loaded(pid: int, so_path: str) -> bool:
        """Checks /proc/<pid>/maps to see if so_path (or its basename) is already mapped."""
        basename = os.path.basename(so_path)
        regions = MemoryEngine.get_maps(pid)
        for r in regions:
            if basename in r.pathname:
                return True
        return False

    @classmethod
    def inject(cls, pid: int, so_path: str, elevate_if_needed: bool = True) -> Tuple[bool, str]:
        """
        Injects so_path into target PID via GDB dlopen().
        Returns (success: bool, message: str).
        """
        so_path = os.path.abspath(so_path)
        if not os.path.exists(so_path):
            return False, f"Shared object file not found: {so_path}"

        if not os.path.exists(f"/proc/{pid}"):
            return False, f"Target process PID {pid} is not running."

        # Check if already loaded
        if cls.is_module_loaded(pid, so_path):
            return True, f"Module '{os.path.basename(so_path)}' is already loaded in PID {pid}."

        # Prepare GDB commands
        # RTLD_NOW is 2
        gdb_cmd = [
            "gdb", "-q", "-batch",
            "-ex", f"attach {pid}",
            "-ex", f'call (void*)dlopen("{so_path}", 2)',
            "-ex", "detach",
            "-ex", "quit"
        ]

        def run_gdb(cmd_list):
            return subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=8
            )

        try:
            res = run_gdb(gdb_cmd)
            stdout = res.stdout
            stderr = res.stderr
            combined = (stdout + "\n" + stderr).strip()

            # Check for permission denied / ptrace hint
            if "Operation not permitted" in combined and elevate_if_needed:
                # Retry with pkexec
                pkexec_cmd = ["pkexec"] + gdb_cmd
                res = run_gdb(pkexec_cmd)
                combined = (res.stdout + "\n" + res.stderr).strip()

            # Verify through maps
            if cls.is_module_loaded(pid, so_path):
                return True, f"Successfully injected {os.path.basename(so_path)} into PID {pid}!"

            # If not in maps, check return value of dlopen
            if "$1 = (void *) 0x0" in combined or "$1 = 0x0" in combined:
                return False, f"dlopen() returned NULL in target. Missing dependencies or wrong arch?\nGDB Output:\n{combined}"

            return False, f"Injection finished but module was not found in /proc/{pid}/maps.\nGDB Output:\n{combined}"

        except subprocess.TimeoutExpired:
            return False, "GDB injection timed out after 8 seconds."
        except FileNotFoundError:
            return False, "gdb command not found. Please install gdb."
        except Exception as e:
            return False, f"Injection error: {str(e)}"

    @classmethod
    def unload(cls, pid: int, so_name: str) -> Tuple[bool, str]:
        """
        Attempts to call dlclose on the target module in PID.
        """
        basename = os.path.basename(so_name)
        # Find mapped address in maps
        regions = MemoryEngine.get_maps(pid)
        target_reg = None
        for r in regions:
            if basename in r.pathname:
                target_reg = r
                break

        if not target_reg:
            return False, f"Module '{basename}' is not loaded in PID {pid}."

        # Call dlclose in GDB
        gdb_cmd = [
            "gdb", "-q", "-batch",
            "-ex", f"attach {pid}",
            "-ex", f'call (int)dlclose((void*)0x{target_reg.start:x})',
            "-ex", "detach",
            "-ex", "quit"
        ]
        try:
            res = subprocess.run(gdb_cmd, capture_output=True, text=True, timeout=8)
            return True, f"Unload command executed for {basename}."
        except Exception as e:
            return False, f"Unload failed: {str(e)}"
