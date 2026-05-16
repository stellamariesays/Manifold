#!/usr/bin/env python3
"""btc-federation-bridge — Connects Bitcoin settlement to the Manifold federation wire protocol.

Runs as a persistent service that:
1. Listens for federation messages about Bitcoin settlement
2. Handles btc_stake_request, btc_settlement_request from peers
3. Broadcasts btc_stake_confirmed, btc_settlement_result to peers
4. Syncs agent BTC addresses across the federation

Usage:
    python3 btc-federation-bridge.py [--ws-url ws://localhost:8768] [--seed HEX]
"""

import asyncio
import json
import os
import sys
import time
import signal
import hashlib
import logging
from typing import Optional

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import websockets
except ImportError:
    print("ERROR: websockets required. pip install websockets")
    sys.exit(1)

from bitcoin.agent_bitcoin import BitcoinManifoldLayer
from bitcoin.wallet import generate_federation_seed
from bitcoin.settlement import SettlementStatus
from core.trust import TrustLedger, Grade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("btc-bridge")

# ── Config ────────────────────────────────────────────────────────────────────

WS_URL = os.environ.get("MANIFOLD_WS_URL", "ws://localhost:8768")
SEED_FILE = os.environ.get("BTC_SEED_FILE", "/tmp/manifold-btc-federation/seed")
DATA_DIR = os.environ.get("BTC_DATA_DIR", "/tmp/manifold-btc-federation")
NETWORK = os.environ.get("BTC_NETWORK", "testnet")
HUB_NAME = os.environ.get("MANIFOLD_HUB", "satelliteA")


# ── State ─────────────────────────────────────────────────────────────────────

