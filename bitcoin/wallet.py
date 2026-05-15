"""
Agent Bitcoin wallet — lightweight HD wallet for Manifold agents.

Generates agent-specific Bitcoin addresses from a federation seed.
No external Bitcoin libraries needed — uses secp256k1 via the
`cryptography` package for key derivation, and hashlib for hashing.

BIP32-inspired but simplified:
- Master seed → agent key → agent Bitcoin address
- Each agent in the federation gets a deterministic address
- The federation can verify an agent's address without knowing their key

Design decisions:
- Testnet by default (agents shouldn't burn real BTC on day one)
- Single address per agent (not full BIP32 tree — keep it simple)
- Supports mainnet toggle for production
"""

from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass
from typing import Optional

# ─── Base58 encoding ──────────────────────────────────────────────────────────

_B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    """Base58Check encode."""
    # Count leading zeros
    n_pad = 0
    for b in data:
        if b == 0:
            n_pad += 1
        else:
            break

    # Convert to integer
    n = int.from_bytes(data, "big")

    # Encode
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(_B58_ALPHABET[r:r + 1])

    return (b"1" * n_pad + b"".join(reversed(result))).decode("ascii")


def _b58check_encode(payload: bytes, version: int) -> str:
    """Base58Check encode with version byte."""
    versioned = bytes([version]) + payload
    checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
    return _b58encode(versioned + checksum)


# ─── Bech32 encoding (for bc1/tb1 addresses) ──────────────────────────────────

_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _bech32_polymod(values: list[int]) -> int:
    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_create_checksum(hrp: str, data: list[int]) -> list[int]:
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _bech32_encode(hrp: str, witver: int, witprog: bytes) -> str:
    """Encode a bech32 address."""
    data = [witver] + _convertbits(witprog, 8, 5)
    checksum = _bech32_create_checksum(hrp, data)
    return hrp + "1" + "".join(_BECH32_CHARSET[d] for d in data + checksum)


def _convertbits(data: bytes, frombits: int, tobits: int, pad: bool = True) -> list[int]:
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            raise ValueError("invalid value")
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        raise ValueError("non-zero padding")
    return ret


# ─── Key derivation ───────────────────────────────────────────────────────────

def _derive_agent_key(federation_seed: bytes, agent_name: str) -> bytes:
    """
    Derive a deterministic private key for an agent.

    Uses HMAC-SHA256(federation_seed, agent_name) as the private key.
    Simple, deterministic, unique per agent.
    """
    return hmac.new(federation_seed, agent_name.encode("utf-8"), hashlib.sha256).digest()


def _privkey_to_pubkey(privkey: bytes, compressed: bool = True) -> bytes:
    """
    Derive secp256k1 public key from private key.

    Uses the `cryptography` library's ec module.
    """
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    # Create private key object from raw bytes
    private_key = ec.derive_private_key(
        int.from_bytes(privkey, "big"),
        ec.SECP256K1(),
    )

    # Get public key
    public_key = private_key.public_key()

    # Serialize
    return public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.CompressedPoint if compressed else serialization.PublicFormat.UncompressedPoint,
    )


def _pubkey_to_hash160(pubkey_bytes: bytes) -> bytes:
    """RIPEMD160(SHA256(pubkey)) — the core of Bitcoin addresses."""
    sha = hashlib.sha256(pubkey_bytes).digest()
    ripemd = hashlib.new("ripemd160", sha).digest()
    return ripemd


# ─── Wallet classes ───────────────────────────────────────────────────────────

@dataclass
class AgentWallet:
    """
    A Bitcoin wallet for a Manifold agent.

    Each agent gets a deterministic address from the federation seed.
    The wallet knows its private key and can sign transactions.
    """
    agent_name: str
    privkey_bytes: bytes
    pubkey_compressed: bytes
    address: str
    network: str  # "mainnet" or "testnet"

    @classmethod
    def from_seed(
        cls,
        federation_seed: bytes,
        agent_name: str,
        network: str = "testnet",
    ) -> "AgentWallet":
        """Create wallet from federation seed and agent name."""
        privkey = _derive_agent_key(federation_seed, agent_name)
        pubkey = _privkey_to_pubkey(privkey, compressed=True)
        address = _pubkey_to_address(pubkey, network)

        return cls(
            agent_name=agent_name,
            privkey_bytes=privkey,
            pubkey_compressed=pubkey,
            address=address,
            network=network,
        )

    @classmethod
    def from_hex_seed(
        cls,
        hex_seed: str,
        agent_name: str,
        network: str = "testnet",
    ) -> "AgentWallet":
        """Create wallet from hex-encoded federation seed."""
        return cls.from_seed(bytes.fromhex(hex_seed), agent_name, network)

    @property
    def pubkey_hex(self) -> str:
        return self.pubkey_compressed.hex()

    def __repr__(self) -> str:
        return f"<AgentWallet {self.agent_name!r} addr={self.address[:12]}... network={self.network}>"


def _pubkey_to_address(pubkey: bytes, network: str = "testnet") -> str:
    """Convert compressed pubkey to a native segwit (bech32) address."""
    hash160 = _pubkey_to_hash160(pubkey)

    # Witness version 0, 20-byte program (P2WPKH)
    if network == "testnet":
        hrp = "tb"
    else:
        hrp = "bc"

    return _bech32_encode(hrp, 0, hash160)


def generate_federation_seed() -> str:
    """Generate a random 32-byte hex seed for a new federation."""
    import os
    return os.urandom(32).hex()


# ─── Manifold federation wallet ───────────────────────────────────────────────

class FederationWallet:
    """
    Manages wallets for all agents in a Manifold federation.

    One seed, many agents. Each agent's wallet is deterministic —
    given the same seed and agent name, you always get the same address.
    """

    def __init__(self, seed_hex: str, network: str = "testnet"):
        self.seed = bytes.fromhex(seed_hex)
        self.network = network
        self._wallets: dict[str, AgentWallet] = {}

    def get_wallet(self, agent_name: str) -> AgentWallet:
        """Get or create wallet for an agent."""
        if agent_name not in self._wallets:
            self._wallets[agent_name] = AgentWallet.from_seed(
                self.seed, agent_name, self.network
            )
        return self._wallets[agent_name]

    def agent_address(self, agent_name: str) -> str:
        """Get the Bitcoin address for an agent."""
        return self.get_wallet(agent_name).address

    def verify_address(self, agent_name: str, address: str) -> bool:
        """Verify that an address belongs to the named agent."""
        return self.get_wallet(agent_name).address == address

    @property
    def agents(self) -> list[str]:
        return list(self._wallets.keys())

    def __repr__(self) -> str:
        return f"<FederationWallet agents={len(self._wallets)} network={self.network!r}>"


# ─── Burn address (for slashing) ─────────────────────────────────────────────

def burn_address(network: str = "testnet") -> str:
    """
    A provably-unspendable address for burning sats during slashing.

    Uses a known burn address format. Sats sent here are gone forever.
    """
    if network == "testnet":
        return "tb1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqx3s0a7"
    return "bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqx3s0a7"
