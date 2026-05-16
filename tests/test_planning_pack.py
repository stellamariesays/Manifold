"""Tests for planning and scheduling capability packs."""

import asyncio
import pytest
from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_planning_pack, load_schedule_pack
from manifold.scheduler import AgentScheduler


# ── Planning Pack Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_toposort_linear_chain():
    """Topological sort handles a linear dependency chain."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_planning_pack(builder)

    res = await builder.invoke("plan-toposort", {
        "tasks": [
            {"name": "fetch", "depends_on": []},
            {"name": "parse", "depends_on": ["fetch"]},
            {"name": "store", "depends_on": ["parse"]},
        ]
    })
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert result["order"] == ["fetch", "parse", "store"]
    assert result["total"] == 3
    print(f"✅ Toposort linear: {result['order']}")


@pytest.mark.asyncio
async def test_toposort_diamond():
    """Topological sort handles diamond dependency."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_planning_pack(builder)

    res = await builder.invoke("plan-toposort", {
        "tasks": [
            {"name": "root", "depends_on": []},
            {"name": "left", "depends_on": ["root"]},
            {"name": "right", "depends_on": ["root"]},
            {"name": "merge", "depends_on": ["left", "right"]},
        ]
    })
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert result["order"][0] == "root"
    assert result["order"][-1] == "merge"
    print(f"✅ Toposort diamond: {result['order']}")


@pytest.mark.asyncio
async def test_toposort_cycle_detection():
    """Topological sort detects circular dependencies."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_planning_pack(builder)

    res = await builder.invoke("plan-toposort", {
        "tasks": [
            {"name": "a", "depends_on": ["b"]},
            {"name": "b", "depends_on": ["a"]},
        ]
    })
    assert res.ok
    result = res.output
    assert result["ok"] is False
    assert "circular" in result["error"].lower()
    print(f"✅ Cycle detected: {result['error']}")


@pytest.mark.asyncio
async def test_toposort_empty():
    """Topological sort rejects empty task list."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_planning_pack(builder)

    res = await builder.invoke("plan-toposort", {"tasks": []})
    assert res.ok
    result = res.output
    assert result["ok"] is False
    print(f"✅ Empty rejected: {result['error']}")


@pytest.mark.asyncio
async def test_priority_queue_basic():
    """Priority queue sorts by priority value."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_planning_pack(builder)

    res = await builder.invoke("plan-priority-queue", {
        "tasks": [
            {"name": "low", "priority": 0.9},
            {"name": "high", "priority": 0.1},
            {"name": "mid", "priority": 0.5},
        ]
    })
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert result["order"] == ["high", "mid", "low"]
    print(f"✅ Priority queue: {result['order']}")


@pytest.mark.asyncio
async def test_priority_queue_with_grouping():
    """Priority queue groups tasks by a field."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_planning_pack(builder)

    res = await builder.invoke("plan-priority-queue", {
        "tasks": [
            {"name": "a1", "priority": 0.1, "team": "alpha"},
            {"name": "b1", "priority": 0.2, "team": "beta"},
            {"name": "a2", "priority": 0.3, "team": "alpha"},
        ],
        "group_by": "team",
    })
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert "groups" in result
    assert result["groups"]["alpha"] == ["a1", "a2"]
    assert result["groups"]["beta"] == ["b1"]
    print(f"✅ Grouped: {result['groups']}")


@pytest.mark.asyncio
async def test_estimate_serial():
    """Estimation with parallelism=1 sums tasks."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_planning_pack(builder)

    res = await builder.invoke("plan-estimate", {
        "tasks": [
            {"name": "a", "estimate_seconds": 10},
            {"name": "b", "estimate_seconds": 20},
            {"name": "c", "estimate_seconds": 30},
        ],
        "parallelism": 1,
    })
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert result["total_serial_seconds"] == 60
    assert result["estimated_seconds"] > 60  # 10% overhead
    print(f"✅ Serial estimate: {result['estimated_seconds']}s")


@pytest.mark.asyncio
async def test_estimate_parallel():
    """Estimation with parallelism reduces wall time."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_planning_pack(builder)

    res = await builder.invoke("plan-estimate", {
        "tasks": [
            {"name": "a", "estimate_seconds": 10},
            {"name": "b", "estimate_seconds": 10},
            {"name": "c", "estimate_seconds": 10},
            {"name": "d", "estimate_seconds": 10},
        ],
        "parallelism": 4,
    })
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert result["estimated_seconds"] < 15
    assert result["critical_path_seconds"] == 10
    print(f"✅ Parallel estimate: {result['estimated_seconds']}s (parallelism=4)")


# ── Scheduling Pack Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_one_shot():
    """Schedule a one-shot task."""
    agent = Agent(name="scheduler", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    sched = AgentScheduler(agent)
    load_schedule_pack(builder, sched)

    res = await builder.invoke("schedule-task", {
        "topic": "health-check",
        "delay_seconds": 60,
        "priority": 0.8,
    })
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert "job_id" in result
    assert result["topic"] == "health-check"
    print(f"✅ Scheduled one-shot: {result['job_id']}")


@pytest.mark.asyncio
async def test_schedule_recurring():
    """Schedule a recurring task."""
    agent = Agent(name="scheduler", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    sched = AgentScheduler(agent)
    load_schedule_pack(builder, sched)

    res = await builder.invoke("schedule-task", {
        "topic": "telemetry",
        "interval_seconds": 300,
    })
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert result["kind"] == "recurring"
    print(f"✅ Scheduled recurring: {result['job_id']}")


@pytest.mark.asyncio
async def test_schedule_list():
    """List scheduled jobs."""
    agent = Agent(name="scheduler", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    sched = AgentScheduler(agent)
    load_schedule_pack(builder, sched)

    await builder.invoke("schedule-task", {"topic": "a", "delay_seconds": 10})
    await builder.invoke("schedule-task", {"topic": "b", "delay_seconds": 20})

    res = await builder.invoke("schedule-list", {})
    assert res.ok
    result = res.output
    assert result["ok"] is True
    assert result["count"] == 2
    print(f"✅ Listed jobs: {result['count']}")


@pytest.mark.asyncio
async def test_schedule_cancel():
    """Cancel a scheduled job."""
    agent = Agent(name="scheduler", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    sched = AgentScheduler(agent)
    load_schedule_pack(builder, sched)

    sched_res = await builder.invoke("schedule-task", {"topic": "to-cancel", "delay_seconds": 100})
    job_id = sched_res.output["job_id"]

    cancel_res = await builder.invoke("schedule-cancel", {"job_id": job_id})
    assert cancel_res.ok
    assert cancel_res.output["ok"] is True

    # Verify cancelled job removed from active pending
    list_res = await builder.invoke("schedule-list", {})
    active = [j for j in list_res.output["jobs"] if j["status"] != "cancelled"]
    assert all(j["job_id"] != job_id for j in active)
    print(f"✅ Cancelled job: {job_id}")


@pytest.mark.asyncio
async def test_plan_caps_registered():
    """Planning pack registers all capabilities on the agent."""
    agent = Agent(name="planner", transport="memory://test")
    await agent.join()
    builder = CapabilityBuilder(agent)
    specs = load_planning_pack(builder)

    names = [s.name for s in specs]
    assert "plan-toposort" in names
    assert "plan-priority-queue" in names
    assert "plan-estimate" in names
    print(f"✅ Registered caps: {names}")
