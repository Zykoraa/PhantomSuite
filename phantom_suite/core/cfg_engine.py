"""
PhantomSuite Control Flow Graph (CFG) Engine
Disassembles x86_64 functions using Capstone, partitions instructions into basic blocks,
constructs directed control flow graphs, computes layered DAG layouts (Sugiyama),
and provides runtime branch inversion and NOP patching.
"""

import struct
from typing import List, Dict, Tuple, Optional, Set, Any
from dataclasses import dataclass, field

try:
    import capstone
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    HAS_CAPSTONE = True
except ImportError:
    HAS_CAPSTONE = False

from phantom_suite.core.memory_engine import MemoryEngine


# Branch classification tables for x86_64
CONDITIONAL_BRANCHES = {
    "je", "jz", "jne", "jnz", "jg", "jnle", "jge", "jnl",
    "jl", "jnge", "jle", "jng", "ja", "jnbe", "jae", "jnb",
    "jb", "jnae", "jbe", "jna", "js", "jns", "jo", "jno",
    "jp", "jpe", "jnp", "jpo", "jcxz", "jecxz", "jrcxz", "loop", "loope", "loopne"
}

UNCONDITIONAL_BRANCHES = {"jmp"}
CALL_INSTRUCTIONS = {"call"}
RET_INSTRUCTIONS = {"ret", "retn", "retf"}

# Inversion lookup table: op_name -> (inverted_op_name, 1-byte opcode pair, 2-byte 0x0F pair)
BRANCH_INVERSION_OPCODES = {
    # 1-byte short jumps (0x70 - 0x7F)
    0x74: 0x75, 0x75: 0x74, # je <-> jne
    0x7C: 0x7D, 0x7D: 0x7C, # jl <-> jge
    0x7E: 0x7F, 0x7F: 0x7E, # jle <-> jg
    0x72: 0x73, 0x73: 0x72, # jb <-> jae
    0x76: 0x77, 0x77: 0x76, # jbe <-> ja
    0x78: 0x79, 0x79: 0x78, # js <-> jns
    0x7A: 0x7B, 0x7B: 0x7A, # jp <-> jnp
    0x70: 0x71, 0x71: 0x70, # jo <-> jno
}

BRANCH_INVERSION_0F_OPCODES = {
    # 2-byte near jumps (0x0F 0x80 - 0x0F 0x8F)
    0x84: 0x85, 0x85: 0x84, # je <-> jne
    0x8C: 0x8D, 0x8D: 0x8C, # jl <-> jge
    0x8E: 0x8F, 0x8F: 0x8E, # jle <-> jg
    0x82: 0x83, 0x83: 0x82, # jb <-> jae
    0x86: 0x87, 0x87: 0x86, # jbe <-> ja
    0x88: 0x89, 0x89: 0x88, # js <-> jns
    0x8A: 0x8B, 0x8B: 0x8A, # jp <-> jnp
    0x80: 0x81, 0x81: 0x80, # jo <-> jno
}


@dataclass
class CFGInstruction:
    address: int
    mnemonic: str
    op_str: str
    size: int
    raw_bytes: bytes
    is_branch: bool
    is_conditional: bool
    is_call: bool
    is_ret: bool
    jump_target: Optional[int] = None


@dataclass
class BasicBlock:
    id: int
    start_addr: int
    end_addr: int
    instructions: List[CFGInstruction] = field(default_factory=list)
    successors: List[int] = field(default_factory=list) # target block IDs
    predecessors: List[int] = field(default_factory=list)
    edge_types: Dict[int, str] = field(default_factory=dict) # succ_id -> "taken" | "fallthrough" | "unconditional" | "indirect"
    # Layout coordinates for GUI rendering
    x: float = 0.0
    y: float = 0.0
    layer: int = 0


@dataclass
class ControlFlowGraph:
    entry_block_id: int
    blocks: Dict[int, BasicBlock] = field(default_factory=dict)
    total_instructions: int = 0

    def get_entry_block(self) -> Optional[BasicBlock]:
        return self.blocks.get(self.entry_block_id)