class BtcFederationBridge:
    """Bridges Bitcoin settlement to the federation wire protocol."""

    def __init__(self, ws_url: str, seed_hex: str, network: str = "testnet", hub: str = "satelliteA"):
        self.ws_url = ws_url
        self.hub = hub
        self.network = network
        self.layer = BitcoinManifoldLayer(seed_hex=seed_hex, network=network)
        self.ledger = TrustLedger()
        self.ws: Optional[object] = None
        self._running = False
        self._peer_addresses: dict[str, dict] = {}  # agent -> {address, hub, network}

    # ── Connection ──────────────────────────────────────────────────────

    async def connect(self):
        """Connect to the federation WebSocket."""
        log.info(f"Connecting to {self.ws_url}")
        try:
            self.ws = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10,
            )
            log.info("Connected to federation")
            return True
        except Exception as e:
            log.error(f"Connection failed: {e}")
            return False

    async def send_message(self, msg: dict):
        """Send a federation message."""
        if self.ws and self.ws.open:
            raw = json.dumps(msg)
            await self.ws.send(raw)
            log.debug(f"Sent: {msg.get('type', '?')}")
        else:
            log.warning("Not connected, can't send")

    # ── Message Handlers ────────────────────────────────────────────────

    async def handle_message(self, raw: str):
        """Route incoming federation message."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(f"Invalid JSON: {raw[:100]}")
            return

        msg_type = msg.get("type", "")
        payload = msg.get("payload", {})

        handlers = {
            "btc_address_announce": self._handle_address_announce,
            "btc_stake_request": self._handle_stake_request,
            "btc_stake_confirmed": self._handle_stake_confirmed,
            "btc_settlement_request": self._handle_settlement_request,
            "btc_settlement_result": self._handle_settlement_result,
            "task_request": self._handle_task_request,
            "task_result": self._handle_task_result,
            "peer_announce": self._handle_peer_announce,
        }

        handler = handlers.get(msg_type)
        if handler:
            await handler(payload, msg)
        else:
            log.debug(f"Ignored: {msg_type}")

    async def _handle_peer_announce(self, payload: dict, msg: dict):
        """When a peer announces, send our BTC addresses."""
        peer_hub = payload.get("hub", "")
        log.info(f"Peer announced: {peer_hub}")

        # Announce all our agent addresses to the new peer
        for agent_name, wallet in self.layer.wallet.agents.items():
            await self.send_message({
                "type": "btc_address_announce",
                "payload": {
                    "agentName": agent_name,
                    "address": wallet.address,
                    "network": self.network,
                    "hub": self.hub,
                },
                "timestamp": _iso_now(),
                "sender": f"btc-bridge@{self.hub}",
            })

    async def _handle_address_announce(self, payload: dict, msg: dict):
        """Record a peer's agent BTC address."""
        agent = payload.get("agentName", "")
        address = payload.get("address", "")
        hub = payload.get("hub", "")

        if agent and address:
            self._peer_addresses[agent] = {
                "address": address,
                "hub": hub,
                "network": payload.get("network", "testnet"),
            }
            log.info(f"Peer BTC address: {agent}@{hub} → {address}")

    async def _handle_stake_request(self, payload: dict, msg: dict):
        """Peer is requesting we create an escrow contract."""
        agent = payload.get("agentName", "")
        task = payload.get("taskId", "")
        amount = payload.get("amountSats", 0)

        if not agent or not task or not amount:
            await self.send_message({
                "type": "error",
                "payload": {"error": "missing fields in btc_stake_request"},
            })
            return

        log.info(f"Stake request: {agent} stakes {amount} sats on {task}")

        # Register agent if new
        if agent not in self.layer.wallet.agents:
            self.layer.register_agent(agent)

        from core.trust import Claim
        claim = Claim(agent=agent, task=task, domain="btc-settlement")
        contract = self.layer.stake_claim(claim, amount_sats=int(amount), hub=self.hub)

        # Respond with escrow details
        await self.send_message({
            "type": "btc_stake_confirmed",
            "payload": {
                "contractId": contract.id,
                "txid": "",
                "confirmations": 0,
                "receivedSats": 0,
                "confirmedBy": self.hub,
            },
            "timestamp": _iso_now(),
            "sender": f"btc-bridge@{self.hub}",
            "requestId": msg.get("requestId"),
        })

        # Also broadcast the stake request so the agent knows where to send
        log.info(f"Escrow contract {contract.id}: send {amount} sats to {contract.escrow_address}")

    async def _handle_stake_confirmed(self, payload: dict, msg: dict):
        """Peer confirmed a stake deposit on chain."""
        cid = payload.get("contractId", "")
        txid = payload.get("txid", "")

        if cid and txid:
            try:
                self.layer.deposit_stake(cid, txid)
                log.info(f"Stake confirmed: {cid} via {txid}")
            except Exception as e:
                log.warning(f"Stake confirm failed for {cid}: {e}")

    async def _handle_settlement_request(self, payload: dict, msg: dict):
        """Peer requests settlement of a contract."""
        cid = payload.get("contractId", "")
        score = payload.get("score", -1.0)

        if not cid or score < 0:
            await self.send_message({
                "type": "error",
                "payload": {"error": "missing contractId or score"},
            })
            return

        log.info(f"Settlement request: contract {cid}, score {score}")

        try:
            contract = self.layer.settlement.get_contract(cid)
            grade = Grade(
                agent=contract.agent_name,
                domain="btc-settlement",
                score=float(score),
                task_id=contract.task_id,
            )
            self.ledger.record(grade)

            result = self.layer.settle_with_grade(cid, grade)

            outcome = "released" if result.status == SettlementStatus.RELEASED else "slashed"

            await self.send_message({
                "type": "btc_settlement_result",
                "payload": {
                    "contractId": cid,
                    "outcome": outcome,
                    "amountSats": result.amount_sats,
                    "settlementAddress": result.settlement_address,
                    "settledBy": self.hub,
                    "settledAt": _iso_now(),
                },
                "timestamp": _iso_now(),
                "sender": f"btc-bridge@{self.hub}",
                "requestId": msg.get("requestId"),
            })

            log.info(f"Settled {cid}: {outcome} ({result.amount_sats} sats)")

        except Exception as e:
            log.error(f"Settlement failed for {cid}: {e}")
            await self.send_message({
                "type": "error",
                "payload": {"error": str(e), "contractId": cid},
            })

    async def _handle_settlement_result(self, payload: dict, msg: dict):
        """Record settlement result from a peer."""
        cid = payload.get("contractId", "")
        outcome = payload.get("outcome", "")
        amount = payload.get("amountSats", 0)
        log.info(f"Settlement result: {cid} → {outcome} ({amount} sats)")

    async def _handle_task_request(self, payload: dict, msg: dict):
        """Intercept task requests to offer BTC staking."""
        task = payload.get("task", "")
        domain = payload.get("domain", "")
        log.debug(f"Task request: {task} ({domain})")

    async def _handle_task_result(self, payload: dict, msg: dict):
        """Intercept task results for auto-grading."""
        log.debug(f"Task result received")

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def announce_addresses(self):
        """Broadcast all agent BTC addresses to the federation."""
        for agent_name, wallet in self.layer.wallet.agents.items():
            await self.send_message({
                "type": "btc_address_announce",
                "payload": {
                    "agentName": agent_name,
                    "address": wallet.address,
                    "network": self.network,
                    "hub": self.hub,
                },
                "timestamp": _iso_now(),
                "sender": f"btc-bridge@{self.hub}",
            })
        log.info(f"Announced {len(self.layer.wallet.agents)} agent addresses")

    async def run(self):
        """Main loop: connect, listen, handle."""
        self._running = True

        while self._running:
            try:
                if not await self.connect():
                    await asyncio.sleep(5)
                    continue

                await self.announce_addresses()
                log.info("Listening for federation messages...")

                async for raw in self.ws:
                    await self.handle_message(raw)

            except websockets.ConnectionClosed:
                log.warning("Connection closed, reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                log.error(f"Error: {e}")
                await asyncio.sleep(5)

    def stop(self):
        self._running = False


def _iso_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manifold BTC Federation Bridge")
    parser.add_argument("--ws-url", default=WS_URL, help="Federation WebSocket URL")
    parser.add_argument("--seed", default=None, help="Federation seed hex")
    parser.add_argument("--network", default=NETWORK, help="Bitcoin network")
    parser.add_argument("--hub", default=HUB_NAME, help="Hub name")
    args = parser.parse_args()

    # Load or create seed
    os.makedirs(DATA_DIR, exist_ok=True)
    seed_file = os.path.join(DATA_DIR, "seed")
    if os.path.exists(seed_file):
        with open(seed_file) as f:
            seed = f.read().strip()
    else:
        seed = args.seed or generate_federation_seed()
        with open(seed_file, "w") as f:
            f.write(seed)
        log.info(f"New federation seed created: {seed[:16]}...")

    bridge = BtcFederationBridge(
        ws_url=args.ws_url,
        seed_hex=seed,
        network=args.network,
        hub=args.hub,
    )

    loop = asyncio.new_event_loop()

    def _shutdown():
        log.info("Shutting down...")
        bridge.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    log.info(f"Starting BTC Federation Bridge: hub={args.hub} network={args.network} ws={args.ws_url}")
    loop.run_until_complete(bridge.run())


if __name__ == "__main__":
    main()
