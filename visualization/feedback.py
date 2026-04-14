"""
Feedback loop — topology and trust informing each other.

The strange loop made explicit:

    think(topic) → topology edges shift  →  agent becomes a strong peer
    strong peer gets task  →  grade filed  →  trust score rises
    trust score rises  →  topology edge boosted  →  agent stays close

Neither layer knows about the other directly. This bridge is the
connection — applied intentionally, not automatically.

Two flows:

    trust → topology:
        After grading, call `sync_edge()` to push the accumulated trust
        score for an agent into their topology edge weight. High-trust
        agents become topologically closer. Slashed agents drift away.

    topology → trust:
        When ranking claims, call `proximity_boost()` to add a small
        edge-weight signal to each score. Cognitive closeness is weak
        prior evidence of task fit — not a substitute for grades.

The weight parameters matter:

    topology_trust_weight (default 0.4):
        How much trust influences edge weight. Combined with the
        focus-similarity component that TopologyManager already computes.
        0.0 = pure focus similarity. 1.0 = pure trust score.

    proximity_weight (default 0.05):
        How much topology closeness boosts a trust score during ranking.
        Intentionally small — topology is a hint, not a credential.
        Set to 0.0 to disable the topology → trust direction entirely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .topology import TopologyManager, TopologyEdge
    from .trust import TrustLedger, Claim


# ─── Bridge ───────────────────────────────────────────────────────────────────


class TrustTopologyBridge:
    """
    The feedback loop between trust and topology.

    Stateless — holds configuration weights and exposes two methods.
    Create once, call on every grade and every ranking pass.

    Usage::

        bridge = TrustTopologyBridge()

        # After grading an agent
        g = stella.grade("solver", domain="orbit-calc", score=0.94, task_id="t3")
        bridge.sync_edge("stella", "solver", stella.ledger, topology)

        # Before ranking claims
        boosted = bridge.proximity_boost(claims, topology, stella.ledger, domain="orbit-calc")
        ranked  = stella.select(boosted, domain="orbit-calc")
    """

    def __init__(
        self,
        topology_trust_weight: float = 0.4,
        proximity_weight: float = 0.05,
    ) -> None:
        """
        Args:
            topology_trust_weight:
                How much trust scores influence topology edge weight (0–1).
                Blended with the existing focus-similarity weight.
                Default 0.4 — trust is real signal but focus similarity
                is still the primary driver of the topology.

            proximity_weight:
                How much a strong topology edge boosts a trust score during
                claim ranking. Intentionally small (default 0.05 = max 5%
                boost for an edge weight of 1.0).
        """
        if not 0.0 <= topology_trust_weight <= 1.0:
            raise ValueError(f"topology_trust_weight must be in [0,1]; got {topology_trust_weight}")
        if not 0.0 <= proximity_weight <= 1.0:
            raise ValueError(f"proximity_weight must be in [0,1]; got {proximity_weight}")

        self.topology_trust_weight = topology_trust_weight
        self.proximity_weight = proximity_weight

    # ─── trust → topology ─────────────────────────────────────────────────

    def sync_edge(
        self,
        source: str,
        target: str,
        ledger: "TrustLedger",
        topology: "TopologyManager",
        domain: str | None = None,
    ) -> float | None:
        """
        Push accumulated trust into a topology edge.

        After grading an agent, call this to update the topology edge
        weight so it reflects both focus similarity and trust history.

        The blend is:
            new_weight = (1 - topology_trust_weight) * focus_weight
                       +      topology_trust_weight  * trust_score

        where focus_weight is the existing edge weight (computed from
        focus similarity by TopologyManager) and trust_score is the
        domain_score from the ledger, or 0.5 (neutral) if no history.

        Args:
            source:  The agent doing the grading (holds the topology).
            target:  The agent being graded.
            ledger:  The grading agent's TrustLedger.
            topology: The grading agent's TopologyManager.
            domain:  Domain to pull the trust score from. If None, uses
                     the average across all domains for this target.

        Returns:
            The new edge weight, or None if no edge to `target` exists
            (i.e. they haven't announced focus yet).
        """
        key = (source, target)
        edge = topology._edges.get(key)
        if edge is None:
            return None  # no topology edge yet — focus sync hasn't happened

        # Get trust score for this target
        if domain is not None:
            trust_score = ledger.domain_score(target, domain)
            slash_pen   = ledger.slash_rate(target, domain) * 0.3
        else:
            # Average across all domains for this target
            target_domains = ledger._records.get(target, {})
            if target_domains:
                scores = [
                    (ledger.domain_score(target, d) or 0.5)
                    - ledger.slash_rate(target, d) * 0.3
                    for d in target_domains
                ]
                trust_score = sum(scores) / len(scores)
                slash_pen   = 0.0
            else:
                trust_score = None
                slash_pen   = 0.0

        if trust_score is None:
            trust_score = 0.5  # neutral prior — no grades yet
        else:
            trust_score = max(0.0, trust_score - slash_pen)

        # Blend with existing focus weight
        focus_weight = edge.weight
        new_weight = round(
            (1 - self.topology_trust_weight) * focus_weight
            + self.topology_trust_weight * trust_score,
            4,
        )
        edge.weight = new_weight
        import time as _time
        edge.last_active = _time.time()

        return new_weight

    # ─── topology → trust ─────────────────────────────────────────────────

    def proximity_boost(
        self,
        claims: "list[Claim]",
        topology: "TopologyManager",
        ledger: "TrustLedger",
        domain: str | None = None,
    ) -> "list[Claim]":
        """
        Return claims annotated with a topology proximity bonus.

        Does NOT modify the ledger. Returns a new list of Claim objects
        where each claim's effective stake is slightly inflated based on
        topology edge weight — so the ranking function naturally picks up
        the proximity signal.

        The boost is additive on stake — using the existing stake_bonus
        path rather than modifying scores directly:

            effective_stake = claim.stake + edge_weight * proximity_weight * 100

        For proximity_weight=0.05 and edge_weight=0.9: +4.5 effective stake.
        This is deliberately small — topology proximity is a tie-breaker,
        not a promotion.

        For agents with no topology edge: no boost (edge_weight assumed 0).
        For agents with zero proximity_weight: returns claims unchanged.

        Args:
            claims:    The claims to boost.
            topology:  The requesting agent's TopologyManager.
            ledger:    The requesting agent's TrustLedger (unused here,
                       but passed for consistency and future extension).
            domain:    Passed through — unused in boost logic.

        Returns:
            New list of Claim objects (original claims unmodified).
        """
        if self.proximity_weight == 0.0:
            return list(claims)

        from .trust import Claim as _Claim, Stake as _Stake

        boosted = []
        for c in claims:
            key = (topology._agent_name, c.agent)
            edge = topology._edges.get(key)
            edge_weight = edge.weight if edge is not None else 0.0

            if edge_weight <= 0.0:
                boosted.append(c)
                continue

            # Synthesize a small extra stake reflecting topology proximity
            extra_stake = edge_weight * self.proximity_weight * 100
            current_stake = c.stake_amount
            new_amount = current_stake + extra_stake

            new_stake = _Stake(
                agent=c.agent,
                domain=c.domain,
                amount=new_amount,
                task_id=c.stake.task_id if c.stake else "",
            )
            boosted.append(_Claim(
                agent=c.agent,
                task=c.task,
                domain=c.domain,
                stake=new_stake,
            ))

        return boosted


# ─── Convenience: describe the current feedback state ─────────────────────────

def describe_loop(
    source: str,
    target: str,
    ledger: "TrustLedger",
    topology: "TopologyManager",
) -> dict:
    """
    Snapshot of the feedback loop state between two agents.

    Returns a dict with:
        edge_weight:   current topology edge (source → target)
        trust_scores:  per-domain scores in the ledger
        grade_count:   total grades filed for target
        slash_rate:    average slash rate across domains
        loop_strength: composite signal 0–1 (mean of edge_weight + mean trust)
    """
    key = (source, target)
    edge = topology._edges.get(key)
    edge_weight = edge.weight if edge else None

    target_domains = ledger._records.get(target, {})
    trust_scores = {
        d: ledger.domain_score(target, d)
        for d in target_domains
    }
    grade_count = sum(len(rec.grades) for rec in target_domains.values())
    slash_rates = [ledger.slash_rate(target, d) for d in target_domains]
    avg_slash = sum(slash_rates) / len(slash_rates) if slash_rates else 0.0
    avg_trust = (
        sum(s for s in trust_scores.values() if s is not None)
        / max(1, sum(1 for s in trust_scores.values() if s is not None))
    )

    loop_strength = None
    if edge_weight is not None and trust_scores:
        loop_strength = round((edge_weight + avg_trust) / 2, 4)

    return {
        "source":       source,
        "target":       target,
        "edge_weight":  edge_weight,
        "trust_scores": trust_scores,
        "grade_count":  grade_count,
        "avg_slash":    round(avg_slash, 4),
        "loop_strength": loop_strength,
    }
