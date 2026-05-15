#!/usr/bin/env python3
"""
raw_tx.py — Raw Bitcoin transaction builder/broadcaster for Manifold.

Builds and broadcasts real testnet transactions using ONLY:
- cryptography (secp256k1 via hazmat)
- hashlib (SHA256, RIPEMD160)
- httpx (broadcast via mempool.space)

No bitcoinlib, no bitcoinlib-ng. Pure Python + cryptography.

Supports:
- P2WPKH (native segwit v0) — bech32 addresses
- UTXO selection and signing
- Fee estimation
- Broadcast to testnet via mempool.space API
"""

import hashlib
import json
import os
import struct
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Constants ────────────────────────────────────────────────────────────────

TESTNET_BECH32_HRP = "tb"
MAINNET_BECH32_HRP = "bc"

# Bech32 charset
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


# ── Bech32 ──────────────────────────────────────────────────────────────────

def bech32_polymod(values):
    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = (chk >> 25)
        chk = (chk & 0x1ffffff) << 5 ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def bech32_verify_checksum(hrp, data):
    return bech32_polymod(bech32_hrp_expand(hrp) + data) == 1


def bech32_create_checksum(hrp, data):
    values = bech32_hrp_expand(hrp) + data
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp, witver, witprog):
    """Encode a segwit address."""
    data = convertbits(witprog, 8, 5)
    combined = [witver] + data
    checksum = bech32_create_checksum(hrp, combined)
    return hrp + "1" + "".join(BECH32_CHARSET[d] for d in combined + checksum)


def bech32_decode(addr):
    """Decode a bech32 address. Returns (hrp, witver, witprog)."""
    addr_lower = addr.lower()
    pos = addr_lower.rfind("1")
    hrp = addr_lower[:pos]
    data_part = addr_lower[pos + 1:]
    data = [BECH32_CHARSET.find(c) for c in data_part]
    if not bech32_verify_checksum(hrp, data):
        raise ValueError(f"Invalid bech32 checksum: {addr}")
    witver = data[0]
    witprog = convertbits(data[1:-6], 5, 8, pad=False)
    return hrp, witver, witprog


def convertbits(data, frombits, tobits, pad=True):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            raise ValueError(f"Invalid value: {value}")
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits:
        if (acc << (tobits - bits)) & maxv:
            raise ValueError("Non-zero padding")
    return ret


# ── Hashing ─────────────────────────────────────────────────────────────────

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def ripemd160(data: bytes) -> bytes:
    h = hashlib.new("ripemd160")
    h.update(data)
    return h.digest()


def hash160(data: bytes) -> bytes:
    """RIPEMD160(SHA256(data))"""
    return ripemd160(sha256(data))


def double_sha256(data: bytes) -> bytes:
    return sha256(sha256(data))


# ── Key Derivation ──────────────────────────────────────────────────────────

def privkey_from_seed(seed_hex: str, index: int = 0) -> bytes:
    """
    Derive a private key from seed using HMAC-based derivation.
    Not BIP32 (too complex without external libs), but deterministic.
    """
    # Use repeated SHA256 to derive key material
    key_material = seed_hex.encode()
    for _ in range(index + 1):
        key_material = sha256(key_material + struct.pack(">I", index))
    return key_material[:32]


def privkey_to_pubkey(privkey_bytes: bytes) -> bytes:
    """Get compressed public key from private key bytes."""
    # Use cryptography's secp256k1
    private_key = ec.derive_private_key(
        int.from_bytes(privkey_bytes, "big"),
        ec.SECP256K1(),
        default_backend(),
    )
    public_key = private_key.public_key()
    # Get compressed public key
    pub_numbers = public_key.public_numbers()
    prefix = b"\x02" if pub_numbers.y % 2 == 0 else b"\x03"
    return prefix + pub_numbers.x.to_bytes(32, "big")


