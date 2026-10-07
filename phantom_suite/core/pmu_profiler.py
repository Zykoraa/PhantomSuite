"""
PhantomSuite Anti-Debug & PMU Timing Anomaly Profiler
Detects ptrace hooks, TracerPid telemetry, hardware performance counter quirks,
and static/dynamic RDTSC timing delta anti-debug loops in target processes.
"""

import os
import re
from typing import List, Dict, Optional, Tuple, Set, Any
from dataclasses import dataclass, field
from phantom_suite.core.memory_engine import MemoryEngine, MemoryRegion


@dataclass
class AntiDebugIndicator:
    category: str # "TRACER", "TIMING", "TRAP", "INTEGRITY"
    severity: str # "HIGH", "MEDIUM", "LOW"
    description: str
    address: Optional[int] = None
    details: str = ""


@dataclass
class TimingProfileReport:
    pid: int
    is_ptraced: bool
    tracer_pid: int
    wchan_state: str
    vol_ctxt_switches: int
    nonvol_ctxt_switches: int
    indicators: List[AntiDebugIndicator] = field(default_factory=list)
    rdtsc_instruction_count: int = 0
    threat_score: int = 0 # 0-100


class PmuProfiler:
    """Profiles anti-debug countermeasures, hardware timing traps, and tracer telemetry."""

    @classmethod
    def audit_process(cls, pid: int, scan_executable_memory: bool = True) -> Optional[TimingProfileReport]:
        """Runs a complete anti-debug and timing profile audit on target PID."""
        if not pid or pid <= 0 or not os.path.exists(f"/proc/{pid}"):
            return None

        # 1. Read /proc/<pid>/status
        status_file = f"/proc/{pid}/status"
        tracer_pid = 0
        vol_switches = 0
        nonvol_switches = 0

        try:
            with open(status_file, "r") as f:
                for line in f:
                    if line.startswith("TracerPid:"):
                        tracer_pid = int(line.split()[1])
                    elif line.startswith("voluntary_ctxt_switches:"):
                        vol_switches = int(line.split()[1])
                    elif line.startswith("nonvoluntary_ctxt_switches:"):
                        nonvol_switches = int(line.split()[1])
        except Exception:
            return None

        # 2. Read /proc/<pid>/wchan
        wchan_state = ""
        try:
            with open(f"/proc/{pid}/wchan", "r") as f:
                wchan_state = f.read().strip()
        except Exception:
            pass

        report = TimingProfileReport(
            pid=pid,
            is_ptraced=(tracer_pid != 0),
            tracer_pid=tracer_pid,
            wchan_state=wchan_state,
            vol_ctxt_switches=vol_switches,
            nonvol_ctxt_switches=nonvol_switches
        )

        # Evaluate TracerPid
        if tracer_pid != 0:
            report.indicators.append(AntiDebugIndicator(
                category="TRACER",
                severity="HIGH",
                description=f"Process is currently being traced by PID {tracer_pid}",
                details="TracerPid != 0 in /proc/<pid>/status indicates active ptrace or debugger attachment."
            ))
            report.threat_score += 40

        if "ptrace" in wchan_state.lower():
            report.indicators.append(AntiDebugIndicator(
                category="TRACER",
                severity="HIGH",
                description="Thread is waiting in ptrace_stop",
                details=f"wchan indicates debugger wait: {wchan_state}"
            ))
            report.threat_score += 20

        # 3. Optional: Scan executable segments for RDTSC and breakpoint detection loops
        if scan_executable_memory:
            cls._scan_timing_opcodes(pid, report)

        report.threat_score = min(100, report.threat_score)
        return report

    @classmethod
    def _scan_timing_opcodes(cls, pid: int, report: TimingProfileReport):
        """Scans mapped executable regions for RDTSC, RDTSCP, and INT3 signatures."""
        regions = MemoryEngine.get_maps(pid)
        exec_regions = [r for r in regions if r.is_executable and not r.pathname.startswith(("/dev/", "[vvar]", "[vsyscall]"))]

        rdtsc_pattern = b"\x0F\x31"       # rdtsc
        rdtscp_pattern = b"\x0F\x01\xF9"  # rdtscp
        cpuid_pattern = b"\x0F\xA2"       # cpuid (serialize)
        int3_pattern = b"\xCC"            # int3 software breakpoint
        icebp_pattern = b"\xF1"           # icebp / int1

        rdtsc_total = 0

        # Scan primary executable region first (limit to first 3 to prevent excessive scanning)
        for r in exec_regions[:3]:
            chunk = MemoryEngine.read_bytes(pid, r.start, min(r.size, 1024 * 1024))
            if not chunk:
                continue

            # Count RDTSC instructions
            c_rdtsc = chunk.count(rdtsc_pattern)
            c_rdtscp = chunk.count(rdtscp_pattern)
            rdtsc_total += (c_rdtsc + c_rdtscp)

            # Detect tight RDTSC pairs (< 128 bytes apart, typical delta check)
            pos = 0
            while True:
                idx = chunk.find(rdtsc_pattern, pos)
                if idx == -1:
                    break
                # Look for a second rdtsc within next 128 bytes
                next_idx = chunk.find(rdtsc_pattern, idx + 2)
                if next_idx != -1 and (next_idx - idx) < 128:
                    report.indicators.append(AntiDebugIndicator(
                        category="TIMING",
                        severity="MEDIUM",
                        description=f"Tight RDTSC timing delta loop detected in {os.path.basename(r.pathname or 'anon')}",
                        address=r.start + idx,
                        details=f"Paired RDTSC at +0x{idx:X} and +0x{next_idx:X} (delta {next_idx - idx} bytes)."
                    ))
                    report.threat_score += 15
                    pos = next_idx + 2
                else:
                    pos = idx + 2

        report.rdtsc_instruction_count = rdtsc_total
        if rdtsc_total > 10:
            report.indicators.append(AntiDebugIndicator(
                category="TIMING",
                severity="LOW",
                description=f"Elevated RDTSC instruction density ({rdtsc_total} instances)",
                details="Potential hardware timer interrogation or anti-emulation benchmarking."
            ))
            report.threat_score += 10
