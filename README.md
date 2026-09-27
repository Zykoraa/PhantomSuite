# PhantomSuite // Ultimate Linux Reverse-Engineering & Process Workbench

A cyberpunk-themed, high-performance Linux desktop workbench combining the capabilities of **Cheat Engine**, **Process Hacker**, **ReClass.NET**, **x64dbg**, and **Glory Injector** into a unified, native PySide6 (Qt6) interface.

Built specifically for Linux (Wayland / Hyprland and X11), utilizing zero-latency Linux kernel syscalls (`process_vm_readv`, `process_vm_writev`), hardware debug registers (`DR0-DR3`), `/proc` introspection, and GNU binutils.

---

## 🚀 Modern Cockpit & Ergonomic Navigation Overhaul

PhantomSuite features a streamlined, productivity-first desktop layout designed for fast, frictionless reverse engineering:

```
┌───────────┬────────────────────────────────────────────────────────────────────────┐
│ PHANTOM   │ [ TARGET: (PID 12345) dummy_target ] [⚡ Speed: 2.0x] [⌘ Palette] [🪟] │
├───────────┼────────────────────────────────────────────────────────────────────────┤
│ 🚀 MISSION│ 🎯 Attach Active Window  ⚡ Process Explorer  📂 Load Table  🐍 Console│
│ 🎯 TARGET │ ────────────────────────────────────────────────────────────────────── │
│  Processes│ RECENT TARGETS:                                                        │
│  Threads  │ ⚡ [12345] dummy_target  — /home/eve/Projects/PhantomSuite/tests/target │
│  Handles  │ ⚡ [67890] steam_app     — /home/eve/.local/share/Steam/steamapps/...  │
│ 🔍 MEMORY │ ────────────────────────────────────────────────────────────────────── │
│ ▶ Scanner │ Value: [ 1337       ] Type: [ int32 ▼ ] [ ⚡ First Scan ] [ 🔍 Next ]   │
│  Snap Diff│ ┌───────────────┬──────────────┬───────────────┐                       │
│  Treemap  │ │ Address       │ Value        │ Previous      │                       │
│ 🔬 REVERSE│ └───────────────┴──────────────┴───────────────┘                       │
│  Hex/Disam│ Saved Address Table & Value Freezer:                                   │
│  Structs  │ [✓] 0x55AFC0A4A080  | Health | int32 | 100     [ 🎯 Find What Writes ] │
│  Symbols  │                                                                        │
│  Deserial │                                                                        │
│ ⚡ TOOLBOX │                                                                        │
│  Injector │                                                                        │
│  Syscalls │                                                                        │
│  Console  │                                                                        │
└───────────┴────────────────────────────────────────────────────────────────────────┘
```

* **Modern Collapsible Left Sidebar**: Replaces overflowing horizontal tabs with a grouped, categorized vertical navigation bar (`Ctrl+B` toggles between full labels and a compact 54px icon-only rail).
* **Command Palette (`Ctrl+K` / `Ctrl+P`)**: Instant fuzzy search launcher across all tools, quick actions (Speedhack, HUD, Pause/Resume, Snapshots), and instant memory address jumping (e.g. `0x55AFC...` jumps directly to Hex View or Struct Dissector).
* **Mission Control & Recent Targets (`Ctrl+0`)**: High-level launchpad with 1-click active window attachment, cheat table opening, Python scripting, and persistent recent target memory.
* **Workflow Mode Presets**: Switch between focused toolsets with 1 click:
  * **🎮 Game Modding**: Processes, Memory Scanner, Snapshot Diff, Struct Dissector.
  * **🔬 Binary Reversing**: Processes, Hex & Disasm, Struct Dissector, ELF Symbols, Data Deserializer, Python Console.
  * **🕵️ System Forensics**: Processes, Threads, Sockets/Handles, Syscall Monitor, Memory Treemap.
  * **⚡ All Tools**: Full workbench access to all 13 tools.

---

## ⚡ 13 Core Modules & Features

