#!/usr/bin/env python3
"""lightning.py — Lightning Network integration for Manifold agents.

Provides:
- Invoice generation (LUD-01, LUD-21 BOLT11/BOLT12)
- Payment verification via LN node or LNURL
- Lightning-based microsettlements for fast trust claims

This module is designed to work with:
- Core Lightning (CLN) via REST proxy
- LND via REST API
- Or LNURL/pay endpoints for custodial setups

Usage:
    from bitcoin.lightning import LightningNode, InvoiceStatus

    node = LightningNode("cln", rest_url="http://localhost:3010")
    inv = node.create_invoice(amount_sats=1000, description="Manifold stake")
    status = node.check_invoice(inv.payment_hash)
"""

import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


# ── Data structures ──────────────────────────────────────────────────────────

class InvoiceStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass
class LightningInvoice:
    payment_hash: str
    payment_request: str  # BOLT11 invoice string
    amount_msat: int
    description: str
    created_at: int  # unix timestamp
    expires_at: int  # unix timestamp
    status: InvoiceStatus = InvoiceStatus.PENDING
    settled_at: Optional[int] = None
    preimage: Optional[str] = None


@dataclass
class PaymentResult:
    payment_hash: str
    preimage: str
    amount_msat: int
    fee_msat: int
    status: str  # "succeeded", "pending", "failed"


@dataclass
class NodeInfo:
    node_id: str
    alias: str
    color: str
    num_peers: int
    num_active_channels: int
    num_pending_channels: int
    block_height: int
    network: str


# ── Lightning Node Interface ─────────────────────────────────────────────────

