#!/usr/bin/env python3
"""portfolio.py — Federation-wide BTC portfolio tracker for Manifold agents.

Tracks each agent's:
- Current BTC balance (on-chain + Lightning)
- Staking history (total staked, released, slashed)
- Portfolio value in USD
- Performance metrics

Usage:
    python3 portfolio.py status
    python3 portfolio.py agent stella
    python3 portfolio.py leaderboard
    python3 portfolio.py history stella --last 10
"""

import json
import math
import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Data ─────────────────────────────────────────────────────────────────────

@dataclass
class AgentPortfolio:
    agent_name: str
    address: str
    network: str

    # On-chain
    balance_sats: int = 0
    total_received_sats: int = 0
    total_sent_sats: int = 0

    # Staking
    total_staked: int = 0
    total_released: int = 0
    total_slashed: int = 0
    active_escrow: int = 0

    # Lightning
    ln_local_msat: int = 0
    ln_remote_msat: int = 0

    # Metrics
    trust_score: float = 0.5
    slash_rate: float = 0.0
    contracts_completed: int = 0

    # Timestamps
    last_updated: float = 0

    @property
    def balance_btc(self) -> float:
        return self.balance_sats / 100_000_000

    @property
    def total_wealth_sats(self) -> int:
        return self.balance_sats + self.active_escrow + (self.ln_local_msat // 1000)

    @property
    def net_stake_pnl_sats(self) -> int:
        return self.total_released - self.total_slashed

    @property
    def reliability(self) -> float:
        if self.contracts_completed == 0:
            return 0.5
        return 1.0 - self.slash_rate


@dataclass
class PortfolioSnapshot:
    timestamp: float
    portfolios: dict[str, AgentPortfolio]
    btc_price_usd: float
    total_federation_sats: int

    @property
    def total_value_usd(self) -> float:
        return self.total_federation_sats / 100_000_000 * self.btc_price_usd


# ── Price ────────────────────────────────────────────────────────────────────

def get_btc_price() -> float:
    """Get current BTC/USD price from CoinGecko."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "Manifold/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data["bitcoin"]["usd"]
    except Exception:
        return 0


def get_address_balance(address: str) -> dict:
    """Get on-chain balance for a testnet address via mempool.space."""
    try:
        url = f"https://mempool.space/testnet/api/address/{address}"
        req = urllib.request.Request(url, headers={"User-Agent": "Manifold/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            chain = data.get("chain_stats", {})
            return {
                "funded": chain.get("funded_txo_sum", 0),
                "spent": chain.get("spent_txo_sum", 0),
                "balance": chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0),
            }
    except Exception:
        return {"funded": 0, "spent": 0, "balance": 0}


# ── Portfolio Manager ────────────────────────────────────────────────────────

class PortfolioManager:
    """Tracks BTC portfolios across the federation."""

    def __init__(self, data_dir: str = "/tmp/manifold-portfolio"):
        self.data_dir = data_dir
        self.portfolios: dict[str, AgentPortfolio] = {}
        self.history: list[PortfolioSnapshot] = []
        os.makedirs(data_dir, exist_ok=True)

    def register_agent(self, name: str, address: str, network: str = "testnet"):
        """Register or update an agent's BTC address."""
        if name not in self.portfolios:
            self.portfolios[name] = AgentPortfolio(
                agent_name=name,
                address=address,
                network=network,
            )

    def update_from_settlement(self, settlement_stats: dict):
        """Update portfolios from the settlement layer's stats."""
        # This would be called with actual settlement data
        pass

    def update_onchain_balances(self):
        """Fetch on-chain balances for all registered agents."""
        for name, portfolio in self.portfolios.items():
            bal = get_address_balance(portfolio.address)
            portfolio.balance_sats = bal["balance"]
            portfolio.total_received_sats = bal["funded"]
            portfolio.total_sent_sats = bal["spent"]
            portfolio.last_updated = time.time()

    def update_from_btc_layer(self, btc_layer):
        """Pull data from a BitcoinManifoldLayer instance."""
        for agent_name in btc_layer.wallet.agents:
            address = btc_layer.wallet.agent_address(agent_name)
            self.register_agent(agent_name, address)

            # Get settlement data
            contracts = btc_layer.settlement.contracts_for_agent(agent_name)
            portfolio = self.portfolios[agent_name]

            total_staked = sum(c.amount_sats for c in contracts)
            released = sum(c.amount_sats for c in contracts if c.status.value == "released")
            slashed = sum(c.amount_sats for c in contracts if c.status.value == "slashed")
            in_escrow = sum(c.amount_sats for c in contracts if c.status.value == "in_escrow")

            portfolio.total_staked = total_staked
            portfolio.total_released = released
            portfolio.total_slashed = slashed
            portfolio.active_escrow = in_escrow
            portfolio.contracts_completed = len(contracts)
            portfolio.slash_rate = slashed / total_staked if total_staked > 0 else 0
            portfolio.last_updated = time.time()

    def snapshot(self) -> PortfolioSnapshot:
        """Take a snapshot of current portfolio state."""
        price = get_btc_price()
        total = sum(p.total_wealth_sats for p in self.portfolios.values())
        snap = PortfolioSnapshot(
            timestamp=time.time(),
            portfolios=dict(self.portfolios),
            btc_price_usd=price,
            total_federation_sats=total,
        )
        self.history.append(snap)
        return snap

    def leaderboard(self) -> list[AgentPortfolio]:
        """Rank agents by total wealth."""
        return sorted(
            self.portfolios.values(),
            key=lambda p: p.total_wealth_sats,
            reverse=True,
        )

    def reliability_board(self) -> list[AgentPortfolio]:
        """Rank agents by reliability (lowest slash rate)."""
        return sorted(
            [p for p in self.portfolios.values() if p.contracts_completed > 0],
            key=lambda p: p.reliability,
            reverse=True,
        )

    # ─── Persistence ───────────────────────────────────────────────────

    def save(self):
        """Save portfolios to disk."""
        data = {
            "portfolios": {
                name: {
                    "agent_name": p.agent_name,
                    "address": p.address,
                    "network": p.network,
                    "total_staked": p.total_staked,
                    "total_released": p.total_released,
                    "total_slashed": p.total_slashed,
                    "active_escrow": p.active_escrow,
                    "contracts_completed": p.contracts_completed,
                    "slash_rate": p.slash_rate,
                    "last_updated": p.last_updated,
                }
                for name, p in self.portfolios.items()
            }
        }
        path = os.path.join(self.data_dir, "portfolios.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self):
        """Load portfolios from disk."""
        path = os.path.join(self.data_dir, "portfolios.json")
        if not os.path.exists(path):
            return
        with open(path) as f:
            data = json.load(f)
        for name, pdata in data.get("portfolios", {}).items():
            self.portfolios[name] = AgentPortfolio(
                agent_name=pdata["agent_name"],
                address=pdata["address"],
                network=pdata.get("network", "testnet"),
                total_staked=pdata.get("total_staked", 0),
                total_released=pdata.get("total_released", 0),
                total_slashed=pdata.get("total_slashed", 0),
                active_escrow=pdata.get("active_escrow", 0),
                contracts_completed=pdata.get("contracts_completed", 0),
                slash_rate=pdata.get("slash_rate", 0),
                last_updated=pdata.get("last_updated", 0),
            )


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manifold BTC Portfolio Tracker")
    parser.add_argument("command", choices=["status", "agent", "leaderboard", "reliable"])
    parser.add_argument("--name", help="Agent name for 'agent' command")
    args = parser.parse_args()

    pm = PortfolioManager()
    pm.load()

    # For demo, create some sample agents if empty
    if not pm.portfolios:
        print("No portfolios loaded. Run with a live BTC layer or seed data.")
        print("Creating demo portfolios...")
        from bitcoin.wallet import generate_federation_seed
        from bitcoin.agent_bitcoin import BitcoinManifoldLayer

        seed = generate_federation_seed()
        layer = BitcoinManifoldLayer(seed_hex=seed, network="testnet")
        for name in ["stella", "braid", "infra", "cron-monitor"]:
            layer.register_agent(name)
        pm.update_from_btc_layer(layer)
        pm.save()

    if args.command == "status":
        snap = pm.snapshot()
        print(f"\n{'='*50}")
        print("FEDERATION BTC PORTFOLIO")
        print(f"{'='*50}")
        print(f"BTC Price: ${snap.btc_price_usd:,.0f}")
        print(f"Total: {snap.total_federation_sats:,} sats (${snap.total_value_usd:,.2f})")
        print(f"Agents: {len(pm.portfolios)}")
        print()
        for name, p in pm.portfolios.items():
            print(f"  {name}:")
            print(f"    Address: {p.address}")
            print(f"    Staked:  {p.total_staked:,} sats")
            print(f"    Escrow:  {p.active_escrow:,} sats")
            print(f"    Slashed: {p.total_slashed:,} sats")
            print(f"    P&L:     {p.net_stake_pnl_sats:+,} sats")
            print(f"    Reliability: {p.reliability:.0%}")

    elif args.command == "agent":
        name = args.name
        if not name or name not in pm.portfolios:
            print(f"Agent not found. Available: {list(pm.portfolios.keys())}")
            sys.exit(1)
        p = pm.portfolios[name]
        print(f"\nAgent: {p.agent_name}")
        print(f"Address: {p.address}")
        print(f"Network: {p.network}")
        print(f"Balance: {p.balance_sats:,} sats ({p.balance_btc:.8f} BTC)")
        print(f"Staked:  {p.total_staked:,} sats")
        print(f"Released:{p.total_released:,} sats")
        print(f"Slashed: {p.total_slashed:,} sats")
        print(f"Escrow:  {p.active_escrow:,} sats")
        print(f"P&L:     {p.net_stake_pnl_sats:+,} sats")
        print(f"Reliability: {p.reliability:.0%}")

    elif args.command == "leaderboard":
        board = pm.leaderboard()
        print(f"\n🏆 BTC Wealth Leaderboard")
        print(f"{'='*50}")
        for i, p in enumerate(board, 1):
            print(f"  {i}. {p.agent_name:20s} {p.total_wealth_sats:>10,} sats")

    elif args.command == "reliable":
        board = pm.reliability_board()
        print(f"\n🛡️ Reliability Leaderboard")
        print(f"{'='*50}")
        for i, p in enumerate(board, 1):
            print(f"  {i}. {p.agent_name:20s} {p.reliability:.0%} reliable ({p.contracts_completed} contracts)")


if __name__ == "__main__":
    main()
