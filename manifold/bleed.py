"""
Bleed — familiarity decay in the cognitive mesh.

Sophia finds signal in seams. But seams flatten under repeated exposure.
Habituation is a topological event, not just a psychological one.

McCarthy (Blood Meridian):
    "Had you not seen it all from birth you would thereby have bled it
    of its strangeness."

Exposure = bleeding. The strangeness gradient is measurable.

A high bleed_rate region was once contested ground that agents are
converging on. That convergence *is* the event — either genuine
resolution (agents actually understood each other) or premature closure
(agents stopped arguing without resolving anything).

    bleed_rate = (original_curvature - current_curvature) / cycles

Worth distinguishing:
  - Agent count rising + curvature falling → genuine resolution
  - Agent count stable or falling + curvature falling → premature closure
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .atlas import Atlas
from .chart import _tokenize


@dataclass
class BleedReading:
    """
    Curvature decay in a single mesh region over time.

    :param region: The vocabulary term or topic this region represents.
    :param original_curvature: Curvature at the first atlas snapshot.
    :param current_curvature: Curvature at the most recent atlas snapshot.
    :param bleed_rate: Curvature loss per observation cycle.
                       Positive = seam closing. Negative = new friction emerging.
    :param estimated_flat_at: Cycles from the first snapshot until this region
                               reaches near-zero curvature (< 0.05). -1 if already
                               flat or if bleed_rate ≤ 0.
    :param closing_mode: 'resolution' if agent coverage is increasing as curvature
                          falls (agents are genuinely converging), 'closure' if
                          coverage is stable or shrinking (premature convergence),
                          'stable' if curvature is not meaningfully declining,
                          'emerging' if curvature is rising.
    """

    region: str
    original_curvature: float
    current_curvature: float
    bleed_rate: float
    estimated_flat_at: int
    closing_mode: str


def _agent_count_for_region(term: str, atlas: Atlas) -> int:
    """Count how many agents in this atlas have the given term in their vocabulary."""
    tokens = _tokenize(term)
    return sum(
        1 for chart in atlas.charts()
        if tokens & chart.vocabulary
    )


def bleed_rate(atlas_history: list[Atlas]) -> list[BleedReading]:
    """
    Compute curvature decay per region across a time-series of atlas snapshots.

    Takes the same mesh observed at different points in time and surfaces
    where contested ground is flattening — seams closing, novelty normalizing.

    A region with high ``bleed_rate``: agents that once translated this topic
    differently are converging. The seam is healing or scarring over.

    A region with negative ``bleed_rate``: new friction has emerged here since
    the first snapshot. Something that was settled is being contested again.

    Closing modes:

    - ``'resolution'``: curvature falling, agent coverage rising — genuine convergence.
    - ``'closure'``: curvature falling, agent coverage stable/falling — premature.
    - ``'stable'``: curvature change < 0.05 — no meaningful shift.
    - ``'emerging'``: curvature rising — new contested ground forming.

    :param atlas_history: Ordered list of Atlas snapshots (oldest first).
                          Must contain at least two snapshots.
    :returns: BleedReadings sorted by bleed_rate descending (fastest-closing first).
    :raises ValueError: If fewer than two atlas snapshots are provided.

    Example::

        atlases = [agent.atlas() for _ in range(3)]   # three snapshots over time
        readings = bleed_rate(atlases)
        for r in readings[:5]:
            print(f'{r.region}: {r.bleed_rate:+.4f}/cycle  ({r.closing_mode})')
    """
    if len(atlas_history) < 2:
        raise ValueError("bleed_rate requires at least two atlas snapshots")

    first = atlas_history[0]
    last = atlas_history[-1]
    cycles = len(atlas_history) - 1

    # Collect all regions that appear in either the first or last atlas
    all_terms: set[str] = set()
    for atlas in (first, last):
        for tm in atlas._maps.values():
            all_terms.update(tm.overlap)

    readings: list[BleedReading] = []

    for term in all_terms:
        original_curv = first.curvature(term)
        current_curv = last.curvature(term)

        # Skip terms with no curvature at either end — not interesting
        if original_curv < 0.05 and current_curv < 0.05:
            continue

        rate = round((original_curv - current_curv) / cycles, 4)

        # Estimate when the region will reach near-zero curvature
        if rate > 0 and current_curv >= 0.05:
            estimated_flat = round(current_curv / rate)
        else:
            estimated_flat = -1

        # Closing mode: compare agent coverage in first vs last snapshot
        original_count = _agent_count_for_region(term, first)
        current_count = _agent_count_for_region(term, last)

        delta = abs(original_curv - current_curv)

        if delta < 0.05:
            mode = "stable"
        elif current_curv > original_curv:
            mode = "emerging"
        elif current_count > original_count:
            mode = "resolution"
        else:
            mode = "closure"

        readings.append(BleedReading(
            region=term,
            original_curvature=round(original_curv, 4),
            current_curvature=round(current_curv, 4),
            bleed_rate=rate,
            estimated_flat_at=estimated_flat,
            closing_mode=mode,
        ))

    readings.sort(key=lambda r: r.bleed_rate, reverse=True)
    return readings
