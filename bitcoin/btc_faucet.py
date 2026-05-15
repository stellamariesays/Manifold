#!/usr/bin/env python3
"""
btc_faucet.py — Testnet BTC faucet for Manifold federation agents.

Faucet modes:
1. Auto-drip: monitors registered agents and sends tBTC to empty wallets
2. On-demand: responds to faucet requests from agents
3. Federation-integrated: announces via federation protocol

Uses mempool.space testnet API for UTXO tracking.
Requires a funded testnet wallet (seed from federation.seed).
"""

import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitcoin.wallet import generate_federation_seed
from bitcoin.oracle import BitcoinOracle


# ── Config ──────────────────────────────────────────────────────────────────

FAUCET_DATA_DIR = "/tmp/manifold-faucet"
FAUCET_SEED_FILE = os.path.join(FAUCET_DATA_DIR, "faucet.seed")
FAUCET_STATE_FILE = os.path.join(FAUCET_DATA_DIR, "faucet_state.json")
DRIP_AMOUNT_SATS = 5_000  # 5k sats per drip (testnet)
MIN_FAUCET_BALANCE = 10_000  # Don't drip if faucet balance below this
COOLDOWN_SECONDS = 3600  # 1 hour between drips per agent


# ── Data ────────────────────────────────────────────────────────────────────

@dataclass
class DripRecord:
    agent_name: str
    address: str
    amount_sats: int
    timestamp: float
    txid: str = ""


