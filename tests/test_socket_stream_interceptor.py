"""
Unit tests for PhantomSuite PID-Scoped Socket & Stream Interceptor.
"""

import unittest
from unittest.mock import patch, mock_open
from phantom_suite.core.socket_stream_interceptor import (
    SocketStreamInterceptor, SocketConnection
)


class TestSocketStreamInterceptor(unittest.TestCase):

    def test_parse_ipv4(self):
        # 0100007F is 127.0.0.1 in little-endian hex
        ip = SocketStreamInterceptor._parse_ipv4("0100007F")
        self.assertEqual(ip, "127.0.0.1")

    def test_parse_net_entry_tcp(self):
        # Sample line from /proc/net/tcp
        # 127.0.0.1:8080 (0100007F:1F90) -> 127.0.0.1:443 (0100007F:01BB), state ESTABLISHED (01), inode 98765
        line = "   1: 0100007F:1F90 0100007F:01BB 01 00000000:00000000 00:00000000 00000000  1000        0 98765 1 0000000000000000 100 0 0 10 0"
        res = SocketStreamInterceptor._parse_net_entry(line, is_ipv6=False)
        self.assertIsNotNone(res)
        inode, loc_ip, loc_port, rem_ip, rem_port, state, tx_q, rx_q = res
        self.assertEqual(inode, 98765)
        self.assertEqual(loc_ip, "127.0.0.1")
        self.assertEqual(loc_port, 8080)
        self.assertEqual(rem_ip, "127.0.0.1")
        self.assertEqual(rem_port, 443)
        self.assertEqual(state, "ESTABLISHED")

    def test_format_hex_stream(self):
        data = b"HTTP/1.1 200 OK\r\n"
        preview = SocketStreamInterceptor.format_hex_stream(data)
        self.assertIn("48 54 54 50", preview)
        self.assertIn("HTTP/1.1 200 OK", preview)

    @patch("phantom_suite.core.socket_stream_interceptor.SocketStreamInterceptor.get_process_socket_inodes")
    @patch("os.path.exists")
    def test_get_process_sockets_mock(self, mock_exists, mock_inodes):
        mock_inodes.return_value = {98765: [3]}
        mock_exists.side_effect = lambda path: "tcp" in path and "tcp6" not in path

        mock_tcp_data = (
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            "   1: 0100007F:1F90 0100007F:01BB 01 00000000:00000000 00:00000000 00000000  1000        0 98765 1 0\n"
        )

        with patch("builtins.open", mock_open(read_data=mock_tcp_data)):
            socks = SocketStreamInterceptor.get_process_sockets(1234)
            self.assertEqual(len(socks), 1)
            conn = socks[0]
            self.assertEqual(conn.fd, 3)
            self.assertEqual(conn.inode, 98765)
            self.assertEqual(conn.remote_port, 443)
            self.assertEqual(conn.protocol_hint, "HTTPS/TLS")
            self.assertEqual(conn.state, "ESTABLISHED")

    def test_negative_or_zero_pid(self):
        self.assertEqual(SocketStreamInterceptor.get_process_sockets(0), [])
        self.assertEqual(SocketStreamInterceptor.get_process_sockets(-1), [])

    @patch("phantom_suite.core.socket_stream_interceptor.SocketStreamInterceptor.get_process_socket_inodes")
    @patch("os.path.exists")
    def test_multiple_fds_per_inode(self, mock_exists, mock_inodes):
        # Inode 11111 shared between fd 3 and fd 4 (via dup2)
        mock_inodes.return_value = {11111: [3, 4]}
        mock_exists.side_effect = lambda path: "tcp" in path and "tcp6" not in path

        mock_tcp_data = (
            "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            "   1: 0100007F:1F90 0100007F:01BB 01 00000000:00000000 00:00000000 00000000  1000        0 11111 1 0\n"
        )
        with patch("builtins.open", mock_open(read_data=mock_tcp_data)):
            socks = SocketStreamInterceptor.get_process_sockets(1234)
            self.assertEqual(len(socks), 2)
            fds = [s.fd for s in socks]
            self.assertIn(3, fds)
            self.assertIn(4, fds)


if __name__ == "__main__":
    unittest.main()
