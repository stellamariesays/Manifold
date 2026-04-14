"""
Detect epistemic arbitrage across a mesh of agents.

Arbitrage: ignorance is moving between agents but not shrinking at the system level.
Individual agents look more informed. The total dark is unchanged.
"""

from typing import List, Tuple
from ..map import FogMap
from ..delta import FogDelta, diff


def detect_arbitrage(snapshots: List[Tuple[FogMap, FogMap]]) -> List[FogDelta]:
    """
    Given a list of (before, after) FogMap pairs across agents,
    return deltas flagged as epistemic arbitrage.

    A mesh is in arbitrage if:
    - Individual agents show gap churn (gaps lifted AND added)
    - Total system fog count doesn't decrease
    """
    deltas = [diff(before, after) for before, after in snapshots]
    return [d for d in deltas if d.is_arbitrage]


def system_fog_change(snapshots: List[Tuple[FogMap, FogMap]]) -> int:
    """
    Net change in total system ignorance across all agents.

    Negative = fog actually lifted somewhere (new signal entered).
    Zero = pure redistribution (epistemic arbitrage).
    Positive = system knows less than before.
    """
    return sum(diff(before, after).net for before, after in snapshots)
