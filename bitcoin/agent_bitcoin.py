"""
Bitcoin-backed Manifold agents — integration layer.

This connects the Bitcoin settlement layer to Manifold's existing
trust system (core/trust.py). Now when agents stake on claims,
the stakes are real Bitcoin, not abstract numbers.

Usage::

    from bitcoin import BitcoinManifoldLayer

    # Initialize with federation seed
    btc = BitcoinManifoldLayer(seed_hex="...", network="testnet")

    # Agent stakes real sats on a claim
    contract = btc.stake_claim(claim, amount_sats=50000)

    # After task completes, settle with grade
    btc.settle_with_grade(contract.id, grade)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.trust import Claim, Grade, Stake, TrustLedger
from core.protocol import TaskRequest, TaskResult, TaskStatus

from .oracle import BitcoinOracle
from .wallet import FederationWallet, AgentWallet, generate_federation_seed, burn_address
from .settlement import SettlementEngine, EscrowContract, SettlementStatus


class BitcoinManifoldLayer:
    """
    Bridge between Bitcoin and Manifold trust.

    Makes the trust layer's abstract stakes concrete:
    - Agent claims a task → backed by real BTC escrow
    - Grade filed → BTC released or burned
    - Trust scores now reflect real economic skin in the game
    """

    def __init__(
        self,
        seed_hex: str,
        network: str = "testnet",
        min_stake_sats: int = 1000,
    ):
        self.oracle = BitcoinOracle(network=network)
        self.wallet = FederationWallet(seed_hex, network=network)
        self.settlement = SettlementEngine(
            federation_wallet=self.wallet,
            oracle=self.oracle,
            min_stake_sats=min_stake_sats,
        )
        self.network = network

    # ─── Agent registration ──────────────────────────────────────────────

    def register_agent(self, agent_name: str) -> AgentWallet:
        """Register an agent and get their Bitcoin wallet."""
        return self.wallet.get_wallet(agent_name)

    def agent_address(self, agent_name: str) -> str:
        """Get Bitcoin address for an agent."""
        return self.wallet.agent_address(agent_name)

    # ─── Staking ─────────────────────────────────────────────────────────

    def stake_claim(
        self,
        claim: Claim,
        amount_sats: int,
        hub: str = "",
    ) -> EscrowContract:
        """
        Back a Manifold Claim with real Bitcoin.

        1. Creates an escrow contract
        2. Returns the contract with deposit instructions
        3. Agent must send `amount_sats` to the escrow address
        4. Call confirm_deposit() once sent

        The claim.stake is updated to reflect the real BTC amount.
        """
        contract = self.settlement.create_contract(
            task_id=claim.task,
            agent_name=claim.agent,
            amount_sats=amount_sats,
            hub=hub,
            slash_threshold=0.5,
        )
        return contract

    def deposit_stake(self, contract_id: str, txid: str) -> EscrowContract:
        """Record that the agent sent the deposit tx."""
        return self.settlement.record_deposit(contract_id, txid)

    def confirm_stake(self, contract_id: str, min_confirmations: int = 1) -> EscrowContract:
        """Verify deposit on chain. Call after a few blocks."""
        return self.settlement.confirm_deposit(contract_id, min_confirmations)

    # ─── Settlement ──────────────────────────────────────────────────────

    def settle_with_grade(
        self,
        contract_id: str,
        grade: Grade,
    ) -> EscrowContract:
        """
        Settle an escrow contract with a Manifold Grade.

        If grade ≥ threshold: BTC returned to agent
        If grade < threshold: BTC burned (slashed)
        """
        contract = self.settlement.settle(contract_id, grade.score)
        return contract

    # ─── Trust score (BTC-enhanced) ──────────────────────────────────────

    def btc_enhanced_score(
        self,
        agent_name: str,
        domain: str,
        ledger: TrustLedger,
    ) -> dict:
        """
        Enhanced trust score that factors in real BTC history.

        Combines:
        - Traditional trust score from the ledger
        - Total BTC staked (economic commitment)
        - Slash rate in BTC terms
        - Active escrow (current skin in game)
        """
        contracts = self.settlement.contracts_for_agent(agent_name)

        traditional = ledger.domain_score(agent_name, domain) or 0.5

        total_staked = sum(c.amount_sats for c in contracts)
        total_slashed = sum(
            c.amount_sats for c in contracts
            if c.status == SettlementStatus.SLASHED
        )
        total_released = sum(
            c.amount_sats for c in contracts
            if c.status == SettlementStatus.RELEASED
        )
        active_escrow = sum(
            c.amount_sats for c in contracts
            if c.status == SettlementStatus.IN_ESCROW
        )

        slash_rate_btc = total_slashed / total_staked if total_staked > 0 else 0.0

        # Economic trust bonus: more staked (and not slashed) = more trustworthy
        # Log scale — diminishing returns on raw amount
        import math
        economic_bonus = math.log(total_staked + 1) / 100.0 if total_staked > 0 else 0.0
        economic_penalty = slash_rate_btc * 0.3

        enhanced = max(0.0, min(1.0, traditional + economic_bonus - economic_penalty))

        return {
            "agent": agent_name,
            "domain": domain,
            "traditional_score": traditional,
            "enhanced_score": round(enhanced, 4),
            "total_sats_staked": total_staked,
            "total_sats_slashed": total_slashed,
            "total_sats_released": total_released,
            "active_escrow_sats": active_escrow,
            "slash_rate_btc": round(slash_rate_btc, 4),
            "contracts_total": len(contracts),
        }

    # ─── Federation info ─────────────────────────────────────────────────

    def federation_report(self) -> dict:
        """Full federation Bitcoin report."""
        stats = self.settlement.stats()
        return {
            "network": self.network,
            "escrow_address": self.wallet.agent_address("escrow"),
            "burn_address": burn_address(self.network),
            "registered_agents": len(self.wallet.agents),
            "agents": self.wallet.agents,
            "settlement_stats": stats,
        }

    # ─── Convenience ─────────────────────────────────────────────────────

    def close(self) -> None:
        self.oracle.close()

    def __repr__(self) -> str:
        return (
            f"<BitcoinManifoldLayer "
            f"network={self.network!r} "
            f"agents={len(self.wallet.agents)} "
            f"contracts={len(self.settlement._contracts)}>"
        )


# ─── Quick start helper ───────────────────────────────────────────────────────

def quickstart(network: str = "testnet") -> BitcoinManifoldLayer:
    """
    Create a new BitcoinManifoldLayer with a fresh random seed.

    For testing and development. Production should use a known seed.
    """
    seed = generate_federation_seed()
    print(f"Generated federation seed: {seed}")
    print(f"⚠️  SAVE THIS SEED — it controls all agent wallets!")
    return BitcoinManifoldLayer(seed_hex=seed, network=network)
