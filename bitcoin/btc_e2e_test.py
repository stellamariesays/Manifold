#!/usr/bin/env python3
"""btc-e2e-test — End-to-end Bitcoin settlement test across a simulated federation.

Creates two hubs, registers agents on each, stakes claims, grades, and settles.
No real Bitcoin moved (testnet simulation), but full protocol flow.

Usage:
    python3 btc-e2e-test.py
    python3 btc-e2e-test.py --verbose
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitcoin.agent_bitcoin import BitcoinManifoldLayer
from bitcoin.wallet import generate_federation_seed
from bitcoin.settlement import SettlementStatus
from bitcoin.btc_federation_bridge import BtcFederationBridge
from core.trust import TrustLedger, Claim, Grade, Stake


# ── Simulated Hub ─────────────────────────────────────────────────────────────

@dataclass
class SimHub:
    """Simulated federation hub with BTC layer."""
    name: str
    bridge: BtcFederationBridge
    ledger: TrustLedger = field(default_factory=TrustLedger)
    peers: list = field(default_factory=list)
    received_messages: list = field(default_factory=list)

    def register_agent(self, name: str):
        addr = self.bridge.layer.register_agent(name)
        return addr


class SimFederation:
    """Two-hub simulated federation for testing."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.seed = generate_federation_seed()
        self.hubs: dict[str, SimHub] = {}
        self.log: list[str] = []

    def add_hub(self, name: str) -> SimHub:
        bridge = BtcFederationBridge(
            ws_url="ws://localhost:0",  # not connecting
            seed_hex=self.seed,
            network="testnet",
            hub=name,
        )
        hub = SimHub(name=name, bridge=bridge)
        self.hubs[name] = hub
        self._log(f"Hub '{name}' created")
        return hub

    def _log(self, msg: str):
        self.log.append(msg)
        if self.verbose:
            print(f"  [sim] {msg}")

    def connect_hubs(self, hub_a: str, hub_b: str):
        """Simulate peer connection — exchange addresses."""
        a = self.hubs[hub_a]
        b = self.hubs[hub_b]
        a.peers.append(b)
        b.peers.append(a)
        self._log(f"Connected {hub_a} ↔ {hub_b}")

        # Exchange BTC addresses
        for agent_name in a.bridge.layer.wallet.agents:
            addr = a.bridge.layer.wallet.agent_address(agent_name)
            b.bridge._peer_addresses[agent_name] = {
                "address": addr,
                "hub": hub_a,
                "network": "testnet",
            }
        for agent_name in b.bridge.layer.wallet.agents:
            addr = b.bridge.layer.wallet.agent_address(agent_name)
            a.bridge._peer_addresses[agent_name] = {
                "address": addr,
                "hub": hub_b,
                "network": "testnet",
            }

    def cross_hub_stake(self, from_hub: str, agent: str, task: str, amount: int, grade_score: float):
        """Simulate cross-hub stake + settle flow."""
        hub = self.hubs[from_hub]
        layer = hub.bridge.layer

        claim = Claim(agent=agent, task=task, domain="cross-hub")
        contract = layer.stake_claim(claim, amount_sats=amount, hub=from_hub)
        self._log(f"[{from_hub}] {agent} stakes {amount} sats on '{task}' → contract {contract.id}")

        # Simulate deposit + confirm (skip oracle in simulation)
        layer.settlement.record_deposit(contract.id, f"sim_tx_{contract.id}")
        from bitcoin.settlement import SettlementStatus
        contract.status = SettlementStatus.IN_ESCROW
        self._log(f"[{from_hub}] Deposit confirmed for {contract.id}")

        # Grade
        grade = Grade(agent=agent, domain="cross-hub", score=grade_score, task_id=task)
        hub.ledger.record(grade)
        self._log(f"[{from_hub}] Grade filed: {grade_score:.2f}")

        # Settle
        result = layer.settle_with_grade(contract.id, grade)
        outcome = "RELEASED" if result.status == SettlementStatus.RELEASED else "SLASHED"
        self._log(f"[{from_hub}] Settled: {outcome} ({result.amount_sats} sats)")
        return contract, result

    def federation_report(self):
        """Print federation-wide BTC status."""
        print("\n" + "=" * 60)
        print("FEDERATION BTC REPORT")
        print("=" * 60)
        for name, hub in self.hubs.items():
            layer = hub.bridge.layer
            report = layer.federation_report()
            stats = report.get('settlement_stats', {})
            print(f"\nHub: {name}")
            print(f"  Network:  {report['network']}")
            print(f"  Agents:   {len(report['agents'])}")
            print(f"  Contracts:{stats.get('total_contracts', 0)}")
            print(f"  Released: {stats.get('released', 0)}")
            print(f"  Slashed:  {stats.get('slashed', 0)}")
            print(f"  In escrow:{stats.get('in_escrow', 0)}")

            for agent_name in report['agents']:
                addr = layer.wallet.agent_address(agent_name)
                print(f"    {agent_name:20s} → {addr}")

        print(f"\nPeer addresses known:")
        for name, hub in self.hubs.items():
            for agent, info in hub.bridge._peer_addresses.items():
                print(f"  {name} knows {agent}@{info['hub']} → {info['address']}")


# ── Test Scenarios ────────────────────────────────────────────────────────────

def test_basic_stake_and_release():
    """Basic: stake, grade well, release."""
    fed = SimFederation(verbose=True)
    satellite = fed.add_hub("satelliteA")
    satellite.register_agent("stella")
    satellite.register_agent("braid")

    contract, result = fed.cross_hub_stake("satelliteA", "stella", "compute-hash", 50000, 0.95)
    assert result.status == SettlementStatus.RELEASED
    assert result.amount_sats == 50000
    print("\n✅ test_basic_stake_and_release PASSED")


