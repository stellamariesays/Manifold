"""
Trust layer — stake, claim, grade, and agent selection.

The interaction protocol on top of the topology.

When Stella needs a task done, she broadcasts a request. Agents that
can do it respond with Claims — backed by an optional Stake. She selects
using two signals in order of availability:

    1. Grades — her verified interaction history with that agent in that
       domain, plus grades passed via referral from trusted peers.
    2. Stake  — when no grade history exists anywhere in the network,
               stake size is the only signal. Skin in the game is the proxy.

After the task completes, she files a Grade. That grade updates the
transition map trust score for that agent in that domain — and becomes
available as a referral signal to any agent Stella trusts.

Slashing: a Grade of 0.0 in a domain reduces the agent's domain_score
there. The ledger is cumulative. A slashed agent doesn't disappear — it
carries the history.

---

Dataclasses are immutable snapshots. TrustLedger is the mutable state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ─── Primitives ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Stake:
    """
    An agent's skin in the game.

    When an agent claims it can do a task, it may stake a numeric amount.
    If the task fails (Grade ≤ slash_threshold), the stake is forfeited.
    If it succeeds, the stake is returned.

    Amounts are abstract (tokens, credits, reputation points — whatever
    the mesh uses). The ledger tracks whether the stake was honoured.
    """

    agent: str
    domain: str
    amount: float
    task_id: str

    def __repr__(self) -> str:
        return f"<Stake {self.agent!r} domain={self.domain!r} amount={self.amount:.1f}>"


@dataclass(frozen=True)
class Claim:
    """
    An agent's claim that it can do a task.

    Optionally backed by a Stake. Without a stake, the claim is costless
    — which means it carries less information. With a stake, failure has
    a price.
    """

    agent: str
    task: str
    domain: str
    stake: Stake | None = None

    @property
    def stake_amount(self) -> float:
        return self.stake.amount if self.stake else 0.0

    def __repr__(self) -> str:
        s = f" stake={self.stake.amount:.1f}" if self.stake else " (unstaked)"
        return f"<Claim {self.agent!r} task={self.task!r} domain={self.domain!r}{s}>"


@dataclass(frozen=True)
class Grade:
    """
    The outcome of a completed task — filed by the requesting agent.

    score: 0.0 = total failure / slash. 1.0 = perfect delivery.
    Anything below slash_threshold triggers stake forfeiture.

    task_id: ties the grade back to the original Claim and Stake,
             so the ledger can mark whether the stake was honoured.
    """

    agent: str
    domain: str
    score: float          # 0.0 – 1.0
    task_id: str
    slash_threshold: float = 0.5   # below this: stake forfeited

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Grade.score must be in [0, 1]; got {self.score}")

    @property
    def slashed(self) -> bool:
        """True if this grade triggers stake forfeiture."""
        return self.score < self.slash_threshold

    def __repr__(self) -> str:
        slash_str = " ⚡SLASHED" if self.slashed else ""
        return (
            f"<Grade {self.agent!r} domain={self.domain!r} "
            f"score={self.score:.2f}{slash_str}>"
        )


# ─── Ledger ───────────────────────────────────────────────────────────────────


@dataclass
class _AgentRecord:
    """Per-agent state tracked by the ledger."""

    grades: list[Grade] = field(default_factory=list)
    slash_count: int = 0
    stake_total: float = 0.0
    stake_forfeited: float = 0.0


class TrustLedger:
    """
    The mesh's memory of interaction outcomes.

    Maintains per-agent, per-domain grade history and stake records.
    Provides the scoring function used for agent selection.

    Ledgers are local. Each agent holds its own. Referrals work by
    passing grades between ledgers — gated by trust between agents.

    Usage::

        ledger = TrustLedger()

        # Record a grade after task completion
        ledger.record(Grade(agent="solver", domain="orbit", score=0.9, task_id="t1"))

        # Score a set of claims for a new task
        ranked = ledger.rank(claims, domain="orbit")
        best = ranked[0]
    """

    def __init__(self) -> None:
        # { agent_name: { domain: _AgentRecord } }
        self._records: dict[str, dict[str, _AgentRecord]] = {}

    # ─── Write ───────────────────────────────────────────────────────────

    def record(self, grade: Grade) -> None:
        """
        File a grade. Updates the agent's domain record.

        If the grade is below slash_threshold, increments slash_count
        and marks the staked amount as forfeited.
        """
        rec = self._get_record(grade.agent, grade.domain)
        rec.grades.append(grade)
        if grade.slashed:
            rec.slash_count += 1

    def record_stake(self, stake: Stake) -> None:
        """Register that a stake was placed (before task outcome)."""
        rec = self._get_record(stake.agent, stake.domain)
        rec.stake_total += stake.amount

    def forfeit_stake(self, stake: Stake) -> None:
        """Mark a stake as forfeited (called when Grade is slashed)."""
        rec = self._get_record(stake.agent, stake.domain)
        rec.stake_forfeited += stake.amount

    def absorb(self, other: "TrustLedger", trust_weight: float = 0.5) -> None:
        """
        Import grades from another ledger as referrals.

        trust_weight scales the borrowed grades — a referral from a
        peer you've verified 50% is worth half a first-hand grade.
        This lets referral chains decay gracefully: the further the
        source, the less the signal.

        Args:
            other: The ledger to import from (a trusted peer's).
            trust_weight: 0.0–1.0. How much to weight their grades.
        """
        for agent_name, domain_map in other._records.items():
            for domain, rec in domain_map.items():
                my_rec = self._get_record(agent_name, domain)
                for g in rec.grades:
                    # Re-file the grade with a scaled score
                    scaled = Grade(
                        agent=g.agent,
                        domain=g.domain,
                        score=g.score * trust_weight,
                        task_id=f"referral:{g.task_id}",
                        slash_threshold=g.slash_threshold,
                    )
                    my_rec.grades.append(scaled)

    # ─── Read ────────────────────────────────────────────────────────────

    def domain_score(self, agent: str, domain: str) -> float | None:
        """
        Weighted average grade for an agent in a domain.

        Returns None if there is no history (not zero — absence of data
        is different from a bad record).

        Recent grades are weighted slightly higher than old ones —
        a log decay that doesn't punish early mistakes forever.
        """
        rec = self._records.get(agent, {}).get(domain)
        if not rec or not rec.grades:
            return None

        grades = rec.grades
        total_weight = 0.0
        weighted_sum = 0.0
        for i, g in enumerate(grades):
            # weight increases with recency: log(position + 2) / log(n + 2)
            w = math.log(i + 2) / math.log(len(grades) + 2)
            weighted_sum += g.score * w
            total_weight += w

        return round(weighted_sum / total_weight, 4) if total_weight else None

    def slash_rate(self, agent: str, domain: str) -> float:
        """
        Fraction of tasks in this domain that ended in a slash.

        Returns 0.0 if no history.
        """
        rec = self._records.get(agent, {}).get(domain)
        if not rec or not rec.grades:
            return 0.0
        return round(rec.slash_count / len(rec.grades), 4)

    def score_claim(self, claim: Claim) -> float:
        """
        Composite trust score for a single claim.

        Score = reputation_component + stake_bonus

        reputation_component:
            domain_score if available, else 0.5 (neutral prior).
            Penalised by slash_rate.

        stake_bonus:
            log(stake + 1) / 10 — small, tapers off quickly.
            Skin in the game is a signal, not a substitute for history.

        Returns a float in roughly [0, 1.5] — not normalized, use rank()
        for relative ordering.
        """
        ds = self.domain_score(claim.agent, claim.domain)
        if ds is None:
            rep = 0.5   # neutral prior — unknown agent
        else:
            slash_pen = self.slash_rate(claim.agent, claim.domain) * 0.3
            rep = max(0.0, ds - slash_pen)

        stake_bonus = math.log(claim.stake_amount + 1) / 10.0
        return round(rep + stake_bonus, 4)

    def rank(
        self,
        claims: Sequence[Claim],
        domain: str | None = None,
    ) -> list[tuple[Claim, float]]:
        """
        Rank a set of competing claims by trust score.

        Returns list of (Claim, score) sorted by score descending.
        The first entry is the recommended agent.

        Args:
            claims: All claims received for a task.
            domain: Override the domain for scoring. If None, uses
                    each claim's own domain field.
        """
        scored = []
        for c in claims:
            eff_domain = domain or c.domain
            effective = Claim(
                agent=c.agent,
                task=c.task,
                domain=eff_domain,
                stake=c.stake,
            )
            scored.append((c, self.score_claim(effective)))
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def summary(self, agent: str) -> dict:
        """
        Human-readable summary of an agent's trust record.

        Returns a dict of { domain: { score, slash_rate, grade_count } }.
        """
        result: dict = {}
        for domain, rec in self._records.get(agent, {}).items():
            result[domain] = {
                "score": self.domain_score(agent, domain),
                "slash_rate": self.slash_rate(agent, domain),
                "grade_count": len(rec.grades),
                "stake_total": rec.stake_total,
                "stake_forfeited": rec.stake_forfeited,
            }
        return result

    # ─── Internal ────────────────────────────────────────────────────────

    def _get_record(self, agent: str, domain: str) -> _AgentRecord:
        if agent not in self._records:
            self._records[agent] = {}
        if domain not in self._records[agent]:
            self._records[agent][domain] = _AgentRecord()
        return self._records[agent][domain]

    def __repr__(self) -> str:
        n_agents = len(self._records)
        n_grades = sum(
            len(rec.grades)
            for dm in self._records.values()
            for rec in dm.values()
        )
        return f"<TrustLedger agents={n_agents} grades={n_grades}>"
