# PhantomSuite v3.0 // Linux Reverse-Engineering & Process Workbench

A cyberpunk-themed, high-performance Linux desktop workbench combining the capabilities of **Cheat Engine**, **Process Hacker**, **ReClass.NET**, and **Glory Injector** into a unified, native PySide6 (Qt6) interface.

Built specifically for Linux (Wayland / Hyprland and X11), utilizing zero-latency Linux kernel syscalls (`process_vm_readv`, `process_vm_writev`), `/proc` introspection, and GNU binutils.

---

## ⚡ Core Features (v3.0)

### 1. 🔬 Live Struct Dissector & Heatmap Data Analyzer
* **Interactive Structure Dissection**: Dissect heap entities, C++ class instances, or player structs at any memory address with configurable stride (32-bit / 64-bit) and buffer sizes.
* **Heuristic Type Auto-Detection**:
  * **64-bit Pointers**: Identifies valid pointers and resolves them to their mapped region/module (e.g. `-> [heap] + 0x120` or `-> libc.so.6 + 0x2A00`).
  * **Floating Point Coordinates**: Detects IEEE-754 floats (player positions, speed, velocities, health).
  * **Integers**: Detects 32-bit and 64-bit integers and counters.
  * **Strings**: Detects ASCII and UTF-8 strings.
* **🔥 Live Heatmaps**: Periodic differential tracking highlights memory values that fluctuate during gameplay in bright neon magenta.
* **📄 Export C Struct**: 1-click generation of compilable C header struct definitions (`typedef struct { ... }`) matching the dissected memory layout.
* **⬇ Add to Address Table**: Export dissected struct members straight into the saved Cheat Table.

### 2. 📦 ELF Symbol & Module Explorer
* **Symbol Table Introspection**: Parses `.symtab` and `.dynsym` with automatic C++ symbol demangling (`readelf --demangle`).
* **Runtime Address Resolution**: Automatically calculates real-time virtual addresses (`module_base + file_offset`) accounting for ASLR.
* **Filtering & Searching**: Instant search by symbol name or filter by type (Functions `FUNC`, Global Objects `OBJECT`, Defined, Imported).
* **1-Click Actions**:
  * **🔬 Disassemble**: Instantly jumps to the symbol's runtime address in the Hex & Disassembly tab.
  * **⬇ Add to Table**: Direct export of symbol addresses to the Cheat Table.
  * **📋 Copy Addr**: Copies formatted virtual address to clipboard.

### 3. ✨ AOB Pattern Scanner & Automatic SigMaker
* **Pattern Scanning with Wildcards**: Scan memory for byte patterns with wildcard masks (e.g. `48 89 5C ?? ?? 48 83 EC *`).
* **Automated SigMaker**: Select any instruction in the live disassembler and click **"SigMaker"** to generate the shortest unique AOB signature to make your hooks survive game patches.
* **Integrated Memory Scanner**: Dedicated AOB scanning mode inside the Memory Scanner tab.

### 4. 🪟 Process Explorer & Hyprland Integration
* **Hyprland IPC Binding**: Auto-discovers active Wayland windows (`hyprctl clients -j`) with window titles, classes, and workspace IDs.
* **Quick Attach**: 1-click **"Attach Active Window"** button automatically attaches to whichever window is currently focused.
* **Process Controls**: Pause (`SIGSTOP`), Resume (`SIGCONT`), Terminate (`SIGTERM`), or Kill (`SIGKILL`) target processes directly from the table.
* **Filter Modes**: Filter by Hyprland windows, current user processes, or all system processes.

### 5. 🔍 Memory Scanner, Value Freezer & .phantom Tables
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

### 6. ⚡ Live x86_64 Disassembler & 1-Click NOP Patcher
* **Real-Time Code Disassembly**: Disassembles instructions around any memory address into clean Intel-syntax x86_64 assembly.
* **🚫 Replace with NOPs (`0x90`)**: 1-click instruction NOPing to disable stat decrease or damage routines at the machine code level.
* **↺ Restore Original**: Automatically tracks original instruction bytes with instant 1-click restoration.

