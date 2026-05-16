"""
Manifold Bitcoin Layer — real sats behind trust claims.

Agents in the Manifold federation can now back their claims with actual Bitcoin.
Stake = sats on chain. Slash = sats burned or sent to a burn address.
Grades get real economic weight.

Architecture:
- wallet.py: HD wallet for agents (BIP32-ish, simplified)
- settlement.py: Escrow + slash settlement protocol
- oracle.py: Blockchain data via mempool.space API (no auth needed)
- agent_bitcoin.py: Integration layer connecting Bitcoin to Manifold trust

Depends only on: cryptography (already installed), httpx (already installed)
"""