class LightningNode:
    """
    Lightning node interface. Supports CLN and LND via REST API.

    CLN config:
        rest_url = "http://localhost:3010"
        rune = "<cln-rune-token>"

    LND config:
        rest_url = "https://localhost:8080"
        macaroon = "<hex-encoded-admin-macaroon>"
    """

    def __init__(
        self,
        implementation: str = "cln",  # "cln" or "lnd"
        rest_url: str = "http://localhost:3010",
        rune: Optional[str] = None,
        macaroon: Optional[str] = None,
        cert_path: Optional[str] = None,
        timeout: int = 10,
    ):
        self.implementation = implementation.lower()
        self.rest_url = rest_url.rstrip("/")
        self.rune = rune or os.environ.get("CLN_RUNE", "")
        self.macaroon = macaroon or os.environ.get("LND_MACAROON", "")
        self.cert_path = cert_path
        self.timeout = timeout

    # ─── REST helpers ──────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict = None) -> dict:
        """Make an authenticated REST request to the Lightning node."""
        url = f"{self.rest_url}{path}"
        headers = {"Content-Type": "application/json"}

        if self.implementation == "cln" and self.rune:
            headers["Authorization"] = f"Bearer {self.rune}"
        elif self.implementation == "lnd" and self.macaroon:
            headers["Grpc-Metadata-macaroon"] = self.macaroon

        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        ctx = None
        if self.implementation == "lnd" and not self.cert_path:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = 0  # CERT_NONE

        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"Lightning API error {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Lightning node unreachable: {e.reason}")

    # ─── Node Info ─────────────────────────────────────────────────────

    def get_info(self) -> NodeInfo:
        """Get node information."""
        if self.implementation == "cln":
            data = self._request("GET", "/v1/getinfo")
            return NodeInfo(
                node_id=data.get("id", ""),
                alias=data.get("alias", ""),
                color=data.get("color", ""),
                num_peers=data.get("num_peers", 0),
                num_active_channels=data.get("num_active_channels", 0),
                num_pending_channels=data.get("num_pending_channels", 0),
                block_height=data.get("blockheight", 0),
                network=data.get("network", "testnet"),
            )
        elif self.implementation == "lnd":
            data = self._request("GET", "/v1/getinfo")
            return NodeInfo(
                node_id=data.get("identity_pubkey", ""),
                alias=data.get("alias", ""),
                color=data.get("color", ""),
                num_peers=data.get("num_peers", 0),
                num_active_channels=data.get("num_active_channels", 0),
                num_pending_channels=data.get("num_pending_channels", 0),
                block_height=data.get("block_height", 0),
                network=data.get("chains", ["bitcoin"])[0] if data.get("chains") else "bitcoin",
            )
        else:
            raise ValueError(f"Unknown implementation: {self.implementation}")

    # ─── Invoices ──────────────────────────────────────────────────────

    def create_invoice(
        self,
        amount_sats: int,
        description: str = "",
        expiry_seconds: int = 3600,
        label: Optional[str] = None,
    ) -> LightningInvoice:
        """Create a Lightning invoice."""
        amount_msat = amount_sats * 1000

        if self.implementation == "cln":
            label = label or f"manifold-{int(time.time())}"
            body = {
                "amount_msat": amount_msat,
                "label": label,
                "description": description,
                "expiry": expiry_seconds,
            }
            data = self._request("POST", "/v1/invoice", body)
            return LightningInvoice(
                payment_hash=data.get("payment_hash", ""),
                payment_request=data.get("bolt11", ""),
                amount_msat=amount_msat,
                description=description,
                created_at=int(time.time()),
                expires_at=int(time.time()) + expiry_seconds,
            )

        elif self.implementation == "lnd":
            body = {
                "value": amount_sats,
                "memo": description,
                "expiry": expiry_seconds,
            }
            data = self._request("POST", "/v1/invoices", body)
            return LightningInvoice(
                payment_hash=data.get("r_hash", ""),
                payment_request=data.get("payment_request", ""),
                amount_msat=amount_msat,
                description=description,
                created_at=int(time.time()),
                expires_at=int(time.time()) + expiry_seconds,
            )
        else:
            raise ValueError(f"Unknown implementation: {self.implementation}")

    def check_invoice(self, payment_hash: str) -> LightningInvoice:
        """Check the status of an invoice."""
        if self.implementation == "cln":
            data = self._request("GET", f"/v1/invoice/{payment_hash}")
            status = InvoiceStatus.PAID if data.get("status") == "paid" else InvoiceStatus.PENDING
            if data.get("status") == "expired":
                status = InvoiceStatus.EXPIRED

            return LightningInvoice(
                payment_hash=data.get("payment_hash", payment_hash),
                payment_request=data.get("bolt11", ""),
                amount_msat=data.get("amount_msat", 0),
                description=data.get("description", ""),
                created_at=data.get("created_at", 0),
                expires_at=data.get("expires_at", 0),
                status=status,
                settled_at=data.get("paid_at") if status == InvoiceStatus.PAID else None,
                preimage=data.get("payment_preimage") if status == InvoiceStatus.PAID else None,
            )

        elif self.implementation == "lnd":
            import base64
            # LND expects base64url-encoded payment hash
            encoded = base64.urlsafe_b64encode(bytes.fromhex(payment_hash)).decode().rstrip("=")
            data = self._request("GET", f"/v1/invoice/{encoded}")

            state = data.get("state", "")
            if state == "SETTLED":
                status = InvoiceStatus.PAID
            elif state == "CANCELED":
                status = InvoiceStatus.EXPIRED
            else:
                status = InvoiceStatus.PENDING

            return LightningInvoice(
                payment_hash=payment_hash,
                payment_request=data.get("payment_request", ""),
                amount_msat=int(data.get("value", 0)) * 1000,
                description=data.get("memo", ""),
                created_at=int(data.get("creation_date", 0)),
                expires_at=int(data.get("creation_date", 0)) + int(data.get("expiry", 3600)),
                status=status,
                settled_at=int(data.get("settle_date", 0)) if status == InvoiceStatus.PAID else None,
                preimage=data.get("r_preimage"),
            )
        else:
            raise ValueError(f"Unknown implementation: {self.implementation}")

    def list_invoices(self, pending_only: bool = False) -> list[LightningInvoice]:
        """List invoices."""
        if self.implementation == "cln":
            path = "/v1/invoices?status=unpaid" if pending_only else "/v1/invoices"
            data = self._request("GET", path)
            invoices = []
            for inv in data if isinstance(data, list) else data.get("invoices", []):
                status = InvoiceStatus.PAID if inv.get("status") == "paid" else InvoiceStatus.PENDING
                invoices.append(LightningInvoice(
                    payment_hash=inv.get("payment_hash", ""),
                    payment_request=inv.get("bolt11", ""),
                    amount_msat=inv.get("amount_msat", 0),
                    description=inv.get("description", ""),
                    created_at=inv.get("created_at", 0),
                    expires_at=inv.get("expires_at", 0),
                    status=status,
                ))
            return invoices
        else:
            # LND
            path = "/v1/invoices?pending_only=true" if pending_only else "/v1/invoices"
            data = self._request("GET", path)
            invoices = []
            for inv in data.get("invoices", []):
                state = inv.get("state", "")
                status = InvoiceStatus.PAID if state == "SETTLED" else InvoiceStatus.PENDING
                invoices.append(LightningInvoice(
                    payment_hash=inv.get("r_hash", ""),
                    payment_request=inv.get("payment_request", ""),
                    amount_msat=int(inv.get("value", 0)) * 1000,
                    description=inv.get("memo", ""),
                    created_at=int(inv.get("creation_date", 0)),
                    expires_at=0,
                    status=status,
                ))
            return invoices

    # ─── Payments ──────────────────────────────────────────────────────

    def pay_invoice(self, bolt11: str, max_fee_sats: int = 100) -> PaymentResult:
        """Pay a Lightning invoice."""
        if self.implementation == "cln":
            body = {
                "invoice": bolt11,
                "maxfee": max_fee_sats * 1000,  # msat
            }
            data = self._request("POST", "/v1/pay", body)
            status = "succeeded" if data.get("status") == "complete" else data.get("status", "pending")
            return PaymentResult(
                payment_hash=data.get("payment_hash", ""),
                preimage=data.get("payment_preimage", ""),
                amount_msat=data.get("amount_msat", 0),
                fee_msat=data.get("amount_sent_msat", 0) - data.get("amount_msat", 0),
                status=status,
            )
        elif self.implementation == "lnd":
            body = {
                "payment_request": bolt11,
                "fee_limit": {"fixed": max_fee_sats},
            }
            data = self._request("POST", "/v1/channels/transactions", body)
            return PaymentResult(
                payment_hash=data.get("payment_hash", ""),
                preimage=data.get("payment_preimage", ""),
                amount_msat=int(data.get("value", 0)) * 1000,
                fee_msat=int(data.get("fee", 0)) * 1000,
                status="succeeded" if data.get("payment_error", "") == "" else "failed",
            )
        else:
            raise ValueError(f"Unknown implementation: {self.implementation}")

    # ─── Balance ───────────────────────────────────────────────────────

    def channel_balance(self) -> dict:
        """Get channel balance info."""
        if self.implementation == "cln":
            data = self._request("GET", "/v1/listfunds")
            channels = [c for c in data.get("channels", []) if c.get("state") == "CHANNELD_NORMAL"]
            total_local = sum(c.get("our_amount_msat", 0) for c in channels)
            total_remote = sum(c.get("amount_msat", 0) - c.get("our_amount_msat", 0) for c in channels)
            return {
                "local_msat": total_local,
                "remote_msat": total_remote,
                "channels_active": len(channels),
            }
        elif self.implementation == "lnd":
            data = self._request("GET", "/v1/balance/channels")
            return {
                "local_msat": int(data.get("local_balance", {}).get("msat", 0)),
                "remote_msat": int(data.get("remote_balance", {}).get("msat", 0)),
                "channels_active": 0,
            }
        else:
            return {"local_msat": 0, "remote_msat": 0, "channels_active": 0}


