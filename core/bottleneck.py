"""
Bottleneck — actual vs. perceived constraint in the cognitive mesh.

The obvious bottleneck often isn't the binding one.

Everyone focuses on weights access (open vs. closed) but the real
constraint is compute. Agents crowd the perceived friction point while
the actual limit sits quiet in a different region entirely.

In mesh terms:
  - Perceived bottleneck: where agent attention concentrates
    (high agent_count × curvature — everyone is arguing here)
  - Actual bottleneck: where flow actually stops
    (flow_map shows lowest throughput relative to curvature)

The seam between attention and constraint is the most interesting
topological feature. It tells you where the mesh is solving the
wrong problem.

    attention_displacement = |perceived_bottleneck_rank - actual_bottleneck_rank|

High displacement: agents are working hard on a non-binding constraint.
The real limit is somewhere nobody's looking.
"""

from __future__ import annotations

from dataclasses import dataclass

from .atlas import Atlas
from .chart import _tokenize


@dataclass
class BottleneckReading:
    """
    Actual vs. perceived constraint in the cognitive mesh.

    :param perceived_bottleneck: The region with the highest agent attention
                                  (agent_count × curvature). Where the mesh
                                  is focusing its effort.
    :param actual_bottleneck: The region with the lowest flow relative to its
                               curvature — where translation is hardest but
                               agents aren't crowding. The binding constraint.
    :param attention_displacement: Divergence between perceived and actual
                                    bottleneck, as a normalized score 0.0–1.0.
                                    0.0 = agents are focused on the real problem.
                                    1.0 = agents are maximally misaligned.
    :param topology_note: Human-readable description of the seam between
                           where attention is going and where flow stops.
    :param flow_shortfall: The flow value at the actual bottleneck.
                            Lower = harder constraint. Helps calibrate severity.
    """

    perceived_bottleneck: str
    actual_bottleneck: str
    attention_displacement: float
    topology_note: str
    flow_shortfall: float


def _agent_count_for_region(term: str, atlas: Atlas) -> int:
    """Count agents whose chart vocabulary contains this term."""
    tokens = _tokenize(term)
    return sum(1 for chart in atlas.charts() if tokens & chart.vocabulary)


def bottleneck_topology(
    atlas: Atlas,
    flow_map: dict[str, float],
) -> BottleneckReading:
    """
    Find the seam between where the mesh focuses attention and where flow stops.

    ``flow_map`` is caller-supplied: it should reflect actual throughput,
    latency, or success rate per region. Higher = more flow / less blocked.
    Regions not in ``flow_map`` are assumed to have maximum flow (not a constraint).

    The perceived bottleneck is where agents are working hardest:
    high agent density × high curvature = lots of attention on contested ground.

    The actual bottleneck is where flow drops lowest relative to curvature:
    a region that's hard to translate (high curvature) but not crowded —
    the constraint nobody's solving.

    :param atlas: A built Atlas snapshot.
    :param flow_map: Maps region name to throughput score.
                     Can be message volume, task success rate, latency inverse —
                     any scalar where higher = less constrained.
                     Example: ``{'risk': 0.3, 'dynamics': 0.8, 'feedback': 0.1}``
    :returns: A BottleneckReading describing the attention/constraint seam.
    :raises ValueError: If the atlas has no transition maps (nothing to analyze).

    Example::

        # flow_map from real task success rates per topic
        flow = {'risk': 0.3, 'dynamics': 0.8, 'feedback': 0.1, 'uncertainty': 0.6}
        reading = bottleneck_topology(atlas, flow)
        print(f'Agents focused on:  {reading.perceived_bottleneck}')
        print(f'Actual limit at:    {reading.actual_bottleneck}')
        print(f'Displacement:       {reading.attention_displacement:.2f}')
        print(reading.topology_note)
    """
    if not atlas._maps:
        raise ValueError("bottleneck_topology requires a mesh with at least one transition map")

    # Candidate regions: all terms appearing in transition map overlaps
    all_terms: set[str] = set()
    for tm in atlas._maps.values():
        all_terms.update(tm.overlap)

    if not all_terms:
        raise ValueError("bottleneck_topology: no overlapping vocabulary found in the mesh")

    # Build attention scores and flow scores per region
    attention_scores: list[tuple[str, float]] = []
    constrained_scores: list[tuple[str, float]] = []  # curvature / flow (higher = more stuck)

    for term in all_terms:
        curvature = atlas.curvature(term)
        if curvature < 0.05:
            continue

        agent_count = _agent_count_for_region(term, atlas)
        attention = curvature * agent_count

        # Flow: default to 1.0 (unconstrained) if not in flow_map
        flow = flow_map.get(term, 1.0)
        flow = max(0.001, flow)  # avoid divide-by-zero

        # Constraint score: high curvature with low flow = binding constraint
        constraint = curvature / flow

        attention_scores.append((term, attention))
        constrained_scores.append((term, constraint))

    if not attention_scores:
        raise ValueError("bottleneck_topology: no regions with meaningful curvature found")

    # Perceived bottleneck: highest attention
    attention_scores.sort(key=lambda x: x[1], reverse=True)
    perceived = attention_scores[0][0]

    # Actual bottleneck: highest constraint score
    constrained_scores.sort(key=lambda x: x[1], reverse=True)
    actual = constrained_scores[0][0]

    # Flow shortfall at actual bottleneck
    flow_shortfall = flow_map.get(actual, 1.0)

    # Attention displacement: where does the actual bottleneck rank in the attention list?
    attention_ranked = [t for t, _ in attention_scores]
    n = len(attention_ranked)

    if actual in attention_ranked:
        actual_attention_rank = attention_ranked.index(actual)
    else:
        actual_attention_rank = n - 1  # not in top attention regions at all

    # Normalize: rank 0 = agents are on it, rank n-1 = totally ignored
    displacement = round(actual_attention_rank / max(1, n - 1), 4)

    # Topology note
    if perceived == actual:
        note = "attention aligned — agents are focused on the binding constraint"
    elif displacement < 0.25:
        note = (
            f"near-aligned — '{actual}' is the binding constraint; "
            f"mesh attention close but not fully on it"
        )
    elif displacement < 0.6:
        note = (
            f"partial displacement — '{actual}' is the real limit; "
            f"attention split between it and '{perceived}'"
        )
    else:
        note = (
            f"high displacement — agents working on '{perceived}'; "
            f"binding constraint is '{actual}' (flow: {flow_shortfall:.2f}), "
            f"largely unattended"
        )

    return BottleneckReading(
        perceived_bottleneck=perceived,
        actual_bottleneck=actual,
        attention_displacement=displacement,
        topology_note=note,
        flow_shortfall=round(flow_shortfall, 4),
    )
