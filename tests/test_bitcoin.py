"""
Tests for the Manifold Bitcoin layer.

Run with: python -m pytest tests/test_bitcoin.py -v
"""

import pytest
import time

# Add project root to path
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitcoin.wallet import (
    AgentWallet, FederationWallet, generate_federation_seed,
    _derive_agent_key, _pubkey_to_address, burn_address,
)
from bitcoin.oracle import BitcoinOracle, is_valid_address
from bitcoin.settlement import SettlementEngine, SettlementStatus
from bitcoin.agent_bitcoin import BitcoinManifoldLayer

from core.trust import Claim, Grade, TrustLedger


# ─── Wallet tests ─────────────────────────────────────────────────────────────

class TestWallet:
    def test_deterministic_derivation(self):
        """Same seed + agent name = same key, every time."""
        seed = bytes(range(32))
        key1 = _derive_agent_key(seed, "stella")
        key2 = _derive_agent_key(seed, "stella")
        assert key1 == key2

    def test_different_agents_different_keys(self):
        """Different agent names = different keys."""
        seed = bytes(range(32))
        k1 = _derive_agent_key(seed, "stella")
        k2 = _derive_agent_key(seed, "braid")
        assert k1 != k2

    def test_agent_wallet_creation(self):
        wallet = AgentWallet.from_hex_seed("ab" * 32, "test-agent", "testnet")
        assert wallet.agent_name == "test-agent"
        assert wallet.address.startswith("tb1")
        assert len(wallet.pubkey_compressed) == 33  # compressed

    def test_mainnet_address(self):
        wallet = AgentWallet.from_hex_seed("ab" * 32, "test-agent", "mainnet")
        assert wallet.address.startswith("bc1")

    def test_federation_wallet(self):
        seed = generate_federation_seed()
        fed = FederationWallet(seed, network="testnet")

        w1 = fed.get_wallet("stella")
        w2 = fed.get_wallet("braid")

        assert w1.address != w2.address
        assert fed.agent_address("stella") == w1.address
        assert fed.verify_address("stella", w1.address)
        assert not fed.verify_address("stella", w2.address)

    def test_wallet_deterministic_across_instances(self):
        seed = "ab" * 32
        w1 = AgentWallet.from_hex_seed(seed, "stella", "testnet")
        w2 = AgentWallet.from_hex_seed(seed, "stella", "testnet")
        assert w1.address == w2.address
        assert w1.privkey_bytes == w2.privkey_bytes

    def test_burn_address(self):
        assert burn_address("testnet").startswith("tb1")
        assert burn_address("mainnet").startswith("bc1")


# ─── Address validation tests ─────────────────────────────────────────────────

class TestAddressValidation:
    def test_bech32_mainnet(self):
        assert is_valid_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")

    def test_bech32_testnet(self):
        assert is_valid_address("tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx")

    def test_legacy(self):
        assert is_valid_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")

    def test_invalid(self):
        assert not is_valid_address("")
        assert not is_valid_address("not-a-bitcoin-address")


# ─── Settlement tests (no network calls) ──────────────────────────────────────

class TestSettlement:
    def setup_method(self):
        self.seed = generate_federation_seed()
        self.wallet = FederationWallet(self.seed, "testnet")

        # Mock oracle that doesn't make network calls
        self.oracle = BitcoinOracle.__new__(BitcoinOracle)
        self.oracle.network = "testnet"
        self.oracle.base_url = "https://mempool.space/testnet/api"
        self.oracle._client = None
        self.oracle._cache = {}
        self.oracle._cache_ttl = 30.0

        self.engine = SettlementEngine(
            federation_wallet=self.wallet,
            oracle=self.oracle,
        )

    def test_create_contract(self):
        contract = self.engine.create_contract(
            task_id="task-001",
            agent_name="stella",
            amount_sats=50000,
            hub="satelliteA",
        )
        assert contract.agent_name == "stella"
        assert contract.amount_sats == 50000
        assert contract.status == SettlementStatus.PENDING
        assert contract.escrow_address  # Has an escrow address

    def test_min_stake(self):
        with pytest.raises(ValueError, match="at least"):
            self.engine.create_contract("t1", "stella", 100)  # Below min

    def test_record_deposit(self):
        contract = self.engine.create_contract("t1", "stella", 10000)
        updated = self.engine.record_deposit(contract.id, "abc123txid")
        assert updated.status == SettlementStatus.DEPOSITED
        assert updated.deposit_txid == "abc123txid"

    def test_settle_success(self):
        contract = self.engine.create_contract("t1", "stella", 10000)
        self.engine.record_deposit(contract.id, "abc123")
        # Manually set to IN_ESCROW (normally done by confirm_deposit)
        contract.status = SettlementStatus.IN_ESCROW

        result = self.engine.settle(contract.id, grade_score=0.8)
        assert result.status == SettlementStatus.RELEASED
        assert result.grade_score == 0.8
        # Settlement address should be agent's address
        assert result.settlement_address == self.wallet.agent_address("stella")

    def test_settle_slash(self):
        contract = self.engine.create_contract("t1", "stella", 10000)
        self.engine.record_deposit(contract.id, "abc123")
        contract.status = SettlementStatus.IN_ESCROW

        result = self.engine.settle(contract.id, grade_score=0.2)
        assert result.status == SettlementStatus.SLASHED
        assert result.settlement_address == burn_address("testnet")

    def test_stats(self):
        self.engine.create_contract("t1", "stella", 10000)
        self.engine.create_contract("t2", "braid", 20000)

        stats = self.engine.stats()
        assert stats["total"] == 2
        assert stats["pending"] == 2


# ─── Integration: BitcoinManifoldLayer ────────────────────────────────────────

class TestBitcoinManifoldLayer:
    def setup_method(self):
        self.seed = generate_federation_seed()
        self.layer = BitcoinManifoldLayer(self.seed, network="testnet")

    def test_register_agent(self):
        wallet = self.layer.register_agent("stella")
        assert wallet.agent_name == "stella"
        assert wallet.address.startswith("tb1")

    def test_stake_claim(self):
        claim = Claim(agent="stella", task="do-math", stake=50.0, domain="math")
        contract = self.layer.stake_claim(claim, 50000, hub="satelliteA")
        assert contract.agent_name == "stella"
        assert contract.amount_sats == 50000
        assert contract.status == SettlementStatus.PENDING

    def test_btc_enhanced_score(self):
        self.layer.register_agent("stella")
        ledger = TrustLedger()

        # File some grades
        ledger.record(Grade(agent="stella", domain="math", score=0.9, task_id="test-1"))

        score = self.layer.btc_enhanced_score("stella", "math", ledger)
        assert score["traditional_score"] == 0.9
        assert score["total_sats_staked"] == 0  # No contracts yet
        assert score["contracts_total"] == 0

    def test_federation_report(self):
        self.layer.register_agent("stella")
        self.layer.register_agent("braid")

        report = self.layer.federation_report()
        assert report["network"] == "testnet"
        assert report["registered_agents"] >= 2  # escrow agent auto-registered
        assert "stella" in report["agents"]
        assert "braid" in report["agents"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
