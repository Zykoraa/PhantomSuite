"""
PhantomSuite Hardware Watchpoint Tracer
Uses x86_64 hardware debug registers via GDB to determine which instructions
in the target process read from or write to a specific memory address.
"""

import os
import re
import subprocess
import tempfile
import time
from typing import List, Optional
from dataclasses import dataclass
from phantom_suite.core.table_serializer import TableSerializer
from phantom_suite.core.disassembler import Disassembler, Instruction


@dataclass
class WatchpointHit:
    target_address: int
    instruction_address: int
    module_name: str
    offset: int
    function_name: str
    old_value: str
    new_value: str
    instruction_text: str
    timestamp: float


class WatchpointTracer:
    """Detects instructions that write to or access a specific memory address."""

    HIT_REGEX = re.compile(
        r"(?:Old value\s*=\s*(.*?)\n\s*New value\s*=\s*(.*?)\n)?"
        r"(0x[0-9a-fA-F]+)\s+in\s+([a-zA-Z0-9_<>+*&:]+)"
    )

    @classmethod
    def trace_address(
        cls,
        pid: int,
        address: int,
        watch_type: str = "write", # "write", "access", "read"
        timeout_sec: float = 3.0
    ) -> List[WatchpointHit]:
        """
        Attaches GDB with a hardware watchpoint on `address` for `timeout_sec` seconds.
        Returns all instructions that touched the address.
        """
        hits: List[WatchpointHit] = []
        if not pid or pid <= 0 or address <= 0:
            return hits

        wp_cmd = "watch" if watch_type == "write" else ("rwatch" if watch_type == "read" else "awatch")

        # Create temporary GDB script
        with tempfile.NamedTemporaryFile("w", suffix=".gdb", delete=False) as script_file:
            script_path = script_file.name
            script_file.write(
                "set debuginfod enabled off\n"
                "set pagination off\n"
                f"{wp_cmd} *(int*){address}\n"
                "continue\n"
                "detach\n"
                "quit\n"
            )

        try:
            res = subprocess.run(
                ["gdb", "-q", "-p", str(pid), "-batch", "-x", script_path],
                capture_output=True,
                text=True,
                timeout=timeout_sec + 2.0
            )
            output = res.stdout

            matches = cls.HIT_REGEX.findall(output)
            for m in matches:
                old_val, new_val, addr_hex, func_name = m
                inst_addr = int(addr_hex, 16)

                mod_name, off = TableSerializer.resolve_runtime_address(pid, inst_addr)
                
                # Disassemble instruction at inst_addr
                inst_text = ""
                instructions = Disassembler.disassemble(pid, max(0, inst_addr - 10), length=32)
                for inst in instructions:
                    if inst.address == inst_addr or (inst.address <= inst_addr < inst.address + inst.size):
                        inst_text = inst.full_text
                        break
                if not inst_text and instructions:
                    inst_text = instructions[0].full_text

                hits.append(WatchpointHit(
                    target_address=address,
                    instruction_address=inst_addr,
                    module_name=mod_name or "",
                    offset=off,
                    function_name=func_name,
                    old_value=old_val.strip() if old_val else "-",
                    new_value=new_val.strip() if new_val else "-",
                    instruction_text=inst_text or "[instruction]",
                    timestamp=time.time()
                ))

        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)

        return hits
