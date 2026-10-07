"""
PhantomSuite Micro-Execution & Sub-Function Emulation Engine
Provides isolated, safe x86_64 CPU state emulation and sub-function
stepping without triggering anti-debug traps or modifying target process memory.
Supports shadow memory paging, lazy target process reads, and snapshot rollbacks.
"""

import copy
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

try:
    import capstone
    from capstone import x86
    CAPSTONE_AVAILABLE = True
except ImportError:
    CAPSTONE_AVAILABLE = False

from phantom_suite.core.memory_engine import MemoryEngine


@dataclass
class StepTrace:
    """Records the execution delta of a single emulated instruction."""
    address: int
    mnemonic: str
    op_str: str
    raw_bytes: bytes
    rip_before: int
    rip_after: int
    regs_delta: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    mem_reads: List[Tuple[int, int]] = field(default_factory=list)   # (addr, val)
    mem_writes: List[Tuple[int, int]] = field(default_factory=list)  # (addr, val)


@dataclass
class EmulationResult:
    """Summary of a micro-execution run."""
    steps_executed: int
    terminated: bool
    halt_reason: str
    final_rip: int
    registers: Dict[str, int]
    trace: List[StepTrace] = field(default_factory=list)


class MicroEmulator:
    """
    Lightweight x86_64 Micro-Execution Engine for reversing sub-routines,
    string decoders, and math algorithms in an isolated CPU state.
    """

    PAGE_SIZE = 4096
    STACK_BASE = 0x7FFF00000000
    STACK_SIZE = 0x10000  # 64 KB
    DEFAULT_RSP = 0x7FFF0000FF00

    REG_64_NAMES = [
        "rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp",
        "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15", "rip"
    ]

    # Map Capstone register IDs to canonical register names & bit sizes
    CAPSTONE_REG_MAP = {
        # 64-bit
        "rax": ("rax", 64, 0), "rbx": ("rbx", 64, 0), "rcx": ("rcx", 64, 0), "rdx": ("rdx", 64, 0),
        "rsi": ("rsi", 64, 0), "rdi": ("rdi", 64, 0), "rbp": ("rbp", 64, 0), "rsp": ("rsp", 64, 0),
        "r8": ("r8", 64, 0), "r9": ("r9", 64, 0), "r10": ("r10", 64, 0), "r11": ("r11", 64, 0),
        "r12": ("r12", 64, 0), "r13": ("r13", 64, 0), "r14": ("r14", 64, 0), "r15": ("r15", 64, 0),
        "rip": ("rip", 64, 0),
        # 32-bit (writing zero-extends into 64-bit per x86_64)
        "eax": ("rax", 32, 0), "ebx": ("rbx", 32, 0), "ecx": ("rcx", 32, 0), "edx": ("rdx", 32, 0),
        "esi": ("rsi", 32, 0), "edi": ("rdi", 32, 0), "ebp": ("rbp", 32, 0), "esp": ("rsp", 32, 0),
        "r8d": ("r8", 32, 0), "r9d": ("r9", 32, 0), "r10d": ("r10", 32, 0), "r11d": ("r11", 32, 0),
        "r12d": ("r12", 32, 0), "r13d": ("r13", 32, 0), "r14d": ("r14", 32, 0), "r15d": ("r15", 32, 0),
        # 16-bit
        "ax": ("rax", 16, 0), "bx": ("rbx", 16, 0), "cx": ("rcx", 16, 0), "dx": ("rdx", 16, 0),
        "si": ("rsi", 16, 0), "di": ("rdi", 16, 0), "bp": ("rbp", 16, 0), "sp": ("rsp", 16, 0),
        "r8w": ("r8", 16, 0), "r9w": ("r9", 16, 0), "r10w": ("r10", 16, 0), "r11w": ("r11", 16, 0),
        # 8-bit low
        "al": ("rax", 8, 0), "bl": ("rbx", 8, 0), "cl": ("rcx", 8, 0), "dl": ("rdx", 8, 0),
        "sil": ("rsi", 8, 0), "dil": ("rdi", 8, 0), "bpl": ("rbp", 8, 0), "spl": ("rsp", 8, 0),
        "r8b": ("r8", 8, 0), "r9b": ("r9", 8, 0), "r10b": ("r10", 8, 0), "r11b": ("r11", 8, 0),
        # 8-bit high
        "ah": ("rax", 8, 8), "bh": ("rbx", 8, 8), "ch": ("rcx", 8, 8), "dh": ("rdx", 8, 8),
    }

    def __init__(self, target_pid: Optional[int] = None):
        self.target_pid = target_pid
        self.regs: Dict[str, int] = {r: 0 for r in self.REG_64_NAMES}
        self.regs["rsp"] = self.DEFAULT_RSP
        self.flags: Dict[str, bool] = {"cf": False, "zf": False, "sf": False, "of": False, "pf": False}

        # Page-indexed shadow memory: page_addr -> bytearray(4096)
        self.pages: Dict[int, bytearray] = {}
        self.trace: List[StepTrace] = []
        self._snapshots: List[Tuple[Dict[str, int], Dict[str, bool], Dict[int, bytearray]]] = []

        if CAPSTONE_AVAILABLE:
            self._cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
            self._cs.detail = True
        else:
            self._cs = None

    # --- Register Management ---

    def get_reg(self, name: str) -> int:
        """Reads a register or sub-register value."""
        low = name.lower()
        if low in self.CAPSTONE_REG_MAP:
            base_reg, bits, shift = self.CAPSTONE_REG_MAP[low]
            val = (self.regs[base_reg] >> shift) & ((1 << bits) - 1)
            return val
        return self.regs.get(low, 0)

    def set_reg(self, name: str, val: int):
        """Writes a register or sub-register value."""
        low = name.lower()
        val = val & 0xFFFFFFFFFFFFFFFF
        if low in self.CAPSTONE_REG_MAP:
            base_reg, bits, shift = self.CAPSTONE_REG_MAP[low]
            if bits == 64:
                self.regs[base_reg] = val & 0xFFFFFFFFFFFFFFFF
            elif bits == 32:
                # In x86_64, writing 32-bit register clears upper 32-bits!
                self.regs[base_reg] = val & 0xFFFFFFFF
            else:
                # 16-bit or 8-bit modifies only designated slice
                mask = ((1 << bits) - 1) << shift
                inv_mask = (~mask) & 0xFFFFFFFFFFFFFFFF
                curr = self.regs[base_reg]
                new_val = (curr & inv_mask) | ((val & ((1 << bits) - 1)) << shift)
                self.regs[base_reg] = new_val
        elif low in self.regs:
            self.regs[low] = val

    # --- Shadow Memory Management ---

    def _get_page(self, addr: int, create: bool = False) -> Optional[bytearray]:
        page_base = addr & ~(self.PAGE_SIZE - 1)
        if page_base in self.pages:
            return self.pages[page_base]

        # Lazy read from target process if attached (used for both read and COW create)
        if self.target_pid and self.target_pid > 0:
            target_data = MemoryEngine.read_bytes(self.target_pid, page_base, self.PAGE_SIZE)
            if target_data:
                page_buf = bytearray(target_data.ljust(self.PAGE_SIZE, b"\x00"))
                self.pages[page_base] = page_buf
                return page_buf

        if create:
            new_page = bytearray(self.PAGE_SIZE)
            self.pages[page_base] = new_page
            return new_page

        return None

    def read_mem(self, addr: int, size: int) -> bytes:
        """Reads bytes from shadow memory or lazy target paging."""
        result = bytearray()
        remaining = size
        curr_addr = addr

        while remaining > 0:
            page = self._get_page(curr_addr, create=False)
            offset = curr_addr & (self.PAGE_SIZE - 1)
            chunk_size = min(remaining, self.PAGE_SIZE - offset)

            if page:
                result.extend(page[offset:offset + chunk_size])
            else:
                result.extend(b"\x00" * chunk_size)

            curr_addr += chunk_size
            remaining -= chunk_size

        return bytes(result)

    def write_mem(self, addr: int, data: bytes):
        """Writes bytes into local shadow memory (never modifies target process)."""
        remaining = len(data)
        curr_addr = addr
        data_offset = 0

        while remaining > 0:
            page = self._get_page(curr_addr, create=True)
            offset = curr_addr & (self.PAGE_SIZE - 1)
            chunk_size = min(remaining, self.PAGE_SIZE - offset)

            page[offset:offset + chunk_size] = data[data_offset:data_offset + chunk_size]

            curr_addr += chunk_size
            data_offset += chunk_size
            remaining -= chunk_size

    def read_u64(self, addr: int) -> int:
        raw = self.read_mem(addr, 8)
        return struct.unpack("<Q", raw)[0] if len(raw) == 8 else 0

    def write_u64(self, addr: int, val: int):
        self.write_mem(addr, struct.pack("<Q", val & 0xFFFFFFFFFFFFFFFF))

    def push(self, val: int):
        rsp = (self.regs["rsp"] - 8) & 0xFFFFFFFFFFFFFFFF
        self.regs["rsp"] = rsp
        self.write_u64(rsp, val)

    def pop(self) -> int:
        rsp = self.regs["rsp"]
        val = self.read_u64(rsp)
        self.regs["rsp"] = (rsp + 8) & 0xFFFFFFFFFFFFFFFF
        return val

    # --- Snapshots ---

    def save_snapshot(self):
        """Saves CPU and memory state to stack."""
        copied_pages = {k: bytearray(v) for k, v in self.pages.items()}
        self._snapshots.append((dict(self.regs), dict(self.flags), copied_pages))

    def restore_snapshot(self) -> bool:
        """Restores last saved CPU and memory state."""
        if not self._snapshots:
            return False
        regs, flags, pages = self._snapshots.pop()
        self.regs = regs
        self.flags = flags
        self.pages = pages
        return True

    # --- Execution & Stepping ---

    def _resolve_mem_operand(self, ins, mem_op) -> int:
        base_val = 0
        if mem_op.base != 0:
            reg_name = ins.reg_name(mem_op.base).lower()
            if reg_name == "rip":
                # In x86_64, RIP-relative displacement is relative to next instruction
                base_val = (self.regs["rip"] + ins.size) & 0xFFFFFFFFFFFFFFFF
            else:
                base_val = self.get_reg(reg_name)

        index_val = 0
        if mem_op.index != 0:
            reg_name = ins.reg_name(mem_op.index).lower()
            index_val = self.get_reg(reg_name)

        scale = mem_op.scale
        disp = mem_op.disp
        eff_addr = (base_val + (index_val * scale) + disp) & 0xFFFFFFFFFFFFFFFF
        return eff_addr

    def _resolve_operand_value(self, ins, op, record_reads: Optional[List[Tuple[int, int]]] = None) -> int:
        if op.type == x86.X86_OP_REG:
            return self.get_reg(ins.reg_name(op.value.reg))
        elif op.type == x86.X86_OP_IMM:
            return op.value.imm & 0xFFFFFFFFFFFFFFFF
        elif op.type == x86.X86_OP_MEM:
            addr = self._resolve_mem_operand(ins, op.value.mem)
            size = op.size if op.size > 0 else 8
            raw = self.read_mem(addr, size)
            val = 0
            if size == 1:
                val = raw[0] if raw else 0
            elif size == 2:
                val = struct.unpack("<H", raw)[0] if len(raw) == 2 else 0
            elif size == 4:
                val = struct.unpack("<I", raw)[0] if len(raw) == 4 else 0
            elif size == 8:
                val = struct.unpack("<Q", raw)[0] if len(raw) == 8 else 0
            if record_reads is not None:
                record_reads.append((addr, val))
            return val
        return 0

    def step(self) -> Tuple[bool, Optional[StepTrace], str]:
        """
        Executes a single instruction at current RIP.
        Returns (success, StepTrace, status_message).
        """
        if not CAPSTONE_AVAILABLE or not self._cs:
            return False, None, "Capstone engine not available"

        rip = self.regs["rip"]
        code_bytes = self.read_mem(rip, 15)
        if not code_bytes or all(b == 0 for b in code_bytes):
            return False, None, f"Zero or unmapped instruction bytes at 0x{rip:X}"

        disasms = list(self._cs.disasm(code_bytes, rip, count=1))
        if not disasms:
            return False, None, f"Failed to decode instruction at 0x{rip:X}"

        ins = disasms[0]
        mnemonic = ins.mnemonic.lower()
        next_rip = (rip + ins.size) & 0xFFFFFFFFFFFFFFFF

        old_regs = dict(self.regs)
        mem_reads: List[Tuple[int, int]] = []
        mem_writes: List[Tuple[int, int]] = []

        # Execute instruction semantics
        if mnemonic == "nop":
            self.regs["rip"] = next_rip

        elif mnemonic == "ret":
            ret_addr = self.pop()
            self.regs["rip"] = ret_addr
            trace = StepTrace(
                address=rip,
                mnemonic=mnemonic,
                op_str=ins.op_str,
                raw_bytes=ins.bytes,
                rip_before=rip,
                rip_after=ret_addr,
                regs_delta={"rip": (rip, ret_addr), "rsp": (old_regs["rsp"], self.regs["rsp"])}
            )
            self.trace.append(trace)
            return True, trace, "ret"

        elif mnemonic == "mov":
            dst, src = ins.operands[0], ins.operands[1]
            val = self._resolve_operand_value(ins, src, record_reads=mem_reads)
            if dst.type == x86.X86_OP_REG:
                self.set_reg(ins.reg_name(dst.value.reg), val)
            elif dst.type == x86.X86_OP_MEM:
                addr = self._resolve_mem_operand(ins, dst.value.mem)
                size = dst.size if dst.size > 0 else 8
                if size == 1:
                    self.write_mem(addr, bytes([val & 0xFF]))
                elif size == 2:
                    self.write_mem(addr, struct.pack("<H", val & 0xFFFF))
                elif size == 4:
                    self.write_mem(addr, struct.pack("<I", val & 0xFFFFFFFF))
                elif size == 8:
                    self.write_u64(addr, val)
                mem_writes.append((addr, val))
            self.regs["rip"] = next_rip

        elif mnemonic == "lea":
            dst, src = ins.operands[0], ins.operands[1]
            if src.type == x86.X86_OP_MEM:
                addr = self._resolve_mem_operand(ins, src.value.mem)
                self.set_reg(ins.reg_name(dst.value.reg), addr)
            self.regs["rip"] = next_rip

        elif mnemonic == "push":
            src = ins.operands[0]
            val = self._resolve_operand_value(ins, src, record_reads=mem_reads)
            self.push(val)
            self.regs["rip"] = next_rip

        elif mnemonic == "pop":
            dst = ins.operands[0]
            val = self.pop()
            if dst.type == x86.X86_OP_REG:
                self.set_reg(ins.reg_name(dst.value.reg), val)
            self.regs["rip"] = next_rip

        elif mnemonic in ("add", "sub", "xor", "and", "or"):
            dst, src = ins.operands[0], ins.operands[1]
            d_val = self._resolve_operand_value(ins, dst, record_reads=mem_reads)
            s_val = self._resolve_operand_value(ins, src, record_reads=mem_reads)

            if mnemonic == "add":
                res = (d_val + s_val) & 0xFFFFFFFFFFFFFFFF
            elif mnemonic == "sub":
                res = (d_val - s_val) & 0xFFFFFFFFFFFFFFFF
            elif mnemonic == "xor":
                res = d_val ^ s_val
            elif mnemonic == "and":
                res = d_val & s_val
            elif mnemonic == "or":
                res = d_val | s_val

            op_bits = (dst.size * 8) if (hasattr(dst, "size") and dst.size > 0) else 64
            sign_mask = 1 << (op_bits - 1)
            self.flags["zf"] = (res == 0)
            self.flags["sf"] = bool(res & sign_mask)

            if dst.type == x86.X86_OP_REG:
                self.set_reg(ins.reg_name(dst.value.reg), res)
            elif dst.type == x86.X86_OP_MEM:
                addr = self._resolve_mem_operand(ins, dst.value.mem)
                size = dst.size if dst.size > 0 else 8
                if size == 1:
                    self.write_mem(addr, bytes([res & 0xFF]))
                elif size == 2:
                    self.write_mem(addr, struct.pack("<H", res & 0xFFFF))
                elif size == 4:
                    self.write_mem(addr, struct.pack("<I", res & 0xFFFFFFFF))
                elif size == 8:
                    self.write_u64(addr, res)
                mem_writes.append((addr, res))
            self.regs["rip"] = next_rip

        elif mnemonic == "cmp":
            dst, src = ins.operands[0], ins.operands[1]
            d_val = self._resolve_operand_value(ins, dst, record_reads=mem_reads)
            s_val = self._resolve_operand_value(ins, src, record_reads=mem_reads)
            res = (d_val - s_val) & 0xFFFFFFFFFFFFFFFF
            self.flags["zf"] = (d_val == s_val)
            self.flags["cf"] = (d_val < s_val)
            op_bits = (dst.size * 8) if (hasattr(dst, "size") and dst.size > 0) else 64
            sign_mask = 1 << (op_bits - 1)
            self.flags["sf"] = bool(res & sign_mask)
            self.regs["rip"] = next_rip

        elif mnemonic == "test":
            dst, src = ins.operands[0], ins.operands[1]
            d_val = self._resolve_operand_value(ins, dst, record_reads=mem_reads)
            s_val = self._resolve_operand_value(ins, src, record_reads=mem_reads)
            res = d_val & s_val
            op_bits = (dst.size * 8) if (hasattr(dst, "size") and dst.size > 0) else 64
            sign_mask = 1 << (op_bits - 1)
            self.flags["zf"] = (res == 0)
            self.flags["sf"] = bool(res & sign_mask)
            self.flags["cf"] = False
            self.regs["rip"] = next_rip

        elif mnemonic == "jmp":
            target = self._resolve_operand_value(ins, ins.operands[0])
            self.regs["rip"] = target

        elif mnemonic in ("je", "jz"):
            target = self._resolve_operand_value(ins, ins.operands[0])
            self.regs["rip"] = target if self.flags["zf"] else next_rip

        elif mnemonic in ("jne", "jnz"):
            target = self._resolve_operand_value(ins, ins.operands[0])
            self.regs["rip"] = target if not self.flags["zf"] else next_rip

        elif mnemonic in ("jb", "jc"):
            target = self._resolve_operand_value(ins, ins.operands[0])
            self.regs["rip"] = target if self.flags["cf"] else next_rip

        elif mnemonic in ("jnb", "jnc", "jae"):
            target = self._resolve_operand_value(ins, ins.operands[0])
            self.regs["rip"] = target if not self.flags["cf"] else next_rip

        elif mnemonic == "call":
            target = self._resolve_operand_value(ins, ins.operands[0])
            self.push(next_rip)
            self.regs["rip"] = target

        else:
            # Fallback for unrecognized instruction: advance RIP
            self.regs["rip"] = next_rip

        # Record register deltas
        regs_delta = {}
        for r, old_v in old_regs.items():
            new_v = self.regs[r]
            if old_v != new_v:
                regs_delta[r] = (old_v, new_v)

        trace = StepTrace(
            address=rip,
            mnemonic=ins.mnemonic,
            op_str=ins.op_str,
            raw_bytes=ins.bytes,
            rip_before=rip,
            rip_after=self.regs["rip"],
            regs_delta=regs_delta,
            mem_reads=mem_reads,
            mem_writes=mem_writes
        )
        self.trace.append(trace)
        return True, trace, "ok"

    def run(self, max_steps: int = 1000, stop_at: Optional[int] = None) -> EmulationResult:
        """
        Executes instructions continuously until ret, stop_at address, or step limit.
        """
        steps = 0
        terminated = False
        reason = "step_limit"

        while steps < max_steps:
            if stop_at and self.regs["rip"] == stop_at:
                terminated = True
                reason = "stop_address_reached"
                break

            success, trace, msg = self.step()
            if not success:
                terminated = False
                reason = f"fault: {msg}"
                break

            steps += 1
            if msg == "ret":
                terminated = True
                reason = "returned"
                break

        return EmulationResult(
            steps_executed=steps,
            terminated=terminated,
            halt_reason=reason,
            final_rip=self.regs["rip"],
            registers=dict(self.regs),
            trace=self.trace
        )
