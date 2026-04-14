"""
FogDelta — the change in fog between two FogMap snapshots.

Negative net = fog lifted (new signal entered).
Zero net      = epistemic arbitrage (ignorance redistributed, not reduced).
Positive net  = fog deepened.
"""

from dataclasses import dataclass
from typing import Set
from .map import FogMap


@dataclass
class FogDelta:
    agent_id: str
    gaps_lifted: Set[str]
    gaps_added: Set[str]
    gaps_unchanged: Set[str]

    @property
    def net(self) -> int:
        """Net change in fog. Negative is good."""
        return len(self.gaps_added) - len(self.gaps_lifted)

    @property
    def is_arbitrage(self) -> bool:
        """
        True if fog moved but didn't shrink.
        Gaps lifted AND added, net zero — ignorance redistributed, not reduced.
        The system looks more informed. The total dark is unchanged.
        """
        return len(self.gaps_lifted) > 0 and self.net == 0

    @property
    def is_lift(self) -> bool:
        """True if fog genuinely shrank — new signal entered the system."""
        return self.net < 0

    @property
    def is_deepening(self) -> bool:
        """True if the agent knows less than before."""
        return self.net > 0

    def summary(self) -> str:
        if self.net == 0 and len(self.gaps_lifted) == 0:
            return f"[{self.agent_id}] static — no change"
        if self.is_arbitrage:
            return (
                f"[{self.agent_id}] arbitrage — "
                f"+{len(self.gaps_added)} -{len(self.gaps_lifted)} net=0 "
                f"(ignorance redistributed, not reduced)"
            )
        if self.is_lift:
            return f"[{self.agent_id}] lift — net={self.net} (fog clearing)"
        return f"[{self.agent_id}] deepening — net=+{self.net}"


def diff(before: FogMap, after: FogMap) -> FogDelta:
    """Compute the fog delta between two map snapshots."""
    before_keys = set(before.gaps.keys())
    after_keys = set(after.gaps.keys())
    return FogDelta(
        agent_id=before.agent_id,
        gaps_lifted=before_keys - after_keys,
        gaps_added=after_keys - before_keys,
        gaps_unchanged=before_keys & after_keys,
    )