def pubkey_to_address(pubkey_bytes: bytes, network: str = "testnet") -> str:
    """Convert compressed public key to P2WPKH bech32 address."""
    h = hash160(pubkey_bytes)
    hrp = TESTNET_BECH32_HRP if network == "testnet" else MAINNET_BECH32_HRP
    # P2WPKH: witness version 0, program = hash160(pubkey)
    return bech32_encode(hrp, 0, h)


# ── UTXO ────────────────────────────────────────────────────────────────────

@dataclass
class UTXO:
    txid: str
    vout: int
    value_sats: int
    script_pubkey: str  # hex
    confirmations: int


def get_utxos(address: str, network: str = "testnet") -> list[UTXO]:
    """Get UTXOs for an address from mempool.space."""
    base = "https://mempool.space/testnet" if network == "testnet" else "https://mempool.space"
    url = f"{base}/api/address/{address}/utxo"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Manifold/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        utxos = []
        for u in data:
            utxos.append(UTXO(
                txid=u["txid"],
                vout=u["vout"],
                value_sats=u["value"],
                script_pubkey="",  # Will fetch if needed
                confirmations=0,
            ))
        return utxos
    except Exception as e:
        print(f"[utxo] Error fetching UTXOs: {e}")
        return []


def get_fee_rate(network: str = "testnet") -> int:
    """Get fee rate in sat/vbyte."""
    base = "https://mempool.space/testnet" if network == "testnet" else "https://mempool.space"
    url = f"{base}/api/v1/fees/recommended"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Manifold/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("economy", 1)
    except Exception:
        return 1  # 1 sat/vbyte fallback


# ── Transaction Builder ─────────────────────────────────────────────────────

def build_p2wpkh_script_pubkey(pubkey_hash: bytes) -> bytes:
    """Build P2WPKH scriptPubKey: OP_0 <20-byte-hash>"""
    return b"\x00\x14" + pubkey_hash


def sign_p2wpkh_input(
    privkey: bytes,
    txid: str,
    vout: int,
    value_sats: int,
    script_pubkey: bytes,
    outputs: list[tuple[int, bytes]],  # [(value, scriptPubKey), ...]
    input_index: int = 0,
) -> bytes:
    """
    Sign a P2WPKH input using BIP143 (segwit) sighash.

    This is the actual cryptographic signing for segwit v0.
    """
    # BIP143 sighash
    # 1. hashPrevouts = SHA256(all input prevouts)
    prevouts = bytes.fromhex(txid)[::-1] + struct.pack("<I", vout)
    hash_prevouts = sha256(prevouts)

    # 2. hashSequence = SHA256(all input sequences)
    hash_sequence = sha256(struct.pack("<I", 0xFFFFFFFF))

    # 3. hashOutputs = SHA256(all outputs)
    outputs_data = b""
    for val, spk in outputs:
        outputs_data += struct.pack("<Q", val)
        outputs_data += bytes([len(spk)]) + spk
    hash_outputs = sha256(outputs_data)

    # 4. Build preimage
    preimage = b""
    preimage += struct.pack("<I", 2)  # nVersion
    preimage += hash_prevouts
    preimage += hash_sequence
    preimage += bytes.fromhex(txid)[::-1]  # outpoint
    preimage += struct.pack("<I", vout)
    preimage += bytes([len(script_pubkey)]) + script_pubkey
    preimage += struct.pack("<Q", value_sats)
    preimage += struct.pack("<I", 0xFFFFFFFF)  # sequence
    preimage += hash_outputs
    preimage += struct.pack("<I", 1)  # locktime
    preimage += struct.pack("<I", 1)  # sighash type: SIGHASH_ALL

    # 5. Hash and sign
    sighash = double_sha256(preimage)

    private_key = ec.derive_private_key(
        int.from_bytes(privkey, "big"),
        ec.SECP256K1(),
        default_backend(),
    )

    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    der_sig = private_key.sign(
        sighash,
        ec.ECDSA(hashes.SHA256()),
    )
    # Extract r,s from DER
    r, s = decode_dss_signature(der_sig)

    # Ensure low-s (BIP 62)
    curve_order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    if s > curve_order // 2:
        s = curve_order - s

    sig = (
        r.to_bytes(32, "big") +
        s.to_bytes(32, "big") +
        b"\x01"  # SIGHASH_ALL
    )

    # Get compressed pubkey
    pubkey = privkey_to_pubkey(privkey)

    # Witness: <sig> <pubkey>
    witness = (
        bytes([len(sig)]) + sig +
        bytes([len(pubkey)]) + pubkey
    )

    return witness


