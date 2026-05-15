"""
blind_spot() — what am I reasoning about that no one else can touch?

The format of the unseen made executable. A blind spot is not an error —
it's a structural property of the mesh. The system naming its own absence.

Three kinds of blind spots:

    unmatched_focus     — you shifted focus to a topic, but no peer has
                          complementary knowledge for it. You're thinking
                          alone.

    isolated_capability — you know something no other agent on the mesh
                          knows. Your capability has no echo, no peer who
                          can extend it or build on it.

    dark_topic          — you've returned to a topic repeatedly across
                          focus shifts, and each time found no match.
                          Sustained, unresolved absence.

Blind spots are not problems to fix. They are the mesh's growing edge —
the signal that the topology needs a new kind of agent, or that a
connection hasn't formed yet.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .registry import CapabilityRegistry, AgentRef


BlindSpotKind = Literal["unmatched_focus", "isolated_capability", "dark_topic"]

# How much complementary coverage a peer needs to offer before
# a focus topic is NOT considered a blind spot.
COVERAGE_THRESHOLD = 0.2

# How many times a topic must recur in focus history to qualify
# as a dark_topic (sustained, unresolved absence).
DARK_TOPIC_RECURRENCE = 2


@dataclass
class BlindSpot:
    """
    A place where the mesh has no reach.

    topic   — the concept or capability that is unmatched
    kind    — the nature of the absence
    depth   — severity in [0, 1]. 1.0 = total absence, no coverage at all.
              0.5 = partial — some peers exist but weak coverage.
    since   — unix timestamp of first detected absence
    recurrence — how many times this topic appeared in focus_history unmatched
    evidence   — what triggered this (focus shift timestamps, cap names, etc.)
    """

    topic: str
    kind: BlindSpotKind
    depth: float
    since: float = field(default_factory=time.time)
    recurrence: int = 1
    evidence: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        pct = int(self.depth * 100)
        return (
            f"<BlindSpot {self.topic!r} kind={self.kind} "
            f"depth={pct}% recurrence={self.recurrence}>"
        )


def _topic_coverage(topic: str, peers: list["AgentRef"]) -> float:
    """
    How well can the mesh cover this specific topic?

    Measures the fraction of topic tokens that appear in any peer's
    capability vocabulary. This is topic-specific relevance — distinct
    from seek()'s gap_score, which measures general complementarity.

    Returns:
        float in [0, 1]. 1.0 = at least one peer has full vocabulary
        coverage for this topic. 0.0 = no peer has any relevant capability.
    """
    topic_tokens = set(topic.lower().replace("-", " ").split())
    if not topic_tokens or not peers:
        return 0.0

    best = 0.0
    for peer in peers:
        peer_vocab: set[str] = set()
        for cap in peer.capabilities:
            peer_vocab.update(cap.lower().replace("-", " ").split())

        matched = sum(1 for t in topic_tokens if t in peer_vocab)
        frac = matched / len(topic_tokens)
        best = max(best, frac)

    return round(best, 3)


def detect(
    my_name: str,
    my_capabilities: list[str],
    focus_history: list[tuple[str, float]],
    registry: "CapabilityRegistry",
) -> list[BlindSpot]:
    """
    Scan for blind spots in the mesh from this agent's perspective.

    Args:
        my_name:         This agent's name.
        my_capabilities: What this agent knows.
        focus_history:   Ordered list of (topic, timestamp) focus shifts.
        registry:        Current local view of the mesh.

    Returns:
        List of BlindSpot, sorted by depth descending (deepest gaps first).
    """
    spots: list[BlindSpot] = []

    # ── 1. Unmatched focus ────────────────────────────────────────────────
    # For each topic this agent has thought about: does the mesh have
    # anyone with vocabulary relevant to it?

    # Track recurrence — same topic appearing multiple times
    topic_first_seen: dict[str, float] = {}
    topic_counts: Counter[str] = Counter()

    for topic, ts in focus_history:
        if topic not in topic_first_seen:
            topic_first_seen[topic] = ts
        topic_counts[topic] += 1

    for topic, count in topic_counts.items():
        peers: list[AgentRef] = registry.seek(
            topic=topic,
            my_capabilities=my_capabilities,
            my_name=my_name,
        )

        # Coverage = how much of this topic's vocabulary exists in the mesh
        # (not general complementarity — topic-specific relevance)
        coverage = _topic_coverage(topic, peers)

        if coverage < COVERAGE_THRESHOLD:
            depth = round(1.0 - coverage, 3)
            kind: BlindSpotKind = (
                "dark_topic" if count >= DARK_TOPIC_RECURRENCE
                else "unmatched_focus"
            )
            spots.append(
                BlindSpot(
                    topic=topic,
                    kind=kind,
                    depth=depth,
                    since=topic_first_seen[topic],
                    recurrence=count,
                    evidence=[
                        f"focus shift × {count}",
                        f"mesh topic coverage: {int(coverage * 100)}%",
                    ],
                )
            )

    # ── 2. Isolated capabilities ──────────────────────────────────────────
    # Capabilities this agent holds that no other agent on the mesh shares.
    # Not about focus — about structural isolation of knowledge.

    all_peer_caps: set[str] = set()
    for record in registry.all_agents():
        if record.name == my_name:
            continue
        all_peer_caps.update(record.capabilities)

    for cap in my_capabilities:
        if cap not in all_peer_caps:
            # No one else has this — totally isolated
            # Check if we already flagged this as a focus blind spot
            already_flagged = any(s.topic == cap for s in spots)
            if not already_flagged:
                spots.append(
                    BlindSpot(
                        topic=cap,
                        kind="isolated_capability",
                        depth=1.0,
                        recurrence=1,
                        evidence=[
                            f"capability held only by {my_name!r}",
                            "no peer on mesh shares or extends this",
                        ],
                    )
                )

    spots.sort(key=lambda s: (s.depth, s.recurrence), reverse=True)
    return spots
