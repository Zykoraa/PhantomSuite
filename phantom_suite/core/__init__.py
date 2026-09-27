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
]
