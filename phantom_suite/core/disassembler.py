"""
PhantomSuite Disassembler & Code Patcher
Disassembles x86_64 machine code from target process memory into Intel syntax
and provides 1-click NOP patching and original byte restoration.
"""

import os
import subprocess
import tempfile
from typing import List, Tuple, Optional
from dataclasses import dataclass
from phantom_suite.core.memory_engine import MemoryEngine


@dataclass
class Instruction:
    address: int
    hex_bytes: str
    size: int
    mnemonic: str
    operands: str

    @property
    def is_nop(self) -> bool:
        return self.mnemonic.lower() == "nop"

    @property
    def full_text(self) -> str:
        return f"{self.mnemonic} {self.operands}".strip()


class Disassembler:
    """Disassembles x86_64 machine code and handles NOP patching."""

    @classmethod
    def disassemble(
        cls,
        pid: int,
        address: int,
        length: int = 64
    ) -> List[Instruction]:
        """Reads length bytes from target PID at address and disassembles them."""
        instructions: List[Instruction] = []
        raw_bytes = MemoryEngine.read_bytes(pid, address, length)
        if not raw_bytes:
            return instructions

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp.flush()
            tmp_path = tmp.name

        try:
            cmd = [
                "objdump", "-D", "-b", "binary", "-m", "i386:x86-64",
                "-M", "intel", f"--adjust-vma=0x{address:X}", tmp_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
            if res.returncode != 0:
                return instructions

            lines = res.stdout.splitlines()
            start_parsing = False

            for line in lines:
                if "<.data>:" in line:
                    start_parsing = True
                    continue
                if not start_parsing:
                    continue

                line = line.strip()
                if not line or ":" not in line:
                    continue

                # Format: "550000000000:\t89 45 fc             \tmov    DWORD PTR [rbp-0x4],eax"
                parts = line.split(":", 1)
                addr_str = parts[0].strip()
                rest = parts[1].strip()

                try:
                    addr_val = int(addr_str, 16)
                except ValueError:
                    continue

                # Split hex bytes from mnemonic + operands
                tokens = rest.split("\t")
                if len(tokens) >= 2:
                    hex_str = tokens[0].strip()
                    asm_str = tokens[1].strip()
                else:
                    subparts = rest.split(maxsplit=1)
                    hex_str = subparts[0].strip()
                    asm_str = subparts[1].strip() if len(subparts) > 1 else ""

                hex_clean = hex_str.replace(" ", "")
                byte_len = len(hex_clean) // 2

                asm_parts = asm_str.split(maxsplit=1)
                mnemonic = asm_parts[0] if len(asm_parts) > 0 else ""
                operands = asm_parts[1] if len(asm_parts) > 1 else ""

                instructions.append(Instruction(
                    address=addr_val,
                    hex_bytes=hex_str,
                    size=byte_len,
                    mnemonic=mnemonic,
                    operands=operands
                ))

        except Exception:
            pass
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return instructions

    @classmethod
    def nop_instruction(cls, pid: int, address: int, size: int) -> Tuple[bool, str, Optional[bytes]]:
        """
        Overwrites instruction at address with size NOP bytes (0x90).
        Returns (success, message, original_bytes).
        """
        if size <= 0:
            return False, "Invalid instruction size.", None

        orig = MemoryEngine.read_bytes(pid, address, size)
        if not orig:
            return False, f"Could not read memory at 0x{address:X}.", None

        nops = b"\x90" * size
        ok = MemoryEngine.write_bytes(pid, address, nops)
        if ok:
            return True, f"Replaced {size} bytes at 0x{address:X} with NOPs.", orig
        return False, f"Failed to write NOPs to 0x{address:X}.", None

    @classmethod
    def restore_instruction(cls, pid: int, address: int, original_bytes: bytes) -> Tuple[bool, str]:
        """Restores original instruction bytes to address."""
        ok = MemoryEngine.write_bytes(pid, address, original_bytes)
        if ok:
            return True, f"Restored {len(original_bytes)} original bytes at 0x{address:X}."
        return False, f"Failed to restore bytes at 0x{address:X}."