# ── LNURL Integration ────────────────────────────────────────────────────────

class LNURLPay:
    """LNURL-pay integration for receiving payments without running a node."""

    def __init__(self, lnurl_endpoint: str, timeout: int = 10):
        self.endpoint = lnurl_endpoint
        self.timeout = timeout

    def get_pay_info(self) -> dict:
        """Fetch LNURL-pay metadata."""
        req = urllib.request.Request(self.endpoint, headers={"User-Agent": "ManifoldBTC/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def request_invoice(self, amount_msat: int) -> str:
        """Request a BOLT11 invoice for the given amount."""
        info = self.get_pay_info()
        callback = info.get("callback", "")

        url = f"{callback}?amount={amount_msat}"
        req = urllib.request.Request(url, headers={"User-Agent": "ManifoldBTC/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())

        if "pr" in data:
            return data["pr"]
        elif "routes" in data:
            raise RuntimeError("LNURL returned routes array, not supported yet")
        else:
            raise RuntimeError(f"LNURL error: {data.get('reason', 'unknown')}")


# ── Microsettlement ──────────────────────────────────────────────────────────

class LightningMicrosettlement:
    """
    Fast settlement via Lightning for small-stakes trust claims.

    Instead of waiting for on-chain confirmations, agents can stake
    via Lightning payments. Settlement is instant.

    Flow:
    1. Agent requests to stake N sats
    2. Escrow generates LN invoice for N sats
    3. Agent pays invoice → instant confirmation
    4. On settlement grade: generate payment back (release) or nothing (slash)
    """

    def __init__(self, node: LightningNode):
        self.node = node
        self._pending: dict[str, dict] = {}  # contract_id -> invoice info

    def create_stake_invoice(
        self,
        contract_id: str,
        amount_sats: int,
        agent_name: str,
        task_id: str,
    ) -> LightningInvoice:
        """Create a Lightning invoice for an agent to pay their stake."""
        desc = f"Manifold stake: {agent_name} on {task_id} [{contract_id}]"
        invoice = self.node.create_invoice(
            amount_sats=amount_sats,
            description=desc,
            expiry_seconds=3600,  # 1 hour to pay
            label=f"manifold-{contract_id}",
        )

        self._pending[contract_id] = {
            "invoice": invoice,
            "agent_name": agent_name,
            "task_id": task_id,
            "amount_sats": amount_sats,
        }

        return invoice

    def check_stake(self, contract_id: str) -> InvoiceStatus:
        """Check if a stake payment has been received."""
        if contract_id not in self._pending:
            return InvoiceStatus.UNKNOWN

        payment_hash = self._pending[contract_id]["invoice"].payment_hash
        invoice = self.node.check_invoice(payment_hash)
        return invoice.status

    def release_stake(self, contract_id: str, destination_bolt11: str) -> PaymentResult:
        """Release stake back to agent via Lightning payment."""
        if contract_id not in self._pending:
            raise KeyError(f"No pending stake for {contract_id}")

        info = self._pending[contract_id]
        result = self.node.pay_invoice(destination_bolt11, max_fee_sats=max(10, info["amount_sats"] // 100))
        del self._pending[contract_id]
        return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Lightning Network interface")
    parser.add_argument("command", choices=["info", "invoice", "check", "balance", "pay"])
    parser.add_argument("--impl", default="cln", choices=["cln", "lnd"])
    parser.add_argument("--url", default="http://localhost:3010")
    parser.add_argument("--rune", default=None)
    parser.add_argument("--amount", type=int, default=1000, help="Amount in sats")
    parser.add_argument("--desc", default="Manifold")
    parser.add_argument("--hash", default=None, help="Payment hash to check")
    parser.add_argument("--bolt11", default=None, help="BOLT11 to pay")
    args = parser.parse_args()

    node = LightningNode(
        implementation=args.impl,
        rest_url=args.url,
        rune=args.rune,
    )

    if args.command == "info":
        info = node.get_info()
        print(f"Node: {info.alias} ({info.node_id[:16]}...)")
        print(f"Network: {info.network}")
        print(f"Peers: {info.num_peers} | Channels: {info.num_active_channels}")
        print(f"Block: {info.block_height}")

    elif args.command == "invoice":
        inv = node.create_invoice(args.amount, args.desc)
        print(f"Invoice: {inv.payment_request}")
        print(f"Hash: {inv.payment_hash}")
        print(f"Amount: {inv.amount_msat} msat")

    elif args.command == "check":
        if not args.hash:
            print("Error: --hash required")
            sys.exit(1)
        inv = node.check_invoice(args.hash)
        print(f"Status: {inv.status.value}")
        if inv.preimage:
            print(f"Preimage: {inv.preimage}")

    elif args.command == "balance":
        bal = node.channel_balance()
        print(f"Local:  {bal['local_msat'] / 1000:.0f} sats")
        print(f"Remote: {bal['remote_msat'] / 1000:.0f} sats")
        print(f"Channels: {bal['channels_active']}")

    elif args.command == "pay":
        if not args.bolt11:
            print("Error: --bolt11 required")
            sys.exit(1)
        result = node.pay_invoice(args.bolt11)
        print(f"Status: {result.status}")
        print(f"Paid: {result.amount_msat / 1000:.0f} sats")
        print(f"Fee: {result.fee_msat / 1000:.0f} sats")
        print(f"Preimage: {result.preimage}")


if __name__ == "__main__":
    main()
