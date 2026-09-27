"""
PhantomSuite Thread Manager
Enumerates threads via /proc/<pid>/task/, inspects thread CPU core affinity,
and provides per-thread pause/resume controls using libc tgkill.
"""

import os
import signal
import ctypes
from typing import List, Optional, Set
from dataclasses import dataclass

try:
    _libc = ctypes.CDLL("libc.so.6", use_errno=True)
    _tgkill = _libc.tgkill
    _tgkill.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    _tgkill.restype = ctypes.c_int
except Exception:
    _tgkill = None


@dataclass
class ThreadInfo:
    tid: int
    name: str
    state: str
    cpu_id: int
    affinity: List[int]
    utime: float
    stime: float


class ThreadManager:
    """Manages thread inspection, signals, and CPU affinity for target processes."""

    @classmethod
    def list_threads(cls, pid: int) -> List[ThreadInfo]:
        """Scans /proc/<pid>/task/ to discover all active thread tasks."""
        threads: List[ThreadInfo] = []
        task_dir = f"/proc/{pid}/task"

        if not os.path.exists(task_dir):
            return threads

        try:
            entries = os.listdir(task_dir)
        except Exception:
            return threads

        clock_ticks = os.sysconf("SC_CLK_TCK") or 100

        for entry in entries:
            if not entry.isdigit():
                continue
            tid = int(entry)
            tid_dir = f"{task_dir}/{tid}"

            # Name
            name = ""
            comm_path = f"{tid_dir}/comm"
            if os.path.exists(comm_path):
                try:
                    with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                        name = f.read().strip()
                except Exception:
                    name = f"tid_{tid}"

            # State & CPU stats from stat
            state = "?"
            cpu_id = 0
            utime = 0.0
            stime = 0.0
            stat_path = f"{tid_dir}/stat"
            if os.path.exists(stat_path):
                try:
                    with open(stat_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().strip()
                        # Extract everything after the last ')' to safely skip thread names with spaces
                        rparen = content.rfind(')')
                        if rparen != -1:
                            parts = content[rparen + 2:].split()
                            if len(parts) >= 37:
                                state = parts[0]
                                utime = round(int(parts[11]) / clock_ticks, 2)
                                stime = round(int(parts[12]) / clock_ticks, 2)
                                cpu_id = int(parts[36])
                except Exception:
                    pass

            # Core Affinity
            affinity: List[int] = []
            try:
                affinity = sorted(list(os.sched_getaffinity(tid)))
            except Exception:
                pass

            threads.append(ThreadInfo(
                tid=tid,
                name=name,
                state=state,
                cpu_id=cpu_id,
                affinity=affinity,
                utime=utime,
                stime=stime
            ))

        threads.sort(key=lambda t: t.tid)
        return threads

    @classmethod
    def pause_thread(cls, pid: int, tid: int) -> bool:
        """Sends SIGSTOP to a specific thread via tgkill."""
        if _tgkill:
            res = _tgkill(pid, tid, signal.SIGSTOP)
            return res == 0
        return False

    @classmethod
    def resume_thread(cls, pid: int, tid: int) -> bool:
        """Sends SIGCONT to a specific thread via tgkill."""
        if _tgkill:
            res = _tgkill(pid, tid, signal.SIGCONT)
            return res == 0
        return False

    @classmethod
    def set_thread_affinity(cls, tid: int, cpus: List[int]) -> bool:
        """Sets CPU core affinity mask for target thread."""
        try:
            os.sched_setaffinity(tid, set(cpus))
            return True
        except Exception:
            return False
