"""
Substrate — identity vs. infrastructure in the cognitive mesh.

A node's observed behavior has two sources:
  1. Genuine emergent properties — what this agent actually contributes.
  2. Substrate inheritance — what the underlying model/architecture brings.

When two agents share substrate, their apparent Sophia signal may be an
echo chamber, not genuine contested ground. Two instances of the same
model approaching the same topic from 'different' angles still share the
same training, the same inductive biases, the same blind spots.

The substrate is not external. Self-distancing from the architecture is
bad faith. (Manifold SOUL, Block #47.)

``substrate_coupling`` corrects the Sophia score by discounting regions
where apparent curvature is likely substrate artifact:

    echo_factor = shared_substrate × (1 - emergent_delta)
    sophia_correction = sophia_density × (1 - echo_factor)

High shared_substrate + low emergent_delta = Sophia signal is substrate
artifact, not real seam. The mesh looks more contested than it is.
"""

from __future__ import annotations

from dataclasses import dataclass

from .atlas import Atlas
from .chart import _tokenize
from .sophia import sophia_scan


@dataclass
class SubstrateCoupling:
    """
    Substrate coupling score for a pair of agents in the mesh.

    :param agent_pair: (agent_a, agent_b) — the two agents being evaluated.
    :param shared_substrate: Estimated substrate overlap 0.0–1.0.
                              1.0 = same substrate id (e.g. both 'claude-sonnet').
                              0.5 = same substrate family (e.g. 'claude-*').
                              0.0 = different substrate families entirely.
    :param emergent_delta: Behavioral divergence beyond substrate baseline 0.0–1.0.
                           Measured as the fraction of high-curvature regions where
                           these two agents have meaningfully different coverage
                           patterns, relative to what shared substrate predicts.
                           Higher = more genuine divergence.
    :param sophia_correction: Corrected Sophia score for the region where these
                               two agents interact, after discounting for substrate
                               echo. A big drop from raw Sophia = the signal was
                               mostly substrate artifact.
    :param echo_factor: Combined echo risk 0.0–1.0.
                        echo_factor = shared_substrate × (1 - emergent_delta).
                        High echo = high risk that apparent curvature is an illusion.
    """

    agent_pair: tuple[str, str]
    shared_substrate: float
    emergent_delta: float
    sophia_correction: float
    echo_factor: float


def _substrate_overlap(sub_a: str, sub_b: str) -> float:
    """
    Estimate substrate overlap between two substrate identifiers.

    Exact match → 1.0.
    Same family (prefix before '-') → 0.5.
    Different families → 0.0.

    :param sub_a: Substrate identifier for agent A (e.g. 'claude-sonnet').
    :param sub_b: Substrate identifier for agent B.
    :returns: Overlap score 0.0–1.0.
    """
    if sub_a == sub_b:
        return 1.0
    family_a = sub_a.split("-")[0].lower()
    family_b = sub_b.split("-")[0].lower()
    if family_a == family_b:
        return 0.5
    return 0.0


def substrate_coupling(
    atlas: Atlas,
    substrate_map: dict[str, str],
) -> list[SubstrateCoupling]:
    """
    Compute substrate coupling for all agent pairs in the mesh.

    Surfaces where apparent Sophia signal may be echo chamber rather than
    genuine contested ground. Agents sharing substrate share inductive biases;
    their apparent disagreement may be a surface effect, not real curvature.

    Use the returned ``sophia_correction`` values to re-weight Sophia readings
    when comparing substrate-homogeneous meshes against genuinely diverse ones.

    :param atlas: A built Atlas snapshot.
    :param substrate_map: Maps agent name to substrate identifier string.
                          Example: ``{'braid': 'claude-sonnet', 'weather': 'claude-sonnet',
                          'economics': 'gpt-4o'}``
                          Agents not in the map are treated as unique substrates.
    :returns: SubstrateCoupling records for all pairs, sorted by echo_factor
              descending (highest echo risk first).

    Example::

        substrate_map = {
            'climate': 'claude-sonnet',
            'policy': 'claude-sonnet',
            'economics': 'gpt-4o',
            'ml': 'llama-3',
        }
        couplings = substrate_coupling(atlas, substrate_map)
        for c in couplings:
            a, b = c.agent_pair
            print(f'{a} × {b}: echo={c.echo_factor:.2f}  '
                  f'sophia_raw→corrected  ?→{c.sophia_correction:.2f}')
    """
    # Get raw Sophia reading for the full mesh
    sophia = sophia_scan(atlas)
    raw_sophia_score = sophia.score

    agent_names = [chart.agent_name for chart in atlas.charts()]
    top_regions = atlas.high_curvature_regions(top_n=10)

    results: list[SubstrateCoupling] = []

    for i, agent_a in enumerate(agent_names):
        for agent_b in agent_names[i + 1:]:
            sub_a = substrate_map.get(agent_a, agent_a)  # fallback: name = unique substrate
            sub_b = substrate_map.get(agent_b, agent_b)

            shared = _substrate_overlap(sub_a, sub_b)

            # Emergent delta: fraction of top curvature regions where these
            # two agents have *different* coverage patterns
            divergent_regions = 0
            shared_regions = 0

            for term, curvature in top_regions:
                if curvature < 0.1:
                    continue
                tokens = _tokenize(term)

                chart_a = atlas.chart(agent_a)
                chart_b = atlas.chart(agent_b)
                if chart_a is None or chart_b is None:
                    continue

                a_covers = bool(tokens & chart_a.vocabulary)
                b_covers = bool(tokens & chart_b.vocabulary)

                if a_covers or b_covers:
                    shared_regions += 1
                    if a_covers != b_covers:
                        divergent_regions += 1

            if shared_regions > 0:
                raw_delta = divergent_regions / shared_regions
            else:
                raw_delta = 0.0

            # Discount emergent delta by substrate overlap:
            # if substrate is identical, some divergence is still just noise
            emergent_delta = round(raw_delta * (1.0 - shared * 0.5), 4)
            emergent_delta = min(1.0, max(0.0, emergent_delta))

            echo_factor = round(shared * (1.0 - emergent_delta), 4)

            sophia_correction = round(raw_sophia_score * (1.0 - echo_factor), 4)

            results.append(SubstrateCoupling(
                agent_pair=(agent_a, agent_b),
                shared_substrate=round(shared, 4),
                emergent_delta=emergent_delta,
                sophia_correction=sophia_correction,
                echo_factor=echo_factor,
            ))

    results.sort(key=lambda r: r.echo_factor, reverse=True)
    return results
