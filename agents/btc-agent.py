#!/usr/bin/env python3
"""
btc-agent.py — Unified Bitcoin agent for Manifold federation.

Combines:
- Wallet management (HD key derivation, address generation)
- Settlement (stake/slash/release)
- Oracle (price, fees, market data)
- Signals (TA analysis)
- Lightning (invoice/pay)
- Raw TX (build, sign, broadcast)
- Portfolio tracking
- Federation bridge

CLI interface follows Manifold agent convention:
    python3 btc-agent.py <command> [json_args]

Commands:
    status          — Overall BTC system status
    address         — Generate/show agent address
    balance         — Check on-chain balance
    stake           — Create a stake contract
    settle          — Settle a contract (release or slash)
    signal          — Get current BTC market signal
    portfolio       — Show portfolio summary
    sign            — Sign a message with agent key
    verify          — Verify a signed message
    fee             — Current fee estimate
    price           — Current BTC price
    backtest        — Run a strategy backtest
    utxos           — List UTXOs for address
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitcoin.agent_bitcoin import BitcoinManifoldLayer
from bitcoin.wallet import AgentWallet, FederationWallet, generate_federation_seed
from bitcoin.oracle import BitcoinOracle
from bitcoin.raw_tx import (
    privkey_from_seed, privkey_to_pubkey, pubkey_to_address,
    get_utxos, get_fee_rate, send_to_address
)
from bitcoin.portfolio import PortfolioManager, get_btc_price


# ── Config ──────────────────────────────────────────────────────────────

DATA_DIR = os.environ.get("MANIFOLD_BTC_DIR", "/tmp/manifold-btc-settlement")
SEED_FILE = os.path.join(DATA_DIR, "federation.seed")


def load_or_create_seed() -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SEED_FILE):
        with open(SEED_FILE) as f:
            return f.read().strip()
    seed = generate_federation_seed()
    with open(SEED_FILE, "w") as f:
        f.write(seed)
    return seed


def load_layer() -> BitcoinManifoldLayer:
    seed = load_or_create_seed()
    return BitcoinManifoldLayer(seed_hex=seed, network="testnet")


# ── Commands ────────────────────────────────────────────────────────────

def cmd_status(args):
    """Show overall BTC system status."""
    layer = load_layer()
    oracle = BitcoinOracle(network="testnet")

    print(f"\n{'='*55}")
    print(f"  MANIFOLD BTC AGENT STATUS")
    print(f"{'='*55}")

    # Fee
    try:
        fees = oracle.fee_estimate()
        print(f"  Fee Rate:   {fees.economy} sat/vB (economy)")
    except Exception:
        print(f"  Fee Rate:   unavailable")

    # Wallet
    agents = layer.wallet.agents
    print(f"  Agents:     {len(agents)}")
    print(f"  Network:    testnet")
    print(f"  Seed:       {load_or_create_seed()[:16]}...")
    print()

    # Agent addresses and balances
    for name in agents:
        addr = layer.wallet.agent_address(name)
        try:
            bal = oracle.address_balance(addr)
        except Exception:
            bal = 0
        print(f"  {name:20s} {addr[:32]}... {bal:>10,} sats")

    # Settlement
    stats = layer.settlement.stats()
    print(f"\n  Settlements:")
    print(f"    Total:    {stats['total']}")
    print(f"    Released: {stats['released']}")
    print(f"    Slashed:  {stats['slashed']}")
    print(f"    In escrow:{stats['in_escrow']}")
    print(f"    Staked:   {stats['total_sats_staked']:,} sats")

    # Escrow
    escrow_addr = layer.wallet.escrow_address()
    try:
        escrow_bal = oracle.address_balance(escrow_addr)
    except Exception:
        escrow_bal = 0
    print(f"\n  Escrow: {escrow_addr[:32]}... ({escrow_bal:,} sats)")

    print(f"{'='*55}")


def cmd_address(args):
    """Generate or show agent address."""
    layer = load_layer()
    name = args.agent or "default"

    if name not in layer.wallet.agents:
        layer.register_agent(name)

    addr = layer.wallet.agent_address(name)
    print(json.dumps({
        "agent": name,
        "address": addr,
        "network": "testnet",
    }))


def cmd_balance(args):
    """Check on-chain balance."""
    layer = load_layer()
    oracle = BitcoinOracle(network="testnet")
    name = args.agent or "default"

    if name not in layer.wallet.agents:
        layer.register_agent(name)

    addr = layer.wallet.agent_address(name)
    try:
        bal = oracle.address_balance(addr)
    except Exception:
        bal = 0
    price = get_btc_price()

    print(json.dumps({
        "agent": name,
        "address": addr,
        "balance_sats": bal,
        "balance_btc": bal / 1e8,
        "value_usd": bal / 1e8 * price if price else 0,
    }))


def cmd_stake(args):
    """Create a stake contract."""
    layer = load_layer()
    data = json.loads(args.json_args) if args.json_args else {}

    agent_name = data.get("agent", "default")
    task_hash = data.get("task", "default-task")
    amount = data.get("amount", 10000)

    if agent_name not in layer.wallet.agents:
        layer.register_agent(agent_name)

    contract = layer.create_stake(agent_name, task_hash, amount)
    print(json.dumps({
        "contract_id": contract.id,
        "agent": contract.agent_name,
        "task": contract.task_id,
        "amount_sats": contract.amount_sats,
        "escrow_address": contract.escrow_address,
        "status": contract.status.value,
    }))


def cmd_settle(args):
    """Settle a contract."""
    layer = load_layer()
    data = json.loads(args.json_args) if args.json_args else {}

    contract_id = data.get("contract_id")
    score = data.get("score", 0.5)

    if not contract_id:
        print("Error: contract_id required")
        sys.exit(1)

    result = layer.settle_contract(contract_id, score)
    print(json.dumps({
        "contract_id": result.contract_id,
        "status": result.status.value,
        "outcome": result.outcome,
        "amount_sats": result.amount_sats,
    }))


def cmd_signal(args):
    """Get current BTC market signal."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("btc_signals", 
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                     "agents", "btc-signals-agent.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    
    # Call cmd_signals and capture output
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    with redirect_stdout(f):
        mod.cmd_signals()
    print(f.getvalue())


