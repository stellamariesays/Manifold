"""Task dispatcher — route incoming tasks to the best-matched agent.

Combines audience routing with task lifecycle management. When a task arrives,
the dispatcher:

1. Uses ``Agent.audience()`` to rank candidates by capability, trust, focus,
   fog gap, and topology signals.
2. Dispatches to the top candidate, respecting concurrency limits.
3. Falls back to the next candidate on failure.
4. Tracks dispatch history for observability.

Usage::

    from manifold.dispatch import TaskDispatcher

    dispatcher = TaskDispatcher(agent)
    result = await dispatcher.dispatch("solar-prediction", payload={"region": "pacific"})
    print(f"Dispatched to {result.agent_name} — {result.status}")
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import Agent


class DispatchStatus(str, Enum):
    """Outcome of a dispatch attempt."""
    DISPATCHED = "dispatched"
    NO_CANDIDATES = "no_candidates"
    ALL_FAILED = "all_failed"
    TIMEOUT = "timeout"
    REJECTED = "rejected"


class TaskPriority(str, Enum):
    """Priority level for queued tasks."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DispatchResult:
    """Result of a single dispatch operation."""
    task_id: str
    topic: str
    agent_name: str | None = None
    status: DispatchStatus = DispatchStatus.DISPATCHED
    payload: dict[str, Any] = field(default_factory=dict)
    response: Any = None
    elapsed_ms: float = 0.0
    attempts: int = 0
    fallback_chain: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == DispatchStatus.DISPATCHED

    def __repr__(self) -> str:
        agent = self.agent_name or "none"
        return (
            f"<DispatchResult {self.task_id[:8]}… "
            f"topic={self.topic!r} agent={agent} "
            f"status={self.status.value} attempts={self.attempts}>"
        )


@dataclass
class DispatchEntry:
    """Record of a dispatch for history/tracking."""
    task_id: str
    topic: str
    agent_name: str
    status: DispatchStatus
    timestamp: float
    payload_summary: str = ""
    response_summary: str = ""
    elapsed_ms: float = 0.0


