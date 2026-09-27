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

        self.custom_globals = {
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
            "MemoryEngine": MemoryEngine,
            "PatternScanner": PatternScanner,
            "StructDissector": StructDissector,
            "ElfExplorer": ElfExplorer,
            "TableSerializer": TableSerializer,
            "SpeedhackController": SpeedhackController,
            "HandleTracer": HandleTracer
        }

    def execute(self, code_str: str) -> Tuple[bool, str]:
        """
        Executes a block of Python code, capturing stdout and stderr.
        Returns (success, output_string).
        """
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        sys.stdout = stdout_buf
        sys.stderr = stderr_buf

        success = True
        try:
            # First try evaluating as single expression (like REPL)
            try:
                code_obj = compile(code_str, "<script>", "eval")
                res = eval(code_obj, self.custom_globals)
                if res is not None:
                    print(repr(res))
            except SyntaxError:
                # Fallback to multi-line exec
                exec(code_str, self.custom_globals)
        except Exception as e:
            success = False
            import traceback
            traceback.print_exc(file=stderr_buf)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output = stdout_buf.getvalue() + stderr_buf.getvalue()
        return success, output

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
