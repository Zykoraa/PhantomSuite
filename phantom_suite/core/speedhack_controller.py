"""
PhantomSuite Speedhack Controller
Manages injection of speedhack.so and controls process time dilation
via shared memory (/dev/shm/phantom_speed_<pid>).
"""

import os
import struct
from typing import Tuple, Optional
from phantom_suite.core.injector import Injector

PAYLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "payloads")
SPEEDHACK_SO = os.path.join(PAYLOAD_DIR, "speedhack.so")


class SpeedhackController:
    """Controls speedhack injection and live time dilation multiplier."""

    @classmethod
    def get_shm_path(cls, pid: int) -> str:
        return f"/dev/shm/phantom_speed_{pid}"

    @classmethod
    def is_injected(cls, pid: int) -> bool:
        """Returns True if speedhack is already active in target PID."""
        if not pid or pid <= 0:
            return False
        shm_path = cls.get_shm_path(pid)
        if os.path.exists(shm_path):
            return True
        return Injector.is_module_loaded(pid, "speedhack.so")

    @classmethod
    def inject(cls, pid: int) -> Tuple[bool, str]:
        """Injects speedhack.so into target PID."""
        if not os.path.exists(SPEEDHACK_SO):
            return False, f"speedhack.so binary not found at {SPEEDHACK_SO}"
        return Injector.inject(pid, SPEEDHACK_SO)

    @classmethod
    def set_speed(cls, pid: int, speed: float, enabled: bool = True) -> bool:
        """Writes speed multiplier into the target's shared memory."""
        shm_path = cls.get_shm_path(pid)
        if not os.path.exists(shm_path):
            return False

        try:
            with open(shm_path, "r+b") as f:
                f.write(struct.pack("<di", float(speed), 1 if enabled else 0))
            return True
        except Exception:
            return False

    @classmethod
    def get_speed(cls, pid: int) -> Tuple[float, bool]:
        """Reads current speed and enabled status from target PID."""
        shm_path = cls.get_shm_path(pid)
        if not os.path.exists(shm_path):
            return 1.0, False

        try:
            with open(shm_path, "rb") as f:
                data = f.read(12)
                if len(data) >= 12:
                    speed, enabled = struct.unpack("<di", data)
                    return speed, (enabled == 1)
        except Exception:
            pass
        return 1.0, False
