"""
PhantomSuite Shannon Entropy & Cryptographic Primitive Scanner
Calculates information entropy across memory segments and identifies
cryptographic constants, S-Boxes, initialization vectors, and hash tables.
"""

import math
import struct
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from phantom_suite.core.memory_engine import MemoryEngine


@dataclass
class EntropyBlock:
    """Represents the Shannon entropy of a contiguous memory block."""
    address: int
    size: int
    entropy: float
    classification: str  # "Encrypted/Packed", "Code/Structured", "Sparse/Text"
    is_high_entropy: bool  # entropy >= 7.5


@dataclass
class CryptoSignature:
    """Signature of a known cryptographic constant or lookup table."""
    algorithm: str
    name: str
    patterns: List[bytes]
    description: str
    confidence: float = 1.0


@dataclass
class CryptoMatch:
    """Location and metadata of a detected cryptographic primitive."""
    algorithm: str
    name: str
    address: int
    confidence: float
    description: str
    sample_hex: str


class EntropyCryptoScanner:
    """
    Scans process memory or raw buffers for Shannon entropy and
    standard cryptographic primitives (AES, SHA, ChaCha20, MD5, CRC, Curve25519).
    """

    HIGH_ENTROPY_THRESHOLD = 7.5
    MODERATE_ENTROPY_THRESHOLD = 5.0

    # Cryptographic Constant Database
    SIGNATURES: List[CryptoSignature] = [
        # AES Forward S-Box
        CryptoSignature(
            algorithm="AES",
            name="AES Forward S-Box",
            patterns=[
                bytes([0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76])
            ],
            description="First 16 bytes of the Rijndael forward substitution box (S-Box)",
            confidence=1.0
        ),
        # AES Inverse S-Box
        CryptoSignature(
            algorithm="AES",
            name="AES Inverse S-Box",
            patterns=[
                bytes([0x52, 0x09, 0x6A, 0xD5, 0x30, 0x36, 0xA5, 0x38, 0xBF, 0x40, 0xA3, 0x9E, 0x81, 0xF3, 0xD7, 0xFB])
            ],
            description="First 16 bytes of the Rijndael inverse substitution box (InvS-Box)",
            confidence=1.0
        ),
        # AES Rcon Table
        CryptoSignature(
            algorithm="AES",
            name="AES Key Schedule Rcon Table",
            patterns=[
                bytes([0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36])
            ],
            description="AES round constants (Rcon) table used in key expansion",
            confidence=0.95
        ),
        # SHA-256 Initial Hash State
        CryptoSignature(
            algorithm="SHA-256",
            name="SHA-256 Initial Constants (H0-H7)",
            patterns=[
                struct.pack("<8I", 0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A, 0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19),
                struct.pack(">8I", 0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A, 0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19)
            ],
            description="Initial state vector H[0..7] for SHA-224 / SHA-256 computation",
            confidence=1.0
        ),
        # SHA-256 Round Constants (K0-K7)
        CryptoSignature(
            algorithm="SHA-256",
            name="SHA-256 Round Constants (K0-K7)",
            patterns=[
                struct.pack("<8I", 0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5),
                struct.pack(">8I", 0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5, 0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5)
            ],
            description="First 8 cube root fraction constants K[0..7] for SHA-256 rounds",
            confidence=0.98
        ),
        # SHA-1 Initial State
        CryptoSignature(
            algorithm="SHA-1",
            name="SHA-1 Initial Constants",
            patterns=[
                struct.pack("<5I", 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0),
                struct.pack(">5I", 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0)
            ],
            description="Standard 160-bit state initialization vector for SHA-1",
            confidence=1.0
        ),
        # MD5 Initial State
        CryptoSignature(
            algorithm="MD5",
            name="MD5 Initial State Constants",
            patterns=[
                struct.pack("<4I", 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476),
                struct.pack(">4I", 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476)
            ],
            description="Initial state words A, B, C, D for MD5 digest algorithm",
            confidence=0.95
        ),
        # ChaCha20 Magic String
        CryptoSignature(
            algorithm="ChaCha20",
            name="ChaCha20 Setup Constant ('expand 32-byte k')",
            patterns=[
                b"expand 32-byte k"
            ],
            description="Standard ASCII constant block for ChaCha20 256-bit key expansion",
            confidence=1.0
        ),
        # Salsa20 Magic String
        CryptoSignature(
            algorithm="Salsa20",
            name="Salsa20 Setup Constant ('expand 16-byte k')",
            patterns=[
                b"expand 16-byte k"
            ],
            description="Standard ASCII constant block for Salsa20 128-bit key expansion",
            confidence=1.0
        ),
        # CRC32 Standard Polynomial Table Header
        CryptoSignature(
            algorithm="CRC32",
            name="CRC-32 IEEE 802.3 Lookup Table (Reversed Poly 0xEDB88320)",
            patterns=[
                struct.pack("<4I", 0x00000000, 0x77073096, 0xEE0E612C, 0x990951BA)
            ],
            description="First 4 entries of the standard IEEE 802.3 CRC-32 lookup table",
            confidence=0.95
        ),
        # Curve25519 Prime Header (2^255 - 19)
        CryptoSignature(
            algorithm="Curve25519",
            name="Curve25519 Field Prime (2^255 - 19)",
            patterns=[
                bytes([0xED, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
            ],
            description="First 16 little-endian bytes of the Curve25519 prime field modulus",
            confidence=0.9
        )
    ]

    @classmethod
    def calculate_entropy(cls, data: bytes) -> float:
        """
        Calculates the Shannon Entropy H of a byte buffer:
        H(X) = -sum(P(x) * log2(P(x))) for x in bytes
        Returns float in range [0.0, 8.0].
        """
        if not data:
            return 0.0

        length = len(data)
        counts = Counter(data)
        entropy = 0.0

        for count in counts.values():
            p = count / length
            entropy -= p * math.log2(p)

        return round(entropy, 4)

    @classmethod
    def scan_entropy_blocks(cls, data: bytes, block_size: int = 1024, stride: int = 512, base_address: int = 0) -> List[EntropyBlock]:
        """
        Divides buffer into overlapping or consecutive blocks and calculates entropy for each.
        """
        blocks: List[EntropyBlock] = []
        if not data or block_size <= 0 or stride <= 0:
            return blocks

        data_len = len(data)
        for offset in range(0, data_len, stride):
            chunk = data[offset:offset + block_size]
            # Require minimum sample size (at least 256 bytes) to reliably classify entropy
            if len(chunk) < 256:
                break

            h = cls.calculate_entropy(chunk)
            is_high = h >= cls.HIGH_ENTROPY_THRESHOLD
            if is_high:
                classification = "Encrypted/Packed"
            elif h >= cls.MODERATE_ENTROPY_THRESHOLD:
                classification = "Code/Structured"
            else:
                classification = "Sparse/Text"

            blocks.append(EntropyBlock(
                address=base_address + offset,
                size=len(chunk),
                entropy=h,
                classification=classification,
                is_high_entropy=is_high
            ))

        return blocks

    @classmethod
    def scan_buffer_for_crypto(cls, data: bytes, base_address: int = 0) -> List[CryptoMatch]:
        """
        Scans a byte buffer for standard cryptographic constants and S-boxes.
        """
        matches: List[CryptoMatch] = []
        if not data:
            return matches

        for sig in cls.SIGNATURES:
            for pat in sig.patterns:
                pat_len = len(pat)
                start = 0
                while True:
                    idx = data.find(pat, start)
                    if idx == -1:
                        break

                    matched_addr = base_address + idx
                    sample = data[idx:idx + min(pat_len, 16)].hex().upper()

                    matches.append(CryptoMatch(
                        algorithm=sig.algorithm,
                        name=sig.name,
                        address=matched_addr,
                        confidence=sig.confidence,
                        description=sig.description,
                        sample_hex=sample
                    ))

                    start = idx + 1

        return matches

    @classmethod
    def scan_process(cls, pid: int, max_regions: int = 100) -> Tuple[List[EntropyBlock], List[CryptoMatch]]:
        """
        Scans readable memory regions of a target process for high-entropy clusters
        and cryptographic constants.
        """
        entropy_results: List[EntropyBlock] = []
        crypto_results: List[CryptoMatch] = []

        if not pid or pid <= 0:
            return entropy_results, crypto_results

        regions = MemoryEngine.get_maps(pid)
        scanned_count = 0

        for r in regions:
            # Focus on readable memory, skip pseudo-regions
            if not r.is_readable:
                continue
            if r.pathname.startswith("[vvar]") or r.pathname.startswith("[vdso]"):
                continue

            # Read region up to 1MB per region for performance
            scan_size = min(r.size, 1024 * 1024)
            data = MemoryEngine.read_bytes(pid, r.start, scan_size)
            if not data:
                continue

            # 1. Entropy analysis (large blocks)
            blocks = cls.scan_entropy_blocks(data, block_size=4096, stride=4096, base_address=r.start)
            for b in blocks:
                if b.is_high_entropy:
                    entropy_results.append(b)

            # 2. Crypto primitives scan
            found_crypto = cls.scan_buffer_for_crypto(data, base_address=r.start)
            crypto_results.extend(found_crypto)

            scanned_count += 1
            if scanned_count >= max_regions:
                break

        return entropy_results, crypto_results