### 1. 🪟 Process Explorer & Hyprland Integration (`Ctrl+1`)
* **Hyprland IPC Binding**: Auto-discovers active Wayland windows (`hyprctl clients -j`) with window titles, classes, and workspace IDs.
* **Quick Attach**: 1-click **"Attach Active Window"** button automatically attaches to whichever window is currently focused.
* **Process Controls**: Pause (`SIGSTOP`), Resume (`SIGCONT`), Terminate (`SIGTERM`), or Kill (`SIGKILL`) target processes directly from the table.
* **Filter Modes**: Filter by Hyprland windows, current user processes, or all system processes.

### 2. 🔍 Memory Scanner, Value Freezer & .phantom Tables (`Ctrl+2`)
* **Direct Syscall Engine**: Uses `process_vm_readv` and `process_vm_writev` to scan memory at gigabytes per second with zero overhead.
* **Data Types**: `int8`, `int16`, `int32`, `int64`, `uint32`, `float`, `double`, `string / text`, `hex byte array`, and `AOB / pattern`.
* **Differential Scanning**: *Exact*, *Increased*, *Decreased*, *Changed*, *Unchanged*, *Bigger*, and *Smaller*.
* **Saved Address Table (Cheat Table)**:
  * Double-click found addresses to add them to your saved table.
  * **Value Freezer**: Check the **Active** box to lock/freeze values via a high-frequency background worker thread.
  * **In-Place Value Editing**: Double-click any saved value to rewrite it instantly in process memory.
* **💾 Save & 📂 Load Tables (`.phantom`)**:
  * Saves cheat tables into structured JSON `.phantom` files.
  * **ASLR Surviving**: Resolves addresses relative to base module load offsets so your tables survive game restarts and reboots.
* **🔍 Multi-Level Pointer Scanner**:
  * Crawls memory to discover multi-level pointer paths (`[module.so + offset] -> offset -> target`) for dynamically allocated heap structures.
  * Export pointer paths straight into your cheat table with 1 click.
* **🎯 Hardware Watchpoint Integration**: 1-click "Find What Writes" directly from any scanner or cheat table entry.

### 3. 📸 Full-Process Memory Snapshot & Differential Comparison (`Ctrl+3`)
* **Zero-Knowledge Differential Reverse Engineering**: Capture complete snapshots of all writable process memory (`rw-p`) into memory.
* **Multi-Format Delta Analysis**: Compare Snapshot A vs Snapshot B with sub-second comparison across `int32`, `float`, and raw hex byte arrays.
* **Noise Filter**: Discards ephemeral thread stacks and dynamic noise to isolate game-state variables.
* **Direct Table Export**: Send discovered delta addresses straight into the Cheat Table with 1 click.

### 4. 🧬 Live Memory Hex Editor, Disassembler & SigMaker (`Ctrl+4`)
* **Real-Time Memory Inspection**: Formatted hex dump + ASCII preview of any virtual memory address with 500ms auto-refresh.
* **Live x86_64 Disassembly**: Real-time instruction decoding into clean Intel-syntax assembly.
* **🚫 Replace with NOPs (`0x90`)**: 1-click instruction NOPing to disable stat decrease or damage routines at machine code level.
* **↺ Restore Original**: Automatically tracks original instruction bytes with instant 1-click restoration.
* **✨ Automated SigMaker**: Select any instruction in the live disassembler to generate the shortest unique AOB signature to make your hooks survive game patches.
* **🎯 Find What Writes / Accesses This Address**: Launch hardware watchpoint tracer directly on any selected memory byte.

### 5. 🔬 Live Struct Dissector & Heatmap Data Analyzer (`Ctrl+5`)
* **Interactive Structure Dissection**: Dissect heap entities, C++ class instances, or player structs at any memory address with configurable stride (32-bit / 64-bit) and buffer sizes.
* **Heuristic Type Auto-Detection**:
  * **64-bit Pointers**: Identifies valid pointers and resolves them to their mapped region/module (e.g. `-> [heap] + 0x120` or `-> libc.so.6 + 0x2A00`).
  * **Floating Point Coordinates**: Detects IEEE-754 floats (player positions, speed, velocities, health).
  * **Integers**: Detects 32-bit and 64-bit integers and counters.
  * **Strings**: Detects ASCII and UTF-8 strings.
