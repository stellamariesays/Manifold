#!/usr/bin/env python3
"""
test_bitcoin_extended.py — Tests for Lightning, Raw TX, Portfolio, Faucet modules.

Run: python3 tests/test_bitcoin_extended.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitcoin.wallet import generate_federation_seed
from bitcoin.settlement import SettlementStatus
from bitcoin.agent_bitcoin import BitcoinManifoldLayer
from bitcoin.raw_tx import (
    privkey_from_seed, privkey_to_pubkey, pubkey_to_address,
    bech32_encode, bech32_decode, sha256, hash160, double_sha256,
    build_p2wpkh_script_pubkey,
)
from bitcoin.lightning import LightningNode, InvoiceStatus, LightningMicrosettlement
from bitcoin.portfolio import PortfolioManager, AgentPortfolio
from bitcoin.btc_faucet import BTCFaucet, FaucetState, DripRecord


passed = 0
failed = 0

def run_test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"✅ {name}")
    except Exception as e:
        failed += 1
        print(f"❌ {name}: {e}")


# ── Raw TX ──────────────────────────────────────────────────────────────

def _bech32_roundtrip():
    data = bytes(range(20))
    addr = bech32_encode("tb", 0, data)
    hrp, ver, prog = bech32_decode(addr)
    assert hrp == "tb", f"hrp={hrp}"
    assert ver == 0, f"ver={ver}"
    assert bytes(prog) == data, "data mismatch"

run_test("bech32 encode/decode roundtrip", _bech32_roundtrip)


def _key_derivation():
    seed = "ab" * 32
    pk0 = privkey_from_seed(seed, 0)
    pk1 = privkey_from_seed(seed, 1)
    assert pk0 != pk1, "different indices should differ"
    assert len(pk0) == 32

run_test("key derivation deterministic and unique", _key_derivation)


def _pubkey():
    seed = generate_federation_seed()
    pk = privkey_from_seed(seed, 0)
    pub = privkey_to_pubkey(pk)
    assert len(pub) == 33, f"got {len(pub)}"
    assert pub[0] in (2, 3)

run_test("compressed pubkey generation", _pubkey)


def _address():
    seed = generate_federation_seed()
    pk = privkey_from_seed(seed, 0)
    pub = privkey_to_pubkey(pk)
    addr = pubkey_to_address(pub, "testnet")
    assert addr.startswith("tb1"), f"got {addr}"
    hrp, ver, prog = bech32_decode(addr)
    assert hrp == "tb"
    assert ver == 0
    assert len(prog) == 20

run_test("P2WPKH address generation", _address)


def _hashing():
    assert sha256(b"") == bytes.fromhex("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert len(hash160(b"test")) == 20
    assert double_sha256(b"test") == sha256(sha256(b"test"))

run_test("hash functions", _hashing)


def _script_pubkey():
    pkh = bytes(range(20))
    spk = build_p2wpkh_script_pubkey(pkh)
    assert spk == b"\x00\x14" + pkh

run_test("P2WPKH scriptPubKey", _script_pubkey)


def _unique_addrs():
    seed = generate_federation_seed()
    addrs = set()
    for i in range(10):
        pk = privkey_from_seed(seed, i)
        pub = privkey_to_pubkey(pk)
        addrs.add(pubkey_to_address(pub, "testnet"))
    assert len(addrs) == 10

run_test("unique addresses per index", _unique_addrs)


# ── Lightning ───────────────────────────────────────────────────────────

def _ln_cln():
    node = LightningNode("cln", rest_url="http://localhost:3010", rune="test-rune")
    assert node.implementation == "cln"
    assert node.rune == "test-rune"

run_test("LightningNode CLN init", _ln_cln)


def _ln_lnd():
    node = LightningNode("lnd", rest_url="https://localhost:8080", macaroon="test-mac")
    assert node.implementation == "lnd"
    assert node.macaroon == "test-mac"

run_test("LightningNode LND init", _ln_lnd)


def _microsettlement():
    node = LightningNode("cln", rest_url="http://localhost:9999")
    ms = LightningMicrosettlement(node)
    assert ms.node is node

run_test("LightningMicrosettlement init", _microsettlement)


def _invoice_status():
    assert InvoiceStatus.PENDING == "pending"
    assert InvoiceStatus.PAID == "paid"
    assert InvoiceStatus.EXPIRED == "expired"

run_test("InvoiceStatus enum values", _invoice_status)


# ── Portfolio ───────────────────────────────────────────────────────────

def _portfolio_register():
    pm = PortfolioManager(data_dir="/tmp/test-mf-port-reg")
    pm.register_agent("test-agent", "tb1qtest", "testnet")
    assert "test-agent" in pm.portfolios
    p = pm.portfolios["test-agent"]
    assert p.agent_name == "test-agent"
    assert p.address == "tb1qtest"
    assert p.balance_sats == 0

run_test("PortfolioManager register", _portfolio_register)


def _portfolio_save_load():
    d = "/tmp/test-mf-port-sl"
    pm = PortfolioManager(data_dir=d)
    pm.register_agent("a", "tb1qa", "testnet")
    pm.portfolios["a"].total_staked = 50000
    pm.portfolios["a"].total_released = 40000
    pm.portfolios["a"].total_slashed = 10000
    pm.save()

    pm2 = PortfolioManager(data_dir=d)
    pm2.load()
    assert pm2.portfolios["a"].total_staked == 50000

run_test("PortfolioManager save/load", _portfolio_save_load)


def _portfolio_leaderboard():
    pm = PortfolioManager(data_dir="/tmp/test-mf-port-lb")
    pm.register_agent("poor", "tb1qp", "testnet")
    pm.register_agent("rich", "tb1qr", "testnet")
    pm.portfolios["rich"].balance_sats = 100000
    pm.portfolios["poor"].balance_sats = 1000
    board = pm.leaderboard()
    assert board[0].agent_name == "rich"
    assert board[1].agent_name == "poor"

run_test("PortfolioManager leaderboard", _portfolio_leaderboard)


def _portfolio_props():
    p = AgentPortfolio("test", "tb1q", "testnet")
    p.total_staked = 100000
    p.total_slashed = 20000
    p.total_released = 80000
    p.balance_sats = 50000
    p.active_escrow = 10000
    p.contracts_completed = 5
    p.slash_rate = 20000 / 100000
    assert p.net_stake_pnl_sats == 60000
    assert p.total_wealth_sats == 60000
    assert abs(p.reliability - 0.8) < 0.01

run_test("AgentPortfolio properties", _portfolio_props)


# ── Faucet ──────────────────────────────────────────────────────────────

def _faucet_state():
    p = "/tmp/test-mf-fs.json"
    state = FaucetState(path=p)
    state.drips.append(DripRecord("agent-1", "tb1qagent1", 5000, time.time()))
    state.save()
    state2 = FaucetState(path=p)
    assert len(state2.drips) == 1
    assert state2.drips[0].agent_name == "agent-1"
    assert state2.drips[0].amount_sats == 5000

run_test("FaucetState save/load", _faucet_state)


def _faucet_cooldown():
    p = "/tmp/test-mf-fc.json"
    state = FaucetState(path=p)
    assert state.can_drip("new-agent")
    state.drips.append(DripRecord("existing", "tb1q", 5000, time.time()))
    assert not state.can_drip("existing")

run_test("FaucetState cooldown", _faucet_cooldown)


def _faucet_totals():
    p = "/tmp/test-mf-ft.json"
    state = FaucetState(path=p)
    state.drips = [
        DripRecord("a", "tb1q", 5000, 1.0),
        DripRecord("a", "tb1q", 5000, 2.0),
        DripRecord("b", "tb1q", 10000, 3.0),
    ]
    assert state.total_dripped("a") == 10000
    assert state.total_dripped("b") == 10000
    assert state.total_dripped_all() == 20000

run_test("FaucetState totals", _faucet_totals)


def _faucet_init():
    faucet = BTCFaucet(seed_hex="ab" * 32)
    assert faucet.faucet_address.startswith("tb1")
    status = faucet.status()
    assert "balance_sats" in status

run_test("BTCFaucet init", _faucet_init)


# ── Integration ─────────────────────────────────────────────────────────

def _full_stack():
    seed = generate_federation_seed()
    layer = BitcoinManifoldLayer(seed_hex=seed, network="testnet")
    layer.register_agent("alice")
    layer.register_agent("bob")

    a = layer.wallet.agent_address("alice")
    b = layer.wallet.agent_address("bob")
    assert a.startswith("tb1")
    assert b.startswith("tb1")
    assert a != b

    from bitcoin.agent_bitcoin import Claim
    claim = Claim(agent="alice", task="task-1", stake=50000, domain="default")
    contract = layer.stake_claim(claim, 50000)
    assert contract.status == SettlementStatus.PENDING
    assert contract.amount_sats == 50000

    from bitcoin.agent_bitcoin import Claim, Grade
    layer.settlement.record_deposit(contract.id, "sim_tx_1")
    layer.settlement.confirm_deposit(contract.id)
    result = layer.settle_with_grade(contract.id, Grade(score=0.9, agent="alice", task="task-1", domain="default"))
    assert result.outcome == "released"

    score = layer.btc_enhanced_score("alice", "default", layer.ledger)
    assert score["enhanced_score"] > 0
    assert score["total_sats_staked"] == 50000

run_test("Full stack: wallet → settlement → score", _full_stack)


# ── Summary ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print(f"Extended: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'='*55}")

    if failed > 0:
        sys.exit(1)
