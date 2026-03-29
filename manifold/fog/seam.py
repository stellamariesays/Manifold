"""
FogSeam — the boundary between two agents' fog maps.

This is the epistemic complement to Sophia. Sophia measures where
the mesh holds high curvature across agents that *know*. FogSeam
measures where agents *don't know differently* — asymmetric blindness.

Asymmetric gaps = transfer potential. Agent A is dark on something
Agent B is light on, and vice versa. That asymmetry is signal.

Zero tension = same fog everywhere = pure arbitrage territory.
High tension = agents have different blind spots = genuine exchange possible.
"""

from dataclasses import dataclass
from typing import Set
from .map import FogMap


@dataclass
class FogSeam:
    """
    Boundary region between two agents' fog states.

    :param agent_a: Name of first agent.
    :param agent_b: Name of second agent.
    :param only_in_a: Gaps A has that B doesn't — B may have signal A lacks.
    :param only_in_b: Gaps B has that A doesn't — A may have signal B lacks.
    :param shared: Both dark on this — genuine system gap, needs external signal.
    :param tension: Ratio of asymmetric gaps to total (0.0–1.0).
    """

    agent_a: str
    agent_b: str
    only_in_a: Set[str]
    only_in_b: Set[str]
    shared: Set[str]

    @property
    def tension(self) -> float:
        """
        Seam tension: fraction of gaps that are asymmetric.

        High tension → agents have different blind spots → transfer potential.
        Zero tension → same fog everywhere → pure arbitrage territory.
        This is the Sophia gradient's epistemic inverse: where to route next.
        """
        total = len(self.only_in_a) + len(self.only_in_b) + len(self.shared)
        if total == 0:
            return 0.0
        return round((len(self.only_in_a) + len(self.only_in_b)) / total, 4)

    @property
    def system_gaps(self) -> Set[str]:
        """Gaps neither agent can fill from the other — need external signal."""
        return self.shared

    def interpretation(self) -> str:
        t = self.tension
        if t > 0.7:
            return "high-potential seam — asymmetric blind spots, strong transfer signal"
        elif t > 0.4:
            return "active seam — partial overlap, exchange probable"
        elif t > 0.0:
            return "low-tension seam — mostly shared fog, limited exchange value"
        else:
            return "flat seam — identical fog, no transfer possible"

    def summary(self) -> str:
        return (
            f"FogSeam({self.agent_a}↔{self.agent_b}) "
            f"tension={self.tension:.2f} "
            f"A-only={len(self.only_in_a)} "
            f"B-only={len(self.only_in_b)} "
            f"shared={len(self.shared)} "
            f"— {self.interpretation()}"
        )


def measure(map_a: FogMap, map_b: FogMap) -> FogSeam:
    """Measure the seam between two agents' fog maps."""
    a_keys = set(map_a.gaps.keys())
    b_keys = set(map_b.gaps.keys())
    return FogSeam(
        agent_a=map_a.agent_id,
        agent_b=map_b.agent_id,
        only_in_a=a_keys - b_keys,
        only_in_b=b_keys - a_keys,
        shared=a_keys & b_keys,
    )