### 7. ⚡ Injected Linux Speedhack Engine
* **Precision Time Dilation**: Injected shared library intercepting `clock_gettime(CLOCK_MONOTONIC, ...)` and `gettimeofday(...)`.
* **Zero-Latency Shared Memory**: Controls game speed via `/dev/shm` IPC without syscall overhead.
* **Real-Time Speed Slider**: Fast forward grind screens (up to `5.0x`) or slow down bullet-hell sequences (down to `0.2x`) straight from the top header bar.

### 8. 🧵 Thread Explorer & CPU Affinity Manager
* **Thread Task Enumeration**: Inspects all thread IDs (TIDs) in `/proc/<pid>/task/`.
* **Thread Telemetry**: Displays thread name, CPU core ID, state, user/kernel execution time, and CPU core masks.
* **Per-Thread Control**: Pause (`SIGSTOP`) or resume (`SIGCONT`) individual threads using `libc.tgkill`.
* **Core Affinity**: Pin specific worker threads to dedicated CPU cores (`sched_setaffinity`).

### 9. 💉 Shared Object (`.so`) Injector & Module Explorer
* **GDB dlopen Engine**: Injects `.so` libraries cleanly into running 64-bit processes with automatic verification against `/proc/<pid>/maps`.
* **Elevated Injection Fallback**: Automatically invokes `pkexec` if target process requires elevation.
* **Module Inspector**: Visual breakdown of all mapped shared libraries, virtual address ranges, memory permissions (`r-xp`, `rw-p`), and file paths.
* **Module Unloader**: Call `dlclose()` on loaded modules directly from the interface.

### 10. 🧬 Live Memory Hex Editor & Patcher
* **Real-Time Memory Inspection**: Formatted hex dump + ASCII preview of any virtual memory address.
* **Live Auto-Refresh**: 500ms real-time refresh mode to monitor memory fluctuations live.
* **Byte Patcher**: Select any row or enter an address to write raw hex bytes directly into memory.

### 11. 🌐 Handles, Sockets & File Descriptors
* **Descriptor Tracer**: Enumerates all open file descriptors from `/proc/<pid>/fd/`.
* **Network Socket Resolution**: Cross-references socket inodes with `/proc/net/tcp` and `/proc/net/udp` to display real-time connection state (`ESTABLISHED`, `LISTEN`), local address/port, and remote endpoints.
* **IPC Pipes & Device Files**: Distinguishes between regular files, FIFOs, and hardware devices.

---

## 🚀 Installation & Launch

### Install on Any Linux Machine (One Command)

```bash
git clone https://github.com/Zykoraa/PhantomSuite.git
cd PhantomSuite && ./install.sh
```

**Requirements**:
* `python3` & `python-pyside6` (`sudo pacman -S python-pyside6` on Arch/CachyOS, or `pip install PySide6`)
* `gdb` & `binutils` (for library injection, disassembly, and symbol exploration)

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

This installs:
* `phantom-suite` into `~/.local/bin`
* `phantom-suite.desktop` into `~/.local/share/applications`
* Vector icon into `~/.local/share/icons/hicolor/scalable/apps/`

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

PhantomSuite includes a 26-test automated verification suite tested against live Linux processes:

```bash
python3 -m unittest discover -s tests
```

Tests cover:
* Memory reading, writing, and differential multi-pass scanning.
* Active background value freezing.
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
├── phantom_suite/
│   ├── app.py                    # Application bootstrap & CLI arguments
│   ├── theme.py                  # Cyberpunk dark stylesheet (QSS)
│   ├── core/
│   │   ├── memory_engine.py      # process_vm_readv / writev & scanner
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
│       ├── main_window.py        # Main tabbed shell & target coordinator
│       ├── process_tab.py        # Process list & Hyprland picker
│       ├── scanner_tab.py        # Memory scanner, AOB & cheat table
│       ├── injector_tab.py       # .so injector & module list
│       ├── hex_tab.py            # Memory hex viewer, disasm & SigMaker
│       ├── struct_tab.py         # Live struct dissector & heatmaps
│       ├── symbols_tab.py        # ELF symbol explorer & disasm navigator
│       ├── threads_tab.py        # Thread task explorer & affinity
│       ├── handles_tab.py        # Handles & network sockets
│       └── pointer_dialog.py     # Multi-level pointer scan dialog
└── tests/
    ├── test_target.c             # C binary with predictable memory/sockets
    ├── test_payload.c            # C shared library for injection verification
    ├── test_memory_engine.py     # Scanner & freezer unit tests
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
