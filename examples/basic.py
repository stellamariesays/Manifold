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

    # Let registry announcements propagate through the event loop
    await asyncio.sleep(0.05)

    # braid looks for complementary knowledge
    peers = await braid.seek("orbital-mechanics")
    print(f"braid found {len(peers)} complementary peer(s):")
    for p in peers:
        print(f"  {p}")

    # both agents shift focus to the same problem — topology clusters around it
    await orbit.think("multi-star-prediction")
    await braid.think("multi-star-prediction")
    await asyncio.sleep(0.05)  # let topology updates propagate
    print(f"\nbraid shifted focus → strong peers: {braid.strong_peers(threshold=0.5)}")

    await braid.leave()
    await orbit.leave()


if __name__ == "__main__":
    asyncio.run(main())