* **🔥 Live Heatmaps**: Periodic differential tracking highlights memory values that fluctuate during gameplay in bright neon magenta.
* **📄 Export C Struct**: 1-click generation of compilable C header struct definitions (`typedef struct { ... }`) matching the dissected memory layout.
* **⬇ Add to Address Table**: Export dissected struct members straight into the saved Cheat Table.

### 6. 📦 ELF Symbol & Module Explorer (`Ctrl+6`)
* **Symbol Table Introspection**: Parses `.symtab` and `.dynsym` with automatic C++ symbol demangling (`readelf --demangle`).
* **Runtime Address Resolution**: Automatically calculates real-time virtual addresses (`module_base + file_offset`) accounting for ASLR.
* **Filtering & Searching**: Instant search by symbol name or filter by type (Functions `FUNC`, Global Objects `OBJECT`, Defined, Imported).
* **1-Click Actions**:
  * **🔬 Disassemble**: Instantly jumps to the symbol's runtime address in the Hex & Disassembly tab.
  * **⬇ Add to Table**: Direct export of symbol addresses to the Cheat Table.
  * **📋 Copy Addr**: Copies formatted virtual address to clipboard.

### 7. 🗺️ Virtual Address Space Treemap & Segment Visualizer (`Ctrl+7`)
* **Proportional Memory Distribution Bar**: Visual color-coded proportional bar displaying virtual memory allocation (Heap, Stack, Code, Data, Anonymous mmap, Libraries).
* **KPI Metric Cards**: Real-time statistics on total virtual address space (VIRT), resident physical memory (RSS), writable memory, and mapped segment count.
* **Segment Breakdown**: Searchable breakdown of all `/proc/<pid>/maps` regions with instant jump to **Hex Editor** or **Struct Dissector**.

### 8. 📡 Real-Time Syscall Telemetry Monitor ("GUI strace") (`Ctrl+8`)
* **Streaming Kernel Telemetry**: Live strace capture showing syscall names, arguments, return codes, and elapsed microsecond execution times.
* **Category Color-Coding**: Visual highlights for `FILE` (read, write, open), `NET` (connect, send, recv), `MEM` (mmap, mprotect), `PROC` (clone, execve, kill), and `IPC` (futex, pipe, epoll).
* **Search & Export**: Real-time syscall filtering and 1-click CSV export for external auditing.

### 9. 🐍 Embedded Python Scripting Console & Plugin Engine (`Ctrl+9`)
* **Interactive Script Console**: Integrated multi-line Python editor and REPL with stdout/stderr capture.
* **Process Automation API**: Pre-injected helper functions (`read(addr, len)`, `write(addr, data)`, `read_i32`, `write_i32`, `read_float`, `write_float`, `scan(aob)`, `disasm`, `dissect`, `symbols`).
* **Pre-built Templates**: Instant 1-click scripts for memory dumping, AOB search & replace, pointer chain resolution, and symbol enumeration.
* **Plugin Architecture**: Automatically loads `.py` extensions and custom automation modules from `plugins/`.

### 10. 🧩 Dynamic Data Deserializer & Type Inferer
* **C++ `std::string` Deserializer**: Automatic decoding of GCC `libstdc++` 32-byte layout with Small String Optimization (SSO, length < 16) vs heap dynamic allocation.
* **C++ `std::vector<T>` Deserializer**: Automatic decoding of `_M_start`, `_M_finish`, `_M_end_of_storage`, calculating count, capacity, and previewing elements.
* **Embedded JSON Scanner**: Scans heap buffers and raw memory for valid embedded JSON strings and parses them into structured trees.
* **String Table Parser**: Extracts contiguous null-terminated C-strings from any memory region.

### 11. 💉 Shared Object (`.so`) Injector & Module Explorer
* **GDB dlopen Engine**: Injects `.so` libraries cleanly into running 64-bit processes with automatic verification against `/proc/<pid>/maps`.
* **Elevated Injection Fallback**: Automatically invokes `pkexec` if target process requires elevation.
* **Module Inspector**: Visual breakdown of all mapped shared libraries, virtual address ranges, memory permissions (`r-xp`, `rw-p`), and file paths.
* **Module Unloader**: Call `dlclose()` on loaded modules directly from the interface.

