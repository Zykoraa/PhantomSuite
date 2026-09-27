"""
PhantomSuite ELF Symbol & Module Explorer
Extracts exported/imported symbols, functions, variables, and section headers
from loaded ELF executables and shared libraries. Resolves runtime memory addresses.
"""

import os
import subprocess
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from phantom_suite.core.memory_engine import MemoryEngine
from phantom_suite.core.table_serializer import TableSerializer


@dataclass
class ElfSymbol:
    name: str
    symbol_type: str  # FUNC, OBJECT, NOTYPE, TLS, SECTION, etc.
    bind: str         # GLOBAL, LOCAL, WEAK
    visibility: str   # DEFAULT, HIDDEN, PROTECTED
    size: int
    file_offset: int  # Offset/Value inside ELF
    runtime_address: Optional[int] = None # Offset + module runtime base
    section: str = ""
    is_imported: bool = False


@dataclass
class ElfSection:
    name: str
    section_type: str
    file_offset: int
    size: int
    flags: str
    runtime_address: Optional[int] = None


@dataclass
class LoadedModule:
    name: str
    path: str
    base_address: int
    size: int


class ElfExplorer:
    """Explores symbols and sections of loaded ELF executables and shared libraries."""

    @classmethod
    def get_loaded_modules(cls, pid: int) -> List[LoadedModule]:
        """Returns unique ELF modules (executables and libraries) mapped into target PID."""
        if not pid or pid <= 0:
            return []

        regions = MemoryEngine.get_maps(pid)
        seen: Dict[str, Tuple[int, int]] = {} # path -> (min_start, max_end)

        for r in regions:
            if not r.pathname or not r.pathname.startswith("/"):
                continue
            if not os.path.exists(r.pathname):
                continue

            p = r.pathname
            if p not in seen:
                seen[p] = (r.start, r.end)
            else:
                s, e = seen[p]
                seen[p] = (min(s, r.start), max(e, r.end))

        modules: List[LoadedModule] = []
        for path, (start, end) in seen.items():
            modules.append(LoadedModule(
                name=os.path.basename(path),
                path=path,
                base_address=start,
                size=end - start
            ))

        # Sort so that the main executable is typically first (or by name)
        modules.sort(key=lambda m: (m.base_address))
        return modules

    @classmethod
    def parse_symbols(
        cls,
        filepath: str,
        base_address: Optional[int] = None
    ) -> List[ElfSymbol]:
        """
        Parses symbol tables (.symtab and .dynsym) using readelf --demangle.
        Calculates runtime_address if base_address is provided.
        """
        if not filepath or not os.path.exists(filepath):
            return []

        symbols: List[ElfSymbol] = []
        try:
            res = subprocess.run(
                ["readelf", "-s", "--wide", "--demangle", filepath],
                capture_output=True,
                text=True,
                timeout=5.0
            )
            if res.returncode != 0:
                return []

            lines = res.stdout.splitlines()
            for line in lines:
                parts = line.strip().split()
                # Format: Num: Value Size Type Bind Vis Ndx Name
                if len(parts) < 8 or not parts[0].endswith(":"):
                    continue

                try:
                    val_hex = parts[1]
                    size_val = int(parts[2], 0) if parts[2].isdigit() or parts[2].startswith("0x") else 0
                    sym_type = parts[3]
                    bind = parts[4]
                    vis = parts[5]
                    ndx = parts[6]
                    sym_name = " ".join(parts[7:]) # Names can have spaces if demangled
                except Exception:
                    continue

                try:
                    file_offset = int(val_hex, 16)
                except ValueError:
                    file_offset = 0

                is_imported = (ndx == "UND" or file_offset == 0)
                runtime_addr = None
                if not is_imported and base_address is not None and file_offset > 0:
                    runtime_addr = base_address + file_offset

                symbols.append(ElfSymbol(
                    name=sym_name,
                    symbol_type=sym_type,
                    bind=bind,
                    visibility=vis,
                    size=size_val,
                    file_offset=file_offset,
                    runtime_address=runtime_addr,
                    section=ndx,
                    is_imported=is_imported
                ))

        except Exception:
            return []

        return symbols

    @classmethod
    def parse_sections(
        cls,
        filepath: str,
        base_address: Optional[int] = None
    ) -> List[ElfSection]:
        """Parses section headers (.text, .data, .rodata, etc.) using readelf -S --wide."""
        if not filepath or not os.path.exists(filepath):
            return []

        sections: List[ElfSection] = []
        try:
            res = subprocess.run(
                ["readelf", "-S", "--wide", filepath],
                capture_output=True,
                text=True,
                timeout=4.0
            )
            if res.returncode != 0:
                return []

            for line in res.stdout.splitlines():
                # [Nr] Name Type Address Off Size ES Flg Lk Inf Al
                parts = line.strip().split()
                if len(parts) >= 6 and parts[0].startswith("[") and parts[0].endswith("]"):
                    # Offset format
                    sec_name = parts[1]
                    sec_type = parts[2]
                    try:
                        addr = int(parts[3], 16)
                        sec_size = int(parts[5], 16)
                        flags = parts[7] if len(parts) > 7 else ""
                        runtime_addr = (base_address + addr) if (base_address and addr > 0) else None
                        sections.append(ElfSection(
                            name=sec_name,
                            section_type=sec_type,
                            file_offset=addr,
                            size=sec_size,
                            flags=flags,
                            runtime_address=runtime_addr
                        ))
                    except Exception:
                        continue
        except Exception:
            return []

        return sections
