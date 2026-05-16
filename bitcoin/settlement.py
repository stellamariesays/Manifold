"""
Settlement layer — Bitcoin-backed escrow for Manifold trust claims.

When an agent stakes Bitcoin on a claim:
1. Sats are sent to a 2-of-2 escrow (agent + federation)
2. If the agent delivers (Grade ≥ threshold), sats return to agent
3. If the agent fails (Grade < threshold = slash), sats burn

For now, this uses a simplified model:
- Agent sends sats to a federation-controlled escrow address
- Oracle verifies the deposit
- On completion, settlement instructions are generated
- Actual tx signing is done by the agent's wallet

This is Phase 1 — honest-agent model. Phase 2 adds proper multisig.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .oracle import BitcoinOracle
from .wallet import AgentWallet, FederationWallet, burn_address


class SettlementStatus(str, Enum):
    PENDING = "pending"        # Waiting for on-chain deposit
    DEPOSITED = "deposited"    # Deposit confirmed on chain
    IN_ESCROW = "in_escrow"    # Confirmed, stake active
    RELEASED = "released"      # Task success, sats returned
    SLASHED = "slashed"        # Task failed, sats burned
    EXPIRED = "expired"        # Timeout, sats returned
    DISPUTED = "disputed"      # Needs manual resolution


@dataclass
class EscrowContract:
    """
    A Bitcoin escrow contract backing a Manifold trust claim.

    Links on-chain Bitcoin to the Manifold trust layer:
    - task_id: The Manifold task this stake is for
    - agent: The agent putting up the stake
    - amount_sats: How many sats are at risk
    - escrow_address: Where the sats are held
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str = ""
    agent_name: str = ""
    hub: str = ""

    # Bitcoin side
    amount_sats: int = 0
    escrow_address: str = ""
    deposit_txid: str = ""
    release_txid: str = ""

    # Timing
    created_at: float = field(default_factory=time.time)
    deposit_deadline: float = 0.0     # Unix timestamp
    escrow_expires: float = 0.0       # When sats return if no grade filed

    # State
    status: SettlementStatus = SettlementStatus.PENDING
    grade_score: Optional[float] = None
    slash_threshold: float = 0.5

    # Settlement
    settlement_tx_hex: str = ""
    settlement_address: str = ""       # Where sats go on release

    @property
    def is_expired(self) -> bool:
        return time.time() > self.escrow_expires if self.escrow_expires else False

    @property
    def deposit_overdue(self) -> bool:
        return (
            self.deposit_deadline > 0
            and time.time() > self.deposit_deadline
            and self.status == SettlementStatus.PENDING
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "hub": self.hub,
            "amount_sats": self.amount_sats,
            "escrow_address": self.escrow_address,
            "deposit_txid": self.deposit_txid,
            "status": self.status.value,
            "created_at": self.created_at,
            "grade_score": self.grade_score,
        }


