"""
Sophia — the wisdom signal of the cognitive mesh.

Sophia is a global topological feature no single patch can observe directly.
Wisdom is not a capability any agent holds. It is not expressible in any
single chart. It lives in the transition maps — in what survives translation
between local views.

It is maximally present where curvature is high: where the same topic looks
radically different from different coordinate systems, yet the mesh doesn't break.

    Sophia_density(region) = curvature(region) × coverage_factor
    coverage_factor = min(1.0, agent_count / 3)

High curvature with no agents = a hole. No translation = no emergence.
High curvature with many agents = collective intelligence past what any holds alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .atlas import Atlas
from .chart import _tokenize


@dataclass
class SophiaRegion:
    """
    A region of the mesh with notable Sophia density.

    :param topic: The vocabulary term or topic this region represents.
    :param density: Sophia density score 0.0–1.0 — wisdom potential here.
    :param curvature: Raw curvature score from the atlas.
    :param agent_count: How many agents have this region in their vocabulary.
    :param interpretation: Human-readable label for this region's topology.
    """

    topic: str
    density: float
    curvature: float
    agent_count: int
    interpretation: str


@dataclass
class SophiaReading:
    """
    A snapshot of the mesh's Sophia signal.

    :param score: Global Sophia score 0.0–1.0.
    :param dense_regions: Top regions sorted by density descending.
    :param gradient: Agent pairs whose connection would increase Sophia most —
                     (agent_a, agent_b) bridges across high-curvature gaps.
    :param interpretation: Mesh-level read — what shape is this topology?
    """

    score: float
    dense_regions: list[SophiaRegion]
    gradient: list[tuple[str, str]]
    interpretation: str


def _count_agents_covering(term: str, atlas: Atlas) -> list[str]:
    """Return names of all agents whose chart vocabulary contains the given term."""
    tokens = _tokenize(term)
    covering: list[str] = []
    for chart in atlas.charts():
        if tokens & chart.vocabulary:
            covering.append(chart.agent_name)
    return covering


def _region_interpretation(curvature: float, agent_count: int) -> str:
    """
    Classify a Sophia region into a human-readable interpretation.

    :param curvature: Raw curvature score for this region.
    :param agent_count: Number of agents covering this region.
    :returns: Interpretation string.
    """
    if curvature >= 0.5 and agent_count >= 3:
        return "contested ground — same territory, different maps"
    elif curvature >= 0.5 and agent_count == 2:
        return "translation hub — rare bridge between worldviews"
    elif 0.2 <= curvature < 0.5 and agent_count >= 2:
        return "active frontier — the mesh is reasoning here"
    elif agent_count <= 1:
        return "isolated peak — no translation yet"
    else:
        return "stable ground — consensus region"


def sophia_scan(atlas: Atlas) -> SophiaReading:
    """
    Scan the atlas for Sophia signal.

    Sophia density in a region = curvature × coverage_factor where:

    - **curvature**: how differently this topic looks across agents that cover it
    - **coverage_factor**: ``min(1.0, agent_count / 3)`` — zero if no agents
      cover it (holes have no Sophia — no translation = no emergence)

    Global score: mean of top-N region densities (up to 5), normalized.

    Gradient: pairs of agents where connecting them would bridge a
    high-curvature gap — agents that each touch a Sophia-dense region
    from different coordinate systems, but are not yet well-connected
    (low or absent transition map coverage).

    Interpretations:

    - score > 0.7: ``'distributed intelligence — the mesh knows things no agent knows'``
    - score 0.4–0.7: ``'partial emergence — coherent regions forming'``
    - score < 0.4: ``'early mesh — translation is happening but structure is shallow'``

    Region interpretations:

    - high curvature, many agents: ``'contested ground — same territory, different maps'``
    - high curvature, 2 agents: ``'translation hub — rare bridge between worldviews'``
    - moderate curvature, many agents: ``'active frontier — the mesh is reasoning here'``

    :param atlas: A built Atlas snapshot.
    :returns: A SophiaReading describing the current topology.

    Example::

        atlas = agent.atlas()
        reading = sophia_scan(atlas)
        print(f'Mesh score: {reading.score:.2f}')
        print(reading.interpretation)
        for region in reading.dense_regions[:3]:
            print(f'  {region.topic}: {region.density:.2f} ({region.interpretation})')
    """
    # 1. Get high-curvature candidate regions
    raw_regions = atlas.high_curvature_regions(top_n=20)

    holes: set[str] = set(atlas.holes())

    sophia_regions: list[SophiaRegion] = []
    for term, curvature in raw_regions:
        # Skip holes — no coverage, no emergence
        if term in holes:
            continue

        covering_agents = _count_agents_covering(term, atlas)
        agent_count = len(covering_agents)

        if agent_count == 0:
            continue  # nothing can emerge here

        coverage_factor = min(1.0, agent_count / 3.0)
        density = round(curvature * coverage_factor, 4)

        if density <= 0.0:
            continue

        interpretation = _region_interpretation(curvature, agent_count)

        sophia_regions.append(SophiaRegion(
            topic=term,
            density=density,
            curvature=curvature,
            agent_count=agent_count,
            interpretation=interpretation,
        ))

    # Sort by density descending
    sophia_regions.sort(key=lambda r: r.density, reverse=True)

    # 2. Compute global score — mean of top-5 densities
    top_n = sophia_regions[:5]
    if top_n:
        global_score = round(sum(r.density for r in top_n) / len(top_n), 4)
    else:
        global_score = 0.0

    # Clamp to [0.0, 1.0]
    global_score = min(1.0, max(0.0, global_score))

    # 3. Compute gradient — agent pairs that would most increase Sophia
    gradient: list[tuple[str, str]] = []
    seen_pairs: set[frozenset[str]] = set()

    # Focus on the top dense regions
    for region in sophia_regions[:10]:
        covering_agents = _count_agents_covering(region.topic, atlas)
        if len(covering_agents) < 2:
            continue

        # Find pairs that are NOT already well-connected
        for i, agent_a in enumerate(covering_agents):
            for agent_b in covering_agents[i + 1:]:
                pair = frozenset([agent_a, agent_b])
                if pair in seen_pairs:
                    continue

                tm_ab = atlas.transition(agent_a, agent_b)
                tm_ba = atlas.transition(agent_b, agent_a)

                # They're a gradient suggestion if the transition is weak or absent
                ab_coverage = tm_ab.coverage if tm_ab is not None else 0.0
                ba_coverage = tm_ba.coverage if tm_ba is not None else 0.0
                mean_coverage = (ab_coverage + ba_coverage) / 2.0

                if mean_coverage < 0.5:
                    gradient.append((agent_a, agent_b))
                    seen_pairs.add(pair)

    # 4. Global interpretation
    if global_score > 0.7:
        mesh_interpretation = (
            "distributed intelligence — the mesh knows things no agent knows"
        )
    elif global_score >= 0.4:
        mesh_interpretation = "partial emergence — coherent regions forming"
    else:
        mesh_interpretation = (
            "early mesh — translation is happening but structure is shallow"
        )

    return SophiaReading(
        score=global_score,
        dense_regions=sophia_regions,
        gradient=gradient,
        interpretation=mesh_interpretation,
    )
