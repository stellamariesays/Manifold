"""Tests for the strategy capability pack."""

import pytest

from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_strategy_pack


@pytest.fixture
def builder():
    b = CapabilityBuilder(None)
    load_strategy_pack(b)
    return b


def _invoke(builder, name, payload):
    cap = builder._caps[name]
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(cap.handler(payload))


class TestCostBenefit:
    def test_basic_analysis(self, builder):
        result = _invoke(builder, "cost-benefit", {
            "options": [
                {"name": "A", "costs": [{"name": "time", "value": 10}], "benefits": [{"name": "value", "value": 30}]},
                {"name": "B", "costs": [{"name": "time", "value": 5}], "benefits": [{"name": "value", "value": 5}]},
            ]
        })
        assert result["ok"] is True
        assert result["recommendation"] == "A"
        assert result["analysis"][0]["net_value"] == 20
        assert result["analysis"][0]["rank"] == 1

    def test_roi_calculation(self, builder):
        result = _invoke(builder, "cost-benefit", {
            "options": [
                {"name": "X", "costs": [{"name": "c", "value": 100}], "benefits": [{"name": "b", "value": 300}]},
            ]
        })
        assert result["ok"] is True
        assert result["analysis"][0]["roi"] == 2.0

    def test_no_options(self, builder):
        result = _invoke(builder, "cost-benefit", {"options": []})
        assert result["ok"] is False


class TestPriorityScore:
    def test_ranking(self, builder):
        result = _invoke(builder, "priority-score", {
            "items": [
                {"name": "low", "urgency": 1, "impact": 2},
                {"name": "high", "urgency": 10, "impact": 9},
                {"name": "mid", "urgency": 5, "impact": 5},
            ],
            "criteria": {"urgency": 0.7, "impact": 0.3},
        })
        assert result["ok"] is True
        assert result["rankings"][0]["name"] == "high"
        assert result["rankings"][0]["rank"] == 1

    def test_missing_criteria(self, builder):
        result = _invoke(builder, "priority-score", {"items": [{"name": "a"}], "criteria": {}})
        assert result["ok"] is False


class TestResourceAllocate:
    def test_proportional_allocation(self, builder):
        result = _invoke(builder, "resource-allocate", {
            "budget": 100,
            "demands": [
                {"name": "A", "priority": 3},
                {"name": "B", "priority": 1},
            ]
        })
        assert result["ok"] is True
        assert result["allocated"] == 100.0
        assert result["surplus"] == 0.0
        a_alloc = next(a for a in result["allocations"] if a["name"] == "A")
        b_alloc = next(a for a in result["allocations"] if a["name"] == "B")
        assert a_alloc["allocation"] > b_alloc["allocation"]

    def test_minimum_guarantee(self, builder):
        result = _invoke(builder, "resource-allocate", {
            "budget": 100,
            "demands": [
                {"name": "A", "priority": 1, "minimum": 40},
                {"name": "B", "priority": 1, "minimum": 40},
            ]
        })
        assert result["ok"] is True
        a_alloc = next(a for a in result["allocations"] if a["name"] == "A")
        assert a_alloc["allocation"] >= 40

    def test_cap_respected(self, builder):
        result = _invoke(builder, "resource-allocate", {
            "budget": 100,
            "demands": [
                {"name": "A", "priority": 10, "cap": 30},
                {"name": "B", "priority": 1},
            ]
        })
        a_alloc = next(a for a in result["allocations"] if a["name"] == "A")
        assert a_alloc["allocation"] <= 30


class TestConflictResolve:
    def test_score_strategy(self, builder):
        result = _invoke(builder, "conflict-resolve", {
            "proposals": [
                {"name": "alpha", "score": 50},
                {"name": "beta", "score": 80},
            ],
            "strategy": "score",
        })
        assert result["ok"] is True
        assert result["winner"] == "beta"

    def test_consensus_strategy(self, builder):
        result = _invoke(builder, "conflict-resolve", {
            "proposals": [
                {"name": "p1", "color": "red", "size": 10},
                {"name": "p2", "color": "blue", "size": 10},
            ],
            "strategy": "consensus",
        })
        assert result["ok"] is True
        assert result["merged"]["size"] == 10
        assert any("color" in c for c in result["conflicts"])

    def test_priority_strategy(self, builder):
        result = _invoke(builder, "conflict-resolve", {
            "proposals": [
                {"name": "low", "priority": 1},
                {"name": "high", "priority": 10},
            ],
            "strategy": "priority",
        })
        assert result["ok"] is True
        assert result["winner"] == "high"

    def test_too_few_proposals(self, builder):
        result = _invoke(builder, "conflict-resolve", {"proposals": [{"name": "only"}], "strategy": "score"})
        assert result["ok"] is False


class TestDecisionLog:
    def test_log_records_decisions(self, builder):
        _invoke(builder, "cost-benefit", {
            "options": [{"name": "A", "costs": [], "benefits": [{"name": "v", "value": 10}]}]
        })
        result = _invoke(builder, "decision-log", {})
        assert result["ok"] is True
        assert result["total"] >= 1

    def test_type_filter(self, builder):
        result = _invoke(builder, "decision-log", {"type": "nonexistent"})
        assert result["ok"] is True
        assert result["total"] == 0


class TestTradeoffMatrix:
    def test_pareto_front(self, builder):
        result = _invoke(builder, "tradeoff-matrix", {
            "options": [
                {"name": "dominant", "quality": 10, "reliability": 9},
                {"name": "dominated", "quality": 5, "reliability": 4},
                {"name": "tradeoff", "quality": 8, "reliability": 6},
            ],
            "dimensions": ["quality", "reliability"],
        })
        assert result["ok"] is True
        assert "dominant" in result["pareto_front"]
        assert "dominated" in result["dominated"]

    def test_insufficient_options(self, builder):
        result = _invoke(builder, "tradeoff-matrix", {
            "options": [{"name": "A", "speed": 10}],
            "dimensions": ["speed"],
        })
        assert result["ok"] is False
