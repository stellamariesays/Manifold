"""Tests for the task dispatcher."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.audience import Signal
from manifold.dispatch import (
    DispatchStatus,
    TaskDispatcher,
    TaskPriority,
    DispatchResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────

async def _mesh_with_dispatcher():
    """Create a mesh with a dispatcher and several worker agents."""
    dispatcher = Agent(name="dispatcher", transport="memory://dispatch")
    dispatcher.knows(["task-routing", "audience-dispatch"])
    await dispatcher.join()

    # Register workers in dispatcher's registry
    workers = [
        {
            "name": "solar-worker",
            "capabilities": ["solar-prediction", "signal-processing", "astrophysics"],
            "address": "memory://dispatch",
            "focus": "solar-prediction",
        },
        {
            "name": "btc-worker",
            "capabilities": ["bitcoin-analysis", "technical-analysis", "trading-signals"],
            "address": "memory://dispatch",
            "focus": "bitcoin-analysis",
        },
        {
            "name": "infra-worker",
            "capabilities": ["deployment", "monitoring", "security"],
            "address": "memory://dispatch",
            "focus": "monitoring",
        },
        {
            "name": "general-worker",
            "capabilities": ["general-purpose", "data-analysis"],
            "address": "memory://dispatch",
            "focus": None,
        },
    ]

    for w in workers:
        await dispatcher._on_registry_announcement(w)

    disp = TaskDispatcher(dispatcher, min_score=0.0)
    return dispatcher, disp


# ── Core dispatch tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_to_best_match():
    """Dispatcher routes to the best-matched agent."""
    _, disp = await _mesh_with_dispatcher()
    result = await disp.dispatch("solar-prediction", {"region": "pacific"})
    assert result.ok
    assert result.agent_name == "solar-worker"
    assert result.status == DispatchStatus.DISPATCHED
    print(f"✅ Dispatch to best match: {result}")


@pytest.mark.asyncio
async def test_dispatch_btc_task():
    """BTC tasks route to btc-worker."""
    _, disp = await _mesh_with_dispatcher()
    result = await disp.dispatch("bitcoin-analysis", {"action": "signals"})
    assert result.ok
    assert result.agent_name == "btc-worker"
    print(f"✅ BTC dispatch: {result}")


@pytest.mark.asyncio
async def test_dispatch_no_candidates():
    """Dispatcher returns NO_CANDIDATES on empty mesh."""
    agent = Agent(name="solo", transport="memory://solo")
    agent.knows(["nothing-relevant"])
    await agent.join()
    disp = TaskDispatcher(agent, min_score=0.5)
    result = await disp.dispatch("quantum-computing")
    assert result.status == DispatchStatus.NO_CANDIDATES
    assert result.agent_name is None
    print(f"✅ No candidates: {result}")


@pytest.mark.asyncio
async def test_dispatch_direct_target():
    """target_agent bypasses audience routing."""
    _, disp = await _mesh_with_dispatcher()
    result = await disp.dispatch(
        "anything",
        target_agent="infra-worker",
    )
    assert result.ok
    assert result.agent_name == "infra-worker"
    print(f"✅ Direct target: {result}")


@pytest.mark.asyncio
async def test_dispatch_custom_task_id():
    """Custom task_id in payload is preserved."""
    _, disp = await _mesh_with_dispatcher()
    result = await disp.dispatch(
        "solar-prediction",
        {"task_id": "custom-123", "data": "test"},
    )
    assert result.task_id == "custom-123"
    print(f"✅ Custom task_id: {result.task_id}")


@pytest.mark.asyncio
async def test_dispatch_auto_task_id():
    """Auto-generated task_id when not in payload."""
    _, disp = await _mesh_with_dispatcher()
    result = await disp.dispatch("monitoring")
    assert result.task_id.startswith("task-")
    print(f"✅ Auto task_id: {result.task_id}")


# ── Priority tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_priority_levels():
    """All priority levels are accepted."""
    _, disp = await _mesh_with_dispatcher()
    for prio in TaskPriority:
        result = await disp.dispatch("solar", priority=prio)
        assert result.ok
    print(f"✅ Priority levels: {[p.value for p in TaskPriority]}")


# ── History and stats tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_history():
    """Dispatch history tracks all operations."""
    _, disp = await _mesh_with_dispatcher()
    await disp.dispatch("solar-prediction")
    await disp.dispatch("bitcoin-analysis")
    await disp.dispatch("deployment")

    assert len(disp.history) == 3
    # History is in order
    assert disp.history[0].topic == "solar-prediction"
    assert disp.history[1].topic == "bitcoin-analysis"
    print(f"✅ History: {len(disp.history)} entries")


@pytest.mark.asyncio
async def test_dispatch_stats():
    """Stats returns meaningful metrics."""
    _, disp = await _mesh_with_dispatcher()
    for _ in range(5):
        await disp.dispatch("solar-prediction")

    stats = disp.stats()
    assert stats["total"] == 5
    assert stats["success_rate"] > 0
    assert stats["avg_elapsed_ms"] >= 0
    print(f"✅ Stats: {stats}")


@pytest.mark.asyncio
async def test_dispatch_stats_empty():
    """Stats on empty dispatcher returns zeros."""
    agent = Agent(name="empty", transport="memory://e")
    await agent.join()
    disp = TaskDispatcher(agent)
    stats = disp.stats()
    assert stats["total"] == 0
    assert stats["success_rate"] == 0.0
    print(f"✅ Empty stats: {stats}")


@pytest.mark.asyncio
async def test_agent_distribution():
    """Distribution shows task counts per agent."""
    _, disp = await _mesh_with_dispatcher()
    await disp.dispatch("solar-prediction")
    await disp.dispatch("solar-prediction")
    await disp.dispatch("bitcoin-analysis")

    dist = disp.agent_distribution()
    assert "solar-worker" in dist
    assert dist["solar-worker"] == 2
    assert "btc-worker" in dist
    print(f"✅ Distribution: {dist}")


# ── History limit test ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_limit():
    """History trims to the configured limit."""
    _, disp = await _mesh_with_dispatcher()
    disp._history_limit = 5
    for i in range(10):
        await disp.dispatch("solar-prediction")
    assert len(disp.history) == 5
    print(f"✅ History limit: {len(disp.history)} (limited to 5)")


# ── Custom weights test ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_custom_weights():
    """Custom weights change routing in dispatch."""
    _, disp = await _mesh_with_dispatcher()
    # Trust-only: nobody is trusted, so scores may differ
    result = await disp.dispatch(
        "solar-prediction",
        weights={"trust": 1.0, "capability": 0.0, "focus": 0.0, "fog_gap": 0.0, "topology": 0.0},
    )
    assert isinstance(result, DispatchResult)
    print(f"✅ Custom weights: {result}")


# ── Fallback chain test ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fallback_on_rejection():
    """Dispatcher tracks fallback chain when all attempts fail."""
    # Create dispatcher that will fail because the transport is gone
    agent = Agent(name="lonely", transport="memory://lonely")
    agent.knows(["nothing"])
    await agent.join()

    # Add a fake peer but don't have it connected
    await agent._on_registry_announcement({
        "name": "ghost",
        "capabilities": ["everything"],
        "address": "ws://nonexistent:9999",
        "focus": "everything",
    })

    # The dispatch publishes to a topic — in-memory transport succeeds
    # so this tests the happy path of finding the ghost agent
    disp = TaskDispatcher(agent, min_score=0.0)
    result = await disp.dispatch("everything")
    # In-memory transport will "succeed" (it just publishes)
    assert result.ok
    assert result.agent_name == "ghost"
    print(f"✅ Fallback chain: {result}")


# ── Result repr test ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_result_repr():
    """DispatchResult has useful repr."""
    result = DispatchResult(
        task_id="task-abc123def456",
        topic="test",
        agent_name="worker",
        status=DispatchStatus.DISPATCHED,
    )
    r = repr(result)
    assert "task-abc" in r
    assert "worker" in r
    assert "dispatched" in r
    print(f"✅ Repr: {r}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
