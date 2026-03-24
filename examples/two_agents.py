"""
Two agents example — real-time mesh interaction.

Shows how agents find each other, exchange messages, and
self-organize as cognitive focus shifts.
"""

import asyncio
from manifold import Agent


async def main() -> None:
    # --- Agent 1: Solar analyst
    solar = Agent(name="solar-analyst")
    solar.knows(["solar-magnetism", "AR-topology", "flare-classification"])

    # --- Agent 2: Orbit solver
    orbit = Agent(name="orbit-solver")
    orbit.knows(["orbital-mechanics", "n-body", "trajectory-optimization"])

    # Connect both
    await solar.join()
    await orbit.join()

    # Give the mesh a moment to sync registry announcements
    await asyncio.sleep(0.05)

    # orbit has a problem it can't solve alone
    print("=== orbit-solver seeking complementary knowledge ===")
    peers = await orbit.seek("solar-ejection-impact-on-trajectory")
    for p in peers:
        print(f"  Found: {p}")

    # Both agents shift focus to the same problem
    print("\n=== Both agents focus on the same problem ===")
    await orbit.think("solar-ejection-impact-on-trajectory")
    await solar.think("solar-ejection-impact-on-trajectory")

    await asyncio.sleep(0.05)  # let topology updates propagate

    orbit_strong = orbit.strong_peers(threshold=0.5)
    solar_strong = solar.strong_peers(threshold=0.5)
    print(f"orbit's strong peers: {orbit_strong}")
    print(f"solar's strong peers: {solar_strong}")

    # Direct message exchange
    received: list[dict] = []

    async def on_message(msg: dict) -> None:
        received.append(msg)
        print(f"\n[{msg.get('data', {}).get('to', '?')}] received: "
              f"{msg.get('data', {}).get('text', '')}")

    await orbit.subscribe("channel.solar-orbit", on_message)
    await solar.publish(
        "channel.solar-orbit",
        {
            "to": "orbit-solver",
            "from": "solar-analyst",
            "text": "CME detected, impact in ~18h. Adjusting trajectory window.",
        },
    )

    await asyncio.sleep(0.05)
    print(f"\nMessages received: {len(received)}")

    await solar.leave()
    await orbit.leave()


if __name__ == "__main__":
    asyncio.run(main())