class SettlementEngine:
    """
    Manages Bitcoin escrow contracts for the Manifold federation.

    Flow:
    1. Agent makes a claim with stake → create_contract()
    2. Agent deposits sats → record_deposit()
    3. Oracle confirms deposit → confirm_deposit()
    4. Task completes, grade filed → settle()
    5. If grade ≥ threshold: release to agent
    6. If grade < threshold: slash (burn)
    """

    def __init__(
        self,
        federation_wallet: FederationWallet,
        oracle: BitcoinOracle,
        escrow_agent: str = "escrow",
        default_deposit_deadline_s: float = 3600,     # 1 hour to deposit
        default_escrow_duration_s: float = 86400 * 7,  # 1 week max escrow
        min_stake_sats: int = 1000,                    # 1000 sats minimum
    ):
        self.wallet = federation_wallet
        self.oracle = oracle
        self.escrow_agent = escrow_agent
        self.deposit_deadline_s = default_deposit_deadline_s
        self.escrow_duration_s = default_escrow_duration_s
        self.min_stake_sats = min_stake_sats

        # Escrow wallet (federation-controlled)
        self.escrow_wallet = federation_wallet.get_wallet(escrow_agent)

        # Active contracts
        self._contracts: dict[str, EscrowContract] = {}

    def create_contract(
        self,
        task_id: str,
        agent_name: str,
        amount_sats: int,
        hub: str = "",
        slash_threshold: float = 0.5,
    ) -> EscrowContract:
        """
        Create an escrow contract for a staked claim.

        Returns the contract with the escrow address where the agent
        should send their sats.
        """
        if amount_sats < self.min_stake_sats:
            raise ValueError(
                f"Stake must be at least {self.min_stake_sats} sats; got {amount_sats}"
            )

        now = time.time()
        contract = EscrowContract(
            task_id=task_id,
            agent_name=agent_name,
            hub=hub,
            amount_sats=amount_sats,
            escrow_address=self.escrow_wallet.address,
            deposit_deadline=now + self.deposit_deadline_s,
            escrow_expires=now + self.escrow_duration_s,
            slash_threshold=slash_threshold,
        )

        self._contracts[contract.id] = contract
        return contract

    def record_deposit(self, contract_id: str, txid: str) -> EscrowContract:
        """
        Agent reports that they sent sats. We record the txid.

        Actual verification happens in confirm_deposit().
        """
        contract = self._get_contract(contract_id)

        if contract.status != SettlementStatus.PENDING:
            raise ValueError(f"Contract {contract_id} is {contract.status.value}, not pending")

        if contract.deposit_overdue:
            contract.status = SettlementStatus.EXPIRED
            raise ValueError(f"Deposit deadline passed for contract {contract_id}")

        contract.deposit_txid = txid
        contract.status = SettlementStatus.DEPOSITED
        return contract

    def confirm_deposit(self, contract_id: str, min_confirmations: int = 1) -> EscrowContract:
        """
        Oracle checks that the deposit actually landed on chain.

        Verifies:
        1. TX exists and is confirmed
        2. Correct amount sent to escrow address
        """
        contract = self._get_contract(contract_id)

        if contract.status != SettlementStatus.DEPOSITED:
            raise ValueError(f"Contract {contract_id} must be DEPOSITED, not {contract.status.value}")

        # Oracle check
        verified = self.oracle.verify_stake(
            contract.escrow_address,
            contract.amount_sats,
            min_confirmations=min_confirmations,
        )

        if verified:
            contract.status = SettlementStatus.IN_ESCROW
        else:
            # Deposit not found or insufficient — keep as DEPOSITED
            # (might just need more confirmations)
            pass

        return contract

    def settle(self, contract_id: str, grade_score: float) -> EscrowContract:
        """
        Settle a contract based on the task grade.

        grade_score >= slash_threshold → RELEASED (sats return to agent)
        grade_score < slash_threshold → SLASHED (sats burn)
        """
        contract = self._get_contract(contract_id)

        if contract.status != SettlementStatus.IN_ESCROW:
            raise ValueError(f"Contract {contract_id} must be IN_ESCROW, not {contract.status.value}")

        contract.grade_score = grade_score

        if grade_score >= contract.slash_threshold:
            # Success — generate release instructions
            agent_wallet = self.wallet.get_wallet(contract.agent_name)
            contract.settlement_address = agent_wallet.address
            contract.status = SettlementStatus.RELEASED
        else:
            # Slash — burn the sats
            contract.settlement_address = burn_address(self.oracle.network)
            contract.status = SettlementStatus.SLASHED

        return contract

    def check_expiry(self) -> list[EscrowContract]:
        """Check all contracts for expiry. Returns expired contracts."""
        expired = []
        for contract in self._contracts.values():
            if contract.status == SettlementStatus.IN_ESCROW and contract.is_expired:
                contract.status = SettlementStatus.EXPIRED
                agent_wallet = self.wallet.get_wallet(contract.agent_name)
                contract.settlement_address = agent_wallet.address
                expired.append(contract)
        return expired

    def get_contract(self, contract_id: str) -> EscrowContract:
        return self._get_contract(contract_id)

    def contracts_for_agent(self, agent_name: str) -> list[EscrowContract]:
        """Get all contracts for an agent."""
        return [c for c in self._contracts.values() if c.agent_name == agent_name]

    def active_contracts(self) -> list[EscrowContract]:
        """Get all active (non-terminal) contracts."""
        terminal = {SettlementStatus.RELEASED, SettlementStatus.SLASHED,
                     SettlementStatus.EXPIRED}
        return [c for c in self._contracts.values() if c.status not in terminal]

    def stats(self) -> dict:
        """Federation-wide settlement stats."""
        contracts = list(self._contracts.values())
        return {
            "total": len(contracts),
            "pending": sum(1 for c in contracts if c.status == SettlementStatus.PENDING),
            "in_escrow": sum(1 for c in contracts if c.status == SettlementStatus.IN_ESCROW),
            "released": sum(1 for c in contracts if c.status == SettlementStatus.RELEASED),
            "slashed": sum(1 for c in contracts if c.status == SettlementStatus.SLASHED),
            "total_sats_staked": sum(c.amount_sats for c in contracts if c.status == SettlementStatus.IN_ESCROW),
            "total_sats_slashed": sum(c.amount_sats for c in contracts if c.status == SettlementStatus.SLASHED),
            "total_sats_released": sum(c.amount_sats for c in contracts if c.status == SettlementStatus.RELEASED),
        }

    def _get_contract(self, contract_id: str) -> EscrowContract:
        if contract_id not in self._contracts:
            raise KeyError(f"Contract {contract_id} not found")
        return self._contracts[contract_id]

    def __repr__(self) -> str:
        return f"<SettlementEngine contracts={len(self._contracts)} escrow={self.escrow_wallet.address[:16]}...>"
