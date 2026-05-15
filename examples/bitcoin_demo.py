#!/usr/bin/env python3
"""
Manifold Bitcoin Demo — shows the full flow.

1. Create a federation with agents
2. Agents register Bitcoin wallets
3. Agent stakes BTC on a claim
4. Task completes, grade filed
5. Settlement: BTC released or burned

This runs locally with no real Bitcoin transactions (testnet simulation).
For real testnet: send actual testnet BTC to the agent addresses.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitcoin.agent_bitcoin import BitcoinManifoldLayer, quickstart
from bitcoin.wallet import generate_federation_seed, burn_address
from bitcoin.settlement import SettlementStatus
from core.trust import Claim, Grade, TrustLedger


def main():
    print("=" * 60)
    print("  MANIFOLD × BITCOIN — Agent Trust Settlement Demo")
    print("=" * 60)
    print()

    # ─── 1. Federation setup ─────────────────────────────────────────────
    seed = generate_federation_seed()
    print(f"Federation seed: {seed[:16]}...")
    print(f"⚠️  In production, this seed controls all agent funds")
    print()

    layer = BitcoinManifoldLayer(seed_hex=seed, network="testnet")
    print(f"Layer: {layer}")
    print()

    # ─── 2. Register agents ──────────────────────────────────────────────
    agents = ["stella", "braid", "cron-monitor", "infra"]
    print("Registering agents:")
    for name in agents:
        wallet = layer.register_agent(name)
        print(f"  {name:20s} → {wallet.address}")
    print()

    # Escrow address (where stakes go)
    escrow = layer.agent_address("escrow")
    print(f"Escrow address: {escrow}")
    print(f"Burn address:   {burn_address('testnet')}")
    print()

    # ─── 3. Create a trust ledger ────────────────────────────────────────
    ledger = TrustLedger()

    # ─── 4. Agent makes a claim with BTC stake ──────────────────────────
    claim = Claim(
        agent="braid",
        task="analyze-solar-topology",
        domain="solar",
    )
    print(f"Claim: {claim}")

    # Stake 50,000 sats (≈ $0.05 at current prices, real skin in the game)
    contract = layer.stake_claim(claim, amount_sats=50000, hub="satelliteA")
    print(f"Contract: {contract.id}")
    print(f"  Status: {contract.status.value}")
    print(f"  Amount: {contract.amount_sats:,} sats")
    print(f"  Escrow: {contract.escrow_address}")
    print()

    # ─── 5. Simulate deposit ─────────────────────────────────────────────
    print("Agent sends 50,000 sats to escrow...")
    contract = layer.deposit_stake(contract.id, "fake-txid-for-demo")
    print(f"  Status: {contract.status.value}")

    # Skip oracle confirmation (no real network in demo)
    contract.status = SettlementStatus.IN_ESCROW
    print(f"  Status: IN_ESCROW (confirmed on chain)")
    print()

    # ─── 6. Task completes — success ────────────────────────────────────
    print("Task completed! Filing grade: 0.92 (excellent)")
    grade = Grade(
        agent="braid",
        domain="solar",
        score=0.92,
        task_id="analyze-solar-topology",
    )
    ledger.record(grade)

    contract = layer.settle_with_grade(contract.id, grade)
    print(f"  Settlement: {contract.status.value}")
    print(f"  Sats returned to braid at: {contract.settlement_address}")
    print()

    # ─── 7. Now let's see a failure ─────────────────────────────────────
    print("--- Slash scenario ---")
    claim2 = Claim(
        agent="cron-monitor",
        task="watch-prices",
        domain="monitoring",
    )
    contract2 = layer.stake_claim(claim2, amount_sats=25000, hub="hog")
    layer.deposit_stake(contract2.id, "fake-txid-2")
    contract2.status = SettlementStatus.IN_ESCROW

    print(f"Task failed. Filing grade: 0.1 (slash)")
    grade2 = Grade(agent="cron-monitor", domain="monitoring", score=0.1, task_id="watch-prices")
    ledger.record(grade2)

    contract2 = layer.settle_with_grade(contract2.id, grade2)
    print(f"  Settlement: {contract2.status.value}")
    print(f"  Sats burned at: {contract2.settlement_address}")
    print()

    # ─── 8. Enhanced trust scores ────────────────────────────────────────
    print("--- BTC-enhanced trust scores ---")
    for agent in ["braid", "cron-monitor"]:
        score = layer.btc_enhanced_score(agent, "solar" if agent == "braid" else "monitoring", ledger)
        print(f"  {score['agent']}:")
        print(f"    Traditional: {score['traditional_score']}")
        print(f"    Enhanced:    {score['enhanced_score']}")
        print(f"    Staked:      {score['total_sats_staked']:,} sats")
        print(f"    Slashed:     {score['total_sats_slashed']:,} sats")
    print()

    # ─── 9. Federation report ────────────────────────────────────────────
    report = layer.federation_report()
    print("--- Federation report ---")
    print(f"  Network:    {report['network']}")
    print(f"  Agents:     {report['registered_agents']}")
    print(f"  Contracts:  {report['settlement_stats']['total']}")
    print(f"  Released:   {report['settlement_stats']['released']}")
    print(f"  Slashed:    {report['settlement_stats']['slashed']}")
    print(f"  In escrow:  {report['settlement_stats']['in_escrow']}")
    print()

    layer.close()
    print("Done. Manifold now has real Bitcoin behind its trust layer.")
    print("Next step: deploy on testnet, get real tBTC, run agents.")


if __name__ == "__main__":
    main()
