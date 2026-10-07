"""
PhantomSuite GDB/MI Debug Bridge & Core Dump Importer
Provides headless GDB Machine Interface (GDB/MI) automation for dynamic debugging
and native 64-bit ELF core dump parser for inspecting post-mortem process crashes,
registers, signals, and virtual memory mappings.
"""

import os
import re
import signal
import socket
import struct
import shutil
import select
import mmap
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


# Signal Number to Name mapping
SIGNAL_NAMES = {
    1: "SIGHUP", 2: "SIGINT", 3: "SIGQUIT", 4: "SIGILL", 5: "SIGTRAP",
    6: "SIGABRT", 7: "SIGBUS", 8: "SIGFPE", 9: "SIGKILL", 11: "SIGSEGV",
    13: "SIGPIPE", 14: "SIGALRM", 15: "SIGTERM", 18: "SIGCONT", 19: "SIGSTOP"
}

X86_64_GREG_NAMES = [
    "r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10",
    "r9", "r8", "rax", "rcx", "rdx", "rsi", "rdi", "orig_rax",
    "rip", "cs", "eflags", "rsp", "ss", "fs_base", "gs_base",
    "ds", "es", "fs", "gs"
]


@dataclass
class CoreSegment:
    """Represents a PT_LOAD segment dumped in an ELF core dump."""
    vaddr: int
    filesz: int
    memsz: int
    offset: int
    flags: int


@dataclass
class CoreDumpMetadata:
    """Parsed metadata from an ELF core dump."""
    pid: int
    exec_name: str
    cmdline: str
    signal_num: int
    signal_name: str
    registers: Dict[str, int]
    segments: List[CoreSegment] = field(default_factory=list)


