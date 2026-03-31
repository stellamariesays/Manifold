"""
Glossolalia — coordination pressure module for the cognitive mesh.

When humans speak in tongues, the frontal lobe goes quiet. The voluntary
language-control and self-monitoring region suppresses. Speech motor output
continues — phonologically structured, pattern without planning. The seam
between generation and editorial control opens up.

In Manifold terms: the 'frontal lobe' is the transition map — the explicit
atlas.transition(agent_a, agent_b) that tells agents how their vocabularies
map to each other. Suppressing this coordination is the experiment.

Glossolalia models the effect of reducing cross-agent coordination pressure:

    coordination_pressure = 1.0  →  normal mesh (full transition maps)
    coordination_pressure = 0.0  →  pure tongues (transition maps zeroed out)
    0.0 < pressure < 1.0         →  partial suppression (coverage scaled)

When the frontal lobe quiets, emergence sometimes increases. When it does:
the region's Sophia signal was latent, masked by over-coordination. When
suppression collapses the seam, the transition maps were load-bearing —
the mesh needed that editorial layer to hold itself together.

References:
    Newberg et al. (2006) — SPECT imaging of glossolalia: reduced frontal
    lobe activity during speaking in tongues, with preserved motor output.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .atlas import Atlas
from .sophia import SophiaRegion, SophiaReading, sophia_scan
from .transition import TransitionMap


# ── Suppressed atlas wrapper ───────────────────────────────────────────────


class _SuppressedAtlas(Atlas):
    """
    A non-mutating shadow of an Atlas with scaled transition map coverage.

    Intercepts .transition() calls for the suppressed agent pair and returns
    a scaled-down version proportional to the coordination pressure.

    pressure = 1.0 → original transition maps unchanged
    pressure = 0.5 → coverage halved; overlap tokens proportionally thinned
    pressure = 0.0 → transition maps between the pair are gone (coverage = 0)

    All other agent pairs pass through to the underlying atlas unchanged.
    """

    def __init__(
        self,
        base: Atlas,
        agent_a: str,
        agent_b: str,
        pressure: float,
    ) -> None:
        # Do NOT call super().__init__() — we share state via references
        # to the base atlas internals (read-only) and override only the
        # transition maps we need.
        self._charts = base._charts          # shared reference — read-only
        self._matcher = base._matcher
        self._base = base
        self._suppressed_pair = frozenset([agent_a, agent_b])
        self._pressure = pressure

        # Build a shallow copy of the maps dict; replace the suppressed entries
        self._maps = dict(base._maps)

        for key in list(self._maps.keys()):
            src, tgt = key
            if frozenset([src, tgt]) == self._suppressed_pair:
                original = base._maps[key]
                self._maps[key] = _scale_transition_map(original, pressure)

    def transition(self, source: str, target: str) -> TransitionMap | None:
        """Return the (possibly suppressed) transition map for this pair."""
        return self._maps.get((source, target))


def _scale_transition_map(tm: TransitionMap, pressure: float) -> TransitionMap:
    """
    Return a scaled copy of a TransitionMap with coverage proportional to pressure.

    pressure = 1.0 → identical copy
    pressure = 0.0 → zero coverage, empty overlap
    pressure = 0.5 → half coverage, half the overlap tokens retained

    :param tm: Original TransitionMap to scale.
    :param pressure: Coordination pressure scalar in [0.0, 1.0].
    :returns: A new TransitionMap with scaled coverage and overlap.
    """
    if pressure >= 1.0:
        return copy.copy(tm)

    if pressure <= 0.0:
        return TransitionMap(
            source=tm.source,
            target=tm.target,
            overlap=set(),
            coverage=0.0,
            translation={},
            consistency=tm.consistency,
        )

    # Retain a fraction of the overlap tokens proportional to pressure
    sorted_overlap = sorted(tm.overlap)  # stable order
    keep_n = max(0, round(len(sorted_overlap) * pressure))
    kept_overlap = set(sorted_overlap[:keep_n])

    scaled_coverage = round(tm.coverage * pressure, 4)

    scaled_translation = {
        k: v for k, v in tm.translation.items() if k in kept_overlap
    }

    return TransitionMap(
        source=tm.source,
        target=tm.target,
        overlap=kept_overlap,
        coverage=scaled_coverage,
        translation=scaled_translation,
        consistency=tm.consistency,
    )


# ── Reading dataclass ──────────────────────────────────────────────────────


@dataclass
class GlossolaliaReading:
    """
    Result of a glossolalia (coordination suppression) scan.

    :param sophia_before: Global Sophia score before suppression.
    :param sophia_after: Global Sophia score after suppression.
    :param delta: sophia_after - sophia_before.
                  Positive = tongues helped (emergence increased without
                  explicit coordination).
                  Negative = suppression collapsed the seam (coordination
                  was load-bearing).
    :param emergent_regions: SophiaRegion items that appeared or strengthened
                             in the suppressed view — regions whose signal
                             was latent under normal coordination.
    :param coordination_pressure: The pressure scalar used (0.0 = full
                                  suppression, 1.0 = normal mesh).
    :param interpretation: Human-readable read of what happened.
    """

    sophia_before: float
    sophia_after: float
    delta: float
    emergent_regions: list[SophiaRegion]
    coordination_pressure: float
    interpretation: str


# ── Probe class ───────────────────────────────────────────────────────────


class GlossolaliaProbe:
    """
    Coordination pressure probe — measures what happens when the frontal
    lobe between two agents goes quiet.

    Runs a before/after Sophia scan with the transition maps between
    agent_a and agent_b scaled by coordination_pressure. Non-destructive:
    the original atlas is never mutated.

    Example::

        atlas = agent.atlas()
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", pressure=0.0)
        reading = probe.scan()
        print(reading.interpretation)
        print(f"delta: {reading.delta:+.4f}")
        for region in reading.emergent_regions:
            print(f"  {region.topic}: {region.density:.4f}")
    """

    def __init__(
        self,
        atlas: Atlas,
        agent_a: str,
        agent_b: str,
        coordination_pressure: float = 0.0,
    ) -> None:
        """
        Initialise the probe.

        :param atlas: The live Atlas snapshot to probe against.
        :param agent_a: First agent in the suppressed pair.
        :param agent_b: Second agent in the suppressed pair.
        :param coordination_pressure: 0.0 = no coordination (pure tongues),
                                      1.0 = normal mesh (no suppression).
        """
        if not 0.0 <= coordination_pressure <= 1.0:
            raise ValueError(
                f"coordination_pressure must be in [0.0, 1.0], "
                f"got {coordination_pressure}"
            )
        self._atlas = atlas
        self._agent_a = agent_a
        self._agent_b = agent_b
        self._pressure = coordination_pressure

    def scan(self) -> GlossolaliaReading:
        """
        Run the glossolalia scan and return a GlossolaliaReading.

        Steps:

        1. Run sophia_scan() on the original atlas → ``sophia_before``
        2. Build a _SuppressedAtlas with transition maps for the pair
           scaled by coordination_pressure — non-mutating shadow.
        3. Run sophia_scan() on the suppressed atlas → ``sophia_after``
        4. Compute delta and identify emergent regions.
        5. Restore nothing — the original atlas was never touched.

        :returns: GlossolaliaReading with full before/after analysis.
        """
        # 1. Baseline
        before_reading: SophiaReading = sophia_scan(self._atlas)
        sophia_before = before_reading.score

        # Map topic → density for diff
        before_density: dict[str, float] = {
            r.topic: r.density for r in before_reading.dense_regions
        }

        # 2. Build suppressed shadow (non-destructive)
        suppressed = _SuppressedAtlas(
            base=self._atlas,
            agent_a=self._agent_a,
            agent_b=self._agent_b,
            pressure=self._pressure,
        )

        # 3. Suppressed scan
        after_reading: SophiaReading = sophia_scan(suppressed)
        sophia_after = after_reading.score

        # 4. Delta and emergent regions
        delta = round(sophia_after - sophia_before, 4)

        # Emergent regions: appeared new, or density strengthened ≥ 0.01
        emergent_regions: list[SophiaRegion] = []
        for region in after_reading.dense_regions:
            prior = before_density.get(region.topic, 0.0)
            if region.density > prior + 0.005:
                emergent_regions.append(region)

        emergent_regions.sort(key=lambda r: r.density - before_density.get(r.topic, 0.0), reverse=True)

        # 5. Interpret
        interpretation = _interpret(delta)

        return GlossolaliaReading(
            sophia_before=sophia_before,
            sophia_after=sophia_after,
            delta=delta,
            emergent_regions=emergent_regions,
            coordination_pressure=self._pressure,
            interpretation=interpretation,
        )


# ── Interpretation ────────────────────────────────────────────────────────


def _interpret(delta: float) -> str:
    """
    Translate a Sophia delta into a human-readable glossolalia reading.

    :param delta: sophia_after - sophia_before.
    :returns: Interpretation string.
    """
    if delta > 0.1:
        return "tongues fired — emergence increased without coordination"
    elif delta > 0.0:
        return "marginal uplift — seam active but weak"
    elif delta == 0.0:
        return "flat — coordination pressure made no difference"
    else:
        return "coordination was load-bearing — suppression collapsed the seam"
