"""Tests for manifold.task_router — unified audience→negotiate→dispatch."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.audience import AudienceEntry, AudienceReport
from manifold.task_router import (
    RoutePolicy,
    RouteResult,
    RouteStatus,
    RouteStrategy,
    TaskRouter,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_agent(name: str = "alice", capabilities: list[str] | None = None) -> Agent:
    agent = Agent(name=name)
    if capabilities:
        agent.capabilities = capabilities
    return agent


def _make_agent_with_audience(
    name: str = "alice",
    audience_entries: list[AudienceEntry] | None = None,
) -> Agent:
    """Create an agent whose audience() returns fixed entries."""
    agent = Agent(name=name)
    report = AudienceReport(
        topic="test",
        entries=audience_entries or [],
    )
    agent.audience = lambda task="": report  # type: ignore[assignment]
    return agent


def _entry(name: str, score: float = 0.5, caps: list[str] | None = None) -> AudienceEntry:
    return AudienceEntry(
        name=name,
        score=score,
        capabilities=caps or ["test"],
    )


# ─── RouteResult ────────────────────────────────────────────────────────────

class TestRouteResult:
    def test_repr(self):
        r = RouteResult(task="ping", status=RouteStatus.COMPLETED, agent_name="bob")
        s = repr(r)
        assert "bob" in s
        assert "completed" in s

    def test_defaults(self):
        r = RouteResult()
        assert r.status == RouteStatus.COMPLETED
        assert r.attempts == 0


# ─── No candidates ──────────────────────────────────────────────────────────

class TestNoCandidates:
    @pytest.mark.asyncio
    async def test_empty_audience(self):
        agent = _make_agent_with_audience("alice", [])
        router = TaskRouter(agent)
        result = await router.route("missing-task")
        assert result.status == RouteStatus.NO_CANDIDATES

    @pytest.mark.asyncio
    async def test_all_below_min_score(self):
        entries = [_entry("bob", score=0.01)]
        agent = _make_agent_with_audience("alice", entries)
        policy = RoutePolicy(min_audience_score=0.5)
        router = TaskRouter(agent, policy=policy)
        result = await router.route("hard-task")
        assert result.status == RouteStatus.NO_CANDIDATES


# ─── Best-first strategy ───────────────────────────────────────────────────

class TestBestFirst:
    @pytest.mark.asyncio
    async def test_best_first_attempts_top(self):
        """Best-first should attempt the top candidate."""
        entries = [_entry("stranger", score=0.9)]
        agent = _make_agent_with_audience("alice", entries)
        policy = RoutePolicy(strategy=RouteStrategy.BEST_FIRST)
        router = TaskRouter(agent, policy=policy)
        result = await router.route("test-cap")
        # Will fail (no real capability) but should have attempted
        assert result.agent_name == "stranger"
        assert result.attempts == 1


# ─── Top-N strategy (default) ──────────────────────────────────────────────

class TestTopN:
    @pytest.mark.asyncio
    async def test_fallback_tries_all(self):
        """Should try all candidates when they all fail."""
        entries = [
            _entry("stranger1", score=0.9),
            _entry("stranger2", score=0.8),
            _entry("stranger3", score=0.7),
        ]
        agent = _make_agent_with_audience("alice", entries)
        policy = RoutePolicy(strategy=RouteStrategy.TOP_N, max_attempts=3)
        router = TaskRouter(agent, policy=policy)
        result = await router.route("test-cap")
        assert result.status == RouteStatus.ALL_FAILED
        assert result.attempts == 3
        assert len(result.fallback_log) == 3

    @pytest.mark.asyncio
    async def test_respects_max_candidates(self):
        entries = [_entry(f"agent{i}", score=0.9 - i * 0.05) for i in range(10)]
        agent = _make_agent_with_audience("alice", entries)
        policy = RoutePolicy(strategy=RouteStrategy.TOP_N, max_candidates=3, max_attempts=10)
        router = TaskRouter(agent, policy=policy)
        result = await router.route("something")
        assert result.attempts <= 3

    @pytest.mark.asyncio
    async def test_fallback_log_tracks_agents(self):
        entries = [_entry("a", score=0.9), _entry("b", score=0.8)]
        agent = _make_agent_with_audience("alice", entries)
        router = TaskRouter(agent)
        result = await router.route("task")
        log = result.fallback_log
        assert len(log) == 2
        assert log[0]["agent"] == "a"
        assert log[1]["agent"] == "b"


# ─── Parallel strategy ─────────────────────────────────────────────────────

class TestParallel:
    @pytest.mark.asyncio
    async def test_parallel_attempts_all(self):
        entries = [_entry("x", score=0.9), _entry("y", score=0.8)]
        agent = _make_agent_with_audience("alice", entries)
        policy = RoutePolicy(strategy=RouteStrategy.PARALLEL)
        router = TaskRouter(agent, policy=policy)
        result = await router.route("task")
        assert result.status == RouteStatus.ALL_FAILED
        # Both should have been attempted
        assert len(result.fallback_log) == 2


# ─── Competitive strategy ──────────────────────────────────────────────────

class TestCompetitive:
    @pytest.mark.asyncio
    async def test_competitive_attempts_candidates(self):
        entries = [_entry("x", score=0.9), _entry("y", score=0.8)]
        agent = _make_agent_with_audience("alice", entries)
        policy = RoutePolicy(strategy=RouteStrategy.COMPETITIVE)
        router = TaskRouter(agent, policy=policy)
        result = await router.route("task")
        # Will fail but should have attempted
        assert result.status == RouteStatus.ALL_FAILED


# ─── Policy ─────────────────────────────────────────────────────────────────

class TestPolicy:
    def test_defaults(self):
        p = RoutePolicy()
        assert p.strategy == RouteStrategy.TOP_N
        assert p.max_candidates == 5
        assert p.max_attempts == 3
        assert p.min_audience_score == 0.1

    def test_custom(self):
        p = RoutePolicy(
            strategy=RouteStrategy.BEST_FIRST,
            max_candidates=10,
            min_audience_score=0.5,
        )
        assert p.strategy == RouteStrategy.BEST_FIRST
        assert p.max_candidates == 10


# ─── Stats & Summary ───────────────────────────────────────────────────────

class TestStatsAndSummary:
    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        entries = [_entry("alice", score=0.9, caps=["ping"])]
        agent = _make_agent_with_audience("alice", entries)
        router = TaskRouter(agent)

        await router.route("ping")
        await router.route("ping")
        await router.route("missing")

        stats = router.stats()
        assert stats["total_routed"] == 3
        assert "success_rate" in stats
        assert "path_distribution" in stats

    @pytest.mark.asyncio
    async def test_summary_format(self):
        entries = [_entry("alice", score=0.9, caps=["ping"])]
        agent = _make_agent_with_audience("alice", entries)
        router = TaskRouter(agent)
        await router.route("ping")

        summary = router.summary()
        assert "TaskRouter" in summary

    @pytest.mark.asyncio
    async def test_recent(self):
        entries = [_entry("alice", score=0.9, caps=["ping"])]
        agent = _make_agent_with_audience("alice", entries)
        router = TaskRouter(agent)
        await router.route("ping")

        recent = router.recent(5)
        assert len(recent) >= 1
        assert isinstance(recent[0], RouteResult)
