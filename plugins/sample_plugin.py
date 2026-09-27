"""
Sample PhantomSuite Plugin
Demonstrates extending the scripting environment with custom helper utilities.
"""

def print_banner(target_pid: int = None):
    """Prints a styled target status banner."""
    print("=" * 50)
    print(f"[*] PhantomSuite Plugin Active | Target PID: {target_pid}")
    print("=" * 50)

def dump_range_preview(engine, address: int, size: int = 64):
    """Utility to hex-dump a small range to the console."""
    raw = engine.read(address, size)
    hex_str = " ".join(f"{b:02X}" for b in raw)
    print(f"[0x{address:X}] ({size} bytes):")
    print(hex_str)
