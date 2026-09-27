"""
PhantomSuite Process Manager
Discovers processes via /proc, integrates with Hyprland IPC,
and provides process control (pause, resume, kill).
"""

import os
import signal
import subprocess
import json
import pwd
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cmdline: str
    user: str
    rss_mb: float
    state: str
    is_window: bool = False
    window_title: str = ""
    window_class: str = ""
    hypr_address: str = ""


class ProcessManager:
    """Manages system process discovery and Hyprland window mappings."""

    @staticmethod
    def get_hyprland_windows() -> Dict[int, Dict[str, str]]:
        """Queries hyprctl clients -j to map PID to Hyprland window details."""
        windows: Dict[int, Dict[str, str]] = {}
        try:
            res = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True,
                text=True,
                timeout=1.5
            )
            if res.returncode == 0 and res.stdout.strip():
                clients = json.loads(res.stdout)
                for client in clients:
                    pid = client.get("pid")
                    if pid and pid > 0:
                        windows[pid] = {
                            "title": client.get("title", ""),
                            "class": client.get("class", ""),
                            "address": client.get("address", ""),
                        }
        except Exception:
            pass
        return windows

    @classmethod
    def list_processes(cls, include_threads: bool = False) -> List[ProcessInfo]:
        """Lists all visible processes from /proc with Hyprland window metadata."""
        procs: List[ProcessInfo] = []
        windows = cls.get_hyprland_windows()
        current_uid = os.getuid()

        # Cache username mapping
        user_cache: Dict[int, str] = {}

        try:
            entries = os.listdir("/proc")
        except Exception:
            return procs

        for entry in entries:
            if not entry.isdigit():
                continue
            pid = int(entry)
            proc_dir = f"/proc/{pid}"

            try:
                # Name
                name = ""
                comm_path = f"{proc_dir}/comm"
                if os.path.exists(comm_path):
                    with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                        name = f.read().strip()

                # Status (State, UID)
                state = "?"
                uid = 0
                status_path = f"{proc_dir}/status"
                if os.path.exists(status_path):
                    with open(status_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if line.startswith("State:"):
                                state = line.split()[1]
                            elif line.startswith("Uid:"):
                                uid = int(line.split()[1])

                # Username
                if uid not in user_cache:
                    try:
                        user_cache[uid] = pwd.getpwuid(uid).pw_name
                    except KeyError:
                        user_cache[uid] = str(uid)
                user = user_cache[uid]

                # Memory RSS (pages in statm * page_size)
                rss_mb = 0.0
                statm_path = f"{proc_dir}/statm"
                if os.path.exists(statm_path):
                    with open(statm_path, "r", encoding="utf-8", errors="ignore") as f:
                        parts = f.read().split()
                        if len(parts) >= 2:
                            rss_pages = int(parts[1])
                            rss_mb = round((rss_pages * os.sysconf("SC_PAGE_SIZE")) / (1024 * 1024), 1)

                # Cmdline
                cmdline = ""
                cmdline_path = f"{proc_dir}/cmdline"
                if os.path.exists(cmdline_path):
                    with open(cmdline_path, "rb") as f:
                        raw = f.read()
                        cmdline = raw.replace(b'\x00', b' ').decode("utf-8", errors="replace").strip()

                if not name and cmdline:
                    name = cmdline.split()[0].split("/")[-1]
                if not name:
                    name = f"pid_{pid}"

                # Hyprland window check
                win = windows.get(pid)
                is_win = win is not None
                win_title = win["title"] if win else ""
                win_class = win["class"] if win else ""
                hypr_addr = win["address"] if win else ""

                procs.append(ProcessInfo(
                    pid=pid,
                    name=name,
                    cmdline=cmdline,
                    user=user,
                    rss_mb=rss_mb,
                    state=state,
                    is_window=is_win,
                    window_title=win_title,
                    window_class=win_class,
                    hypr_address=hypr_addr
                ))
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue

        # Sort: Windows first, then by name
        procs.sort(key=lambda p: (not p.is_window, p.name.lower()))
        return procs

    @staticmethod
    def pause_process(pid: int) -> bool:
        """Sends SIGSTOP to pause target process."""
        try:
            os.kill(pid, signal.SIGSTOP)
            return True
        except Exception:
            return False

    @staticmethod
    def resume_process(pid: int) -> bool:
        """Sends SIGCONT to resume target process."""
        try:
            os.kill(pid, signal.SIGCONT)
            return True
        except Exception:
            return False

    @staticmethod
    def terminate_process(pid: int) -> bool:
        """Sends SIGTERM to gracefully close process."""
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except Exception:
            return False

    @staticmethod
    def kill_process(pid: int) -> bool:
        """Sends SIGKILL to force kill process."""
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except Exception:
            return False
