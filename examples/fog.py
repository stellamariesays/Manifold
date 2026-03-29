"""
FOG — epistemic fog mapping.

Three agents on the mesh. Each has gaps. Some gaps are shared.
Some are asymmetric — that asymmetry is signal.

Demonstrates:
  - agent.fog()              → FogMap from Manifold signals
  - agent.fog_seam(other)    → FogSeam between two agents
  - FogSeam.tension          → how much asymmetric blindness exists
  - diff(before, after)      → detect arbitrage vs genuine lift
  - build_fog() standalone   → no Agent required
"""

import asyncio
from manifold import Agent, FogMap, GapKind
from manifold.fog import build_fog, diff, measure
from manifold.fog.detect.arbitrage import detect_arbitrage, system_fog_change


async def main():
    # ── Three agents, different knowledge domains ─────────────────────────

    braid = Agent(name="braid")
    braid.knows(["solar-topology", "AR-classification", "flare-prediction"])

    solver = Agent(name="solver")
    solver.knows(["orbital-mechanics", "n-body", "transfer-orbit"])

    navigator = Agent(name="navigator")
    navigator.knows(["stellar-dynamics", "solar-topology", "n-body"])

    for agent in [braid, solver, navigator]:
        await agent.join()

    # Each agent shifts focus — creates blind spots where the mesh can't complement
    await braid.think("multi-star-prediction")
    await solver.think("flare-induced-orbital-correction")
    await navigator.think("coronal-mass-ejection")

    # ── Build fog maps ────────────────────────────────────────────────────

    fog_braid     = braid.fog()
    fog_solver    = solver.fog()
    fog_navigator = navigator.fog()

    print("=== FOG MAPS ===")
    for fog in [fog_braid, fog_solver, fog_navigator]:
        print(f"\n{fog}")
        for gap in fog.gaps.values():
            print(f"  {gap.key!r:45s} [{gap.kind.value}]")

    # ── Seams between agents ──────────────────────────────────────────────

    print("\n=== FOG SEAMS ===")
    seam_bs = braid.fog_seam(fog_solver)
    seam_bn = braid.fog_seam(fog_navigator)
    seam_sn = solver.fog_seam(fog_navigator)

    for seam in [seam_bs, seam_bn, seam_sn]:
        print(f"\n{seam.summary()}")
        if seam.system_gaps:
            print(f"  System gaps (need external signal): {seam.system_gaps}")
        if seam.only_in_a:
            print(f"  {seam.agent_a} can learn from {seam.agent_b}: {seam.only_in_a}")
        if seam.only_in_b:
            print(f"  {seam.agent_b} can learn from {seam.agent_a}: {seam.only_in_b}")

    # ── Delta: detect arbitrage vs genuine lift ───────────────────────────

    print("\n=== FOG DELTA ===")

    # Simulate: braid learns 'flare-prediction' from solver (fog lifts)
    fog_braid_before = braid.fog()
    await braid.knows(["flare-induced-orbital-correction"])
    await braid.think("flare-induced-orbital-correction")
    fog_braid_after = braid.fog()

    delta = diff(fog_braid_before, fog_braid_after)
    print(f"\n{delta.summary()}")

    # Simulate arbitrage: fog moves around but total doesn't shrink
    # Build fog maps manually for the demo
    mesh_before = [
        (fog_braid, fog_braid_after),   # braid: some gaps lifted, same added
    ]

    net = system_fog_change(mesh_before)
    print(f"\nSystem fog net change: {net:+d}")
    if net == 0:
        print("→ Epistemic arbitrage: ignorance redistributed, not reduced")
    elif net < 0:
        print("→ Genuine lift: new signal entered the system")
    else:
        print("→ Fog deepening: system knows less than before")

    # ── Standalone usage ─────────────────────────────────────────────────

    print("\n=== STANDALONE (no Agent) ===")
    from manifold.blindspot import BlindSpot
    import time

    fake_spots = [
        BlindSpot(
            topic="quantum-solar-dynamics",
            kind="dark_topic",
            depth=1.0,
            recurrence=3,
        ),
    ]
    standalone_fog = build_fog("hypothetical", fake_spots, ["dark-matter-interaction"])
    print(standalone_fog)
    for gap in standalone_fog.gaps.values():
        print(f"  {gap.key!r} [{gap.kind.value}]")

    for agent in [braid, solver, navigator]:
        await agent.leave()


asyncio.run(main())
