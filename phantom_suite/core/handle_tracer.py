"""
PhantomSuite Handle & Socket Tracer
Inspects open file descriptors, network connections, pipes,
and devices for target processes.
"""

import os
import socket
import struct
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class SocketInfo:
    inode: int
    proto: str
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    state: str


@dataclass
class HandleInfo:
    fd: int
    kind: str  # "FILE", "SOCKET", "PIPE", "DEVICE", "ANON"
    target: str
    details: str


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


class HandleTracer:
    """Discovers and parses handles and open sockets for a target PID."""

    @staticmethod
    def _parse_ipv4(hex_addr: str) -> str:
        try:
            addr_int = int(hex_addr, 16)
            return socket.inet_ntoa(struct.pack("<L", addr_int))
        except Exception:
            return hex_addr

    @classmethod
    def _parse_net_file(cls, path: str, proto: str) -> Dict[int, SocketInfo]:
        sockets: Dict[int, SocketInfo] = {}
        if not os.path.exists(path):
            return sockets

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                for line in lines[1:]:
                    parts = line.strip().split()
                    if len(parts) < 10:
                        continue
                    local = parts[1].split(':')
                    remote = parts[2].split(':')
                    state_hex = parts[3]
                    inode_str = parts[9]

                    if not inode_str.isdigit():
                        continue
                    inode = int(inode_str)

                    local_ip = cls._parse_ipv4(local[0])
                    local_port = int(local[1], 16)
                    remote_ip = cls._parse_ipv4(remote[0])
                    remote_port = int(remote[1], 16)
                    state = TCP_STATES.get(state_hex, state_hex)

                    sockets[inode] = SocketInfo(
                        inode=inode,
                        proto=proto,
                        local_ip=local_ip,
                        local_port=local_port,
                        remote_ip=remote_ip,
                        remote_port=remote_port,
                        state=state
                    )
        except Exception:
            pass
        return sockets

    @classmethod
    def get_system_sockets(cls, pid: int) -> Dict[int, SocketInfo]:
        """Collects TCP and UDP sockets available in /proc/<pid>/net/."""
        all_socks: Dict[int, SocketInfo] = {}
        base = f"/proc/{pid}/net"
        if not os.path.exists(base):
            base = "/proc/net"

        all_socks.update(cls._parse_net_file(f"{base}/tcp", "TCP"))
        all_socks.update(cls._parse_net_file(f"{base}/udp", "UDP"))
        return all_socks

    @classmethod
    def list_handles(cls, pid: int) -> List[HandleInfo]:
        """Lists all open file descriptors for target PID."""
        handles: List[HandleInfo] = []
        fd_dir = f"/proc/{pid}/fd"

        if not os.path.exists(fd_dir):
            return handles

        sockets_map = cls.get_system_sockets(pid)

        try:
            entries = os.listdir(fd_dir)
        except Exception:
            return handles

        for entry in entries:
            if not entry.isdigit():
                continue
            fd = int(entry)
            fd_path = f"{fd_dir}/{fd}"

            try:
                target = os.readlink(fd_path)
            except Exception:
                target = "<unreadable>"

            kind = "FILE"
            details = ""

            if target.startswith("socket:["):
                kind = "SOCKET"
                inode_str = target[8:-1]
                if inode_str.isdigit():
                    inode = int(inode_str)
                    sock = sockets_map.get(inode)
                    if sock:
                        details = f"{sock.proto} {sock.local_ip}:{sock.local_port} -> {sock.remote_ip}:{sock.remote_port} [{sock.state}]"
                    else:
                        details = f"UNIX / Local Socket (inode {inode})"
                else:
                    details = "Socket"
            elif target.startswith("pipe:["):
                kind = "PIPE"
                details = f"IPC FIFO ({target})"
            elif target.startswith("/dev/"):
                kind = "DEVICE"
                details = "Hardware / Virtual Device"
            elif target.startswith("anon_inode:"):
                kind = "ANON"
                details = target
            else:
                kind = "FILE"
                if os.path.exists(target):
                    try:
                        sz = os.path.getsize(target)
                        details = f"Size: {sz:,} bytes"
                    except Exception:
                        details = "Regular File"
                else:
                    details = "Regular File (or unlinked)"

            handles.append(HandleInfo(
                fd=fd,
                kind=kind,
                target=target,
                details=details
            ))

        handles.sort(key=lambda h: h.fd)
        return handles
