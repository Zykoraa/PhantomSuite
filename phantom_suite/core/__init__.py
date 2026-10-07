"""
PhantomSuite Core Package
Linux Process & Memory Inspection Subsystem
"""

from phantom_suite.core.memory_engine import (
    MemoryEngine, TypeFormat, ScanType, ScanResult, FreezeManager, MemoryRegion
)
from phantom_suite.core.process_manager import ProcessManager, ProcessInfo
from phantom_suite.core.injector import Injector
from phantom_suite.core.hex_viewer import HexViewer, HexLine
from phantom_suite.core.disassembler import Disassembler, Instruction
from phantom_suite.core.pointer_scanner import PointerScanner, PointerPath
from phantom_suite.core.table_serializer import TableSerializer
from phantom_suite.core.speedhack_controller import SpeedhackController
from phantom_suite.core.thread_manager import ThreadManager, ThreadInfo
from phantom_suite.core.handle_tracer import HandleTracer, SocketInfo, HandleInfo
from phantom_suite.core.pattern_scanner import PatternScanner, PatternMatch
from phantom_suite.core.struct_dissector import StructDissector, DissectedField
from phantom_suite.core.elf_explorer import ElfExplorer, ElfSymbol, ElfSection, LoadedModule
from phantom_suite.core.snapshot_engine import SnapshotEngine, MemorySnapshot, SnapshotDiffItem, SnapshotRegion
from phantom_suite.core.memory_map import MemoryMapAnalyzer, VisualMemoryBlock, MapCategoryStats
from phantom_suite.core.syscall_tracer import SyscallTracer, SyscallEvent
from phantom_suite.core.data_deserializer import DataDeserializer, DecodedString, DecodedVector, DecodedJson
from phantom_suite.core.watchpoint_tracer import WatchpointTracer, WatchpointHit
from phantom_suite.core.script_engine import ScriptEngine
from phantom_suite.core.symbolic_solver import (
    SymbolicPointerSolver, SymbolicStructSynthesizer, SymbolicGraph, SymbolicEdge
)
from phantom_suite.core.dwarf_synthesizer import DwarfSynthesizer, DwarfStruct, DwarfMember
from phantom_suite.core.cfg_engine import CFGEngine, ControlFlowGraph, BasicBlock, CFGInstruction
from phantom_suite.core.heap_inspector import HeapInspector, HeapSnapshot, HeapChunk
from phantom_suite.core.detour_engine import DetourEngine, DetourHook
from phantom_suite.core.pmu_profiler import PmuProfiler, TimingProfileReport, AntiDebugIndicator

__all__ = [
    "MemoryEngine",
    "TypeFormat",
    "ScanType",
    "ScanResult",
    "FreezeManager",
    "MemoryRegion",
    "ProcessManager",
    "ProcessInfo",
    "Injector",
    "HexViewer",
    "HexLine",
    "Disassembler",
    "Instruction",
    "PointerScanner",
    "PointerPath",
    "TableSerializer",
    "SpeedhackController",
    "ThreadManager",
    "ThreadInfo",
    "HandleTracer",
    "SocketInfo",
    "HandleInfo",
    "PatternScanner",
    "PatternMatch",
    "StructDissector",
    "DissectedField",
    "ElfExplorer",
    "ElfSymbol",
    "ElfSection",
    "LoadedModule",
    "SnapshotEngine",
    "MemorySnapshot",
    "SnapshotDiffItem",
    "SnapshotRegion",
    "MemoryMapAnalyzer",
    "VisualMemoryBlock",
    "MapCategoryStats",
    "SyscallTracer",
    "SyscallEvent",
    "DataDeserializer",
    "DecodedString",
    "DecodedVector",
    "DecodedJson",
    "WatchpointTracer",
    "WatchpointHit",
    "ScriptEngine",
    "SymbolicPointerSolver",
    "SymbolicStructSynthesizer",
    "SymbolicGraph",
    "SymbolicEdge",
    "DwarfSynthesizer",
    "DwarfStruct",
    "DwarfMember",
    "CFGEngine",
    "ControlFlowGraph",
    "BasicBlock",
    "CFGInstruction",
    "HeapInspector",
    "HeapSnapshot",
    "HeapChunk",
    "DetourEngine",
    "DetourHook",
    "PmuProfiler",
    "TimingProfileReport",
    "AntiDebugIndicator",
]