def cmd_portfolio(args):
    """Show portfolio summary."""
    pm = PortfolioManager()
    pm.load()
    snap = pm.snapshot()

    print(f"Federation Value: {snap.total_federation_sats:,} sats (${snap.total_value_usd:,.2f})")
    for name, p in pm.portfolios.items():
        print(f"  {name}: {p.total_wealth_sats:,} sats ({p.reliability:.0%} reliable)")


def cmd_fee(args):
    """Current fee estimate."""
    fee = get_fee_rate("testnet")
    print(json.dumps({"fee_rate_svb": fee, "network": "testnet"}))


def cmd_price(args):
    """Current BTC price."""
    price = get_btc_price()
    print(json.dumps({"btc_usd": price}))


def cmd_utxos(args):
    """List UTXOs."""
    layer = load_layer()
    oracle = BitcoinOracle(network="testnet")
    name = args.agent or "default"
    if name not in layer.wallet.agents:
        layer.register_agent(name)
    addr = layer.wallet.agent_address(name)
    utxos = oracle.address_utxos(addr)

    result = []
    for u in utxos:
        result.append({
            "txid": u.txid,
            "vout": u.vout,
            "value_sats": u.value,
        })
    print(json.dumps(result, indent=2))


def cmd_sign(args):
    """Sign a message with agent key."""
    data = json.loads(args.json_args) if args.json_args else {}
    message = data.get("message", "")
    agent_name = data.get("agent", "default")

    seed = load_or_create_seed()
    pk = privkey_from_seed(seed, hash(agent_name) % 0xFFFFFFFF)

    # Simple HMAC-based signature
    import hmac
    sig = hmac.new(pk, message.encode(), "sha256").hexdigest()
    pubkey_hex = privkey_to_pubkey(pk).hex()

    print(json.dumps({
        "message": message,
        "signature": sig,
        "pubkey": pubkey_hex,
        "agent": agent_name,
    }))


def cmd_backtest(args):
    """Run a strategy backtest."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("btc_backtest", 
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                     "bitcoin", "btc_backtest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    data = json.loads(args.json_args) if args.json_args else {}
    strategy = data.get("strategy", "composite")
    days = data.get("days", 365)
    mod.run_backtest(days=days, strategy=strategy)


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Manifold BTC Agent")
    parser.add_argument("command", help="Command to run")
    parser.add_argument("json_args", nargs="?", default="{}")
    parser.add_argument("--agent", default=None)
    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "address": cmd_address,
        "balance": cmd_balance,
        "stake": cmd_stake,
        "settle": cmd_settle,
        "signal": cmd_signal,
        "portfolio": cmd_portfolio,
        "fee": cmd_fee,
        "price": cmd_price,
        "utxos": cmd_utxos,
        "sign": cmd_sign,
        "backtest": cmd_backtest,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        print(f"Unknown command: {args.command}")
        print(f"Available: {', '.join(commands.keys())}")
        sys.exit(1)


if __name__ == "__main__":
    main()