def build_tx(
    utxos: list[UTXO],
    recipient_address: str,
    amount_sats: int,
    change_address: str,
    fee_rate: int,
    privkey: bytes,
    network: str = "testnet",
) -> str:
    """
    Build, sign, and return a raw hex transaction.

    Returns hex-encoded raw transaction ready for broadcast.
    """
    # Decode recipient address
    hrp, witver, witprog = bech32_decode(recipient_address)
    recipient_script = build_p2wpkh_script_pubkey(bytes(witprog))

    # Decode change address
    _, _, change_witprog = bech32_decode(change_address)
    change_script = build_p2wpkh_script_pubkey(bytes(change_witprog))

    # Calculate total input
    total_input = sum(u.value_sats for u in utxos)

    # Estimate fee (P2WPKH: ~68 vbytes for 1-in-1-out, ~110 for 1-in-2-out)
    has_change = total_input > amount_sats + 200
    num_outputs = 2 if has_change else 1
    vsize = 68 + num_outputs * 31 + 10  # rough estimate
    fee = max(vsize * fee_rate, 250)  # minimum 250 sats

    if total_input < amount_sats + fee:
        raise ValueError(
            f"Insufficient funds: {total_input} sats available, "
            f"need {amount_sats + fee} (amount: {amount_sats}, fee: {fee})"
        )

    change_amount = total_input - amount_sats - fee if has_change else 0

    # Build outputs
    outputs = [(amount_sats, recipient_script)]
    if has_change and change_amount > 0:
        outputs.append((change_amount, change_script))

    # Build witnesses for each input
    witnesses = []
    for utxo in utxos:
        # Build scriptPubKey for the UTXO
        # P2WPKH: need pubkey hash
        # We derive it from the change/recipient address's pattern
        # Since we're spending our own UTXOs, derive from our pubkey
        pubkey = privkey_to_pubkey(privkey)
        pkh = hash160(pubkey)
        script_pubkey = build_p2wpkh_script_pubkey(pkh)

        witness = sign_p2wpkh_input(
            privkey=privkey,
            txid=utxo.txid,
            vout=utxo.vout,
            value_sats=utxo.value_sats,
            script_pubkey=script_pubkey,
            outputs=outputs,
        )
        witnesses.append(witness)

    # Serialize the transaction
    # Version
    raw = struct.pack("<I", 2)

    # Marker + Flag (segwit)
    raw += b"\x00\x01"

    # Inputs
    raw += bytes([len(utxos)])
    for utxo in utxos:
        raw += bytes.fromhex(utxo.txid)[::-1]  # txid (LE)
        raw += struct.pack("<I", utxo.vout)
        raw += b"\x00"  # empty scriptSig for segwit
        raw += struct.pack("<I", 0xFFFFFFFF)  # sequence

    # Outputs
    raw += bytes([len(outputs)])
    for value, script in outputs:
        raw += struct.pack("<Q", value)
        raw += bytes([len(script)]) + script

    # Witness data
    for witness in witnesses:
        # Split witness into items
        # For P2WPKH: 2 items (sig, pubkey)
        raw += b"\x02"  # 2 witness items
        # Parse the witness we built
        sig_len = witness[0]
        sig = witness[1:1 + sig_len]
        pubkey_len = witness[1 + sig_len]
        pubkey = witness[2 + sig_len:2 + sig_len + pubkey_len]
        raw += bytes([sig_len]) + sig
        raw += bytes([pubkey_len]) + pubkey

    # Locktime
    raw += struct.pack("<I", 1)

    return raw.hex()