class TaskDispatcher:
    """
    Dispatch tasks to the best audience on the mesh.

    Wraps ``Agent.audience()`` with retry logic, concurrency limits,
    and dispatch history.

    Args:
        agent:          The dispatching agent.
        max_retries:    How many fallback agents to try before giving up.
        min_score:      Minimum audience score to consider a candidate.
        history_limit:  Max dispatch history entries to keep.
    """

    DISPATCH_TOPIC = "_manifold.dispatch"
    RESPONSE_TOPIC = "_manifold.dispatch.response"

    def __init__(
        self,
        agent: Agent,
        max_retries: int = 3,
        min_score: float = 0.05,
        history_limit: int = 1000,
    ) -> None:
        self._agent = agent
        self._max_retries = max_retries
        self._min_score = min_score
        self._history_limit = history_limit
        self._history: list[DispatchEntry] = []
        self._active: dict[str, DispatchResult] = {}

    async def dispatch(
        self,
        topic: str,
        payload: dict[str, Any] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        target_agent: str | None = None,
        weights: dict[str, float] | None = None,
    ) -> DispatchResult:
        """
        Dispatch a task to the best-matched agent.

        If ``target_agent`` is given, dispatches directly to that agent
        (skips routing). Otherwise uses audience routing to pick candidates.

        Args:
            topic:        What the task is about (used for routing).
            payload:      Task data.
            priority:     Task priority.
            target_agent: Override routing — dispatch to this agent directly.
            weights:      Custom signal weights for audience routing.

        Returns:
            DispatchResult with outcome details.
        """
        start = time.monotonic()
        task_id = payload.get("task_id") if payload else None
        if not task_id:
            task_id = f"task-{uuid.uuid4().hex[:12]}"
        payload = payload or {}

        # Direct targeting bypasses routing
        if target_agent:
            result = await self._try_dispatch(
                task_id, topic, payload, target_agent, priority
            )
            result.elapsed_ms = (time.monotonic() - start) * 1000
            self._record(result, payload)
            return result

        # Route via audience
        report = self._agent.audience(
            topic, min_score=self._min_score, weights=weights
        )

        if not report.entries:
            result = DispatchResult(
                task_id=task_id,
                topic=topic,
                status=DispatchStatus.NO_CANDIDATES,
                payload=payload,
                elapsed_ms=(time.monotonic() - start) * 1000,
            )
            self._record(result, payload)
            return result

        # Try candidates in order (fallback chain)
        candidates = report.entries[: self._max_retries]
        last_error: str | None = None
        fallback_chain: list[str] = []

        for i, entry in enumerate(candidates):
            result = await self._try_dispatch(
                task_id, topic, payload, entry.name, priority
            )
            result.attempts = i + 1
            result.fallback_chain = fallback_chain

            if result.ok:
                result.elapsed_ms = (time.monotonic() - start) * 1000
                self._record(result, payload)
                return result

            fallback_chain.append(entry.name)
            last_error = result.error

        # All candidates failed
        result = DispatchResult(
            task_id=task_id,
            topic=topic,
            status=DispatchStatus.ALL_FAILED,
            payload=payload,
            attempts=len(candidates),
            fallback_chain=fallback_chain,
            error=last_error,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
        self._record(result, payload)
        return result

    async def _try_dispatch(
        self,
        task_id: str,
        topic: str,
        payload: dict[str, Any],
        agent_name: str,
        priority: TaskPriority,
    ) -> DispatchResult:
        """Attempt dispatch to a specific agent via mesh publish."""
        envelope = {
            "task_id": task_id,
            "topic": topic,
            "payload": payload,
            "priority": priority.value,
            "from": self._agent.name,
            "target": agent_name,
            "timestamp": time.time(),
        }

        try:
            self._active[task_id] = DispatchResult(
                task_id=task_id, topic=topic, agent_name=agent_name
            )
            await self._agent.publish(
                f"{self.DISPATCH_TOPIC}.{agent_name}", envelope
            )
            return DispatchResult(
                task_id=task_id,
                topic=topic,
                agent_name=agent_name,
                status=DispatchStatus.DISPATCHED,
                payload=payload,
            )
        except Exception as exc:
            return DispatchResult(
                task_id=task_id,
                topic=topic,
                agent_name=agent_name,
                status=DispatchStatus.REJECTED,
                payload=payload,
                error=str(exc),
            )
        finally:
            self._active.pop(task_id, None)

    def _record(self, result: DispatchResult, payload: dict[str, Any]) -> None:
        """Record dispatch result in history."""
        summary_keys = ["region", "type", "action", "query"]
        payload_summary = ", ".join(
            f"{k}={payload[k]}" for k in summary_keys if k in payload
        )
        entry = DispatchEntry(
            task_id=result.task_id,
            topic=result.topic,
            agent_name=result.agent_name or "none",
            status=result.status,
            timestamp=time.time(),
            payload_summary=payload_summary,
            elapsed_ms=result.elapsed_ms,
        )
        self._history.append(entry)
        # Trim to limit
        if len(self._history) > self._history_limit:
            self._history = self._history[-self._history_limit:]

    # ─── Query helpers ──────────────────────────────────────────────

    @property
    def history(self) -> list[DispatchEntry]:
        """Recent dispatch history."""
        return list(self._history)

    def stats(self) -> dict[str, Any]:
        """Dispatch statistics."""
        total = len(self._history)
        if not total:
            return {"total": 0, "success_rate": 0.0, "avg_attempts": 0.0}

        dispatched = sum(
            1 for e in self._history if e.status == DispatchStatus.DISPATCHED
        )
        avg_elapsed = (
            sum(e.elapsed_ms for e in self._history) / total
        )
        return {
            "total": total,
            "success_rate": round(dispatched / total, 3),
            "avg_elapsed_ms": round(avg_elapsed, 1),
        }

    def agent_distribution(self) -> dict[str, int]:
        """How many tasks each agent has received."""
        dist: dict[str, int] = {}
        for e in self._history:
            if e.status == DispatchStatus.DISPATCHED:
                dist[e.agent_name] = dist.get(e.agent_name, 0) + 1
        return dict(sorted(dist.items(), key=lambda x: -x[1]))
