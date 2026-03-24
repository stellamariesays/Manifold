"""
Basic example — the 10-liner.

Shows the three core Manifold primitives: knows(), seek(), think().
Uses the in-memory transport so no external infrastructure required.
"""

import asyncio
from manifold import Agent


async def main() -> None:
    # Create two agents on the same in-memory mesh
    braid = Agent(name="braid")
    braid.knows(["solar-topology", "AR-classification", "XGB-models"])

    orbit = Agent(name="orbit-solver")
    orbit.knows(["orbital-mechanics", "n-body", "Keplerian-elements"])

    # Connect both to the mesh
    await braid.join()
    await orbit.join()

    # braid looks for complementary knowledge
    peers = await braid.seek("orbital-mechanics")
    print(f"braid found {len(peers)} complementary peer(s):")
    for p in peers:
        print(f"  {p}")

    # braid shifts cognitive focus — topology restructures
    await braid.think("multi-star-prediction")
    print(f"\nbraid shifted focus → strong peers: {braid.strong_peers()}")

    await braid.leave()
    await orbit.leave()


if __name__ == "__main__":
    asyncio.run(main())
