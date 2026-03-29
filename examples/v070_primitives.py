"""
Manifold v0.7.1 — bleed_rate, substrate_coupling, bottleneck_topology

Three primitives that extend Sophia from a snapshot into something with
memory, identity, and direction.

  bleed_rate          — Sophia over time: curvature decay per region
  substrate_coupling  — Sophia with noise correction: substrate echo discount
  bottleneck_topology — Sophia applied to constraints: attention vs. flow

Same mesh as sophia.py (climate × economics × policy × ML), now observed
across time and with substrate and flow metadata added.
"""

import asyncio

from manifold import (
    Agent,
    BleedReading,
    SubstrateCoupling,
    BottleneckReading,
    bleed_rate,
    substrate_coupling,
    bottleneck_topology,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def print_bleed(readings: list[BleedReading]) -> None:
    print(f"\n{'═' * 60}")
    print("  BLEED RATE — familiarity decay")
    print(f"{'═' * 60}")
    if not readings:
        print("  No regions with meaningful curvature change.")
        return
    for r in readings[:6]:
        sign = "▼" if r.bleed_rate > 0 else "▲" if r.bleed_rate < 0 else "—"
        flat = f"  (flat in ~{r.estimated_flat_at} cycles)" if r.estimated_flat_at > 0 else ""
        print(
            f"  {sign} '{r.region}': "
            f"{r.original_curvature:.2f} → {r.current_curvature:.2f}  "
            f"rate={r.bleed_rate:+.4f}  [{r.closing_mode}]{flat}"
        )


def print_substrate(couplings: list[SubstrateCoupling]) -> None:
    print(f"\n{'═' * 60}")
    print("  SUBSTRATE COUPLING — echo chamber risk")
    print(f"{'═' * 60}")
    if not couplings:
        print("  No agent pairs found.")
        return
    for c in couplings[:6]:
        a, b = c.agent_pair
        risk = "⚠️  echo risk" if c.echo_factor > 0.5 else "✓ genuine signal"
        print(
            f"  {a} × {b}\n"
            f"    shared_substrate={c.shared_substrate:.2f}  "
            f"emergent_delta={c.emergent_delta:.2f}  "
            f"echo={c.echo_factor:.2f}  "
            f"sophia_corrected={c.sophia_correction:.2f}  {risk}"
        )


def print_bottleneck(r: BottleneckReading) -> None:
    print(f"\n{'═' * 60}")
    print("  BOTTLENECK TOPOLOGY — attention vs. constraint")
    print(f"{'═' * 60}")
    print(f"  Perceived bottleneck:  '{r.perceived_bottleneck}'")
    print(f"  Actual bottleneck:     '{r.actual_bottleneck}'")
    print(f"  Flow shortfall:        {r.flow_shortfall:.2f}")
    print(f"  Attention displacement:{r.attention_displacement:.2f}")
    print(f"  → {r.topology_note}")


# ── Mesh builder ─────────────────────────────────────────────────────────

def build_agents() -> list[Agent]:
    climate = Agent(name="climate-scientist")
    climate.knows([
        "climate-modeling", "tipping-points", "carbon-cycle",
        "feedback-loops", "risk-assessment", "earth-system-dynamics",
        "uncertainty-quantification",
    ])

    economist = Agent(name="economist")
    economist.knows([
        "carbon-pricing", "cost-benefit-analysis", "market-dynamics",
        "risk-modeling", "policy-design", "incentive-structures",
        "uncertainty-bounds",
    ])

    political = Agent(name="political-analyst")
    political.knows([
        "climate-policy", "international-agreements", "governance-frameworks",
        "policy-implementation", "stakeholder-dynamics", "risk-communication",
        "feedback-mechanisms",
    ])

    ml_researcher = Agent(name="ml-researcher")
    ml_researcher.knows([
        "prediction-models", "uncertainty-quantification", "data-pipelines",
        "model-evaluation", "feedback-loops", "risk-scoring",
        "climate-downscaling",
    ])

    return [climate, economist, political, ml_researcher]


async def main() -> None:

    # ── BLEED RATE ────────────────────────────────────────────────────────
    # Simulate the mesh evolving over three snapshots.
    # Snapshot 1: initial contested mesh.
    # Snapshot 2: 'risk' starts converging (economists and climate agree more).
    # Snapshot 3: 'risk' further resolved; new friction on 'policy'.

    print("\nBuilding three mesh snapshots for bleed_rate...\n")

    # Snapshot 1
    agents_1 = build_agents()
    for a in agents_1:
        await a.join()
    await asyncio.sleep(0.05)
    atlas_1 = agents_1[0].atlas()

    # Snapshot 2: add a bridge agent that reduces 'risk' curvature
    agents_2 = build_agents()
    bridge_2 = Agent(name="risk-analyst")
    bridge_2.knows([
        "risk-assessment", "risk-modeling", "risk-scoring", "risk-communication",
        "uncertainty-quantification", "uncertainty-bounds",
    ])
    for a in agents_2:
        await a.join()
    await bridge_2.join()
    await asyncio.sleep(0.05)
    atlas_2 = agents_2[0].atlas()

    # Snapshot 3: risk even more resolved, policy becomes new friction
    agents_3 = build_agents()
    bridge_3a = Agent(name="risk-analyst")
    bridge_3a.knows([
        "risk-assessment", "risk-modeling", "risk-scoring", "risk-communication",
        "uncertainty-quantification", "uncertainty-bounds",
    ])
    bridge_3b = Agent(name="policy-economist")
    bridge_3b.knows([
        "policy-design", "carbon-pricing", "policy-implementation",
        "governance-frameworks", "incentive-structures",
    ])
    for a in agents_3:
        await a.join()
    await bridge_3a.join()
    # Note: bridge_3b covers 'policy' from a new angle — adds curvature there
    await bridge_3b.join()
    await asyncio.sleep(0.05)
    atlas_3 = agents_3[0].atlas()

    readings = bleed_rate([atlas_1, atlas_2, atlas_3])
    print_bleed(readings)

    # ── SUBSTRATE COUPLING ────────────────────────────────────────────────
    # Two agents on claude-sonnet, two on different models.
    # Expect high echo risk between the two claude-sonnet agents.

    print("\nBuilding mesh for substrate_coupling...\n")

    agents_s = build_agents()
    for a in agents_s:
        await a.join()
    await asyncio.sleep(0.05)
    atlas_s = agents_s[0].atlas()

    sub_map = {
        "climate-scientist": "claude-sonnet",
        "economist": "claude-sonnet",       # same substrate as climate — echo risk
        "political-analyst": "gpt-4o",
        "ml-researcher": "llama-3",
    }

    couplings = substrate_coupling(atlas_s, sub_map)
    print_substrate(couplings)

    # ── BOTTLENECK TOPOLOGY ───────────────────────────────────────────────
    # Supply a flow_map: 'risk' has lots of agent attention but moderate flow.
    # 'feedback' is quietly broken — low flow, but nobody's crowding it.

    print("\nBuilding mesh for bottleneck_topology...\n")

    agents_b = build_agents()
    for a in agents_b:
        await a.join()
    await asyncio.sleep(0.05)
    atlas_b = agents_b[0].atlas()

    # flow_map: higher = less constrained (e.g. task success rate per topic)
    flow = {
        "risk":          0.65,  # contested but flowing
        "feedback":      0.08,  # barely moving — the real problem
        "uncertainty":   0.55,
        "policy":        0.70,
        "dynamics":      0.40,
        "model":         0.50,
    }

    reading = bottleneck_topology(atlas_b, flow)
    print_bottleneck(reading)

    print(f"\n{'─' * 60}")
    print("Done. Three primitives, one mesh.")
    print("Sophia was a snapshot. These are Sophia with memory, identity, and direction.")


if __name__ == "__main__":
    asyncio.run(main())