### 12. 🧵 Thread Explorer & CPU Affinity Manager
* **Thread Task Enumeration**: Inspects all thread IDs (TIDs) in `/proc/<pid>/task/`.
* **Thread Telemetry**: Displays thread name, CPU core ID, state, user/kernel execution time, and CPU core masks.
* **Per-Thread Control**: Pause (`SIGSTOP`) or resume (`SIGCONT`) individual threads using `libc.tgkill`.
* **Core Affinity**: Pin specific worker threads to dedicated CPU cores (`sched_setaffinity`).

### 13. 🌐 Handles, Sockets & File Descriptors
* **Descriptor Tracer**: Enumerates all open file descriptors from `/proc/<pid>/fd/`.
* **Network Socket Resolution**: Cross-references socket inodes with `/proc/net/tcp` and `/proc/net/udp` to display real-time connection state (`ESTABLISHED`, `LISTEN`), local address/port, and remote endpoints.
* **IPC Pipes & Device Files**: Distinguishes between regular files, FIFOs, and hardware devices.

---

## 🪟 Additional Cockpit Instruments

### 🎯 Hardware Watchpoints ("Find What Writes / Accesses This Address")
* Leverages x86_64 CPU hardware debug registers (`DR0-DR3`) via GDB batch mode.
* Traps whenever the target process executes instructions that modify or read from a designated memory address.
* Captures old value, new value, instruction RIP, disassembled instruction, and module offset.
* Includes a 1-click **"🚫 Replace with NOPs"** button to patch out the offending instruction instantly!

### 🪟 Wayland / Hyprland On-Screen Display (OSD) Floating HUD
* Frameless, translucent, draggable Cyberpunk HUD overlay.
* Remains floating above games and applications (`WindowStaysOnTopHint`).
* Displays live pinned cheat table values, active speedhack multiplier, target process name, and adjustable opacity slider.

### ⚡ Injected Linux Speedhack Engine
* **Precision Time Dilation**: Injected shared library intercepting `clock_gettime(CLOCK_MONOTONIC, ...)` and `gettimeofday(...)`.
* **Zero-Latency Shared Memory**: Controls game speed via `/dev/shm` IPC without syscall overhead.
* **Real-Time Speed Slider**: Fast forward grind screens (up to `5.0x`) or slow down bullet-hell sequences (down to `0.2x`) straight from the top header bar.

---

## ⌨️ Global Keyboard Shortcuts

| Shortcut | Action | Description |
| :--- | :--- | :--- |
| **Ctrl + K / Ctrl + P** | Command Palette | Global search launcher for tools, actions, and memory addresses |
| **Ctrl + B** | Toggle Sidebar | Collapse sidebar into 54px icon rail or expand to 210px |
| **Ctrl + 0** | Mission Control | Switch to Welcome Hub & Recent Targets |
| **Ctrl + 1** | Processes & Windows | Switch to Process Explorer |
| **Ctrl + 2** | Memory Scanner | Switch to Memory Scanner & Cheat Table |
| **Ctrl + 3** | Snapshot Diff | Switch to Full-Process Memory Snapshot Engine |
| **Ctrl + 4** | Hex & Disasm | Switch to Hex Editor & Live x86_64 Disassembler |
| **Ctrl + 5** | Struct Dissector | Switch to Live Struct Dissector & Heatmaps |
| **Ctrl + 6** | ELF Symbols | Switch to Symbol & Module Explorer |
| **Ctrl + 7** | Memory Treemap | Switch to Virtual Address Space Treemap |
| **Ctrl + 8** | Syscall Monitor | Switch to Real-Time Syscall Telemetry Monitor |
| **Ctrl + 9** | Python Console | Switch to Embedded Python Scripting Console |
| **F3** | Pause / Resume | Toggle process freeze via `SIGSTOP` / `SIGCONT` |
| **F5** | Global Refresh | Refreshes data in the active tool |
| **Ctrl + S** | Save Cheat Table | Exports current address table to `.phantom` JSON |
| **Ctrl + O** | Load Cheat Table | Imports saved `.phantom` cheat table |
| **? / F1** | Shortcuts Cheat Sheet | Opens interactive shortcuts & quick reference dialog |