class CoreDumpReader:
    """
    Parses native 64-bit Linux ELF core dumps.
    Extracts crashing signal, register context, memory regions, and allows arbitrary byte reads.
    Memory-mapped for high-performance reading without RAM exhaustion on large dumps.
    """

    ELF_MAGIC = b"\x7fELF"
    ELFCLASS64 = 2
    ET_CORE = 4
    PT_LOAD = 1
    PT_NOTE = 7

    NT_PRSTATUS = 1
    NT_PRPSINFO = 3
    NT_AUXV = 6

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.metadata: Optional[CoreDumpMetadata] = None
        self.segments: List[CoreSegment] = []
        self._mmap_obj: Optional[mmap.mmap] = None
        self._file_obj = None
        self._data: Any = b""

    def load(self) -> bool:
        """Loads and parses the ELF core dump."""
        if not os.path.exists(self.filepath):
            return False

        try:
            file_size = os.path.getsize(self.filepath)
            if file_size < 64:
                return False

            self._file_obj = open(self.filepath, "rb")
            try:
                self._mmap_obj = mmap.mmap(self._file_obj.fileno(), 0, access=mmap.ACCESS_READ)
                self._data = self._mmap_obj
            except Exception:
                # Fallback to buffer reading if mmap unsupported
                self._data = self._file_obj.read()
        except OSError:
            return False

        if len(self._data) < 64 or not self._data[:4] == self.ELF_MAGIC:
            return False

        # Verify 64-bit and ET_CORE
        elf_class = self._data[4]
        if elf_class != self.ELFCLASS64:
            return False

        e_type = struct.unpack_from("<H", self._data, 16)[0]
        if e_type != self.ET_CORE:
            return False

        e_phoff = struct.unpack_from("<Q", self._data, 32)[0]
        e_phentsize = struct.unpack_from("<H", self._data, 54)[0]
        e_phnum = struct.unpack_from("<H", self._data, 56)[0]

        pid = 0
        exec_name = ""
        cmdline = ""
        sig_num = 0
        regs: Dict[str, int] = {}
        self.segments = []

        # Parse Program Headers
        for i in range(e_phnum):
            ph_off = e_phoff + (i * e_phentsize)
            if ph_off + 56 > len(self._data):
                break

            p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from(
                "<IIQQQQQQ", self._data, ph_off
            )

            if p_type == self.PT_LOAD:
                self.segments.append(CoreSegment(
                    vaddr=p_vaddr,
                    filesz=p_filesz,
                    memsz=p_memsz,
                    offset=p_offset,
                    flags=p_flags
                ))

            elif p_type == self.PT_NOTE:
                note_bytes = bytes(self._data[p_offset:p_offset + p_filesz])
                notes = self._parse_notes(note_bytes)
                for n_type, n_name, n_desc in notes:
                    if n_type == self.NT_PRSTATUS and len(n_desc) >= 328:
                        sig_num = struct.unpack_from("<H", n_desc, 12)[0]
                        pid = struct.unpack_from("<i", n_desc, 32)[0]
                        # Registers start at offset 112 (27 QWORDs)
                        for reg_idx, rname in enumerate(X86_64_GREG_NAMES):
                            reg_val = struct.unpack_from("<Q", n_desc, 112 + (reg_idx * 8))[0]
                            regs[rname] = reg_val

                    elif n_type == self.NT_PRPSINFO:
                        raw_fname = b""
                        raw_args = b""
                        # 64-bit layout: pr_fname at offset 40, pr_psargs at offset 56
                        if len(n_desc) >= 136:
                            raw_fname = n_desc[40:56].split(b"\x00")[0]
                            raw_args = n_desc[56:136].split(b"\x00")[0]
                        # 32-bit layout fallback: pr_fname at 28, pr_psargs at 44
                        if (not raw_fname or not raw_fname.strip()) and len(n_desc) >= 120:
                            raw_fname = n_desc[28:44].split(b"\x00")[0]
                            raw_args = n_desc[44:124].split(b"\x00")[0]

                        exec_name = raw_fname.decode("latin1", errors="replace").strip()
                        cmdline = raw_args.decode("latin1", errors="replace").strip()

        sig_name = SIGNAL_NAMES.get(sig_num, f"SIGNAL_{sig_num}")

        self.metadata = CoreDumpMetadata(
            pid=pid,
            exec_name=exec_name,
            cmdline=cmdline,
            signal_num=sig_num,
            signal_name=sig_name,
            registers=regs,
            segments=self.segments
        )
        return True

    def _parse_notes(self, data: bytes) -> List[Tuple[int, str, bytes]]:
        """Parses ELF notes from a PT_NOTE segment."""
        notes = []
        off = 0
        data_len = len(data)

        while off + 12 <= data_len:
            namesz, descsz, n_type = struct.unpack_from("<III", data, off)
            off += 12

            name_bytes = data[off:off + namesz]
            name_pad = (4 - (namesz % 4)) % 4
            off += namesz + name_pad

            desc_bytes = data[off:off + descsz]
            desc_pad = (4 - (descsz % 4)) % 4
            off += descsz + desc_pad

            name_str = name_bytes.decode("latin1", errors="replace").rstrip("\x00")
            notes.append((n_type, name_str, desc_bytes))

        return notes

    def read_bytes(self, vaddr: int, size: int) -> bytes:
        """Reads virtual memory from the core dump's PT_LOAD segments."""
        if not self._data or size <= 0:
            return b""

        for seg in self.segments:
            if seg.vaddr <= vaddr < seg.vaddr + seg.memsz:
                offset_in_seg = vaddr - seg.vaddr
                if offset_in_seg >= seg.filesz:
                    # Uninitialized BSS section
                    return b"\x00" * size

                available = max(0, seg.filesz - offset_in_seg)
                read_len = min(size, available)
                file_start = seg.offset + offset_in_seg
                chunk = bytes(self._data[file_start:file_start + read_len])
                if len(chunk) < size:
                    chunk += b"\x00" * (size - len(chunk))
                return chunk
        return b""

    def generate_report(self) -> str:
        """Generates a structured post-mortem crash report."""
        if not self.metadata:
            return "No valid core dump loaded."

        m = self.metadata
        lines = [
            "=" * 64,
            f" PHANTOMSUITE CRASH ANALYSIS REPORT: {m.exec_name or 'Unknown'} [PID: {m.pid}]",
            "=" * 64,
            f"Termination Signal: {m.signal_name} (Code: {m.signal_num})",
            f"Command Line:       {m.cmdline or '<none>'}",
            f"Memory Segments:    {len(m.segments)} mapped PT_LOAD blocks",
            "",
            "--- CPU REGISTER CONTEXT (x86_64) ---",
        ]

        if m.registers:
            r = m.registers
            lines.append(f"RIP: 0x{r.get('rip', 0):016X}   RSP: 0x{r.get('rsp', 0):016X}   RBP: 0x{r.get('rbp', 0):016X}")
            lines.append(f"RAX: 0x{r.get('rax', 0):016X}   RBX: 0x{r.get('rbx', 0):016X}   RCX: 0x{r.get('rcx', 0):016X}")
            lines.append(f"RDX: 0x{r.get('rdx', 0):016X}   RSI: 0x{r.get('rsi', 0):016X}   RDI: 0x{r.get('rdi', 0):016X}")
            lines.append(f"R8:  0x{r.get('r8', 0):016X}   R9:  0x{r.get('r9', 0):016X}   R10: 0x{r.get('r10', 0):016X}")
            lines.append(f"R11: 0x{r.get('r11', 0):016X}   R12: 0x{r.get('r12', 0):016X}   R13: 0x{r.get('r13', 0):016X}")
            lines.append(f"R14: 0x{r.get('r14', 0):016X}   R15: 0x{r.get('r15', 0):016X}   EFLAGS: 0x{r.get('eflags', 0):08X}")
        else:
            lines.append("<Register note missing or corrupted>")

        lines.append("=" * 64)
        return "\n".join(lines)

    def close(self):
        """Releases memory-mapped file handles."""
        if self._mmap_obj:
            try:
                self._mmap_obj.close()
            except Exception:
                pass
            self._mmap_obj = None
        if self._file_obj:
            try:
                self._file_obj.close()
            except Exception:
                pass
            self._file_obj = None
        self._data = b""

    def __enter__(self):
        self.load()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()


