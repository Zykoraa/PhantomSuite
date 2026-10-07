"""
Unit tests for PhantomSuite Shannon Entropy & Cryptographic Primitive Scanner.
"""

import os
import unittest
from phantom_suite.core.entropy_crypto_scanner import (
    EntropyCryptoScanner, EntropyBlock, CryptoMatch
)


class TestEntropyCryptoScanner(unittest.TestCase):

    def test_zero_entropy_uniform_bytes(self):
        # All zeros has 0 entropy
        data = b"\x00" * 1024
        h = EntropyCryptoScanner.calculate_entropy(data)
        self.assertEqual(h, 0.0)

    def test_maximum_entropy_all_bytes(self):
        # Equal distribution of 256 bytes has theoretical maximum entropy 8.0
        data = bytes(range(256)) * 4
        h = EntropyCryptoScanner.calculate_entropy(data)
        self.assertAlmostEqual(h, 8.0, places=3)

    def test_block_entropy_classification(self):
        # Create a 2048-byte buffer: first 1024 zeros, second 1024 high-entropy
        part1 = b"\x00" * 1024
        part2 = os.urandom(1024)
        combined = part1 + part2

        blocks = EntropyCryptoScanner.scan_entropy_blocks(combined, block_size=1024, stride=1024, base_address=0x1000)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].classification, "Sparse/Text")
        self.assertFalse(blocks[0].is_high_entropy)
        self.assertTrue(blocks[1].entropy >= 7.0)

    def test_detect_aes_sbox(self):
        aes_sbox = bytes([0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76])
        buffer = b"PREFIX_PADDING_" + aes_sbox + b"_SUFFIX_PADDING"
        matches = EntropyCryptoScanner.scan_buffer_for_crypto(buffer, base_address=0x5000)

        aes_matches = [m for m in matches if m.algorithm == "AES" and "S-Box" in m.name]
        self.assertTrue(len(aes_matches) >= 1)
        self.assertEqual(aes_matches[0].address, 0x5000 + len(b"PREFIX_PADDING_"))

    def test_detect_chacha20_constant(self):
        buffer = b"\x90\x90\x90" + b"expand 32-byte k" + b"\x90\x90"
        matches = EntropyCryptoScanner.scan_buffer_for_crypto(buffer, base_address=0x8000)
        chacha_matches = [m for m in matches if m.algorithm == "ChaCha20"]
        self.assertEqual(len(chacha_matches), 1)
        self.assertEqual(chacha_matches[0].address, 0x8000 + 3)

    def test_detect_sha256_constants(self):
        import struct
        sha_const = struct.pack("<8I", 0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A, 0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19)
        buffer = b"\xCC" * 16 + sha_const + b"\xCC" * 16
        matches = EntropyCryptoScanner.scan_buffer_for_crypto(buffer, base_address=0x9000)
        sha_matches = [m for m in matches if m.algorithm == "SHA-256"]
        self.assertEqual(len(sha_matches), 1)
        self.assertEqual(sha_matches[0].address, 0x9000 + 16)

    def test_scan_process_invalid_pid(self):
        entropy_res, crypto_res = EntropyCryptoScanner.scan_process(0)
        self.assertEqual(entropy_res, [])
        self.assertEqual(crypto_res, [])

    def test_stride_zero_or_negative(self):
        blocks = EntropyCryptoScanner.scan_entropy_blocks(b"hello world", block_size=1024, stride=0)
        self.assertEqual(blocks, [])
        blocks_neg = EntropyCryptoScanner.scan_entropy_blocks(b"hello world", block_size=1024, stride=-1)
        self.assertEqual(blocks_neg, [])

    def test_scan_process_with_mock_maps(self):
        from unittest.mock import patch
        from phantom_suite.core.memory_engine import MemoryRegion

        mock_region = MemoryRegion(
            start=0x10000,
            end=0x11000,
            perms="rw-p",
            offset=0,
            dev="00:00",
            inode=0,
            pathname="[heap]"
        )
        sample_data = b"expand 32-byte k" + (b"\x00" * 4080)

        with patch("phantom_suite.core.memory_engine.MemoryEngine.get_maps", return_value=[mock_region]), \
             patch("phantom_suite.core.memory_engine.MemoryEngine.read_bytes", return_value=sample_data):
            entropy_res, crypto_res = EntropyCryptoScanner.scan_process(1234)
            self.assertTrue(len(crypto_res) >= 1)
            self.assertEqual(crypto_res[0].algorithm, "ChaCha20")


if __name__ == "__main__":
    unittest.main()