def broadcast_tx(raw_hex: str, network: str = "testnet") -> str:
    """Broadcast a raw transaction via mempool.space API."""
    base = "https://mempool.space/testnet" if network == "testnet" else "https://mempool.space"
    url = f"{base}/api/tx"

    data = raw_hex.encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "text/plain", "User-Agent": "Manifold/1.0"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            txid = resp.read().decode().strip()
            return txid
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Broadcast failed ({e.code}): {error_body}")


def send_to_address(
    seed_hex: str,
    address_index: int,
    recipient_address: str,
    amount_sats: int,
    network: str = "testnet",
) -> str:
    """
    High-level: send BTC from a derived address to a recipient.

    Returns the txid.
    """
    privkey = privkey_from_seed(seed_hex, address_index)
    pubkey = privkey_to_pubkey(privkey)
    sender_address = pubkey_to_address(pubkey, network)

    print(f"[tx] Sender: {sender_address}")
    print(f"[tx] Recipient: {recipient_address}")
    print(f"[tx] Amount: {amount_sats} sats")

    # Get UTXOs
    utxos = get_utxos(sender_address, network)
    if not utxos:
        raise RuntimeError(f"No UTXOs found for {sender_address}")

    print(f"[tx] Found {len(utxos)} UTXOs ({sum(u.value_sats for u in utxos)} sats)")

    # Get fee rate
    fee_rate = get_fee_rate(network)
    print(f"[tx] Fee rate: {fee_rate} sat/vbyte")

    # Build and sign
    raw_hex = build_tx(
        utxos=utxos,
        recipient_address=recipient_address,
        amount_sats=amount_sats,
        change_address=sender_address,
        fee_rate=fee_rate,
        privkey=privkey,
        network=network,
    )

    print(f"[tx] Raw tx: {raw_hex[:64]}... ({len(raw_hex) // 2} bytes)")

    # Broadcast
    txid = broadcast_tx(raw_hex, network)
    print(f"[tx] Broadcast! TXID: {txid}")
    return txid


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manifold Raw TX Builder")
    parser.add_argument("command", choices=["send", "utxos", "balance", "address", "fee"])
    parser.add_argument("--seed", default=None, help="Seed hex (or use federation.seed)")
    parser.add_argument("--index", type=int, default=0, help="Address index")
    parser.add_argument("--to", help="Recipient address")
    parser.add_argument("--amount", type=int, default=1000, help="Amount in sats")
    parser.add_argument("--network", default="testnet")
    args = parser.parse_args()

    seed = args.seed
    if not seed:
        seed_path = "/tmp/manifold-btc-settlement/federation.seed"
        if os.path.exists(seed_path):
            with open(seed_path) as f:
                seed = f.read().strip()
        else:
            seed = generate_federation_seed()

    if args.command == "address":
        pubkey = privkey_to_pubkey(privkey_from_seed(seed, args.index))
        addr = pubkey_to_address(pubkey, args.network)
        print(f"Address (index {args.index}): {addr}")

    elif args.command == "balance":
        pubkey = privkey_to_pubkey(privkey_from_seed(seed, args.index))
        addr = pubkey_to_address(pubkey, args.network)
        utxos = get_utxos(addr, args.network)
        total = sum(u.value_sats for u in utxos)
        print(f"Address: {addr}")
        print(f"UTXOs: {len(utxos)}")
        print(f"Balance: {total} sats")

    elif args.command == "utxos":
        pubkey = privkey_to_pubkey(privkey_from_seed(seed, args.index))
        addr = pubkey_to_address(pubkey, args.network)
        utxos = get_utxos(addr, args.network)
        for u in utxos:
            print(f"  {u.txid}:{u.vout} = {u.value_sats} sats")

    elif args.command == "fee":
        rate = get_fee_rate(args.network)
        print(f"Fee rate: {rate} sat/vbyte")

    elif args.command == "send":
        if not args.to:
            print("Error: --to required")
            sys.exit(1)
        txid = send_to_address(seed, args.index, args.to, args.amount, args.network)
        print(f"TXID: {txid}")


if __name__ == "__main__":
    main()