class GdbMiBridge:
    """
    Asynchronous GDB/MI (Machine Interface) Client.
    Automates process debugging via headless GDB session with timeout safety.
    """

    def __init__(self, gdb_path: Optional[str] = None):
        self.gdb_path = gdb_path or shutil.which("gdb") or "/usr/bin/gdb"
        self.proc: Optional[subprocess.Popen] = None
        self.token_counter = 100
        self._lock = threading.Lock()

    @classmethod
    def is_available(cls) -> bool:
        """Checks if GDB executable is available on system."""
        return shutil.which("gdb") is not None

    def start(self) -> bool:
        """Launches GDB subprocess with MI interpreter."""
        if not self.is_available():
            return False

        try:
            self.proc = subprocess.Popen(
                [self.gdb_path, "--interpreter=mi2", "-q", "-nx"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout to prevent pipe buffer deadlocks
                text=True,
                bufsize=1
            )
            return True
        except (OSError, ValueError):
            self.proc = None
            return False

    def stop(self):
        """Terminates GDB subprocess."""
        if self.proc and self.proc.poll() is None:
            try:
                self.send_command("-gdb-exit", timeout=1.0)
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                if self.proc:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
        self.proc = None

    def send_command(self, cmd: str, timeout: float = 3.0) -> Tuple[bool, str]:
        """
        Sends an MI command and waits for the matching result record (^done or ^error).
        Guarded with timeout to prevent hanging.
        Returns (success, response_string).
        """
        if not self.proc or self.proc.poll() is not None or not self.proc.stdin or not self.proc.stdout:
            return False, "GDB process not active"

        with self._lock:
            self.token_counter += 1
            token = str(self.token_counter)
            full_cmd = f"{token}{cmd}\n"

            try:
                self.proc.stdin.write(full_cmd)
                self.proc.stdin.flush()
            except OSError as e:
                return False, f"Failed to write to GDB: {e}"

            output_lines = []
            success = False

            while True:
                has_fileno = False
                try:
                    fn = self.proc.stdout.fileno()
                    has_fileno = isinstance(fn, int)
                except Exception:
                    pass

                if has_fileno and timeout > 0:
                    rlist, _, _ = select.select([self.proc.stdout], [], [], timeout)
                    if not rlist:
                        output_lines.append(f"{token}^error,msg=\"Command timed out after {timeout}s\"")
                        break

                line = self.proc.stdout.readline()
                if not line:
                    break
                stripped = line.strip()
                output_lines.append(stripped)

                if stripped.startswith(f"{token}^done") or stripped.startswith(f"{token}^running"):
                    success = True
                    break
                elif stripped.startswith(f"{token}^error"):
                    success = False
                    break
                elif stripped == "(gdb)":
                    break

            return success, "\n".join(output_lines)

    def attach(self, pid: int) -> Tuple[bool, str]:
        """Attaches GDB to a target process."""
        return self.send_command(f"-target-attach {pid}")

    def detach(self) -> Tuple[bool, str]:
        """Detaches GDB from the target process."""
        return self.send_command("-target-detach")

    def continue_execution(self) -> Tuple[bool, str]:
        """Resumes target process execution."""
        return self.send_command("-exec-continue")

    def interrupt(self) -> Tuple[bool, str]:
        """Interrupts running target process."""
        return self.send_command("-exec-interrupt")

    def step_instruction(self) -> Tuple[bool, str]:
        """Single-steps one machine instruction."""
        return self.send_command("-exec-step-instruction")

    def evaluate_expression(self, expr: str) -> Tuple[bool, str]:
        """Evaluates an expression in GDB context."""
        return self.send_command(f"-data-evaluate-expression \"{expr}\"")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def __del__(self):
        self.stop()
