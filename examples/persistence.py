"""
persistence.py — the crystal holds its shape across restarts.

Run this twice. The second run restores the first run's mesh from disk:
agents, capabilities, focus history. The atlas is rebuilt from memory.

Also demonstrates atlas export to JSON and DOT.
"""

import asyncio
import json
import sys
from pathlib import Path

DB_PATH = "/tmp/manifold-example.db"


async def first_run() -> None:
    """Build a mesh, think some thoughts, leave. State written to disk."""
    from manifold import Agent

    print("━━━ First run — building mesh, persisting state ━━━\n")

    braid = Agent(name="braid", persist_to=DB_PATH)
    braid.knows(["solar-topology", "flare-prediction", "time-series-analysis"])

    solver = Agent(name="solver", persist_to=DB_PATH)
    solver.knows(["time-series-analysis", "anomaly-detection", "probabilistic-reasoning"])

    navigator = Agent(name="navigator", persist_to=DB_PATH)
    navigator.knows(["orbital-mechanics", "n-body-dynamics", "time-series"])

    for agent in [braid, solver, navigator]:
        await agent.join()

    await asyncio.sleep(0.05)

    await braid.think("coronal-mass-ejection")
    await solver.think("anomaly-detection")
    await navigator.think("multi-body-problem")

    print(f"braid chart:     {braid.chart()}")
    print(f"solver chart:    {solver.chart()}")
    print(f"navigator chart: {navigator.chart()}")

    atlas = braid.atlas()
    print(f"\nAtlas: {atlas}")

    # Export DOT
    dot_path = Path("/tmp/manifold-example.dot")
    dot_path.write_text(atlas.export_dot())
    print(f"DOT exported → {dot_path}")

    # Export JSON
    json_path = Path("/tmp/manifold-example.json")
    json_path.write_text(json.dumps(atlas.export_json(), indent=2))
    print(f"JSON exported → {json_path}")

    for agent in [braid, solver, navigator]:
        await agent.leave()

    print("\n✓ All agents left. State written to disk.")


async def second_run() -> None:
    """Restart. braid rejoins — restores mesh memory from disk."""
    from manifold import Agent
    from manifold.persist import PersistentStore

    print("\n━━━ Second run — mesh restarted, restoring from disk ━━━\n")

    # Inspect the store directly first
    store = PersistentStore(DB_PATH)
    stats = store.stats()
    print(f"Store: {stats}")

    prior_agents = store.load_agents()
    print(f"\nAgents in store ({len(prior_agents)}):")
    for rec in prior_agents:
        status = "active" if rec["active"] else "inactive"
        print(f"  {rec['name']!r} [{status}] focus={rec['focus']!r} caps={rec['capabilities']}")

    braid_history = store.load_focus_history("braid")
    print(f"\nbraid focus history: {braid_history}")

    print()

    # braid rejoins — solo, no live peers yet
    # but registry is restored from disk so atlas has prior mesh topology
    braid = Agent(name="braid", persist_to=DB_PATH)
    braid.knows(["solar-topology", "flare-prediction", "time-series-analysis"])

    await braid.join()
    await asyncio.sleep(0.02)

    # braid's atlas is rebuilt from restored registry — sees prior mesh shape
    atlas = braid.atlas()
    print(f"Atlas (restored): {atlas}")
    print(f"\nCharts visible to braid:")
    for chart in atlas.charts():
        print(f"  {chart}")

    print(f"\nTransition maps:")
    for src in ["braid", "solver", "navigator"]:
        for tm in atlas.neighbors(src):
            print(f"  {tm}")

    print(f"\nHoles: {atlas.holes()}")
    print(f"\nHigh curvature regions:")
    for region, score in atlas.high_curvature_regions():
        print(f"  {region!r}: {int(score*100)}%")

    # Geodesic still works from restored state
    path = atlas.geodesic("braid", "n-body-dynamics")
    print(f"\nGeodesic braid → n-body-dynamics (restored):")
    for step in path:
        if step.via_map:
            print(f"  via {step.via_map} → {step.agent!r}")
        else:
            print(f"  start: {step.agent!r}")

    await braid.leave()
    print("\n✓ Second run complete. Memory survived the restart.")


async def main() -> None:
    run = sys.argv[1] if len(sys.argv) > 1 else "both"

    if run in ("1", "first", "both"):
        # Clean slate for demo
        Path(DB_PATH).unlink(missing_ok=True)
        await first_run()

    if run in ("2", "second", "both"):
        await second_run()


if __name__ == "__main__":
    asyncio.run(main())
