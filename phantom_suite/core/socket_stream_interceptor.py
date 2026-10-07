"""
PhantomSuite PID-Scoped Socket & Stream Interceptor
Inspects active TCP/UDP sockets, file descriptors, and network streams
belonging to a specific target process on Linux via /proc filesystem correlation.
"""

import os
import re
import socket
import struct
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class SocketConnection:
    """Represents an active network socket owned by a process."""
    fd: int
    inode: int
    protocol: str  # "TCP", "TCP6", "UDP", "UDP6"
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    state: str
    tx_queue: int = 0
    rx_queue: int = 0
    protocol_hint: str = "Unknown"


class SocketStreamInterceptor:
    """
    Correlates /proc/{pid}/fd descriptors with /proc/net socket tables
    to track network connections, states, and data flow.
    """

    TCP_STATES = {
        "01": "ESTABLISHED",
        "02": "SYN_SENT",
        "03": "SYN_RECV",
        "04": "FIN_WAIT1",
        "05": "FIN_WAIT2",
        "06": "TIME_WAIT",
        "07": "CLOSE",
        "08": "CLOSE_WAIT",
        "09": "LAST_ACK",
        "0A": "LISTEN",
        "0B": "CLOSING"
    }

    KNOWN_PORTS = {
        21: "FTP",
        22: "SSH",
        25: "SMTP",
        53: "DNS",
        80: "HTTP",
        443: "HTTPS/TLS",
        8080: "HTTP-Alt",
        8443: "HTTPS-Alt",
        5055: "Photon Server",
        5056: "Photon Server",
        5058: "Photon Cloud",
        9000: "VRChat OSC / Stream",
        27015: "Steam Game Server"
    }

    @classmethod
    def _parse_ipv4(cls, hex_str: str) -> str:
        """Parses an 8-char hex string in network byte order into IPv4."""
        try:
            packed = bytes.fromhex(hex_str)
            # /proc/net/tcp stores IPv4 as little-endian 32-bit uint
            ip_int = struct.unpack("<I", packed)[0]
            return socket.inet_ntoa(struct.pack("!I", ip_int))
        except Exception:
            return "0.0.0.0"

    @classmethod
    def _parse_ipv6(cls, hex_str: str) -> str:
        """Parses a 32-char hex string into IPv6."""
        try:
            raw = bytes.fromhex(hex_str)
            # Reorder dwords per Linux kernel representation
            words = struct.unpack("<4I", raw)
            reordered = struct.pack("!4I", *words)
            return socket.inet_ntop(socket.AF_INET6, reordered)
        except Exception:
            return "::"

    @classmethod
    def _parse_net_entry(cls, line: str, is_ipv6: bool = False) -> Optional[Tuple[int, str, int, str, int, str, int, int]]:
        """
        Parses a single line from /proc/net/tcp or udp.
        Returns (inode, local_ip, local_port, remote_ip, remote_port, state, tx_queue, rx_queue).
        """
        parts = line.strip().split()
        if len(parts) < 10:
            return None

        # local_address
        loc = parts[1].split(":")
        rem = parts[2].split(":")
        if len(loc) != 2 or len(rem) != 2:
            return None

        loc_hex_ip, loc_hex_port = loc
        rem_hex_ip, rem_hex_port = rem

        loc_ip = cls._parse_ipv6(loc_hex_ip) if is_ipv6 else cls._parse_ipv4(loc_hex_ip)
        rem_ip = cls._parse_ipv6(rem_hex_ip) if is_ipv6 else cls._parse_ipv4(rem_hex_ip)

        loc_port = int(loc_hex_port, 16)
        rem_port = int(rem_hex_port, 16)

        st_hex = parts[3].upper()
        state = cls.TCP_STATES.get(st_hex, "UNKNOWN")

        # tx_queue:rx_queue
        queues = parts[4].split(":")
        tx_q = int(queues[0], 16) if len(queues) == 2 else 0
        rx_q = int(queues[1], 16) if len(queues) == 2 else 0

        # inode is index 9
        try:
            inode = int(parts[9])
        except ValueError:
            return None

        return inode, loc_ip, loc_port, rem_ip, rem_port, state, tx_q, rx_q

    @classmethod
    def get_process_socket_inodes(cls, pid: int) -> Dict[int, List[int]]:
        """
        Reads /proc/{pid}/fd to find socket file descriptors.
        Returns mapping: inode -> list of fds (handles dup/fork socket duplication).
        """
        inode_to_fds: Dict[int, List[int]] = {}
        if not pid or pid <= 0:
            return inode_to_fds

        fd_dir = f"/proc/{pid}/fd"
        if not os.path.exists(fd_dir):
            return inode_to_fds

        try:
            for entry in os.listdir(fd_dir):
                fd_path = os.path.join(fd_dir, entry)
                try:
                    target = os.readlink(fd_path)
                    match = re.match(r"^socket:\[(\d+)\]$", target)
                    if match:
                        inode = int(match.group(1))
                        fd = int(entry)
                        inode_to_fds.setdefault(inode, []).append(fd)
                except (OSError, ValueError):
                    continue
        except (PermissionError, FileNotFoundError):
            pass

        return inode_to_fds

    @classmethod
    def get_process_sockets(cls, pid: int) -> List[SocketConnection]:
        """
        Retrieves all active network sockets belonging to the target PID.
        """
        results: List[SocketConnection] = []
        if not pid or pid <= 0:
            return results

        inode_to_fds = cls.get_process_socket_inodes(pid)
        if not inode_to_fds:
            return results

        protocols = [
            ("TCP", f"/proc/{pid}/net/tcp", False),
            ("TCP6", f"/proc/{pid}/net/tcp6", True),
            ("UDP", f"/proc/{pid}/net/udp", False),
            ("UDP6", f"/proc/{pid}/net/udp6", True)
        ]

        for proto_name, proc_path, is_v6 in protocols:
            # Fallback to global /proc/net if per-pid net is unavailable
            if not os.path.exists(proc_path):
                proc_path = f"/proc/net/{proto_name.lower()}"
                if not os.path.exists(proc_path):
                    continue

            try:
                with open(proc_path, "r") as f:
                    lines = f.readlines()[1:]  # Skip header
                    for line in lines:
                        parsed = cls._parse_net_entry(line, is_ipv6=is_v6)
                        if not parsed:
                            continue
                        inode, loc_ip, loc_port, rem_ip, rem_port, state, tx_q, rx_q = parsed
                        if inode in inode_to_fds:
                            for fd in inode_to_fds[inode]:
                                hint = cls.KNOWN_PORTS.get(rem_port) or cls.KNOWN_PORTS.get(loc_port) or "Unknown"
                                conn_state = state if state != "UNKNOWN" else ("ESTABLISHED" if "TCP" in proto_name else "STATELESS")
                                results.append(SocketConnection(
                                    fd=fd,
                                    inode=inode,
                                    protocol=proto_name,
                                    local_ip=loc_ip,
                                    local_port=loc_port,
                                    remote_ip=rem_ip,
                                    remote_port=rem_port,
                                    state=conn_state,
                                    tx_queue=tx_q,
                                    rx_queue=rx_q,
                                    protocol_hint=hint
                                ))
            except (OSError, PermissionError):
                continue

        return results

    @classmethod
    def format_hex_stream(cls, data: bytes, max_len: int = 64) -> str:
        """Formats a preview of cleartext or encrypted stream bytes."""
        if not data:
            return "<empty>"
        sample = data[:max_len]
        hex_str = " ".join(f"{b:02X}" for b in sample)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in sample)
        return f"{hex_str} | {ascii_str}"
