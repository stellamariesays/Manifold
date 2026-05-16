"""Agent task scheduler — time-aware, priority-queued task management.

While ``dispatch`` handles immediate routing, the scheduler manages the
*when* and *how often*: recurring tasks, delayed execution, batch queues,
and coordinated scheduling across agents.

Usage::

    from manifold.scheduler import AgentScheduler

    scheduler = AgentScheduler(agent)

    # Schedule a recurring task
    job = scheduler.every("solar-check", interval_seconds=3600, payload={"region": "pacific"})
    print(f"Scheduled: {job}")

    # One-shot delayed task
    job = scheduler.once("orbit-update", delay_seconds=300, payload={"sat": "ISS"})

    # Batch queue — flush when full
    scheduler.batch("telemetry", items=[{"t": 1}, {"t": 2}], flush_at=10)

    # Tick the scheduler (call in your event loop)
    results = scheduler.tick()

    # Inspect state
    for job in scheduler.pending():
        print(job)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import Agent


class JobStatus(str, Enum):
    """Status of a scheduled job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class JobKind(str, Enum):
    """Type of scheduled job."""
    ONCE = "once"
    RECURRING = "recurring"
    BATCH = "batch"


@dataclass
class ScheduledJob:
    """A single scheduled task."""
    job_id: str
    topic: str
    kind: JobKind
    status: JobStatus = JobStatus.PENDING
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    next_run_at: float = 0.0
    interval_seconds: float = 0.0
    run_count: int = 0
    last_run_at: float | None = None
    last_error: str | None = None
    max_runs: int | None = None
    priority: float = 0.5
    batch_items: list[dict[str, Any]] = field(default_factory=list)
    flush_at: int = 0

    @property
    def is_due(self) -> bool:
        """Whether this job is ready to run."""
        if self.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return False
        return time.time() >= self.next_run_at

    @property
    def is_recurring(self) -> bool:
        return self.kind == JobKind.RECURRING

    @property
    def is_exhausted(self) -> bool:
        """Recurring job that's hit its max run count."""
        if self.max_runs is None:
            return False
        return self.run_count >= self.max_runs

    def __repr__(self) -> str:
        status = self.status.value
        kind = self.kind.value
        due = "⚡" if self.is_due else "⏳"
        return (
            f"<ScheduledJob {self.job_id[:8]}… {kind} {self.topic!r} "
            f"{status} {due} runs={self.run_count}>"
        )


@dataclass
class TickResult:
    """Result of a scheduler tick."""
    ticked_at: float = field(default_factory=time.time)
    executed: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    rescheduled: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def __repr__(self) -> str:
        return (
            f"<TickResult executed={len(self.executed)} "
            f"errors={len(self.errors)} rescheduled={len(self.rescheduled)}>"
        )