def test_stake_and_slash():
    """Stake, fail badly, slash."""
    fed = SimFederation(verbose=True)
    hog = fed.add_hub("hog")
    hog.register_agent("heavy-lifter")

    contract, result = fed.cross_hub_stake("hog", "heavy-lifter", "bad-computation", 100000, 0.1)
    assert result.status == SettlementStatus.SLASHED
    assert result.amount_sats == 100000
    print("\n✅ test_stake_and_slash PASSED")


def test_two_hub_federation():
    """Two hubs, multiple agents, cross-hub staking."""
    fed = SimFederation(verbose=True)

    sat = fed.add_hub("satelliteA")
    hog = fed.add_hub("hog")

    # Register agents on both hubs
    sat.register_agent("stella")
    sat.register_agent("braid")
    hog.register_agent("heavy-lifter")
    hog.register_agent("data-cruncher")

    fed.connect_hubs("satelliteA", "hog")

    # Cross-hub stake from satelliteA
    fed.cross_hub_stake("satelliteA", "stella", "analyze-market", 75000, 0.88)
    fed.cross_hub_stake("satelliteA", "braid", "monitor-infra", 30000, 0.72)

    # Cross-hub stake from hog
    fed.cross_hub_stake("hog", "heavy-lifter", "train-model", 200000, 0.95)
    fed.cross_hub_stake("hog", "data-cruncher", "parse-logs", 50000, 0.3)  # gets slashed

    fed.federation_report()

    # Verify peer address exchange worked
    assert "stella" in hog.bridge._peer_addresses
    assert "heavy-lifter" in sat.bridge._peer_addresses
    print("\n✅ test_two_hub_federation PASSED")


def test_grade_threshold():
    """Test that grades right at the slash threshold behave correctly."""
    fed = SimFederation(verbose=True)
    hub = fed.add_hub("threshold-hub")
    hub.register_agent("borderline")

    # Exactly at slash threshold (0.5) — should release
    _, result = fed.cross_hub_stake("threshold-hub", "borderline", "task-ok", 10000, 0.5)
    assert result.status == SettlementStatus.RELEASED

    # Just below — should slash
    _, result = fed.cross_hub_stake("threshold-hub", "borderline", "task-bad", 10000, 0.49)
    assert result.status == SettlementStatus.SLASHED

    print("\n✅ test_grade_threshold PASSED")


def test_trust_score_integration():
    """BTC-enhanced trust scores reflect staking history."""
    fed = SimFederation(verbose=True)
    hub = fed.add_hub("trust-hub")
    hub.register_agent("reliable")
    hub.register_agent("flakey")

    # Reliable agent: high scores, multiple stakes
    fed.cross_hub_stake("trust-hub", "reliable", "task-1", 50000, 0.95)
    fed.cross_hub_stake("trust-hub", "reliable", "task-2", 50000, 0.88)
    fed.cross_hub_stake("trust-hub", "reliable", "task-3", 50000, 0.92)

    # Flakey agent: one good, one slashed
    fed.cross_hub_stake("trust-hub", "flakey", "task-a", 25000, 0.8)
    fed.cross_hub_stake("trust-hub", "flakey", "task-b", 25000, 0.2)  # slashed

    layer = hub.bridge.layer

    # Check BTC-enhanced scores
    reliable_score = layer.btc_enhanced_score("reliable", "cross-hub", hub.ledger)
    flakey_score = layer.btc_enhanced_score("flakey", "cross-hub", hub.ledger)

    print(f"\n  Reliable BTC-trust: {reliable_score}")
    print(f"  Flakey BTC-trust:   {flakey_score}")

    assert reliable_score["enhanced_score"] > flakey_score["enhanced_score"], "Reliable should have higher BTC-trust"
    print("\n✅ test_trust_score_integration PASSED")


def test_multi_contract_parallel():
    """Multiple contracts in flight simultaneously."""
    fed = SimFederation(verbose=True)
    hub = fed.add_hub("parallel-hub")
    hub.register_agent("multi-tasker")

    layer = hub.bridge.layer

    # Open 3 contracts without settling
    claims = []
    contracts = []
    for i in range(3):
        claim = Claim(agent="multi-tasker", task=f"parallel-{i}", domain="compute")
        contract = layer.stake_claim(claim, amount_sats=10000 * (i + 1), hub="parallel-hub")
        from bitcoin.settlement import SettlementStatus
        layer.settlement.record_deposit(contract.id, f"tx_{i}")
        contract.status = SettlementStatus.IN_ESCROW
        contracts.append(contract)
        claims.append(claim)

    # Settle them in different order
    grades = [0.9, 0.3, 0.7]  # middle one gets slashed
    for contract, score in zip(contracts, grades):
        grade = Grade(agent="multi-tasker", domain="compute", score=score, task_id=contract.task_id)
        result = layer.settle_with_grade(contract.id, grade)
        status = "RELEASED" if result.status == SettlementStatus.RELEASED else "SLASHED"
        fed._log(f"Contract {contract.id}: score={score} → {status}")

    report = layer.federation_report()
    stats = report['settlement_stats']
    assert stats['released'] == 2
    assert stats['slashed'] == 1
    print(f"\n✅ test_multi_contract_parallel PASSED (2 released, 1 slashed)")


# ── Run all tests ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    tests = [
        test_basic_stake_and_release,
        test_stake_and_slash,
        test_two_hub_federation,
        test_grade_threshold,
        test_trust_score_integration,
        test_multi_contract_parallel,
    ]

    print("=" * 60)
    print("MANIFOLD BTC — End-to-End Federation Tests")
    print("=" * 60)
    print()

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 60)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
