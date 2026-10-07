"""
PhantomSuite Mid-Function Detour & Trampoline Hook Engine
Disassembles instruction boundaries using Capstone, relocates displaced x86_64 instructions,
generates relative (5-byte) and absolute (14-byte) detour trampolines, and safely manages hook lifecycles.
"""

import struct
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

try:
    import capstone
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    HAS_CAPSTONE = True
except ImportError:
    HAS_CAPSTONE = False

from phantom_suite.core.memory_engine import MemoryEngine


@dataclass
class DetourHook:
    hook_id: str
    target_address: int
    cave_address: int
    stolen_bytes: bytes
    stolen_length: int
    trampoline_bytes: bytes
    is_absolute: bool
    is_installed: bool = False


class DetourEngine:
    """Manages low-level inline detour hooks and trampoline generation on x86_64."""

    _active_hooks: Dict[str, DetourHook] = {}

    @classmethod
    def is_available(cls) -> bool:
        return HAS_CAPSTONE

    @classmethod
    def calculate_stolen_boundary(
        cls,
        raw_code: bytes,
        start_address: int,
        required_length: int
    ) -> Optional[Tuple[int, bytes, List[Tuple[int, int, str, str]]]]:
        """
        Disassembles instructions at start_address to find the minimum instruction boundary >= required_length.
        Returns: (stolen_length, stolen_bytes, list of (addr, size, mnem, op_str)).
        """
        if not HAS_CAPSTONE or len(raw_code) < required_length:
            return None

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = True

        stolen_len = 0
        instructions = []

        try:
            for ins in md.disasm(raw_code, start_address):
                stolen_len += ins.size
                instructions.append((ins.address, ins.size, ins.mnemonic, ins.op_str))
                if stolen_len >= required_length:
                    break
        except Exception:
            return None

        if stolen_len < required_length:
            return None

        return (stolen_len, raw_code[:stolen_len], instructions)

    @classmethod
    def build_detour_jump(
        cls,
        source_addr: int,
        destination_addr: int,
        force_absolute: bool = False
    ) -> Tuple[bytes, bool]:
        """
        Generates x86_64 jump payload:
        - 5-byte relative jump if within +-2GB: E9 <disp32>
        - 14-byte absolute jump: FF 25 00 00 00 00 <64-bit destination>
        Returns: (payload_bytes, is_absolute).
        """
        delta = destination_addr - (source_addr + 5)
        can_rel32 = not force_absolute and (-0x80000000 <= delta <= 0x7FFFFFFF)

        if can_rel32:
            disp32 = struct.pack("<i", delta)
            return (b"\xE9" + disp32, False)

        # 14-byte absolute jump: jmp qword ptr [rip+0]
        # FF 25 00 00 00 00 followed by 8-byte pointer
        opcode = b"\xFF\x25\x00\x00\x00\x00"
        addr_bytes = struct.pack("<Q", destination_addr)
        return (opcode + addr_bytes, True)

    @classmethod
    def create_trampoline(
        cls,
        target_addr: int,
        cave_addr: int,
        stolen_bytes: bytes,
        stolen_len: int
    ) -> bytes:
        """
        Constructs the trampoline stub that executes the displaced instructions
        and jumps back to the original function continuation (target_addr + stolen_len).
        """
        continuation_addr = target_addr + stolen_len
        jump_back, _ = cls.build_detour_jump(
            source_addr=cave_addr + stolen_len,
            destination_addr=continuation_addr,
            force_absolute=True # Guarantee return jump works regardless of distance
        )
        return stolen_bytes + jump_back

    @classmethod
    def install_hook(
        cls,
        pid: int,
        target_address: int,
        cave_address: int,
        hook_id: Optional[str] = None
    ) -> Optional[DetourHook]:
        """
        Installs a mid-function detour hook in target PID:
        1. Reads instructions at target_address
        2. Calculates instruction boundary >= 14 bytes (or 5 bytes)
        3. Writes trampoline into cave_address
        4. Writes detour jump + NOP padding into target_address
        """
        if not HAS_CAPSTONE or not pid or pid <= 0 or target_address <= 0 or cave_address <= 0:
            return None

        hook_key = hook_id or f"hook_0x{target_address:X}"
        if hook_key in cls._active_hooks:
            return cls._active_hooks[hook_key]

        # Read 32 bytes for instruction disassembly
        raw_code = MemoryEngine.read_bytes(pid, target_address, 32)
        if not raw_code:
            return None

        # Check if 5-byte relative jump is possible
        delta = cave_address - (target_address + 5)
        can_rel32 = (-0x80000000 <= delta <= 0x7FFFFFFF)
        req_len = 5 if can_rel32 else 14

        boundary = cls.calculate_stolen_boundary(raw_code, target_address, req_len)
        if not boundary:
            # Fall back to 14 bytes if 5 bytes split an instruction unfavorably
            boundary = cls.calculate_stolen_boundary(raw_code, target_address, 14)
            if not boundary:
                return None

        stolen_len, stolen_bytes, _ = boundary
        detour_jump, is_abs = cls.build_detour_jump(target_address, cave_address, force_absolute=not can_rel32)

        # Pad remaining stolen bytes with NOP (0x90)
        padding_len = stolen_len - len(detour_jump)
        if padding_len < 0:
            return None
        patch_payload = detour_jump + (b"\x90" * padding_len)

        # Build trampoline
        trampoline = cls.create_trampoline(target_address, cave_address, stolen_bytes, stolen_len)

        # 1. Write trampoline to cave
        if not MemoryEngine.write_bytes(pid, cave_address, trampoline):
            return None

        # 2. Write patch to target
        if not MemoryEngine.write_bytes(pid, target_address, patch_payload):
            return None

        hook = DetourHook(
            hook_id=hook_key,
            target_address=target_address,
            cave_address=cave_address,
            stolen_bytes=stolen_bytes,
            stolen_length=stolen_len,
            trampoline_bytes=trampoline,
            is_absolute=is_abs,
            is_installed=True
        )
        cls._active_hooks[hook_key] = hook
        return hook

    @classmethod
    def remove_hook(cls, pid: int, hook_id: str) -> bool:
        """Restores original instructions and removes detour hook."""
        if hook_id not in cls._active_hooks:
            return False

        hook = cls._active_hooks[hook_id]
        if not MemoryEngine.write_bytes(pid, hook.target_address, hook.stolen_bytes):
            return False

        hook.is_installed = False
        del cls._active_hooks[hook_id]
        return True

    @classmethod
    def get_active_hooks(cls) -> Dict[str, DetourHook]:
        return dict(cls._active_hooks)
