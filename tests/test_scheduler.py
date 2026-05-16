"""Tests for agent scheduler."""

import asyncio
import time
import pytest
from manifold.agent import Agent
from manifold.scheduler import (
    AgentScheduler,
    ScheduledJob,
    TickResult,
    JobStatus,
    JobKind,
)


# ── Helpers ──────────────────────────────────────────────────────────────

async def _scheduler_agent(name: str = "scheduler-test") -> tuple[Agent, AgentScheduler]:
    """Create an agent with a scheduler."""
    agent = Agent(name=name, transport="memory://test")
    agent.knows(["scheduling", "task-management"])
    await agent.join()
    return agent, AgentScheduler(agent)


# ── One-shot tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_once_immediate():
    """One-shot job with no delay is due immediately."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test-task")
    assert job.kind == JobKind.ONCE
    assert job.is_due
    print(f"✅ Once immediate: {job}")


@pytest.mark.asyncio
async def test_once_delayed():
    """One-shot job with delay is not due immediately."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test-task", delay_seconds=60)
    assert not job.is_due
    print(f"✅ Once delayed: {job}")


@pytest.mark.asyncio
async def test_once_executes_on_tick():
    """One-shot job executes when ticked."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test-task")
    result = sched.tick()
    assert job.job_id in result.executed
    assert job.status == JobStatus.COMPLETED
    assert job.run_count == 1
    print(f"✅ Once executes: {result}")


@pytest.mark.asyncio
async def test_once_does_not_rerun():
    """One-shot job doesn't reschedule after execution."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test-task")
    sched.tick()
    assert job.status == JobStatus.COMPLETED
    # Second tick should not re-execute
    result = sched.tick()
    assert job.job_id not in result.executed
    print(f"✅ Once no-rerun: {result}")


@pytest.mark.asyncio
async def test_once_delayed_not_ready():
    """Delayed one-shot doesn't execute before its time."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test-task", delay_seconds=9999)
    result = sched.tick()
    assert len(result.executed) == 0
    assert job.status == JobStatus.PENDING
    print(f"✅ Once not-ready: {result}")


# ── Recurring tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recurring_reschedules():
    """Recurring job reschedules after execution."""
    agent, sched = await _scheduler_agent()
    job = sched.every("health-check", interval_seconds=10)
    assert job.is_recurring
    result = sched.tick()
    assert job.job_id in result.executed
    assert job.job_id in result.rescheduled
    assert job.status == JobStatus.PENDING  # Back to pending
    assert job.run_count == 1
    print(f"✅ Recurring reschedules: {result}")


@pytest.mark.asyncio
async def test_recurring_max_runs():
    """Recurring job stops after max_runs."""
    agent, sched = await _scheduler_agent()
    job = sched.every("health-check", interval_seconds=0.001, max_runs=3)
    for _ in range(5):
        time.sleep(0.002)
        sched.tick()
    assert job.run_count == 3
    assert job.is_exhausted
    print(f"✅ Recurring max-runs: runs={job.run_count}, exhausted={job.is_exhausted}")


@pytest.mark.asyncio
async def test_recurring_interval():
    """Recurring job respects interval."""
    agent, sched = await _scheduler_agent()
    job = sched.every("check", interval_seconds=9999)
    sched.tick()  # First run (next_run_at was 0 or now)
    assert job.status == JobStatus.PENDING
    assert not job.is_due  # Not due for 9999 seconds
    print(f"✅ Recurring interval: next_run in {job.next_run_at - time.time():.0f}s")


# ── Batch tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_flush_at_threshold():
    """Batch flushes when item count reaches flush_at."""
    agent, sched = await _scheduler_agent()
    job = sched.batch("telemetry", flush_at=3)
    assert job.kind == JobKind.BATCH
    # Add items below threshold
    flushed = sched.push_batch(job.job_id, {"a": 1}, {"b": 2})
    assert not flushed
    assert job.status == JobStatus.PENDING
    # Add one more to hit threshold
    flushed = sched.push_batch(job.job_id, {"c": 3})
    assert flushed
    assert job.status == JobStatus.COMPLETED
    assert job.payload["count"] == 3
    print(f"✅ Batch flush-at: {job}")


@pytest.mark.asyncio
async def test_batch_flush_on_tick_timeout():
    """Batch flushes on tick if past its scheduled time."""
    agent, sched = await _scheduler_agent()
    job = sched.batch("telemetry", items=[{"x": 1}], flush_at=100, max_wait_seconds=0)
    # next_run_at is set to now since items exist
    result = sched.tick()
    assert job.job_id in result.executed
    assert job.status == JobStatus.COMPLETED
    print(f"✅ Batch tick-flush: {result}")


@pytest.mark.asyncio
async def test_batch_empty_no_flush():
    """Empty batch doesn't flush on tick."""
    agent, sched = await _scheduler_agent()
    job = sched.batch("telemetry", flush_at=1, max_wait_seconds=0)
    result = sched.tick()
    assert job.job_id not in result.executed
    print(f"✅ Batch empty: {result}")


