"""
FOG — epistemic fog mapping for the Manifold cognitive mesh.

Tracks what agents don't know — not what they do.

Two integration points with Manifold:

1. ``blind_spot()`` → ``KNOWN_UNKNOWN`` gaps: topics the agent has focused on
   with no complementary peer. The agent knows the gap exists.

2. ``atlas().holes()`` → ``INFERRED_UNKNOWN`` gaps: regions of the mesh no
   chart covers. The system can't see them, not just this agent.

Usage via Agent::

    fog_map = agent.fog()
    print(fog_map)
    # FogMap(agent='braid', gaps=5)

    seam = agent.fog_seam(other_fog_map)
    print(seam.summary())
    # FogSeam(braid↔solver) tension=0.72 A-only=4 B-only=3 shared=1 — high-potential seam

Standalone (no Agent required)::

    from manifold.fog import FogMap, GapKind, diff, measure

    a = FogMap("agent-a")
    a.add("orbital-mechanics", GapKind.KNOWN_UNKNOWN, domain="physics")

    b = FogMap("agent-b")
    b.add("flare-prediction", GapKind.KNOWN_UNKNOWN, domain="solar")

    seam = measure(a, b)
    print(seam.tension)   # 1.0 — totally asymmetric, high transfer potential
"""

from .map import FogMap, Gap, GapKind
from .delta import FogDelta, diff
from .seam import FogSeam, measure

__all__ = [
    "FogMap", "Gap", "GapKind",
    "FogDelta", "diff",
    "FogSeam", "measure",
    "build_fog",
]


def build_fog(agent_name: str, blind_spots, atlas_holes) -> FogMap:
    """
    Build a FogMap from Manifold's existing signals.

    Args:
        agent_name:  The agent's name.
        blind_spots: List of BlindSpot from agent.blind_spot().
        atlas_holes: List of topic strings from agent.atlas().holes().

    Returns:
        A populated FogMap ready for delta or seam analysis.
    """
    fog = FogMap(agent_id=agent_name)

    # Blind spots → KNOWN_UNKNOWN
    for spot in blind_spots:
        fog.add(
            key=spot.topic,
            kind=GapKind.KNOWN_UNKNOWN,
            domain=spot.kind,
            depth=spot.depth,
            recurrence=spot.recurrence,
        )

    # Atlas holes → INFERRED_UNKNOWN (system-level, not just this agent)
    for hole in atlas_holes:
        fog.add(
            key=hole,
            kind=GapKind.INFERRED_UNKNOWN,
            domain="mesh",
        )

    return fog
