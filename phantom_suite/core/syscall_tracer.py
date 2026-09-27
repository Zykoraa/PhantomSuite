"""
PhantomSuite Syscall Telemetry Monitor
Streams and parses real-time system call activity for target processes using strace.
Categorizes I/O, network, memory, and thread/process lifecycle events.
"""

import re
import subprocess
import threading
import time
from typing import Optional, Callable, List
from dataclasses import dataclass


@dataclass
class SyscallEvent:
    timestamp: float
    pid: int
    syscall: str
    args: str
    result: str
    duration: float
    category: str  # "FILE", "NET", "MEM", "PROC", "IPC", "OTHER"
    raw: str


class SyscallTracer:
    """Non-blocking background syscall telemetry capture engine."""

    SYSCALL_CATEGORIES = {
        # File & Directory I/O
        "open": "FILE", "openat": "FILE", "creat": "FILE", "close": "FILE",
        "read": "FILE", "write": "FILE", "pread64": "FILE", "pwrite64": "FILE",
        "stat": "FILE", "fstat": "FILE", "newfstatat": "FILE", "lstat": "FILE",
        "unlink": "FILE", "unlinkat": "FILE", "rename": "FILE", "renameat": "FILE",
        "access": "FILE", "faccessat": "FILE", "ioctl": "FILE", "fcntl": "FILE",
        "lseek": "FILE", "dup": "FILE", "dup2": "FILE", "dup3": "FILE",
        # Network & Sockets
        "socket": "NET", "bind": "NET", "connect": "NET", "listen": "NET",
        "accept": "NET", "accept4": "NET", "sendto": "NET", "recvfrom": "NET",
        "sendmsg": "NET", "recvmsg": "NET", "shutdown": "NET", "getsockopt": "NET",
        "setsockopt": "NET", "getpeername": "NET", "getsockname": "NET",
        # Memory Management
        "mmap": "MEM", "mprotect": "MEM", "munmap": "MEM", "brk": "MEM",
        "madvise": "MEM", "msync": "MEM", "mlock": "MEM", "munlock": "MEM",
        # Process & Threads
        "clone": "PROC", "clone3": "PROC", "fork": "PROC", "vfork": "PROC",
        "execve": "PROC", "execveat": "PROC", "exit": "PROC", "exit_group": "PROC",
        "kill": "PROC", "tgkill": "PROC", "futex": "PROC", "wait4": "PROC",
        "nanosleep": "PROC", "clock_nanosleep": "PROC",
        # IPC & Pipes
        "pipe": "IPC", "pipe2": "IPC", "eventfd": "IPC", "eventfd2": "IPC",
        "epoll_create": "IPC", "epoll_create1": "IPC", "epoll_ctl": "IPC",
        "epoll_wait": "IPC", "poll": "IPC", "ppoll": "IPC", "select": "IPC"
    }

    # Matches: [pid 12345] syscall(arg1, arg2) = res <duration>
    # Or: syscall(arg1, arg2) = res <duration>
    PATTERN_WITH_PID = re.compile(r"^(?:\[pid\s+(\d+)\]\s+)?([a-zA-Z0-9_]+)\((.*)\)\s+=\s+(.*?)(?:\s+<([0-9.]+)>)?$")

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._callback: Optional[Callable[[SyscallEvent], None]] = None

    @property
    def is_tracing(self) -> bool:
        return self._running and self._proc is not None and self._proc.poll() is None

    def start(self, pid: int, callback: Callable[[SyscallEvent], None], category_filter: Optional[str] = None):
        """Starts background strace capture on target pid."""
        if self.is_tracing:
            self.stop()

        self._callback = callback
        self._running = True

        cmd = ["strace", "-p", str(pid), "-f", "-T", "-s", "96"]
        if category_filter and category_filter != "ALL":
            cat_map = {"FILE": "%file,%desc", "NET": "%net", "MEM": "%memory", "PROC": "%process", "IPC": "%ipc"}
            if category_filter in cat_map:
                cmd.extend(["-e", f"trace={cat_map[category_filter]}"])

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
        except Exception:
            self._running = False
            return False

        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Stops active strace capture."""
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    def _reader_loop(self):
        """Reads strace output line by line and dispatches parsed SyscallEvent."""
        if not self._proc or not self._proc.stderr:
            return

        for line in self._proc.stderr:
            if not self._running:
                break
            line_str = line.strip()
            if not line_str or line_str.startswith("strace:"):
                continue

            event = self.parse_line(line_str)
            if event and self._callback:
                try:
                    self._callback(event)
                except Exception:
                    pass

    @classmethod
    def parse_line(cls, line: str) -> Optional[SyscallEvent]:
        """Parses a single strace output line into a structured SyscallEvent."""
        m = cls.PATTERN_WITH_PID.match(line)
        now = time.time()
        if not m:
            # Check for unfinished / resumed syscall lines
            parts = line.split("(", 1)
            if len(parts) == 2:
                sys_name = parts[0].split()[-1]
                cat = cls.SYSCALL_CATEGORIES.get(sys_name, "OTHER")
                return SyscallEvent(
                    timestamp=now,
                    pid=0,
                    syscall=sys_name,
                    args=parts[1],
                    result="...",
                    duration=0.0,
                    category=cat,
                    raw=line
                )
            return None

        pid_str, syscall, args, result, dur_str = m.groups()
        pid_val = int(pid_str) if pid_str else 0
        dur_val = float(dur_str) if dur_str else 0.0
        cat = cls.SYSCALL_CATEGORIES.get(syscall, "OTHER")

        return SyscallEvent(
            timestamp=now,
            pid=pid_val,
            syscall=syscall,
            args=args,
            result=result,
            duration=dur_val,
            category=cat,
            raw=line
        )
