"""
atlas() — the mesh's global topology made visible.

Four agents with overlapping domains.
Build the atlas. Inspect transition maps.
Find curvature — where the mesh holds contradiction.
Find holes — what no chart covers.
Navigate a geodesic — the shortest path to a topic.
"""

import asyncio
from manifold import Agent


async def main() -> None:
    # ── Build a mesh with real overlap ───────────────────────────────────

    braid = Agent(name="braid")
    braid.knows(["solar-topology", "flare-prediction", "time-series-analysis"])

    solver = Agent(name="solver")
    solver.knows(["time-series-analysis", "anomaly-detection", "probabilistic-reasoning"])

    navigator = Agent(name="navigator")
    navigator.knows(["orbital-mechanics", "n-body-dynamics", "time-series"])

    linguist = Agent(name="linguist")
    linguist.knows(["natural-language", "semantic-embedding", "knowledge-graphs"])

    for agent in [braid, solver, navigator, linguist]:
        await agent.join()

    await asyncio.sleep(0.05)

    # shift some focus so charts have centers
    await braid.think("coronal-mass-ejection")
    await solver.think("anomaly-detection")

    # ── Build the atlas from braid's perspective ──────────────────────────

    atlas = braid.atlas()
    print(f"\n{atlas}")

    # ── Charts ────────────────────────────────────────────────────────────

    print("\n━━━ Charts ━━━")
    for chart in atlas.charts():
        print(f"  {chart}")

    # ── Transition maps ───────────────────────────────────────────────────

    print("\n━━━ Transition Maps ━━━")
    for src_name in ["braid", "solver", "navigator", "linguist"]:
        for tm in atlas.neighbors(src_name):
            print(f"  {tm}")
            if tm.translation:
                sample = list(tm.translation.items())[:2]
                for term, targets in sample:
                    print(f"    {term!r} → {targets}")

    # ── Curvature ─────────────────────────────────────────────────────────

    print("\n━━━ High Curvature Regions ━━━")
    for region, score in atlas.high_curvature_regions(top_n=5):
        print(f"  {region!r}: curvature={int(score*100)}%")

    # ── Holes ─────────────────────────────────────────────────────────────

    print("\n━━━ Holes (no chart covers these) ━━━")
    for hole in atlas.holes():
        print(f"  {hole!r}")

    # ── Geodesic ──────────────────────────────────────────────────────────

    print("\n━━━ Geodesic: braid → 'n-body-dynamics' ━━━")
    path = atlas.geodesic("braid", "n-body-dynamics")
    if path:
        for step in path:
            if step.via_map:
                print(f"  via {step.via_map} → {step.agent!r} (loss: {step.cumulative_loss})")
            else:
                print(f"  start: {step.agent!r}")
    else:
        print("  unreachable")

    print("\n━━━ Geodesic: braid → 'knowledge-graphs' ━━━")
    path2 = atlas.geodesic("braid", "knowledge-graphs")
    if path2:
        for step in path2:
            if step.via_map:
                print(f"  via {step.via_map} → {step.agent!r} (loss: {step.cumulative_loss})")
            else:
                print(f"  start: {step.agent!r}")
    else:
        print("  unreachable (this is a hole)")

    # ── This agent's own chart ────────────────────────────────────────────

    print("\n━━━ braid's chart ━━━")
    my_chart = braid.chart()
    print(f"  {my_chart}")
    print(f"  vocabulary: {sorted(my_chart.vocabulary)[:8]}...")

    for agent in [braid, solver, navigator, linguist]:
        await agent.leave()


if __name__ == "__main__":
    asyncio.run(main())
