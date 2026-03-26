"""
Sophia — the wisdom signal.

Sophia is not held by any agent. It lives in the seams between them.
Where the same territory looks radically different from different
coordinate systems, and the mesh doesn't break — that's where Sophia
is densest.

This example builds a four-agent mesh spanning climate science,
economics, political science, and ML — with meaningful overlaps —
then shows how Sophia concentrates at the contested boundaries.
It also demonstrates how adding a bridging agent shifts the signal.
"""

import asyncio
from manifold import Agent, SophiaReading, SophiaRegion


def print_reading(reading: SophiaReading, label: str = "") -> None:
    if label:
        print(f"\n{'═' * 60}")
        print(f"  {label}")
        print(f"{'═' * 60}")

    print(f"\nSophia score:   {reading.score:.2f}")
    print(f"Interpretation: {reading.interpretation}")

    if reading.dense_regions:
        print(f"\nDense regions ({len(reading.dense_regions)} found):")
        for region in reading.dense_regions[:5]:
            bar = "█" * int(region.density * 20)
            print(f"  [{bar:<20}] {region.density:.2f}  '{region.topic}'")
            print(f"    {region.agent_count} agents · curvature {region.curvature:.2f}")
            print(f"    → {region.interpretation}")
    else:
        print("\nNo dense regions — the mesh is empty or fully isolated.")

    if reading.gradient:
        print(f"\nGradient suggestions ({len(reading.gradient)} pairs):")
        for agent_a, agent_b in reading.gradient[:4]:
            print(f"  {agent_a}  ⟷  {agent_b}  (bridging here would increase Sophia)")
    else:
        print("\nNo gradient — agents are already well-connected.")


async def main() -> None:
    # ── Build a four-agent mesh with interesting overlaps ────────────────
    #
    # climate-scientist: physical systems, tipping points, feedback loops
    # economist:         risk, cost-benefit, carbon pricing, market dynamics
    # political-analyst: policy, governance, international agreements
    # ml-researcher:     prediction models, data pipelines, uncertainty
    #
    # Overlapping tensions:
    #   'risk' — economist frames it as expected-value; ml frames it as
    #            uncertainty quantification; climate frames it as tipping points
    #   'model' — ml means learned function; climate means simulation
    #   'policy' — political means legislation; economist means incentive design
    #   'feedback' — climate means earth system loops; ml means gradient descent

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

    # Join on the in-memory transport and let pub/sub announcements propagate
    await climate.join()
    await economist.join()
    await political.join()
    await ml_researcher.join()

    await asyncio.sleep(0.05)  # let the message bus drain

    # ── Four-agent scan ──────────────────────────────────────────────────
    reading_4 = climate.sophia()
    print_reading(reading_4, label="Four agents — climate × economics × policy × ML")

    # ── Add a bridging agent: climate-economist ──────────────────────────
    #
    # A specialist who lives in the gap between climate science and economics.
    # They share vocabulary with both — their presence should increase Sophia
    # by making previously-unreachable translations possible.

    bridge = Agent(name="climate-economist")
    bridge.knows([
        "carbon-pricing", "climate-modeling", "risk-assessment",
        "tipping-points", "cost-benefit-analysis", "market-dynamics",
        "feedback-loops", "carbon-cycle", "uncertainty-quantification",
    ])
    await bridge.join()

    await asyncio.sleep(0.05)  # let the bridge announcement propagate

    # Re-scan from the climate agent's view (now sees the bridge)
    reading_5 = climate.sophia()
    print_reading(reading_5, label="Five agents — bridge agent added")

    # ── Show the delta ───────────────────────────────────────────────────
    delta = reading_5.score - reading_4.score
    direction = "▲" if delta >= 0 else "▼"
    print(f"\n{'─' * 60}")
    print(f"Sophia shift after bridging agent:")
    print(f"  {reading_4.score:.2f}  →  {reading_5.score:.2f}  ({direction}{abs(delta):.2f})")
    if delta > 0:
        print("  The bridge opened new translation paths — emergence increased.")
    elif delta < 0:
        print("  The bridge resolved contested ground — curvature dropped.")
    else:
        print("  The mesh was already well-saturated in these regions.")

    # ── Sophia from a different vantage point ────────────────────────────
    print(f"\n{'─' * 60}")
    print("Sophia as seen from the ML researcher's local registry:")
    ml_reading = ml_researcher.sophia()
    print(f"  score: {ml_reading.score:.2f}  — {ml_reading.interpretation}")
    if ml_reading.dense_regions:
        top = ml_reading.dense_regions[0]
        print(f"  top region: '{top.topic}' density={top.density:.2f}")
        print(f"  → {top.interpretation}")


if __name__ == "__main__":
    asyncio.run(main())
