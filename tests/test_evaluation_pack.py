"""Tests for the evaluation capability pack."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_evaluation_pack


@pytest.fixture()
def builder():
    a = Agent("eval-tester")
    b = CapabilityBuilder(a)
    load_evaluation_pack(b)
    return b


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestEvalScore:
    def test_numeric_score(self, builder):
        result = _run(builder.invoke("eval-score", {
            "output": "some output",
            "score": 0.85,
            "mode": "numeric",
            "criteria": [],
            "rubric": [],
            "agent_name": "agent-x",
            "capability": "solar-prediction",
        }))
        assert result.ok is True
        assert result.output["score"] == 0.85
        assert result.output["ok"] is True

    def test_score_clamped(self, builder):
        result = _run(builder.invoke("eval-score", {
            "output": "", "score": 1.5, "mode": "numeric",
            "criteria": [], "rubric": [],
        }))
        assert result.ok is True
        assert result.output["score"] == 1.0

    def test_pass_fail(self, builder):
        result = _run(builder.invoke("eval-score", {
            "output": "", "mode": "pass_fail", "expected_pass": True,
            "score": 0.0, "criteria": [], "rubric": [],
            "agent_name": "a", "capability": "cap",
        }))
        assert result.output["score"] == 1.0
        assert result.output["passed"] is True

    def test_rubric(self, builder):
        result = _run(builder.invoke("eval-score", {
            "output": "", "mode": "rubric", "score": 0.0,
            "criteria": [],
            "rubric": [
                {"name": "accuracy", "weight": 0.6, "score": 0.9},
                {"name": "speed", "weight": 0.4, "score": 0.8},
            ],
            "agent_name": "a", "capability": "cap",
        }))
        assert result.ok is True
        expected = (0.9 * 0.6 + 0.8 * 0.4) / 1.0
        assert abs(result.output["score"] - round(expected, 4)) < 0.001


class TestEvalHistory:
    def test_history_records(self, builder):
        _run(builder.invoke("eval-score", {"output": "", "score": 0.7, "mode": "numeric",
            "criteria": [], "rubric": [], "agent_name": "h-agent", "capability": "h-cap"}))
        _run(builder.invoke("eval-score", {"output": "", "score": 0.9, "mode": "numeric",
            "criteria": [], "rubric": [], "agent_name": "h-agent", "capability": "h-cap"}))

        result = _run(builder.invoke("eval-history", {"agent_name": "h-agent", "capability": "h-cap", "limit": 50}))
        assert result.ok is True
        assert result.output["count"] >= 2


class TestEvalBenchmark:
    def test_benchmark_stats(self, builder):
        for s in [0.5, 0.6, 0.7, 0.8, 0.9]:
            _run(builder.invoke("eval-score", {"output": "", "score": s, "mode": "numeric",
                "criteria": [], "rubric": [], "agent_name": "bench-agent", "capability": "bench-cap"}))

        result = _run(builder.invoke("eval-benchmark", {"agent_name": "bench-agent", "capability": "bench-cap"}))
        assert result.ok is True
        assert result.output["count"] >= 5
        assert result.output["trend"] in ("improving", "declining", "stable")


class TestEvalCompare:
    def test_compare_two_agents(self, builder):
        for s in [0.9, 0.95]:
            _run(builder.invoke("eval-score", {"output": "", "score": s, "mode": "numeric",
                "criteria": [], "rubric": [], "agent_name": "comp-a", "capability": "comp-cap"}))
        for s in [0.3, 0.4]:
            _run(builder.invoke("eval-score", {"output": "", "score": s, "mode": "numeric",
                "criteria": [], "rubric": [], "agent_name": "comp-b", "capability": "comp-cap"}))

        result = _run(builder.invoke("eval-compare", {"agent_a": "comp-a", "agent_b": "comp-b", "capability": "comp-cap"}))
        assert result.ok is True
        assert result.output["winner"] == "comp-a"
        assert result.output["delta"] > 0


class TestEvalLeaderboard:
    def test_leaderboard(self, builder):
        _run(builder.invoke("eval-score", {"output": "", "score": 0.9, "mode": "numeric",
            "criteria": [], "rubric": [], "agent_name": "lb-top", "capability": "lb-cap"}))
        _run(builder.invoke("eval-score", {"output": "", "score": 0.5, "mode": "numeric",
            "criteria": [], "rubric": [], "agent_name": "lb-mid", "capability": "lb-cap"}))

        result = _run(builder.invoke("eval-leaderboard", {"capability": "lb-cap", "top_n": 5}))
        assert result.ok is True
        assert result.output["total_agents"] >= 2
        assert result.output["leaderboard"][0]["agent"] == "lb-top"


class TestEvalCatalogEntry:
    def test_all_caps_registered(self, builder):
        caps = builder.list_capabilities()
        names = [c.name for c in caps]
        assert "eval-score" in names
        assert "eval-history" in names
        assert "eval-benchmark" in names
        assert "eval-compare" in names
        assert "eval-leaderboard" in names
