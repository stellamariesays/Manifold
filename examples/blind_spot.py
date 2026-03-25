"""
blind_spot() — the mesh naming its own absence.

Three agents on the mesh. One knows something no one else does.
One is thinking about something no one can complement.
The third has been circling the same topic, unmatched, for a while.

Run this and you'll see the system surface its own gaps —
not as errors, but as structure.
"""

import asyncio
from manifold import Agent


async def main() -> None:
    # ── Mesh participants ────────────────────────────────────────────────

    # braid: solar forecasting agent — knows its domain well
    braid = Agent(name="braid")
    braid.knows(["solar-topology", "AR-classification", "flare-prediction"])

    # solver: general reasoning agent — broad but shallow
    solver = Agent(name="solver")
    solver.knows(["probabilistic-reasoning", "time-series", "anomaly-detection"])

    # orphan: knows something no one else on the mesh knows yet
    orphan = Agent(name="orphan")
    orphan.knows(["n-body-dynamics", "keplerian-elements", "multi-star-topology"])

    # Connect all three
    await braid.join()
    await solver.join()
    await orphan.join()

    # Give pub/sub a moment to propagate announcements
    await asyncio.sleep(0.05)

    # ── braid shifts focus ───────────────────────────────────────────────

    # braid keeps returning to coronal-mass-ejection — no one can complement it
    await braid.think("coronal-mass-ejection")
    await asyncio.sleep(0.01)
    await braid.think("flare-loop-feedback")
    await asyncio.sleep(0.01)
    await braid.think("coronal-mass-ejection")   # second visit — dark_topic

    # ── solver shifts focus ──────────────────────────────────────────────

    # solver is thinking about something outside its knowledge
    await solver.think("quantum-error-correction")

    # ── surface the blind spots ──────────────────────────────────────────

    print("\n━━━ braid's blind spots ━━━")
    for spot in braid.blind_spot():
        print(f"  {spot}")
        for e in spot.evidence:
            print(f"    ↳ {e}")

    print("\n━━━ solver's blind spots ━━━")
    for spot in solver.blind_spot():
        print(f"  {spot}")
        for e in spot.evidence:
            print(f"    ↳ {e}")

    print("\n━━━ orphan's blind spots ━━━")
    for spot in orphan.blind_spot():
        print(f"  {spot}")
        for e in spot.evidence:
            print(f"    ↳ {e}")

    # ── what the mesh can't yet think ────────────────────────────────────

    print("\n━━━ what the mesh can't yet think ━━━")
    all_agents = [braid, solver, orphan]
    all_spots = []
    for agent in all_agents:
        for spot in agent.blind_spot():
            all_spots.append((agent.name, spot))

    all_spots.sort(key=lambda x: x[1].depth, reverse=True)
    for agent_name, spot in all_spots:
        print(f"  [{agent_name}] {spot.topic!r} — {spot.kind} (depth {int(spot.depth*100)}%)")

    await braid.leave()
    await solver.leave()
    await orphan.leave()


if __name__ == "__main__":
    asyncio.run(main())