---

## 🚀 Installation & Launch

### Install on Any Linux Machine (One Command)

```bash
git clone https://github.com/Zykoraa/PhantomSuite.git
cd PhantomSuite && ./install.sh
```

**Requirements**:
* `python3` & `python-pyside6` (`sudo pacman -S python-pyside6` on Arch/CachyOS, or `pip install PySide6`)
* `gdb`, `binutils` & `strace` (for library injection, disassembly, symbol exploration, watchpoints, and syscall tracing)

### Quick Launch
From anywhere in your terminal:

```bash
phantom-suite
```

Or pass a target PID directly:

```bash
phantom-suite --pid 12345
```

### Install Desktop Launcher & Icon

```bash
./install.sh
```

To uninstall:
```bash
./install.sh --uninstall
```

---

## 🔒 Permissions (`ptrace_scope`)

Attaching to processes on Linux requires permission to `ptrace` the target process.

* **Check current scope:**
  ```bash
  cat /proc/sys/kernel/yama/ptrace_scope
  ```
* **Scope 0 (Recommended for reverse engineering & modding personal processes):**
  ```bash
  echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
  ```
  *(To make permanent across reboots, add `kernel.yama.ptrace_scope = 0` to `/etc/sysctl.d/10-ptrace.conf`)*

If `ptrace_scope` is set to 1 or higher, PhantomSuite gracefully triggers a `pkexec` prompt when injecting or attaching to protected processes.

---

## 🧪 Automated Testing

PhantomSuite includes a 55-test automated verification suite tested against live Linux processes:

```bash
python3 -m unittest discover -s tests
```

Tests cover:
* Memory reading, writing, and differential multi-pass scanning.
* Active background value freezing.
* Full-process memory snapshots and differential comparison.
* Modern collapsible sidebar navigation, width transitions, and preset mode filtering.
* Command palette fuzzy filtering, action callbacks, and hex address jump parsing.
* Recent targets persistence, deduplication, and history retrieval.
* Virtual address space memory map calculation and KPI aggregations.
* Real-time syscall tracer streaming and line parsing.
* Dynamic data deserialization (`std::string`, `std::vector`, embedded JSON, string tables).
* Python scripting console execution, REPL evaluation, and plugin loader.
* Hardware watchpoint output regex parsing and error handling.
* AOB pattern scanning with wildcards (`??`, `*`) and unique signature generation (`SigMaker`).
* Live Struct dissection, heuristic type detection, and heatmap delta tracking.
* ELF module exploration, symbol demangling, and section parsing.
* Multi-level pointer path crawling and table serialization.
* Process listing, signal dispatch (`SIGSTOP`/`SIGCONT`), and Hyprland window detection.
* Handle and TCP listening socket enumeration.
* Shared object (`.so`) injection and `/proc/<pid>/maps` verification.

---

## 📜 Architecture

