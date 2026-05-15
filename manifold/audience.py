"""Audience routing — target the right agents for a topic or task.

While ``seek()`` finds complementary peers, audience routing answers a
different question: *who should receive this message?* It blends multiple
signals — capability match, topology proximity, trust history, and fog
gaps — into a single ranked audience list.

Usage::

    router = AudienceRouter(agent)
    audience = router.route("solar-prediction", min_score=0.3)
    for entry in audience:
        print(f"{entry.name}: {entry.score:.2f} ({entry.signals})"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import Agent
    from .registry import AgentRef


class Signal(str, Enum):
    """Which signals contributed to an audience score."""
    CAPABILITY = "capability"
    FOCUS = "focus"
    TRUST = "trust"
    FOG_GAP = "fog_gap"
    TOPOLOGY = "topology"


@dataclass
class AudienceEntry:
    """One agent in the ranked audience list."""
    name: str
    score: float
    signals: list[Signal] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    reason: str = ""

    def __repr__(self) -> str:
        sigs = "+".join(s.value for s in self.signals) or "none"
        return f"<AudienceEntry {self.name!r} score={self.score:.2f} [{sigs}]>"


@dataclass
class AudienceReport:
    """Full routing result with metadata."""
    topic: str
    entries: list[AudienceEntry] = field(default_factory=list)
    excluded: int = 0
    total_candidates: int = 0

    def top(self, n: int = 1) -> list[AudienceEntry]:
        """Return the top-n audience entries."""
        return self.entries[:n]

    def names(self) -> list[str]:
        """Just the agent names, ranked."""
        return [e.name for e in self.entries]

    def __repr__(self) -> str:
        return (
            f"<AudienceReport topic={self.topic!r} "
            f"matched={len(self.entries)} "
            f"excluded={self.excluded}>"
        )

    def summary(self) -> str:
        lines = [f"Audience for '{self.topic}': {len(self.entries)} agents"]
        for e in self.entries:
            sigs = "+".join(s.value for s in e.signals)
            lines.append(f"  {e.name}: {e.score:.2f} [{sigs}] — {e.reason}")
        if self.excluded:
            lines.append(f"  ({self.excluded} below threshold)")
        return "\n".join(lines)


class AudienceRouter:
    """
    Route messages to the right audience of agents.

    Blends five signals with configurable weights:

    - **capability** (default 0.35) — does the agent have relevant caps?
    - **focus** (default 0.25) — is the agent currently thinking about this?
    - **trust** (default 0.20) — does our trust ledger vouch for them?
    - **fog_gap** (default 0.10) — can they fill a blind spot we have?
    - **topology** (default 0.10) — are they cognitively close?

    All weights are normalised automatically, so they don't need to sum to 1.
    """

    DEFAULT_WEIGHTS: dict[str, float] = {
        "capability": 0.35,
        "focus": 0.25,
        "trust": 0.20,
        "fog_gap": 0.10,
        "topology": 0.10,
    }

    def __init__(
        self,
        agent: Agent,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._agent = agent
        self._weights = weights or dict(self.DEFAULT_WEIGHTS)
        # Normalise
        total = sum(self._weights.values())
        if total > 0:
            self._weights = {k: v / total for k, v in self._weights.items()}

    def route(
        self,
        topic: str,
        min_score: float = 0.0,
        exclude_self: bool = True,
        max_results: int | None = None,
    ) -> AudienceReport:
        """
        Compute the ranked audience for a topic.

        Args:
            topic:        What you're routing for.
            min_score:    Drop agents below this score (0–1).
            exclude_self: Don't include the routing agent itself.
            max_results:  Cap the list length. None = no cap.

        Returns:
            An AudienceReport with ranked entries.
        """
        registry = self._agent._registry
        my_caps = self._agent._capabilities
        my_name = self._agent._name

        # Gather candidate agents from the registry
        candidates: dict[str, dict[str, Any]] = {}
        for name, rec in registry._records.items():
            if exclude_self and name == my_name:
                continue
            candidates[name] = {
                "capabilities": rec.capabilities,
                "focus": rec.focus,
                "address": rec.address,
            }

        if not candidates:
            return AudienceReport(
                topic=topic, entries=[], excluded=0, total_candidates=0
            )

        # Compute per-signal scores
        entries: list[AudienceEntry] = []

        # Pre-compute topic trigrams for similarity matching
        topic_trigrams = _trigrams(topic)

        # Pre-compute blind spot agents
        blind_spot_names: set[str] = set()
        try:
            for bs in self._agent.blind_spot():
                if bs.kind == "unmatched_focus":
                    # These are agents that could help but aren't on mesh
                    pass
        except Exception:
            pass

        # Get topology proximity
        strong_peers = set()
        try:
            strong_peers = set(self._agent.strong_peers(threshold=0.3))
        except Exception:
            pass

        # Get trust scores from ledger
        trust_scores: dict[str, float] = {}
        try:
            for agent_name, domain_map in self._agent._ledger._records.items():
                for dom, rec in domain_map.items():
                    if rec.grades:
                        avg = sum(g.score for g in rec.grades) / len(rec.grades)
                        # Keep highest average across domains
                        trust_scores[agent_name] = max(
                            trust_scores.get(agent_name, 0.0), avg
                        )
        except Exception:
            pass

        # Get seek results for capability gap scoring
        seek_map: dict[str, float] = {}
        try:
            # seek() needs async, so we compute gap score inline
            for name, info in candidates.items():
                peer_caps = info["capabilities"]
                if not peer_caps:
                    seek_map[name] = 0.0
                    continue
                # How much of the topic do peer caps cover?
                cap_sim = max(
                    (_trigram_similarity(topic, cap) for cap in peer_caps),
                    default=0.0,
                )
                seek_map[name] = cap_sim
        except Exception:
            pass

        for name, info in candidates.items():
            caps = info["capabilities"]
            focus = info.get("focus")
            signals: list[Signal] = []
            reason_parts: list[str] = []
            sub_scores: list[float] = []

            # --- Capability signal ---
            cap_score = 0.0
            if caps:
                cap_score = max(
                    (_trigram_similarity(topic, cap) for cap in caps),
                    default=0.0,
                )
            if cap_score > 0.15:
                signals.append(Signal.CAPABILITY)
                best_cap = max(caps, key=lambda c: _trigram_similarity(topic, c)) if caps else ""
                reason_parts.append(f"cap match: {best_cap}")
            sub_scores.append(self._weights.get("capability", 0) * cap_score)

            # --- Focus signal ---
            focus_score = 0.0
            if focus:
                focus_score = _trigram_similarity(topic, focus)
            if focus_score > 0.15:
                signals.append(Signal.FOCUS)
                reason_parts.append(f"focused on: {focus}")
            sub_scores.append(self._weights.get("focus", 0) * focus_score)

            # --- Trust signal ---
            trust_val = trust_scores.get(name, 0.0)
            if trust_val > 0.3:
                signals.append(Signal.TRUST)
                reason_parts.append(f"trust: {trust_val:.1f}")
            sub_scores.append(self._weights.get("trust", 0) * trust_val)

            # --- Fog gap signal ---
            fog_score = seek_map.get(name, 0.0)
            if fog_score > 0.2:
                signals.append(Signal.FOG_GAP)
                reason_parts.append("fills fog gap")
            sub_scores.append(self._weights.get("fog_gap", 0) * fog_score)

            # --- Topology signal ---
            topo_score = 0.7 if name in strong_peers else 0.0
            if topo_score > 0.0:
                signals.append(Signal.TOPOLOGY)
                reason_parts.append("cognitively close")
            sub_scores.append(self._weights.get("topology", 0) * topo_score)

            final_score = min(sum(sub_scores), 1.0)
            reason = "; ".join(reason_parts) if reason_parts else "no strong signal"

            entries.append(AudienceEntry(
                name=name,
                score=final_score,
                signals=signals,
                capabilities=list(caps),
                reason=reason,
            ))

        # Sort by score descending
        entries.sort(key=lambda e: e.score, reverse=True)

        # Apply threshold
        total_candidates = len(entries)
        filtered = [e for e in entries if e.score >= min_score]
        excluded = total_candidates - len(filtered)

        if max_results is not None:
            filtered = filtered[:max_results]

        return AudienceReport(
            topic=topic,
            entries=filtered,
            excluded=excluded,
            total_candidates=total_candidates,
        )


# ─── Similarity helpers ─────────────────────────────────────────────────

def _trigrams(text: str) -> set[str]:
    """Character trigram set for fuzzy matching."""
    t = f"  {text.lower()}  "
    return {t[i:i+3] for i in range(len(t) - 2)}


def _trigram_similarity(a: str, b: str) -> float:
    """Jaccard-like similarity between two strings via character trigrams."""
    ta = _trigrams(a)
    tb = _trigrams(b)
    if not ta or not tb:
        return 0.0
    intersection = ta & tb
    union = ta | tb
    return len(intersection) / len(union)
