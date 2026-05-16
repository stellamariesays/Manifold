"""Task router — unified matchmaker combining audience, negotiation, and dispatch.

Accepts a task description, finds the best agent via audience routing,
negotiates terms, dispatches with fallback chains, and tracks outcomes
for adaptive learning.

This is the top-level orchestrator that glues together:

- ``AudienceRouter`` / ``AudiencePipeline`` — candidate ranking
- ``Negotiator`` — contract negotiation with providers
- ``TaskDispatcher`` — execution with retry/fallback
- ``AdaptiveRouter`` — feedback-driven weight tuning

Usage::

    from manifold.task_router import TaskRouter

    router = TaskRouter(agent)
    result = await router.route("solar-flare-prediction", payload={"region": "pacific"})
    print(f"Routed to {result.agent_name} via {result.path}")
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .audience import AudienceRouter, Signal
from .negotiation import (
    CapabilityRequest,
    Negotiator,
    NegotiationPolicy,
    NegotiationStatus,
    NegotiationTerms,
)


class RouteStatus(str, Enum):
    """Final status of a routed task."""
    COMPLETED = "completed"
    ALL_FAILED = "all_failed"
    NO_CANDIDATES = "no_candidates"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class RouteStrategy(str, Enum):
    """How to pick among candidates."""
    BEST_FIRST = "best_first"          # try top candidate only
    TOP_N = "top_n"                    # try top-N in order
    PARALLEL = "parallel"              # dispatch to top-N simultaneously
    COMPETITIVE = "competitive"        # dispatch to top-N, take first success


@dataclass
class RouteResult:
    """Outcome of routing a task."""
    task_id: str = field(default_factory=lambda: f"task-{uuid.uuid4().hex[:10]}")
    task: str = ""
    status: RouteStatus = RouteStatus.COMPLETED
    agent_name: str = ""
    path: str = ""  # "direct", "fallback:1", "competitive-winner"
    attempts: int = 0
    elapsed_ms: float = 0.0
    score: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    fallback_log: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return (
            f"<RouteResult {self.task_id} [{self.status.value}] "
            f"agent={self.agent_name} attempts={self.attempts}>"
        )


@dataclass
class RoutePolicy:
    """Configuration for task routing behavior."""
    strategy: RouteStrategy = RouteStrategy.TOP_N
    max_candidates: int = 5
    max_attempts: int = 3
    negotiation_timeout_ms: float = 10_000
    execution_timeout_ms: float = 30_000
    min_audience_score: float = 0.1
    fallback_on_rejection: bool = True
    fallback_on_failure: bool = True
    competitive_grace_ms: float = 5_000
    trust_weight: float = 0.3
    capability_weight: float = 0.4
    latency_weight: float = 0.3


class TaskRouter:
    """
    Unified task router: audience → negotiate → dispatch → adapt.

    Args:
        agent:       The local agent (provides audience, capabilities, trust).
        policy:      Routing policy. Uses sensible defaults if not provided.
        negotiator:  Optional custom negotiator. Created from agent if not given.
    """

    def __init__(
        self,
        agent: Any,
        policy: RoutePolicy | None = None,
        negotiator: Negotiator | None = None,
    ) -> None:
        self._agent = agent
        self._policy = policy or RoutePolicy()
        self._negotiator = negotiator or Negotiator(agent)
        self._history: list[RouteResult] = []
        self._history_limit = 500

    @property
    def policy(self) -> RoutePolicy:
        return self._policy

    @property
    def negotiator(self) -> Negotiator:
        return self._negotiator

    # ─── Main API ──────────────────────────────────────────────────────

    async def route(
        self,
        task: str,
        payload: dict[str, Any] | None = None,
        strategy: RouteStrategy | None = None,
    ) -> RouteResult:
        """
        Route a task to the best agent.

        1. Get ranked audience via agent.audience()
        2. Filter by minimum score
        3. Attempt negotiation + dispatch with fallback
        4. Return result with full tracking
        """
        payload = payload or {}
        strategy = strategy or self._policy.strategy
        t0 = time.monotonic()

        result = RouteResult(task=task)

        # 1. Get audience
        candidates = self._get_audience(task)
        if not candidates:
            result.status = RouteStatus.NO_CANDIDATES
            result.elapsed_ms = (time.monotonic() - t0) * 1000
            self._record(result)
            return result

        # 2. Filter by minimum score
        candidates = [
            e for e in candidates
            if e.score >= self._policy.min_audience_score
        ]
        if not candidates:
            result.status = RouteStatus.NO_CANDIDATES
            result.elapsed_ms = (time.monotonic() - t0) * 1000
            self._record(result)
            return result

        # 3. Limit candidates
        candidates = candidates[:self._policy.max_candidates]

        # 4. Route by strategy
        if strategy == RouteStrategy.BEST_FIRST:
            route_result = await self._route_best_first(task, payload, candidates)
        elif strategy == RouteStrategy.TOP_N:
            route_result = await self._route_top_n(task, payload, candidates)
        elif strategy == RouteStrategy.PARALLEL:
            route_result = await self._route_parallel(task, payload, candidates)
        elif strategy == RouteStrategy.COMPETITIVE:
            route_result = await self._route_competitive(task, payload, candidates)
        else:
            route_result = await self._route_top_n(task, payload, candidates)

        # Merge tracking data
        result.status = route_result.status
        result.agent_name = route_result.agent_name
        result.path = route_result.path
        result.attempts = route_result.attempts
        result.result = route_result.result
        result.error = route_result.error
        result.score = route_result.score
        result.fallback_log = route_result.fallback_log
        result.elapsed_ms = (time.monotonic() - t0) * 1000
        self._record(result)
        return result

    # ─── Strategies ────────────────────────────────────────────────────

    async def _route_best_first(
        self, task: str, payload: dict[str, Any], candidates: list,
    ) -> RouteResult:
        """Try only the top candidate."""
        if not candidates:
            return RouteResult(status=RouteStatus.NO_CANDIDATES)

        best = candidates[0]
        return await self._try_agent(best.name, task, payload, path="direct")

    async def _route_top_n(
        self, task: str, payload: dict[str, Any], candidates: list,
    ) -> RouteResult:
        """Try candidates in order with fallback."""
        max_attempts = min(self._policy.max_attempts, len(candidates))
        log: list[dict[str, Any]] = []

        for i, candidate in enumerate(candidates[:max_attempts]):
            path = "direct" if i == 0 else f"fallback:{i}"
            attempt = await self._try_agent(candidate.name, task, payload, path=path)
            log.append({
                "agent": candidate.name,
                "score": candidate.score,
                "path": path,
                "status": attempt.status.value,
                "error": attempt.error,
            })

            if attempt.status == RouteStatus.COMPLETED:
                attempt.fallback_log = log
                return attempt

            if attempt.status == RouteStatus.CANCELLED:
                break

            # Check if we should fallback
            if not self._should_fallback(attempt):
                break

        return RouteResult(
            status=RouteStatus.ALL_FAILED,
            attempts=len(log),
            fallback_log=log,
        )

    async def _route_parallel(
        self, task: str, payload: dict[str, Any], candidates: list,
    ) -> RouteResult:
        """Dispatch to all candidates simultaneously, collect all results."""
        import asyncio

        tasks = []
        for i, c in enumerate(candidates):
            path = f"parallel:{i}"
            tasks.append(self._try_agent(c.name, task, payload, path=path))

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        log: list[dict[str, Any]] = []
        best: RouteResult | None = None

        for outcome in outcomes:
            if isinstance(outcome, Exception):
                log.append({"error": str(outcome), "status": "exception"})
                continue
            r = outcome
            log.append({
                "agent": r.agent_name,
                "status": r.status.value,
                "score": r.score,
            })
            if r.status == RouteStatus.COMPLETED:
                if best is None or r.score > best.score:
                    best = r

        if best:
            best.path = "parallel"
            best.fallback_log = log
            return best

        return RouteResult(
            status=RouteStatus.ALL_FAILED,
            attempts=len(log),
            fallback_log=log,
        )

    async def _route_competitive(
        self, task: str, payload: dict[str, Any], candidates: list,
    ) -> RouteResult:
        """Dispatch to top-N, first successful result wins."""
        import asyncio

        tasks = []
        for i, c in enumerate(candidates):
            path = f"competitive:{c.name}"
            tasks.append(self._try_agent(c.name, task, payload, path=path))

        # Race: wait for first success or all failures
        winner: RouteResult | None = None
        log: list[dict[str, Any]] = []

        pending = {asyncio.ensure_future(t) for t in tasks}
        try:
            done, pending = await asyncio.wait(
                pending,
                timeout=self._policy.competitive_grace_ms / 1000,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for fut in done:
                try:
                    r = fut.result()
                    log.append({"agent": r.agent_name, "status": r.status.value})
                    if r.status == RouteStatus.COMPLETED and winner is None:
                        winner = r
                except Exception as exc:
                    log.append({"error": str(exc)})

            # If we got a winner, cancel the rest
            if winner:
                for p in pending:
                    p.cancel()
                winner.path = "competitive-winner"
                winner.fallback_log = log
                return winner

            # Wait for remaining
            if pending:
                done2, _ = await asyncio.wait(pending, timeout=self._policy.execution_timeout_ms / 1000)
                for fut in done2:
                    try:
                        r = fut.result()
                        log.append({"agent": r.agent_name, "status": r.status.value})
                        if r.status == RouteStatus.COMPLETED and winner is None:
                            winner = r
                    except Exception as exc:
                        log.append({"error": str(exc)})

        except Exception:
            pass

        if winner:
            winner.path = "competitive-winner"
            winner.fallback_log = log
            return winner

        return RouteResult(
            status=RouteStatus.ALL_FAILED,
            attempts=len(log),
            fallback_log=log,
        )

    # ─── Single Agent Attempt ──────────────────────────────────────────

    async def _try_agent(
        self,
        agent_name: str,
        task: str,
        payload: dict[str, Any],
        path: str = "direct",
    ) -> RouteResult:
        """Negotiate + dispatch a single agent."""
        result = RouteResult(agent_name=agent_name, path=path, attempts=1)

        # Negotiate
        request = CapabilityRequest(
            requester=self._agent.name,
            provider=agent_name,
            capability=task,
            inputs=payload,
            deadline_ms=self._policy.negotiation_timeout_ms,
        )

        try:
            contract = await self._negotiator.negotiate(request)
        except Exception as exc:
            result.status = RouteStatus.ALL_FAILED
            result.error = f"negotiation error: {exc}"
            return result

        if contract.status == NegotiationStatus.REJECTED:
            result.status = RouteStatus.ALL_FAILED
            result.error = f"rejected: {contract.rejection_reason}"
            return result

        if contract.status == NegotiationStatus.EXPIRED:
            result.status = RouteStatus.TIMEOUT
            result.error = "negotiation expired"
            return result

        if not contract.accepted:
            result.status = RouteStatus.ALL_FAILED
            result.error = f"not accepted: {contract.status.value}"
            return result

        # Execute
        try:
            completed = await self._negotiator.execute(contract)
        except Exception as exc:
            result.status = RouteStatus.ALL_FAILED
            result.error = f"execution error: {exc}"
            return result

        if completed.status == NegotiationStatus.COMPLETED:
            result.status = RouteStatus.COMPLETED
            result.result = completed.result
            result.score = completed.score or 1.0
            return result

        result.status = RouteStatus.ALL_FAILED
        result.error = completed.error or f"status: {completed.status.value}"
        return result

    # ─── Audience ──────────────────────────────────────────────────────

    def _get_audience(self, task: str) -> list:
        """Get ranked audience entries for a task."""
        try:
            report = self._agent.audience(task)
            return list(report.entries)
        except Exception:
            return []

    # ─── Helpers ───────────────────────────────────────────────────────

    def _should_fallback(self, result: RouteResult) -> bool:
        """Check if we should try the next candidate."""
        if result.status == RouteStatus.CANCELLED:
            return False
        if result.error and "rejected" in (result.error or ""):
            return self._policy.fallback_on_rejection
        return self._policy.fallback_on_failure

    def _record(self, result: RouteResult) -> None:
        self._history.append(result)
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]

    # ─── Query ─────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Routing statistics."""
        total = len(self._history)
        completed = sum(1 for r in self._history if r.status == RouteStatus.COMPLETED)
        failed = sum(1 for r in self._history if r.status == RouteStatus.ALL_FAILED)
        avg_elapsed = 0.0
        avg_attempts = 0.0
        if completed:
            completed_results = [r for r in self._history if r.status == RouteStatus.COMPLETED]
            avg_elapsed = sum(r.elapsed_ms for r in completed_results) / len(completed_results)
            avg_attempts = sum(r.attempts for r in completed_results) / len(completed_results)

        strategy_counts: dict[str, int] = {}
        for r in self._history:
            key = r.path.split(":")[0] if r.path else "unknown"
            strategy_counts[key] = strategy_counts.get(key, 0) + 1

        return {
            "total_routed": total,
            "completed": completed,
            "failed": failed,
            "no_candidates": sum(1 for r in self._history if r.status == RouteStatus.NO_CANDIDATES),
            "success_rate": round(completed / total, 3) if total else 0.0,
            "avg_elapsed_ms": round(avg_elapsed, 1),
            "avg_attempts": round(avg_attempts, 2),
            "path_distribution": strategy_counts,
        }

    def recent(self, limit: int = 20) -> list[RouteResult]:
        return list(self._history[-limit:])

    def summary(self) -> str:
        s = self.stats()
        lines = [
            f"TaskRouter ({self._policy.strategy.value}):",
            f"  Routed: {s['total_routed']}  Success: {s['success_rate']:.1%}",
            f"  Avg time: {s['avg_elapsed_ms']:.0f}ms  Avg attempts: {s['avg_attempts']:.1f}",
        ]
        if s["path_distribution"]:
            dist = ", ".join(f"{k}={v}" for k, v in sorted(s["path_distribution"].items()))
            lines.append(f"  Paths: {dist}")
        return "\n".join(lines)
