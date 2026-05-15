#!/usr/bin/env python3
"""btc-settlement-agent — Bitcoin-backed trust settlement for Manifold federation.

Manages escrow contracts, stake verification, and settlement.
Integrates the Bitcoin layer with the Manifold trust system.

Commands:
  status              — agent status and federation BTC report
  ping                — health check
  register            — register an agent wallet
  stake               — create escrow contract for a claim
  deposit             — record deposit txid
  confirm             — oracle-confirm a deposit on chain
  settle              — settle contract with grade
  agent-address       — get BTC address for an agent
  agent-score         — BTC-enhanced trust score
  contracts           — list contracts (active or for agent)
  federation-report   — full federation BTC overview
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitcoin.agent_bitcoin import BitcoinManifoldLayer, quickstart
from bitcoin.wallet import generate_federation_seed
from bitcoin.settlement import SettlementStatus
from manifold.trust import TrustLedger, Grade


# ── Persistence ───────────────────────────────────────────────────────────────

_DATA_DIR = os.environ.get("BTC_SETTLEMENT_DATA", "/tmp/manifold-btc-settlement")
_SEED_FILE = os.path.join(_DATA_DIR, "federation.seed")
_LEDGER_FILE = os.path.join(_DATA_DIR, "ledger.json")


def _ensure_data_dir():
    os.makedirs(_DATA_DIR, exist_ok=True)


def _load_or_create_seed() -> str:
    """Load federation seed, or create if first run."""
    _ensure_data_dir()
    if os.path.exists(_SEED_FILE):
        with open(_SEED_FILE, "r") as f:
            return f.read().strip()
    else:
        seed = generate_federation_seed()
        with open(_SEED_FILE, "w") as f:
            f.write(seed)
        return seed


def _load_layer() -> BitcoinManifoldLayer:
    """Create layer from persisted seed."""
    seed = _load_or_create_seed()
    return BitcoinManifoldLayer(seed_hex=seed, network="testnet")


# Lazy singleton
_layer = None
_ledger = None


def _get_layer() -> BitcoinManifoldLayer:
    global _layer
    if _layer is None:
        _layer = _load_layer()
    return _layer


def _get_ledger() -> TrustLedger:
    global _ledger
    if _ledger is None:
        _ledger = TrustLedger()
    return _ledger


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_status():
    layer = _get_layer()
    return {
        "agent": "btc-settlement",
        "status": "ok",
        "capabilities": [
            "agent-registration", "btc-enhanced-scoring",
            "deposit-verification", "escrow-management",
            "federation-report", "on-chain-verification",
            "settlement-engine", "slash-execution",
            "stake-creation", "trust-integration",
        ],
        "network": layer.network,
        "agents_registered": len(layer.wallet.agents),
        "contracts_total": len(layer.settlement._contracts),
    }


def cmd_ping():
    return {"agent": "btc-settlement", "pong": True}


def cmd_register(args: dict):
    """Register an agent. args: {"agent_name": "stella"}"""
    name = args.get("agent_name", "")
    if not name:
        return {"error": "provide agent_name"}
    wallet = _get_layer().register_agent(name)
    return {
        "agent": name,
        "address": wallet.address,
        "network": wallet.network,
        "registered": True,
    }


def cmd_stake(args: dict):
    """Create escrow. args: {"agent_name", "task_id", "amount_sats", "hub?"}"""
    layer = _get_layer()
    agent = args.get("agent_name", "")
    task = args.get("task_id", "")
    amount = args.get("amount_sats", 0)
    hub = args.get("hub", "")

    if not agent or not task or not amount:
        return {"error": "provide agent_name, task_id, amount_sats"}

    from manifold.trust import Claim
    claim = Claim(agent=agent, task=task, domain="btc-settlement")

    try:
        contract = layer.stake_claim(claim, amount_sats=int(amount), hub=hub)
        return {
            "contract_id": contract.id,
            "status": contract.status.value,
            "agent": agent,
            "amount_sats": contract.amount_sats,
            "escrow_address": contract.escrow_address,
            "deposit_deadline": contract.deposit_deadline,
            "message": f"Send {amount} sats to {contract.escrow_address}",
        }
    except Exception as e:
        return {"error": str(e)}


def cmd_deposit(args: dict):
    """Record deposit. args: {"contract_id", "txid"}"""
    cid = args.get("contract_id", "")
    txid = args.get("txid", "")
    if not cid or not txid:
        return {"error": "provide contract_id and txid"}
    try:
        contract = _get_layer().deposit_stake(cid, txid)
        return {"contract_id": cid, "status": contract.status.value, "txid": txid}
    except Exception as e:
        return {"error": str(e)}


def cmd_confirm(args: dict):
    """Confirm deposit on chain. args: {"contract_id", "min_confirmations?"}"""
    cid = args.get("contract_id", "")
    min_conf = args.get("min_confirmations", 1)
    if not cid:
        return {"error": "provide contract_id"}
    try:
        contract = _get_layer().confirm_stake(cid, min_confirmations=min_conf)
        return {"contract_id": cid, "status": contract.status.value}
    except Exception as e:
        return {"error": str(e)}


def cmd_settle(args: dict):
    """Settle contract. args: {"contract_id", "score"}"""
    cid = args.get("contract_id", "")
    score = args.get("score", -1)
    if not cid or score < 0:
        return {"error": "provide contract_id and score (0.0-1.0)"}

    layer = _get_layer()
    ledger = _get_ledger()

    contract = layer.settlement.get_contract(cid)
    grade = Grade(
        agent=contract.agent_name,
        domain="btc-settlement",
        score=float(score),
        task_id=contract.task_id,
    )
    ledger.record(grade)

    try:
        result = layer.settle_with_grade(cid, grade)
        return {
            "contract_id": cid,
            "status": result.status.value,
            "score": score,
            "settlement_address": result.settlement_address,
            "amount_sats": result.amount_sats,
            "action": "released" if result.status == SettlementStatus.RELEASED else "slashed",
        }
    except Exception as e:
        return {"error": str(e)}


def cmd_agent_address(args: dict):
    """Get BTC address. args: {"agent_name"}"""
    name = args.get("agent_name", "")
    if not name:
        return {"error": "provide agent_name"}
    return {"agent": name, "address": _get_layer().agent_address(name)}


def cmd_agent_score(args: dict):
    """BTC-enhanced trust score. args: {"agent_name", "domain"}"""
    name = args.get("agent_name", "")
    domain = args.get("domain", "general")
    if not name:
        return {"error": "provide agent_name"}
    return _get_layer().btc_enhanced_score(name, domain, _get_ledger())


def cmd_contracts(args: dict = None):
    """List contracts. args: {"agent_name?" (optional filter)}"""
    layer = _get_layer()
    args = args or {}
    agent = args.get("agent_name")

    if agent:
        contracts = layer.settlement.contracts_for_agent(agent)
    else:
        contracts = layer.settlement.active_contracts()

    return {
        "count": len(contracts),
        "contracts": [
            {
                "id": c.id,
                "agent": c.agent_name,
                "task": c.task_id,
                "amount_sats": c.amount_sats,
                "status": c.status.value,
            }
            for c in contracts
        ],
    }


def cmd_federation_report():
    """Full federation BTC report."""
    return _get_layer().federation_report()


# ── Main ──────────────────────────────────────────────────────────────────────

COMMANDS = {
    "status": lambda args=None: cmd_status(),
    "ping": lambda args=None: cmd_ping(),
    "register": lambda args: cmd_register(args),
    "stake": lambda args: cmd_stake(args),
    "deposit": lambda args: cmd_deposit(args),
    "confirm": lambda args: cmd_confirm(args),
    "settle": lambda args: cmd_settle(args),
    "agent-address": lambda args: cmd_agent_address(args),
    "agent-score": lambda args: cmd_agent_score(args),
    "contracts": lambda args=None: cmd_contracts(args),
    "federation-report": lambda args=None: cmd_federation_report(),
}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    args = {}
    if len(sys.argv) > 2:
        try:
            args = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            args = {}

    if cmd in COMMANDS:
        result = COMMANDS[cmd](args)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"agent": "btc-settlement", "error": f"unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