# ── Lifecycle tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel():
    """Cancelling a job prevents execution."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test")
    assert sched.cancel(job.job_id)
    assert job.status == JobStatus.CANCELLED
    result = sched.tick()
    assert job.job_id not in result.executed
    print(f"✅ Cancel: {job}")


@pytest.mark.asyncio
async def test_pause_resume():
    """Paused jobs skip execution; resumed jobs don't."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test")
    sched.pause(job.job_id)
    assert job.status == JobStatus.PAUSED
    result = sched.tick()
    assert job.job_id not in result.executed

    sched.resume(job.job_id)
    assert job.status == JobStatus.PENDING
    result = sched.tick()
    assert job.job_id in result.executed
    print(f"✅ Pause/resume: {result}")


@pytest.mark.asyncio
async def test_remove():
    """Removing a job deletes it entirely."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test")
    assert sched.remove(job.job_id)
    assert sched.get(job.job_id) is None
    print(f"✅ Remove: job gone")


@pytest.mark.asyncio
async def test_cancel_nonexistent():
    """Cancelling nonexistent job returns False."""
    agent, sched = await _scheduler_agent()
    assert not sched.cancel("nope")
    print(f"✅ Cancel nonexistent: False")


# ─── Priority tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_priority_ordering():
    """Higher priority jobs execute first."""
    agent, sched = await _scheduler_agent()
    low = sched.once("low-task", priority=0.1)
    high = sched.once("high-task", priority=0.9)
    result = sched.tick()
    # High should execute first
    assert len(result.executed) == 2
    assert result.executed[0] == high.job_id
    print(f"✅ Priority ordering: {[result.executed]}")


# ─── Query tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pending_list():
    """pending() returns pending jobs sorted by next_run_at."""
    agent, sched = await _scheduler_agent()
    j1 = sched.once("task-a", delay_seconds=100)
    j2 = sched.once("task-b", delay_seconds=10)
    j3 = sched.once("task-c", delay_seconds=50)
    pending = sched.pending()
    assert len(pending) == 3
    assert pending[0].job_id == j2.job_id  # Soonest first
    print(f"✅ Pending order: {[p.topic for p in pending]}")


@pytest.mark.asyncio
async def test_jobs_by_topic():
    """jobs_by_topic filters correctly."""
    agent, sched = await _scheduler_agent()
    sched.once("solar-check")
    sched.once("orbit-calc")
    sched.once("solar-check")
    solar = sched.jobs_by_topic("solar-check")
    assert len(solar) == 2
    print(f"✅ Jobs by topic: {len(solar)} solar jobs")


@pytest.mark.asyncio
async def test_stats():
    """stats() returns summary."""
    agent, sched = await _scheduler_agent()
    sched.once("a")
    sched.every("b", interval_seconds=60)
    sched.batch("c")
    stats = sched.stats()
    assert stats["total_jobs"] == 3
    assert stats["by_kind"]["once"] == 1
    assert stats["by_kind"]["recurring"] == 1
    assert stats["by_kind"]["batch"] == 1
    print(f"✅ Stats: {stats}")


# ─── Cleanup tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_completed():
    """clear_completed removes finished jobs."""
    agent, sched = await _scheduler_agent()
    j1 = sched.once("done")
    sched.tick()  # Completes j1
    sched.once("pending")
    removed = sched.clear_completed()
    assert removed == 1
    assert len(sched._jobs) == 1
    print(f"✅ Clear completed: removed {removed}")


# ─── Tick result tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tick_result_ok():
    """TickResult.ok is True when no errors."""
    agent, sched = await _scheduler_agent()
    sched.once("test")
    result = sched.tick()
    assert result.ok
    assert len(result.executed) == 1
    print(f"✅ Tick result ok: {result}")


@pytest.mark.asyncio
async def test_empty_tick():
    """Ticking with no jobs returns empty result."""
    agent, sched = await _scheduler_agent()
    result = sched.tick()
    assert result.ok
    assert len(result.executed) == 0
    print(f"✅ Empty tick: {result}")


# ─── Async tick test ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_async_tick():
    """async tick_async works with dispatcher."""
    agent, sched = await _scheduler_agent()
    job = sched.once("test-task")
    result = await sched.tick_async()
    assert job.job_id in result.executed
    print(f"✅ Async tick: {result}")


if __name__ == "__main__":
    asyncio.run(_run_all())