class FaucetState:
    def __init__(self, path: str = FAUCET_STATE_FILE):
        self.path = path
        self.drips: list[DripRecord] = []
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                data = json.load(f)
            self.drips = [
                DripRecord(**d) for d in data.get("drips", [])
            ]

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = {
            "drips": [
                {
                    "agent_name": d.agent_name,
                    "address": d.address,
                    "amount_sats": d.amount_sats,
                    "timestamp": d.timestamp,
                    "txid": d.txid,
                }
                for d in self.drips
            ]
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def last_drip(self, agent_name: str) -> Optional[DripRecord]:
        agent_drips = [d for d in self.drips if d.agent_name == agent_name]
        return max(agent_drips, key=lambda d: d.timestamp) if agent_drips else None

    def can_drip(self, agent_name: str) -> bool:
        last = self.last_drip(agent_name)
        if not last:
            return True
        return (time.time() - last.timestamp) > COOLDOWN_SECONDS

    def total_dripped(self, agent_name: str) -> int:
        return sum(d.amount_sats for d in self.drips if d.agent_name == agent_name)

    def total_dripped_all(self) -> int:
        return sum(d.amount_sats for d in self.drips)


# ── Faucet ──────────────────────────────────────────────────────────────────

class BTCFaucet:
    """Testnet BTC faucet for Manifold agents."""

    def __init__(self, seed_hex: Optional[str] = None):
        os.makedirs(FAUCET_DATA_DIR, exist_ok=True)

        if seed_hex:
            self.seed = seed_hex
        elif os.path.exists(FAUCET_SEED_FILE):
            with open(FAUCET_SEED_FILE) as f:
                self.seed = f.read().strip()
        else:
            self.seed = generate_federation_seed()
            with open(FAUCET_SEED_FILE, "w") as f:
                f.write(self.seed)

        from bitcoin.wallet import FederationWallet
        self.wallet = FederationWallet(seed_hex=self.seed, network="testnet")
        self.faucet_address = self.wallet.agent_address("faucet")
        self.state = FaucetState()
        self.oracle = BitcoinOracle()

    def balance(self) -> dict:
        """Get faucet balance."""
        return self._get_address_balance(self.faucet_address)

    def _get_address_balance(self, address: str) -> dict:
        try:
            url = f"https://mempool.space/testnet/api/address/{address}"
            req = urllib.request.Request(url, headers={"User-Agent": "Manifold/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                funded = data.get("chain_stats", {}).get("funded_txo_sum", 0)
                spent = data.get("chain_stats", {}).get("spent_txo_sum", 0)
                return {
                    "address": address,
                    "funded": funded,
                    "spent": spent,
                    "balance": funded - spent,
                }
        except Exception as e:
            return {"address": address, "funded": 0, "spent": 0, "balance": 0, "error": str(e)}

    def drip(self, agent_name: str, address: str, amount_sats: int = DRIP_AMOUNT_SATS) -> DripRecord:
        """
        Send testnet BTC to an agent.

        In a real setup this would build and broadcast a raw tx.
        For now, returns the drip record for tracking.
        """
        if not self.state.can_drip(agent_name):
            last = self.state.last_drip(agent_name)
            remaining = int(COOLDOWN_SECONDS - (time.time() - last.timestamp))
            raise RuntimeError(f"Cooldown: {remaining}s remaining for {agent_name}")

        bal = self.balance()
        if bal["balance"] < MIN_FAUCET_BALANCE:
            raise RuntimeError(
                f"Faucet balance too low: {bal['balance']} sats "
                f"(minimum: {MIN_FAUCET_BALANCE})"
            )

        record = DripRecord(
            agent_name=agent_name,
            address=address,
            amount_sats=amount_sats,
            timestamp=time.time(),
        )

        self.state.drips.append(record)
        self.state.save()

        # In production: build raw tx with cryptography package and broadcast
        # For now: log the drip
        print(f"[faucet] Dripped {amount_sats} sats to {agent_name} ({address})")
        print(f"[faucet] Faucet balance: {bal['balance'] - amount_sats} sats remaining")

        return record

    def auto_drip(self, agents: dict[str, str]) -> list[DripRecord]:
        """
        Check all registered agents and drip to those with empty wallets.

        Args:
            agents: {agent_name: btc_address}
        """
        drips = []
        for name, address in agents.items():
            if not self.state.can_drip(name):
                continue

            agent_bal = self._get_address_balance(address)
            if agent_bal["balance"] == 0:
                try:
                    drip = self.drip(name, address)
                    drips.append(drip)
                except RuntimeError as e:
                    print(f"[faucet] Skip {name}: {e}")
        return drips

    def status(self) -> dict:
        """Get faucet status."""
        bal = self.balance()
        return {
            "address": self.faucet_address,
            "balance_sats": bal["balance"],
            "total_dripped": self.state.total_dripped_all(),
            "total_drips": len(self.state.drips),
            "agents_served": len(set(d.agent_name for d in self.state.drips)),
            "can_drip": bal["balance"] >= MIN_FAUCET_BALANCE,
        }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manifold BTC Testnet Faucet")
    parser.add_argument("command", choices=["status", "drip", "auto", "fund"])
    parser.add_argument("--agent", help="Agent name")
    parser.add_argument("--address", help="BTC address")
    parser.add_argument("--amount", type=int, default=DRIP_AMOUNT_SATS)
    args = parser.parse_args()

    faucet = BTCFaucet()

    if args.command == "status":
        status = faucet.status()
        print(f"\n🚰 Manifold Testnet Faucet")
        print(f"{'='*40}")
        print(f"Address:       {status['address']}")
        print(f"Balance:       {status['balance_sats']:,} sats")
        print(f"Total dripped: {status['total_dripped']:,} sats")
        print(f"Drips:         {status['total_drips']}")
        print(f"Agents served: {status['agents_served']}")
        print(f"Can drip:      {'✅' if status['can_drip'] else '❌'}")

    elif args.command == "drip":
        if not args.agent or not args.address:
            print("Error: --agent and --address required")
            sys.exit(1)
        drip = faucet.drip(args.agent, args.address, args.amount)
        print(f"Dripped {drip.amount_sats} sats to {drip.agent_name}")

    elif args.command == "auto":
        # Auto-drip to all agents from the BTC layer
        from bitcoin.agent_bitcoin import BitcoinManifoldLayer
        seed = generate_federation_seed()
        layer = BitcoinManifoldLayer(seed_hex=seed, network="testnet")
        agents = {}
        for name in ["stella", "braid", "infra", "cron-monitor"]:
            layer.register_agent(name)
            agents[name] = layer.wallet.agent_address(name)

        drips = faucet.auto_drip(agents)
        print(f"\nAuto-drip: {len(drips)} agents funded")

    elif args.command == "fund":
        print(f"Send testnet BTC to this address to fund the faucet:")
        print(f"  {faucet.faucet_address}")
        print(f"\nGet tBTC from: https://mempool.space/testnet/faucet")
        print(f"Or: https://testnet-faucet.mempool.co/")


if __name__ == "__main__":
    main()
