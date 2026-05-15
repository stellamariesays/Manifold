"""
Blockchain oracle — read-only access to Bitcoin chain data.

Uses mempool.space API (free, no auth) for:
- Block height / confirmation count
- UTXO lookup for addresses
- Fee estimation
- Transaction broadcast

No API key needed. Rate limited but fine for agent-scale usage.
"""

from __future__ import annotations

import hashlib
import struct
import time
from dataclasses import dataclass
from typing import Any

import httpx

# mempool.space is free, no auth, supports mainnet + testnet
_MEMPOOL_BASE = "https://mempool.space/api"
_MEMPOOL_TESTNET = "https://mempool.space/testnet/api"


@dataclass(frozen=True)
class UTXO:
    """Unspent transaction output."""
    txid: str
    vout: int
    value_sats: int
    confirmations: int
    script_hex: str

    @property
    def confirmed(self) -> bool:
        return self.confirmations >= 1


@dataclass(frozen=True)
class FeeEstimate:
    """Fee estimate in sat/vB."""
    economy: float    # ~144 blocks
    minimum: float    # ~1 block
    fast: float       # next block

    def for_speed(self, speed: str = "medium") -> int:
        """Return sat/vB for the given speed. Returns int ceiling."""
        rates = {
            "slow": self.economy,
            "medium": (self.economy + self.minimum) / 2,
            "fast": self.fast,
        }
        rate = rates.get(speed, self.minimum)
        return max(1, int(rate + 0.5))


@dataclass(frozen=True)
class TransactionInfo:
    """Basic tx info."""
    txid: str
    status: str  # "confirmed" | "pending" | "not_found"
    confirmations: int
    fee_sats: int
    weight: int


class BitcoinOracle:
    """
    Read-only Bitcoin blockchain oracle.

    No private keys, no signing. Just observes and reports.
    This is what agents use to verify that stakes actually landed on chain.
    """

    def __init__(self, network: str = "mainnet", timeout: float = 10.0):
        self.network = network
        self.base_url = _MEMPOOL_TESTNET if network == "testnet" else _MEMPOOL_BASE
        self._client = httpx.Client(timeout=timeout)
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_ttl = 30.0  # seconds

    def _get(self, path: str, use_cache: bool = True) -> dict | list:
        """GET with simple in-memory cache."""
        cache_key = f"{self.base_url}{path}"
        now = time.time()

        if use_cache and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self._cache_ttl:
                return data

        resp = self._client.get(f"{self.base_url}{path}")
        resp.raise_for_status()
        data = resp.json()

        if use_cache:
            self._cache[cache_key] = (now, data)

        return data

    # ─── Blockchain ──────────────────────────────────────────────────────

    def block_height(self) -> int:
        """Current block height."""
        return self._get("/blocks/tip/height")

    def block_hash(self, height: int) -> str:
        """Block hash at given height."""
        return self._get(f"/block-height/{height}")

    # ─── Address ─────────────────────────────────────────────────────────

    def address_utxos(self, address: str) -> list[UTXO]:
        """Get UTXOs for an address."""
        raw = self._get(f"/address/{address}/utxo", use_cache=False)
        utxos = []
        for u in raw:
            # mempool.space returns status.confirmed and status.block_height
            status = u.get("status", {})
            confirmed = status.get("confirmed", False)
            block_height = status.get("block_height", 0)
            current_height = self.block_height()
            confs = (current_height - block_height + 1) if confirmed and block_height else 0

            utxos.append(UTXO(
                txid=u["txid"],
                vout=u["vout"],
                value_sats=u["value"],
                confirmations=confs,
                script_hex=u.get("scriptpubkey", ""),
            ))
        return utxos

    def address_balance(self, address: str) -> int:
        """Total confirmed balance in sats."""
        data = self._get(f"/address/{address}")
        chain_stats = data.get("chain_stats", {})
        return chain_stats.get("funded_txo_sum", 0) - chain_stats.get("spent_txo_sum", 0)

    def address_txs(self, address: str, limit: int = 10) -> list[dict]:
        """Recent transactions for an address."""
        return self._get(f"/address/{address}/txs")[:limit]

    # ─── Transactions ────────────────────────────────────────────────────

    def tx(self, txid: str) -> TransactionInfo:
        """Get transaction details."""
        data = self._get(f"/tx/{txid}")
        status = data.get("status", {})

        if status.get("confirmed"):
            block_height = status.get("block_height", 0)
            current = self.block_height()
            confs = current - block_height + 1
            tx_status = "confirmed"
        elif data.get("txid"):
            tx_status = "pending"
            confs = 0
        else:
            tx_status = "not_found"
            confs = 0

        return TransactionInfo(
            txid=data.get("txid", txid),
            status=tx_status,
            confirmations=confs,
            fee_sats=data.get("fee", 0),
            weight=data.get("weight", 0),
        )

    def broadcast(self, raw_tx_hex: str) -> str:
        """Broadcast a raw transaction. Returns txid."""
        resp = self._client.post(
            f"{self.base_url}/tx",
            content=raw_tx_hex,
            headers={"Content-Type": "text/plain"},
        )
        resp.raise_for_status()
        return resp.text.strip()

    # ─── Fees ────────────────────────────────────────────────────────────

    def fee_estimate(self) -> FeeEstimate:
        """Current fee estimates."""
        data = self._get("/v1/fees/recommended")
        return FeeEstimate(
            economy=data.get("economyFee", data.get("minimumFee", 1)),
            minimum=data.get("minimumFee", 1),
            fast=data.get("fastestFee", 1),
        )

    # ─── Manifold helpers ────────────────────────────────────────────────

    def verify_stake(self, address: str, min_sats: int, min_confirmations: int = 1) -> bool:
        """
        Verify that an address holds at least min_sats with enough confirmations.

        Used by the federation to verify that an agent's stake claim is real.
        """
        utxos = self.address_utxos(address)
        confirmed_total = sum(u.value_sats for u in utxos if u.confirmations >= min_confirmations)
        return confirmed_total >= min_sats

    def verify_burn(self, txid: str, burn_address: str = "bc1q...burn") -> bool:
        """
        Verify that a transaction sent funds to a burn address.

        For slashing: agents prove they burned sats by showing the tx.
        """
        data = self._get(f"/tx/{txid}")
        vout = data.get("vout", [])
        for out in vout:
            scriptpubkey_address = out.get("scriptpubkey_address", "")
            if scriptpubkey_address == burn_address:
                return True
        return False

    def close(self) -> None:
        self._client.close()

    def __repr__(self) -> str:
        return f"<BitcoinOracle network={self.network!r}>"


# ─── Utility: address validation (basic) ──────────────────────────────────────

def is_valid_address(address: str) -> bool:
    """Basic Bitcoin address format check."""
    if not address:
        return False
    # Legacy
    if address[0] in ("1", "3") and 25 <= len(address) <= 34:
        return True
    # Bech32 (bc1...)
    if address.startswith("bc1") and 42 <= len(address) <= 62:
        return True
    # Bech32m (bc1p...)
    if address.startswith("bc1p") and 42 <= len(address) <= 62:
        return True
    # Testnet
    if address.startswith("tb1") and 42 <= len(address) <= 62:
        return True
    if address[0] in ("m", "n", "2") and 25 <= len(address) <= 34:
        return True
    return False


def is_testnet_address(address: str) -> bool:
    """Check if address is testnet."""
    return address.startswith("tb1") or address[0] in ("m", "n", "2")