class CFGEngine:
    """Disassembles functions and constructs structured control flow graphs."""

    @classmethod
    def is_available(cls) -> bool:
        return HAS_CAPSTONE

    @classmethod
    def build_cfg(
        cls,
        pid: int,
        entry_address: int,
        max_bytes: int = 2048,
        max_blocks: int = 100
    ) -> Optional[ControlFlowGraph]:
        """
        Disassembles memory at entry_address and constructs a partitioned ControlFlowGraph.
        """
        if not HAS_CAPSTONE or not pid or pid <= 0 or entry_address <= 0:
            return None

        raw = MemoryEngine.read_bytes(pid, entry_address, max_bytes)
        if not raw:
            return None

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = True

        # Disassemble linear instructions
        parsed_instructions: List[CFGInstruction] = []
        try:
            for ins in md.disasm(raw, entry_address):
                mnem = ins.mnemonic.lower()
                op_str = ins.op_str.strip()
                
                is_cond = mnem in CONDITIONAL_BRANCHES
                is_uncond = mnem in UNCONDITIONAL_BRANCHES
                is_branch = is_cond or is_uncond
                is_call = mnem in CALL_INSTRUCTIONS
                is_ret = mnem in RET_INSTRUCTIONS

                # Calculate jump target if immediate hex
                jump_tgt = None
                if is_branch or is_call:
                    if op_str.startswith("0x") or op_str.isdigit():
                        try:
                            jump_tgt = int(op_str, 16) if op_str.startswith("0x") else int(op_str)
                        except ValueError:
                            pass

                cfg_ins = CFGInstruction(
                    address=ins.address,
                    mnemonic=mnem,
                    op_str=op_str,
                    size=ins.size,
                    raw_bytes=bytes(ins.bytes),
                    is_branch=is_branch,
                    is_conditional=is_cond,
                    is_call=is_call,
                    is_ret=is_ret,
                    jump_target=jump_tgt
                )
                parsed_instructions.append(cfg_ins)
        except Exception:
            return None

        if not parsed_instructions:
            return None

        # Identify leader addresses (start of basic blocks):
        # 1. Function entry address
        # 2. Target of any branch instruction
        # 3. Instruction following a branch or ret
        leaders: Set[int] = {entry_address}
        ins_map: Dict[int, CFGInstruction] = {ins.address: ins for ins in parsed_instructions}
        min_addr = parsed_instructions[0].address
        max_addr = parsed_instructions[-1].address + parsed_instructions[-1].size

        for i, ins in enumerate(parsed_instructions):
            if ins.is_branch or ins.is_ret:
                if ins.jump_target is not None and min_addr <= ins.jump_target < max_addr:
                    leaders.add(ins.jump_target)
                if i + 1 < len(parsed_instructions):
                    leaders.add(parsed_instructions[i + 1].address)

        # Partition instructions into BasicBlocks
        sorted_leaders = sorted(list(leaders))
        addr_to_block_id: Dict[int, int] = {}
        blocks: Dict[int, BasicBlock] = {}

        for bid, l_addr in enumerate(sorted_leaders):
            if l_addr not in ins_map:
                continue
            addr_to_block_id[l_addr] = bid
            bb = BasicBlock(id=bid, start_addr=l_addr, end_addr=l_addr)
            blocks[bid] = bb

        current_block: Optional[BasicBlock] = None
        for ins in parsed_instructions:
            if ins.address in addr_to_block_id:
                bid = addr_to_block_id[ins.address]
                current_block = blocks[bid]

            if current_block is not None:
                current_block.instructions.append(ins)
                current_block.end_addr = ins.address + ins.size

        # Remove empty blocks
        blocks = {bid: bb for bid, bb in blocks.items() if bb.instructions}

        # Resolve edges between blocks
        for bb in blocks.values():
            if not bb.instructions:
                continue
            last_ins = bb.instructions[-1]

            if last_ins.is_ret:
                # Terminal block, no successors
                continue

            elif last_ins.is_conditional:
                # 2 edges: taken (jump_target) and fallthrough (next instruction)
                if last_ins.jump_target in addr_to_block_id:
                    succ_id = addr_to_block_id[last_ins.jump_target]
                    bb.successors.append(succ_id)
                    bb.edge_types[succ_id] = "taken"
                    if succ_id in blocks:
                        blocks[succ_id].predecessors.append(bb.id)

                fallthrough_addr = last_ins.address + last_ins.size
                if fallthrough_addr in addr_to_block_id:
                    succ_id = addr_to_block_id[fallthrough_addr]
                    bb.successors.append(succ_id)
                    bb.edge_types[succ_id] = "fallthrough"
                    if succ_id in blocks:
                        blocks[succ_id].predecessors.append(bb.id)

            elif last_ins.is_branch: # Unconditional jmp
                if last_ins.jump_target in addr_to_block_id:
                    succ_id = addr_to_block_id[last_ins.jump_target]
                    bb.successors.append(succ_id)
                    bb.edge_types[succ_id] = "unconditional"
                    if succ_id in blocks:
                        blocks[succ_id].predecessors.append(bb.id)

            else:
                # Ordinary fallthrough to next block
                next_addr = last_ins.address + last_ins.size
                if next_addr in addr_to_block_id:
                    succ_id = addr_to_block_id[next_addr]
                    bb.successors.append(succ_id)
                    bb.edge_types[succ_id] = "fallthrough"
                    if succ_id in blocks:
                        blocks[succ_id].predecessors.append(bb.id)

        entry_bid = addr_to_block_id.get(entry_address, 0)
        cfg = ControlFlowGraph(
            entry_block_id=entry_bid,
            blocks=blocks,
            total_instructions=len(parsed_instructions)
        )

        # Compute layered DAG visual coordinates (Sugiyama)
        cls._layout_sugiyama(cfg)
        return cfg

    @classmethod
    def _layout_sugiyama(cls, cfg: ControlFlowGraph):
        """Assigns layers and (x, y) coordinates for interactive graph rendering."""
        if not cfg.blocks:
            return

        # 1. Layer assignment via BFS / Topological distance
        layers: Dict[int, List[int]] = {}
        visited: Set[int] = set()
        queue: List[Tuple[int, int]] = [(cfg.entry_block_id, 0)] # (bid, layer)

        while queue:
            bid, layer = queue.pop(0)
            if bid not in cfg.blocks or bid in visited:
                continue
            visited.add(bid)

            bb = cfg.blocks[bid]
            bb.layer = layer
            layers.setdefault(layer, []).append(bid)

            for succ in bb.successors:
                if succ not in visited:
                    queue.append((succ, layer + 1))

        # Position unconnected blocks in layer 0
        for bid, bb in cfg.blocks.items():
            if bid not in visited:
                bb.layer = 0
                layers.setdefault(0, []).append(bid)

        # 2. Coordinate calculation
        node_width = 240
        node_height_base = 60
        x_spacing = 60
        y_spacing = 80

        for layer_idx, block_ids in layers.items():
            total_layer_width = len(block_ids) * node_width + (len(block_ids) - 1) * x_spacing
            start_x = -total_layer_width / 2.0

            for idx, bid in enumerate(block_ids):
                bb = cfg.blocks[bid]
                bb.x = float(start_x + idx * (node_width + x_spacing))
                # Compute approximate height based on instruction count
                inst_count = len(bb.instructions)
                calculated_height = node_height_base + inst_count * 18
                bb.y = float(layer_idx * (calculated_height + y_spacing))

    @classmethod
    def invert_branch(cls, pid: int, branch_address: int) -> bool:
        """
        Inverts a conditional jump in live memory (e.g., JE <-> JNE, JLE <-> JG).
        Patches the target process memory using process_vm_writev.
        """
        if not pid or pid <= 0 or branch_address <= 0:
            return False

        raw = MemoryEngine.read_bytes(pid, branch_address, 6)
        if not raw:
            return False

        # 1. Check 1-byte opcode short jump (0x70 - 0x7F)
        first_b = raw[0]
        if first_b in BRANCH_INVERSION_OPCODES:
            new_b = BRANCH_INVERSION_OPCODES[first_b]
            return MemoryEngine.write_bytes(pid, branch_address, bytes([new_b]))

        # 2. Check 2-byte near jump (0x0F 0x80 - 0x0F 0x8F)
        if len(raw) >= 2 and first_b == 0x0F and raw[1] in BRANCH_INVERSION_0F_OPCODES:
            new_second = BRANCH_INVERSION_0F_OPCODES[raw[1]]
            patch = bytes([0x0F, new_second])
            return MemoryEngine.write_bytes(pid, branch_address, patch)

        return False

    @classmethod
    def nop_instructions(cls, pid: int, address: int, length: int) -> bool:
        """Replaces `length` bytes at `address` with 0x90 NOP instructions."""
        if not pid or pid <= 0 or address <= 0 or length <= 0:
            return False

        nops = b"\x90" * length
        return MemoryEngine.write_bytes(pid, address, nops)
