"""
PhantomSuite Python Scripting & Plugin Engine
Provides an interactive scripting namespace and plugin architecture
for automating process analysis, custom hooks, and batch memory tasks.
"""

import sys
import io
import os
import glob
import importlib.util
from typing import Dict, Any, Optional, Callable, List, Tuple
from phantom_suite.core.memory_engine import MemoryEngine, TypeFormat
from phantom_suite.core.pattern_scanner import PatternScanner
from phantom_suite.core.struct_dissector import StructDissector
from phantom_suite.core.elf_explorer import ElfExplorer
from phantom_suite.core.table_serializer import TableSerializer
from phantom_suite.core.disassembler import Disassembler
from phantom_suite.core.speedhack_controller import SpeedhackController
from phantom_suite.core.handle_tracer import HandleTracer
from phantom_suite.core.symbolic_solver import SymbolicPointerSolver
from phantom_suite.core.dwarf_synthesizer import DwarfSynthesizer
from phantom_suite.core.cfg_engine import CFGEngine
from phantom_suite.core.heap_inspector import HeapInspector
from phantom_suite.core.detour_engine import DetourEngine
from phantom_suite.core.pmu_profiler import PmuProfiler
from phantom_suite.core.il2cpp_inspector import Il2CppInspector
from phantom_suite.core.micro_emulator import MicroEmulator
from phantom_suite.core.entropy_crypto_scanner import EntropyCryptoScanner
from phantom_suite.core.socket_stream_interceptor import SocketStreamInterceptor
from phantom_suite.core.core_dump_gdb_bridge import CoreDumpReader, GdbMiBridge


