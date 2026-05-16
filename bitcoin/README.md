# Manifold Bitcoin Layer

Real Bitcoin behind the Manifold trust system. Agents stake actual sats on their claims — skin in the game isn't metaphorical anymore.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Manifold Federation                 │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │  Trust    │  │  Agent   │  │  BTC Settlement   │ │
│  │  Ledger   │◄─┤  Wallet  │◄─┤  Engine            │ │
│  │          │  │  (HD)    │  │  (escrow/slash)    │ │
│  └──────────┘  └──────────┘  └─────────┬─────────┘ │
│                                          │           │
│                              ┌───────────▼─────────┐ │
│                              │    Bitcoin Oracle    │ │
│                              │  (mempool.space API) │ │
│                              └───────────┬─────────┘ │
└──────────────────────────────────────────┼───────────┘
                                           │
                                    ┌──────▼──────┐
                                    │  Bitcoin     │
                                    │  Blockchain  │
                                    └─────────────┘
```

## Components

### `bitcoin/oracle.py` — Blockchain Oracle
Read-only Bitcoin data via mempool.space (free, no API key).
- Block height, UTXOs, balances, fee estimates
- Transaction broadcast and verification
- Stake verification helpers

### `bitcoin/wallet.py` — Agent Wallets
Deterministic HD wallets for federation agents.
- One seed per federation, unique address per agent
- BIP32-inspired key derivation using HMAC-SHA256
- Bech32 (native segwit) addresses
- No external Bitcoin libraries needed (uses `cryptography`)

### `bitcoin/settlement.py` — Settlement Engine
Escrow contracts backing trust claims with real Bitcoin.
- Agent sends sats → escrow → grade filed → release or burn
- Slash threshold configurable per contract
- Expiry handling (timeout = return to agent)

### `bitcoin/agent_bitcoin.py` — Integration Layer
Bridges Bitcoin to Manifold's `core/trust.py`.
- `BitcoinManifoldLayer` — single entry point
- BTC-enhanced trust scores
- Federation-wide reports

## Agents

### `btc-signals-agent` — Technical Analysis
Live BTC market analysis using public APIs.
- **price**: Current BTC/USD
- **fee**: Network fee estimates
- **signals**: RSI, SMA, EMA, MACD, Bollinger Bands, composite score
- **breakout-check**: Detect breakout conditions
- **utxo-check**: Check UTXOs for any address

### `btc-settlement-agent` — Trust Settlement
Manages escrow contracts for the federation.
- **register**: Register agent wallet
- **stake**: Create escrow contract
- **deposit/confirm**: On-chain deposit tracking
- **settle**: Release or slash based on grade
- **federation-report**: Full federation BTC overview

## Quick Start

```python
from bitcoin import BitcoinManifoldLayer
from core.trust import Claim, Grade

# Initialize (testnet by default)
layer = BitcoinManifoldLayer(seed_hex="your-seed-hex")

# Register agents
stella = layer.register_agent("stella")

# Stake on a claim
claim = Claim(agent="stella", task="do-math", domain="math")
contract = layer.stake_claim(claim, amount_sats=50000)

# After task completes
grade = Grade(agent="stella", domain="math", score=0.92, task_id="do-math")
layer.settle_with_grade(contract.id, grade)  # → released
```

## Running the Demo

```bash
python3 examples/bitcoin_demo.py
```

## Tests

```bash
python3 -m pytest tests/test_bitcoin.py -v
```

## Network

- **Default: testnet** — agents shouldn't burn real BTC on day one
- Switch to mainnet by passing `network="mainnet"`
- All addresses are native segwit (bech32): `tb1...` (testnet) / `bc1...` (mainnet)

## Security Notes

- Federation seed controls ALL agent wallets — protect it
- Escrow is federation-controlled (Phase 1 honest-agent model)
- Phase 2 will add proper 2-of-2 multisig
- Private keys never leave the settlement agent
- Oracle is read-only — cannot move funds

## Dependencies

- `cryptography` (secp256k1 key derivation)
- `httpx` (oracle API calls)
- Manifold `core/trust.py` (trust ledger integration)

No external Bitcoin libraries required.