```
Projects/PhantomSuite/
├── phantom-suite                 # Executable launcher script
├── install.sh                    # User installation script
├── plugins/                      # Custom Python scripting plugins
│   └── sample_plugin.py          # Sample plugin script
├── phantom_suite/
│   ├── app.py                    # Application bootstrap & CLI arguments
│   ├── theme.py                  # Cyberpunk dark stylesheet (QSS)
│   ├── core/
│   │   ├── memory_engine.py      # process_vm_readv / writev & scanner
│   │   ├── snapshot_engine.py    # Full-process memory snapshot diff engine
│   │   ├── memory_map.py         # Virtual address space treemap & KPI analyzer
│   │   ├── syscall_tracer.py     # Real-time strace streaming telemetry
│   │   ├── data_deserializer.py  # C++ STL & embedded JSON deserializer
│   │   ├── script_engine.py      # Embedded Python scripting & plugin engine
│   │   ├── watchpoint_tracer.py  # Hardware debug register watchpoints (GDB)
│   │   ├── recent_targets.py     # Target history persistence
│   │   ├── process_manager.py    # /proc scanner & Hyprland window IPC
│   │   ├── injector.py           # GDB dlopen & module verifier
│   │   ├── hex_viewer.py         # Formatted hex dump & patcher
│   │   ├── disassembler.py       # x86_64 disassembly & NOP patcher
│   │   ├── pointer_scanner.py    # Multi-level pointer path crawler
│   │   ├── pattern_scanner.py    # AOB pattern scanner & SigMaker
│   │   ├── struct_dissector.py   # Live struct dissection & heatmaps
│   │   ├── elf_explorer.py       # ELF symbol (.symtab/.dynsym) & sections
│   │   ├── speedhack_controller.py# Shared memory IPC speedhack controller
│   │   ├── thread_manager.py     # Thread task manager & CPU affinity
│   │   ├── handle_tracer.py      # File descriptors & socket parser
│   │   └── table_serializer.py   # ASLR-surviving .phantom cheat tables
│   ├── payloads/
│   │   ├── speedhack.c           # Hooked clock_gettime & gettimeofday
│   │   └── speedhack.so          # Compiled speedhack payload
│   └── ui/
│       ├── main_window.py        # Main workbench shell
│       ├── sidebar.py            # Collapsible categorized navigation sidebar
│       ├── command_palette.py    # Fuzzy search action & address launcher (Ctrl+K)
│       ├── shortcuts_dialog.py   # Hotkey cheat sheet & quick guide dialog
│       ├── welcome_tab.py        # Mission Control dashboard & recent targets
│       ├── process_tab.py        # Process list & Hyprland picker
│       ├── scanner_tab.py        # Memory scanner, AOB & cheat table
│       ├── snapshot_tab.py       # Memory snapshot & diff viewer
│       ├── injector_tab.py       # .so injector & module list
│       ├── hex_tab.py            # Memory hex viewer, disasm & SigMaker
│       ├── struct_tab.py         # Live struct dissector & heatmaps
│       ├── symbols_tab.py        # ELF symbol explorer & disasm navigator
│       ├── treemap_tab.py        # Memory map visualizer & KPI metrics
│       ├── syscalls_tab.py       # Syscall telemetry monitor & CSV exporter
│       ├── deserializer_tab.py   # Data deserializer (std::string/vector/JSON)
│       ├── console_tab.py        # Python scripting console & plugin runner
│       ├── threads_tab.py        # Thread task explorer & affinity
│       ├── handles_tab.py        # Handles & network sockets
│       ├── osd_overlay.py        # Floating HUD OSD overlay
│       ├── watchpoint_dialog.py  # Hardware watchpoint tracer & NOP patcher
│       └── pointer_dialog.py     # Multi-level pointer scan dialog
└── tests/
    ├── test_target.c             # C binary with predictable memory/sockets
    ├── test_payload.c            # C shared library for injection verification
    ├── test_sidebar.py           # Sidebar navigation & collapsible modes tests
    ├── test_command_palette.py   # Command palette fuzzy search & jump tests
    ├── test_recent_targets.py    # Target history persistence tests
    ├── test_memory_engine.py     # Scanner & freezer unit tests
    ├── test_snapshot_engine.py   # Snapshot & diff unit tests
    ├── test_memory_map.py        # Memory map & KPI tests
    ├── test_syscall_tracer.py    # Syscall tracer unit tests
    ├── test_data_deserializer.py # Data deserializer tests
    ├── test_script_engine.py     # Script engine & plugin loader tests
    ├── test_watchpoint_tracer.py # Watchpoint tracer tests
    ├── test_pattern_scanner.py   # AOB & SigMaker tests
    ├── test_struct_dissector.py  # Struct dissection & heatmap tests
    ├── test_elf_explorer.py      # ELF symbol & section tests
    ├── test_pointer_scanner.py   # Pointer crawler tests
    ├── test_disassembler.py      # Disassembly & NOP patcher tests
    ├── test_speedhack.py         # Speedhack injection & IPC tests
    ├── test_thread_manager.py    # Thread manager tests
    ├── test_process_manager.py   # Process control unit tests
    ├── test_handle_tracer.py     # Socket inspection tests
    ├── test_table_serializer.py  # Cheat table serialization tests
    └── test_injector.py          # Injection tests
```

---

## License

MIT License. Developed for Linux power users, game modders, and security researchers.