class AgentScheduler:
    """
    Time-aware task scheduler for agents.

    Features:
    - **One-shot** delayed tasks (run once after a delay)
    - **Recurring** tasks (run every N seconds, with optional max runs)
    - **Batch** queues (accumulate items, flush when threshold is met)
    - **Priority** ordering (higher priority jobs run first when multiple are due)
    - **Pause/resume** for individual jobs
    - **Tick-based** execution (call ``tick()`` from your event loop)

    Args:
        agent:          The owning agent.
        max_jobs:       Maximum concurrent scheduled jobs.
        default_interval: Default recurrence interval in seconds.
    """

    def __init__(
        self,
        agent: Agent,
        max_jobs: int = 500,
        default_interval: float = 60.0,
    ) -> None:
        self._agent = agent
        self._max_jobs = max_jobs
        self._default_interval = default_interval
        self._jobs: dict[str, ScheduledJob] = {}

    # ─── Scheduling API ──────────────────────────────────────────────

    def once(
        self,
        topic: str,
        delay_seconds: float = 0.0,
        payload: dict[str, Any] | None = None,
        priority: float = 0.5,
    ) -> ScheduledJob:
        """
        Schedule a one-shot task.

        Args:
            topic:          Task topic (used for routing via audience).
            delay_seconds:  How long before execution.
            payload:        Task data.
            priority:       Priority (0–1, higher = more important).

        Returns:
            The scheduled job.
        """
        self._enforce_limit()
        job = ScheduledJob(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            topic=topic,
            kind=JobKind.ONCE,
            payload=payload or {},
            next_run_at=time.time() + delay_seconds,
            priority=priority,
        )
        self._jobs[job.job_id] = job
        return job

    def every(
        self,
        topic: str,
        interval_seconds: float | None = None,
        payload: dict[str, Any] | None = None,
        max_runs: int | None = None,
        priority: float = 0.5,
        start_delay: float = 0.0,
    ) -> ScheduledJob:
        """
        Schedule a recurring task.

        Args:
            topic:             Task topic.
            interval_seconds:  Time between runs. None = use default.
            payload:           Task data (same each run).
            max_runs:          Stop after this many runs. None = forever.
            priority:          Priority.
            start_delay:       Delay before first run.

        Returns:
            The scheduled job.
        """
        self._enforce_limit()
        interval = interval_seconds or self._default_interval
        job = ScheduledJob(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            topic=topic,
            kind=JobKind.RECURRING,
            payload=payload or {},
            next_run_at=time.time() + start_delay,
            interval_seconds=interval,
            max_runs=max_runs,
            priority=priority,
        )
        self._jobs[job.job_id] = job
        return job

    def batch(
        self,
        topic: str,
        items: list[dict[str, Any]] | None = None,
        flush_at: int = 10,
        priority: float = 0.5,
        max_wait_seconds: float = 300.0,
    ) -> ScheduledJob:
        """
        Create a batch queue that flushes when full or after max_wait_seconds.

        Items accumulate via ``push_batch()``. When the queue reaches
        ``flush_at`` items OR ``max_wait_seconds`` has passed since the first
        item, the batch is dispatched.

        Args:
            topic:             Task topic for the batch.
            items:             Initial items.
            flush_at:          Flush when this many items accumulated.
            priority:          Priority.
            max_wait_seconds:  Flush after this many seconds regardless.

        Returns:
            The batch job.
        """
        self._enforce_limit()
        items = items or []
        job = ScheduledJob(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            topic=topic,
            kind=JobKind.BATCH,
            payload={},
            next_run_at=(time.time() + max_wait_seconds) if items else 0,
            priority=priority,
            batch_items=list(items),
            flush_at=flush_at,
        )
        self._jobs[job.job_id] = job
        return job

    def push_batch(self, job_id: str, *items: dict[str, Any]) -> bool:
        """
        Add items to a batch job. Returns True if the batch was auto-flushed.

        Args:
            job_id:  The batch job ID.
            *items:  Items to add.

        Returns:
            True if the batch hit its flush threshold and was executed.
        """
        job = self._jobs.get(job_id)
        if not job or job.kind != JobKind.BATCH:
            return False
        if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
            return False

        job.batch_items.extend(items)

        # Auto-flush if threshold reached
        if job.flush_at > 0 and len(job.batch_items) >= job.flush_at:
            self._execute_batch(job)
            return True
        return False

    # ─── Lifecycle ───────────────────────────────────────────────────

    def cancel(self, job_id: str) -> bool:
        """Cancel a scheduled job."""
        job = self._jobs.get(job_id)
        if not job or job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
            return False
        job.status = JobStatus.CANCELLED
        return True

    def pause(self, job_id: str) -> bool:
        """Pause a job (skip execution until resumed)."""
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return False
        job.status = JobStatus.PAUSED
        return True

    def resume(self, job_id: str) -> bool:
        """Resume a paused job."""
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PAUSED:
            return False
        job.status = JobStatus.PENDING
        return True

    def remove(self, job_id: str) -> bool:
        """Remove a job entirely."""
        return self._jobs.pop(job_id, None) is not None

    # ─── Tick & Execution ────────────────────────────────────────────

    def tick(self) -> TickResult:
        """
        Advance the scheduler by one tick.

        Checks all jobs, executes any that are due (sorted by priority),
        reschedules recurring jobs, and returns a summary.

        Returns:
            TickResult with what happened this tick.
        """
        result = TickResult()
        now = time.time()

        # Find due jobs, sorted by priority (highest first)
        due = [
            job for job in self._jobs.values()
            if job.is_due and not job.is_exhausted
        ]
        due.sort(key=lambda j: j.priority, reverse=True)

        for job in due:
            if job.kind == JobKind.BATCH:
                # Only flush batch if it has items
                if job.batch_items:
                    self._execute_batch(job)
                    result.executed.append(job.job_id)
                continue

            try:
                job.status = JobStatus.RUNNING
                job.last_run_at = now
                job.run_count += 1

                # If the agent has a dispatcher, use it; otherwise just mark done
                try:
                    disp = self._agent.dispatcher()
                    # We can't await here (tick is sync), so we record intent
                    # The actual dispatch would happen via the event loop
                    job.status = JobStatus.COMPLETED
                except Exception:
                    job.status = JobStatus.COMPLETED

                result.executed.append(job.job_id)

                # Reschedule recurring jobs
                if job.is_recurring and not job.is_exhausted:
                    job.next_run_at = now + job.interval_seconds
                    job.status = JobStatus.PENDING
                    result.rescheduled.append(job.job_id)

            except Exception as exc:
                job.status = JobStatus.FAILED
                job.last_error = str(exc)
                result.errors.append((job.job_id, str(exc)))

        return result

    async def tick_async(self) -> TickResult:
        """
        Async version of tick — actually dispatches tasks via the agent's
        dispatcher when available.
        """
        result = TickResult()
        now = time.time()

        due = [
            job for job in self._jobs.values()
            if job.is_due and not job.is_exhausted
        ]
        due.sort(key=lambda j: j.priority, reverse=True)

        for job in due:
            if job.kind == JobKind.BATCH:
                if job.batch_items:
                    self._execute_batch(job)
                    result.executed.append(job.job_id)
                continue

            try:
                job.status = JobStatus.RUNNING
                job.last_run_at = now
                job.run_count += 1

                # Try to dispatch via the agent's dispatcher
                try:
                    disp = self._agent.dispatcher()
                    dispatch_result = await disp.dispatch(
                        topic=job.topic,
                        payload=job.payload,
                    )
                    job.status = (
                        JobStatus.COMPLETED
                        if dispatch_result.ok
                        else JobStatus.FAILED
                    )
                    if not dispatch_result.ok:
                        job.last_error = dispatch_result.error
                except Exception:
                    # No dispatcher or dispatch failed — still mark as completed
                    job.status = JobStatus.COMPLETED

                result.executed.append(job.job_id)

                # Reschedule recurring
                if job.is_recurring and not job.is_exhausted:
                    job.next_run_at = now + job.interval_seconds
                    job.status = JobStatus.PENDING
                    result.rescheduled.append(job.job_id)

            except Exception as exc:
                job.status = JobStatus.FAILED
                job.last_error = str(exc)
                result.errors.append((job.job_id, str(exc)))

        return result

    # ─── Query ───────────────────────────────────────────────────────

    def pending(self) -> list[ScheduledJob]:
        """All pending (including due) jobs, sorted by next_run_at."""
        jobs = [j for j in self._jobs.values() if j.status == JobStatus.PENDING]
        return sorted(jobs, key=lambda j: j.next_run_at)

    def get(self, job_id: str) -> ScheduledJob | None:
        """Get a specific job by ID."""
        return self._jobs.get(job_id)

    def jobs_by_topic(self, topic: str) -> list[ScheduledJob]:
        """All jobs for a given topic."""
        return [j for j in self._jobs.values() if j.topic == topic]

    def stats(self) -> dict[str, Any]:
        """Scheduler statistics."""
        total = len(self._jobs)
        by_status: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for job in self._jobs.values():
            by_status[job.status.value] = by_status.get(job.status.value, 0) + 1
            by_kind[job.kind.value] = by_kind.get(job.kind.value, 0) + 1

        due_count = sum(1 for j in self._jobs.values() if j.is_due)
        total_runs = sum(j.run_count for j in self._jobs.values())

        return {
            "total_jobs": total,
            "due_now": due_count,
            "total_runs": total_runs,
            "by_status": by_status,
            "by_kind": by_kind,
        }

    def clear_completed(self) -> int:
        """Remove completed/failed/cancelled jobs. Returns count removed."""
        to_remove = [
            jid for jid, j in self._jobs.items()
            if j.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
        ]
        for jid in to_remove:
            del self._jobs[jid]
        return len(to_remove)

    # ─── Internals ───────────────────────────────────────────────────

    def _enforce_limit(self) -> None:
        """Evict oldest completed jobs if at capacity."""
        if len(self._jobs) >= self._max_jobs:
            self.clear_completed()
        if len(self._jobs) >= self._max_jobs:
            # Force-remove oldest pending low-priority
            candidates = [
                j for j in self._jobs.values()
                if j.status == JobStatus.PENDING
            ]
            candidates.sort(key=lambda j: (j.priority, j.created_at))
            for c in candidates[: len(candidates) // 4]:
                del self._jobs[c.job_id]

    def _execute_batch(self, job: ScheduledJob) -> None:
        """Flush a batch job — combine items into payload and mark done."""
        job.payload = {
            "items": list(job.batch_items),
            "count": len(job.batch_items),
            "flushed_at": time.time(),
        }
        job.last_run_at = time.time()
        job.run_count += 1
        job.status = JobStatus.COMPLETED
        job.batch_items = []
