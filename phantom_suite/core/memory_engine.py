"""
PhantomSuite Memory Engine
Native Linux process memory reading, writing, scanning, and freezing.
Uses direct process_vm_readv / process_vm_writev syscalls with /proc/<pid>/mem fallback.
"""

import os
import sys
import ctypes
import struct
import time
import threading
from typing import List, Dict, Optional, Tuple, Callable, Any
from dataclasses import dataclass

# Setup libc bindings for process_vm_readv and process_vm_writev
class iovec(ctypes.Structure):
    _fields_ = [
        ('iov_base', ctypes.c_void_p),
        ('iov_len', ctypes.c_size_t)
    ]

try:
    _libc = ctypes.CDLL("libc.so.6", use_errno=True)
    _has_process_vm = hasattr(_libc, "process_vm_readv") and hasattr(_libc, "process_vm_writev")
    if _has_process_vm:
        _process_vm_readv = _libc.process_vm_readv
        _process_vm_readv.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(iovec),
            ctypes.c_long,
            ctypes.POINTER(iovec),
            ctypes.c_long,
            ctypes.c_long
        ]
        _process_vm_readv.restype = ctypes.c_long

        _process_vm_writev = _libc.process_vm_writev
        _process_vm_writev.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(iovec),
            ctypes.c_long,
            ctypes.POINTER(iovec),
            ctypes.c_long,
            ctypes.c_long
        ]
        _process_vm_writev.restype = ctypes.c_long
except Exception:
    _has_process_vm = False


@dataclass
class MemoryRegion:
    start: int
    end: int
    perms: str
    offset: int
    dev: str
    inode: int
    pathname: str

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def is_readable(self) -> bool:
        return 'r' in self.perms

    @property
    def is_writable(self) -> bool:
        return 'w' in self.perms

    @property
    def is_executable(self) -> bool:
        return 'x' in self.perms


@dataclass
class ScanResult:
    address: int
    value: Any
    previous_value: Optional[Any] = None


class TypeFormat:
    INT8 = "int8"
    UINT8 = "uint8"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    INT64 = "int64"
    UINT64 = "uint64"
    FLOAT = "float"
    DOUBLE = "double"
    STRING = "string"
    BYTES = "bytes"

    STRUCT_MAP = {
        INT8: ("<b", 1),
        UINT8: ("<B", 1),
        INT16: ("<h", 2),
        UINT16: ("<H", 2),
        INT32: ("<i", 4),
        UINT32: ("<I", 4),
        INT64: ("<q", 8),
        UINT64: ("<Q", 8),
        FLOAT: ("<f", 4),
        DOUBLE: ("<d", 8),
    }

    @classmethod
    def get_size(cls, val_type: str, custom_val: Any = None) -> int:
        if val_type in cls.STRUCT_MAP:
            return cls.STRUCT_MAP[val_type][1]
        elif val_type == cls.STRING:
            return len(str(custom_val).encode('utf-8')) if custom_val else 1
        elif val_type == cls.BYTES:
            if isinstance(custom_val, (bytes, bytearray)):
                return len(custom_val)
            elif isinstance(custom_val, str):
                return len(bytes.fromhex(custom_val.replace(" ", "")))
            return 1
        return 4


class ScanType:
    EXACT = "Exact Value"
    INCREASED = "Increased Value"
    DECREASED = "Decreased Value"
    CHANGED = "Changed Value"
    UNCHANGED = "Unchanged Value"
    BIGGER_THAN = "Bigger Than"
    SMALLER_THAN = "Smaller Than"