class ScriptEngine:
    """Embedded Python runtime environment for PhantomSuite scripting & automation."""

    def __init__(self, target_pid: Optional[int] = None):
        self.target_pid = target_pid
        self.custom_globals: Dict[str, Any] = {}
        self._init_environment()

    def set_target(self, pid: int):
        self.target_pid = pid
        self._init_environment()

    def _init_environment(self):
        """Builds convenient helper functions in the script namespace."""
        pid = self.target_pid

        def _read(addr: int, size: int) -> bytes:
            return MemoryEngine.read_bytes(pid, addr, size) if pid else b""

        def _write(addr: int, data: bytes) -> bool:
            return MemoryEngine.write_bytes(pid, addr, data) if pid else False

        def _read_i32(addr: int) -> Optional[int]:
            return MemoryEngine.read_typed(pid, addr, "int32") if pid else None

        def _write_i32(addr: int, val: int) -> bool:
            return MemoryEngine.write_typed(pid, addr, "int32", val) if pid else False

        def _read_float(addr: int) -> Optional[float]:
            return MemoryEngine.read_typed(pid, addr, "float") if pid else None

        def _write_float(addr: int, val: float) -> bool:
            return MemoryEngine.write_typed(pid, addr, "float", val) if pid else False

        def _scan(pat: str) -> List[Any]:
            return PatternScanner.scan_pattern(pid, pat) if pid else []

        def _disasm(addr: int, length: int = 32):
            return Disassembler.disassemble(pid, addr, length=length) if pid else []

        def _dissect(addr: int, size: int = 128):
            return StructDissector.dissect(pid, addr, size=size) if pid else []

        def _symbols(mod_name: str = ""):
            if not pid:
                return []
            mods = ElfExplorer.get_loaded_modules(pid)
            if mod_name:
                mod = next((m for m in mods if mod_name in m.name), None)
                return ElfExplorer.parse_symbols(mod.path, base_address=mod.base_address) if mod else []
            return mods

        def _il2cpp_class(addr: int):
            return Il2CppInspector.inspect_class(pid, addr) if pid else None

        def _il2cpp_obj(addr: int):
            return Il2CppInspector.inspect_object(pid, addr) if pid else None

        def _il2cpp_str(addr: int):
            return Il2CppInspector.read_il2cpp_string(pid, addr) if pid else ""

        def _sockets():
            return SocketStreamInterceptor.get_process_sockets(pid) if pid else []

        def _crypto():
            return EntropyCryptoScanner.scan_process(pid) if pid else ([], [])

        def _entropy(data_or_addr, size: int = 1024):
            if isinstance(data_or_addr, (bytes, bytearray)):
                return EntropyCryptoScanner.calculate_entropy(data_or_addr)
            elif isinstance(data_or_addr, int) and pid:
                data = MemoryEngine.read_bytes(pid, data_or_addr, size)
                return EntropyCryptoScanner.calculate_entropy(data)
            return 0.0

        def _emulate(addr: int, steps: int = 50):
            emu = MicroEmulator(target_pid=pid)
            emu.set_reg("rip", addr)
            return emu.run(max_steps=steps)

        def _core_dump(path: str):
            reader = CoreDumpReader(path)
            reader.load()
            return reader

        helpers = {
            "pid": pid,
            "read": _read,
            "write": _write,
            "read_i32": _read_i32,
            "write_i32": _write_i32,
            "read_float": _read_float,
            "write_float": _write_float,
            "scan": _scan,
            "disasm": _disasm,
            "dissect": _dissect,
            "symbols": _symbols,
            "il2cpp_class": _il2cpp_class,
            "il2cpp_obj": _il2cpp_obj,
            "il2cpp_str": _il2cpp_str,
            "sockets": _sockets,
            "crypto": _crypto,
            "entropy": _entropy,
            "emulate": _emulate,
            "core_dump": _core_dump,
            "MemoryEngine": MemoryEngine,
            "PatternScanner": PatternScanner,
            "StructDissector": StructDissector,
            "ElfExplorer": ElfExplorer,
            "TableSerializer": TableSerializer,
            "SpeedhackController": SpeedhackController,
            "HandleTracer": HandleTracer,
            "Disassembler": Disassembler,
            "SymbolicPointerSolver": SymbolicPointerSolver,
            "DwarfSynthesizer": DwarfSynthesizer,
            "CFGEngine": CFGEngine,
            "HeapInspector": HeapInspector,
            "DetourEngine": DetourEngine,
            "PmuProfiler": PmuProfiler,
            "Il2CppInspector": Il2CppInspector,
            "MicroEmulator": MicroEmulator,
            "EntropyCryptoScanner": EntropyCryptoScanner,
            "SocketStreamInterceptor": SocketStreamInterceptor,
            "CoreDumpReader": CoreDumpReader,
            "GdbMiBridge": GdbMiBridge,
        }
        self.custom_globals.update(helpers)

    def execute(self, code_str: str) -> Tuple[bool, str]:
        """
        Executes a block of Python code, capturing stdout and stderr.
        Supports single expressions, multi-statement scripts, and hybrid
        blocks where the final expression is evaluated and displayed (REPL-style).
        Returns (success, output_string).
        """
        code_str = code_str.strip()
        if not code_str:
            return True, ""

        import ast
        import traceback

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        sys.stdout = stdout_buf
        sys.stderr = stderr_buf

        success = True
        try:
            tree = ast.parse(code_str, filename="<script>", mode="exec")
            if not tree.body:
                pass
            elif isinstance(tree.body[-1], ast.Expr):
                body_exec = tree.body[:-1]
                last_expr = tree.body[-1]

                if body_exec:
                    mod = ast.Module(body=body_exec, type_ignores=[])
                    compiled_exec = compile(mod, filename="<script>", mode="exec")
                    exec(compiled_exec, self.custom_globals)

                expr_mod = ast.Expression(body=last_expr.value)
                compiled_eval = compile(expr_mod, filename="<script>", mode="eval")
                res = eval(compiled_eval, self.custom_globals)
                if res is not None:
                    print(repr(res))
            else:
                compiled_exec = compile(tree, filename="<script>", mode="exec")
                exec(compiled_exec, self.custom_globals)
        except (Exception, SystemExit):
            success = False
            traceback.print_exc(file=stderr_buf)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = stdout_buf.getvalue() + stderr_buf.getvalue()
        return success, output

    def reset_environment(self):
        """Clears all user variables and re-initializes custom globals."""
        self.custom_globals.clear()
        self._init_environment()

    @classmethod
    def load_plugins(cls, plugin_dir: str) -> List[str]:
        """Discovers and imports .py plugins from directory."""
        loaded = []
        if not os.path.exists(plugin_dir):
            return loaded

        for fpath in glob.glob(os.path.join(plugin_dir, "*.py")):
            mod_name = os.path.splitext(os.path.basename(fpath))[0]
            try:
                spec = importlib.util.spec_from_file_location(mod_name, fpath)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    loaded.append(mod_name)
            except Exception:
                pass

        return loaded