class MemoryEngine:
    """Core memory reader, writer, scanner, and freezer."""

    @staticmethod
    def get_maps(pid: int) -> List[MemoryRegion]:
        """Parses /proc/<pid>/maps into structured MemoryRegion objects."""
        regions = []
        maps_path = f"/proc/{pid}/maps"
        if not os.path.exists(maps_path):
            return regions

        try:
            with open(maps_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.strip().split(maxsplit=5)
                    if len(parts) < 5:
                        continue
                    addrs = parts[0].split('-')
                    start = int(addrs[0], 16)
                    end = int(addrs[1], 16)
                    perms = parts[1]
                    offset = int(parts[2], 16)
                    dev = parts[3]
                    inode = int(parts[4])
                    pathname = parts[5] if len(parts) >= 6 else ""
                    regions.append(MemoryRegion(
                        start=start, end=end, perms=perms, offset=offset,
                        dev=dev, inode=inode, pathname=pathname
                    ))
        except (PermissionError, ProcessLookupError, FileNotFoundError):
            pass
        return regions

    @staticmethod
    def read_bytes(pid: int, address: int, size: int) -> Optional[bytes]:
        """Reads raw bytes from process virtual memory."""
        if size <= 0:
            return b""

        # 1. Try process_vm_readv for blazing speed
        if _has_process_vm:
            buf = (ctypes.c_char * size)()
            local_iov = iovec(ctypes.cast(buf, ctypes.c_void_p), size)
            remote_iov = iovec(ctypes.c_void_p(address), size)
            res = _process_vm_readv(
                pid,
                ctypes.byref(local_iov), 1,
                ctypes.byref(remote_iov), 1,
                0
            )
            if res == size:
                return bytes(buf)

        # 2. Fallback to /proc/<pid>/mem
        try:
            mem_path = f"/proc/{pid}/mem"
            fd = os.open(mem_path, os.O_RDONLY)
            try:
                return os.pread(fd, size, address)
            finally:
                os.close(fd)
        except Exception:
            return None

    @staticmethod
    def write_bytes(pid: int, address: int, data: bytes) -> bool:
        """Writes raw bytes into process virtual memory."""
        size = len(data)
        if size == 0:
            return True

        # 1. Try process_vm_writev
        if _has_process_vm:
            buf = (ctypes.c_char * size).from_buffer_copy(data)
            local_iov = iovec(ctypes.cast(buf, ctypes.c_void_p), size)
            remote_iov = iovec(ctypes.c_void_p(address), size)
            res = _process_vm_writev(
                pid,
                ctypes.byref(local_iov), 1,
                ctypes.byref(remote_iov), 1,
                0
            )
            if res == size:
                return True

        # 2. Fallback to /proc/<pid>/mem
        try:
            mem_path = f"/proc/{pid}/mem"
            fd = os.open(mem_path, os.O_WRONLY)
            try:
                written = os.pwrite(fd, data, address)
                return written == size
            finally:
                os.close(fd)
        except Exception:
            return False

    @classmethod
    def read_typed(cls, pid: int, address: int, val_type: str, str_len: int = 32) -> Optional[Any]:
        """Reads a typed value from process memory."""
        if val_type in TypeFormat.STRUCT_MAP:
            fmt, size = TypeFormat.STRUCT_MAP[val_type]
            raw = cls.read_bytes(pid, address, size)
            if raw and len(raw) == size:
                return struct.unpack(fmt, raw)[0]
            return None
        elif val_type == TypeFormat.STRING:
            raw = cls.read_bytes(pid, address, str_len)
            if raw:
                # Terminate at null byte if present
                null_pos = raw.find(b'\x00')
                if null_pos != -1:
                    raw = raw[:null_pos]
                return raw.decode('utf-8', errors='replace')
            return None
        elif val_type == TypeFormat.BYTES:
            raw = cls.read_bytes(pid, address, str_len)
            return raw.hex().upper() if raw else None
        return None

    @classmethod
    def write_typed(cls, pid: int, address: int, val_type: str, value: Any) -> bool:
        """Writes a typed value to process memory."""
        try:
            if val_type in TypeFormat.STRUCT_MAP:
                fmt, _ = TypeFormat.STRUCT_MAP[val_type]
                if val_type in (TypeFormat.FLOAT, TypeFormat.DOUBLE):
                    data = struct.pack(fmt, float(value))
                else:
                    data = struct.pack(fmt, int(value))
                return cls.write_bytes(pid, address, data)
            elif val_type == TypeFormat.STRING:
                data = str(value).encode('utf-8') + b'\x00'
                return cls.write_bytes(pid, address, data)
            elif val_type == TypeFormat.BYTES:
                if isinstance(value, str):
                    data = bytes.fromhex(value.replace(" ", ""))
                else:
                    data = bytes(value)
                return cls.write_bytes(pid, address, data)
        except Exception:
            return False
        return False

    @classmethod
    def first_scan(
        cls,
        pid: int,
        val_type: str,
        scan_type: str,
        target_value: Any,
        writable_only: bool = True,
        alignment: int = 4,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[ScanResult]:
        """Performs initial full memory scan across mapped regions."""
        results: List[ScanResult] = []
        regions = cls.get_maps(pid)

        # Filter regions
        candidate_regions = []
        for r in regions:
            if not r.is_readable:
                continue
            if writable_only and not r.is_writable:
                continue
            # Skip special mapped device files or vsyscall
            if r.pathname.startswith(("/dev/", "[vsyscall]", "[vvar]")):
                continue
            candidate_regions.append(r)

        total_bytes = sum(r.size for r in candidate_regions)
        bytes_scanned = 0

        # Prepare target search bytes if exact match
        target_bytes = None
        fmt = None
        val_size = 4
        if val_type in TypeFormat.STRUCT_MAP:
            fmt, val_size = TypeFormat.STRUCT_MAP[val_type]
            if scan_type in (ScanType.EXACT, ScanType.BIGGER_THAN, ScanType.SMALLER_THAN) and target_value is not None:
                parsed_val = float(target_value) if "float" in val_type or "double" in val_type else int(target_value)
                target_bytes = struct.pack(fmt, parsed_val)
        elif val_type == TypeFormat.STRING:
            target_bytes = str(target_value).encode('utf-8')
            val_size = len(target_bytes)
            alignment = 1
        elif val_type == TypeFormat.BYTES:
            target_bytes = bytes.fromhex(str(target_value).replace(" ", ""))
            val_size = len(target_bytes)
            alignment = 1

        chunk_size = 512 * 1024  # 512 KB chunks

        for reg in candidate_regions:
            offset = 0
            while offset < reg.size:
                to_read = min(chunk_size, reg.size - offset)
                current_addr = reg.start + offset
                chunk = cls.read_bytes(pid, current_addr, to_read)

                if chunk:
                    chunk_len = len(chunk)

                    if scan_type == ScanType.EXACT and target_bytes is not None:
                        # Fast binary search within chunk
                        idx = 0
                        while True:
                            pos = chunk.find(target_bytes, idx)
                            if pos == -1:
                                break
                            match_addr = current_addr + pos
                            if (match_addr % alignment) == 0:
                                parsed = cls.read_typed(pid, match_addr, val_type)
                                results.append(ScanResult(address=match_addr, value=parsed))
                                if len(results) >= 50000:
                                    # Safety ceiling to prevent memory explosion
                                    break
                            idx = pos + 1
                    else:
                        # Iterate through chunk with alignment
                        step = max(1, alignment)
                        limit = chunk_len - val_size + 1
                        for pos in range(0, limit, step):
                            val = cls.read_typed(pid, current_addr + pos, val_type)
                            if val is not None:
                                match = False
                                if scan_type == ScanType.EXACT:
                                    match = (val == target_value)
                                elif scan_type == ScanType.BIGGER_THAN:
                                    match = (val > target_value)
                                elif scan_type == ScanType.SMALLER_THAN:
                                    match = (val < target_value)
                                else:
                                    # Unknown initial value condition: record everything
                                    match = True

                                if match:
                                    results.append(ScanResult(address=current_addr + pos, value=val))
                                    if len(results) >= 50000:
                                        break

                bytes_scanned += to_read
                offset += to_read
                if progress_callback and total_bytes > 0:
                    pct = min(1.0, bytes_scanned / total_bytes)
                    progress_callback(pct, f"Scanning: {len(results)} found ({int(pct*100)}%)")

                if len(results) >= 50000:
                    break
            if len(results) >= 50000:
                break

        return results

    @classmethod
    def next_scan(
        cls,
        pid: int,
        val_type: str,
        scan_type: str,
        target_value: Any,
        previous_results: List[ScanResult],
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[ScanResult]:
        """Performs differential subsequent scan only checking previous candidate addresses."""
        refined: List[ScanResult] = []
        total = len(previous_results)

        for i, res in enumerate(previous_results):
            current_val = cls.read_typed(pid, res.address, val_type)
            if current_val is None:
                continue

            match = False
            prev_val = res.value

            if scan_type == ScanType.EXACT:
                match = (current_val == target_value)
            elif scan_type == ScanType.INCREASED:
                match = (current_val > prev_val)
            elif scan_type == ScanType.DECREASED:
                match = (current_val < prev_val)
            elif scan_type == ScanType.CHANGED:
                match = (current_val != prev_val)
            elif scan_type == ScanType.UNCHANGED:
                match = (current_val == prev_val)
            elif scan_type == ScanType.BIGGER_THAN:
                match = (current_val > target_value)
            elif scan_type == ScanType.SMALLER_THAN:
                match = (current_val < target_value)

            if match:
                refined.append(ScanResult(
                    address=res.address,
                    value=current_val,
                    previous_value=prev_val
                ))

            if progress_callback and i % 500 == 0 and total > 0:
                pct = (i + 1) / total
                progress_callback(pct, f"Filtering: {len(refined)} matches ({int(pct*100)}%)")

        return refined


class FreezeManager:
    """Manages continuously locked/frozen memory addresses in target process."""

    def __init__(self, interval_sec: float = 0.05):
        self.interval = interval_sec
        self.targets: Dict[Tuple[int, int], Tuple[str, Any]] = {} # (pid, address) -> (val_type, value)
        self.lock = threading.Lock()
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def stop(self):
        with self.lock:
            self.running = False

    def add(self, pid: int, address: int, val_type: str, value: Any):
        with self.lock:
            self.targets[(pid, address)] = (val_type, value)
        self.start()

    def remove(self, pid: int, address: int):
        with self.lock:
            self.targets.pop((pid, address), None)

    def is_frozen(self, pid: int, address: int) -> bool:
        with self.lock:
            return (pid, address) in self.targets

    def _worker(self):
        while True:
            with self.lock:
                if not self.running:
                    break
                items = list(self.targets.items())

            if not items:
                time.sleep(self.interval)
                continue

            for (pid, addr), (v_type, val) in items:
                try:
                    MemoryEngine.write_typed(pid, addr, v_type, val)
                except Exception:
                    pass

            time.sleep(self.interval)
