"""Tests for audience analytics capability pack."""

import asyncio
import pytest
from manifold.capability_builder import CapabilityBuilder
from manifold.agent import Agent
from manifold.capability_pack import load_audience_analytics_pack, _routing_log


@pytest.fixture(autouse=True)
def clear_routing_log():
    _routing_log.clear()
    yield
    _routing_log.clear()


@pytest.fixture
def builder():
    a = Agent("test-analytics")
    b = CapabilityBuilder(a)
    load_audience_analytics_pack(b)
    return b


def _invoke(builder, name, payload):
    cap = builder.get(name)
    assert cap is not None, f"Capability '{name}' not found"
    return asyncio.run(cap.handler(payload))


def test_pack_registers_all_capabilities(builder):
    names = list(builder._caps.keys())
    assert "audience-record" in names
    assert "audience-analyze" in names
    assert "audience-weights" in names
    assert "audience-suggest" in names


def test_record_routing_decision(builder):
    result = _invoke(builder, "audience-record", {
        "topic": "solar-prediction",
        "agent": "helios",
        "score": 0.85,
        "signals": ["capability", "trust"],
        "outcome": "success",
    })
    assert result["ok"] is True
    assert "recorded_id" in result
    assert result["total"] >= 1


def test_record_multiple_and_analyze(builder):
    entries = [
        {"topic": "solar", "agent": "a", "score": 0.9, "signals": ["capability"], "outcome": "success"},
        {"topic": "solar", "agent": "b", "score": 0.7, "signals": ["trust"], "outcome": "partial"},
        {"topic": "wind", "agent": "a", "score": 0.5, "signals": ["capability"], "outcome": "fail"},
        {"topic": "solar", "agent": "c", "score": 0.3, "signals": ["fog_gap"], "outcome": "timeout"},
    ]
    for e in entries:
        _invoke(builder, "audience-record", e)

    result = _invoke(builder, "audience-analyze", {"topic": "solar"})
    assert result["ok"] is True
    assert result["count"] == 3
    assert result["success_rate"] > 0
    assert "capability" in result["signal_effectiveness"]


def test_analyze_with_outcome_filter(builder):
    _invoke(builder, "audience-record", {"topic": "x", "agent": "a", "score": 0.8, "signals": ["trust"], "outcome": "success"})
    _invoke(builder, "audience-record", {"topic": "x", "agent": "b", "score": 0.4, "signals": ["trust"], "outcome": "fail"})

    result = _invoke(builder, "audience-analyze", {"outcome": "fail"})
    assert result["count"] == 1
    assert result["outcomes"]["fail"] == 1


def test_weights_get_default(builder):
    result = _invoke(builder, "audience-weights", {"action": "get"})
    assert result["ok"] is True
    assert "capability" in result["weights"]
    assert abs(sum(result["weights"].values()) - 1.0) < 0.01


def test_weights_set_and_normalize(builder):
    result = _invoke(builder, "audience-weights", {"action": "set", "weights": {"capability": 0.6, "trust": 0.4}})
    assert result["ok"] is True
    assert result["weights"]["capability"] > result["weights"]["trust"]
    assert abs(sum(result["weights"].values()) - 1.0) < 0.01


def test_weights_auto_tune_no_data(builder):
    result = _invoke(builder, "audience-weights", {"action": "auto_tune"})
    assert result["ok"] is True
    assert result["tuned"] is False


def test_weights_auto_tune_with_data(builder):
    for _ in range(10):
        _invoke(builder, "audience-record", {"topic": "x", "agent": "a", "score": 0.8, "signals": ["capability"], "outcome": "success"})
    for _ in range(5):
        _invoke(builder, "audience-record", {"topic": "x", "agent": "b", "score": 0.4, "signals": ["fog_gap"], "outcome": "fail"})

    result = _invoke(builder, "audience-weights", {"action": "auto_tune"})
    assert result["ok"] is True
    assert result["tuned"] is True
    assert result["weights"]["capability"] > result["weights"]["fog_gap"]


def test_suggest_with_no_data(builder):
    result = _invoke(builder, "audience-suggest", {})
    assert result["ok"] is True
    assert len(result["suggestions"]) >= 1


def test_suggest_identifies_failing_agent(builder):
    for _ in range(5):
        _invoke(builder, "audience-record", {"topic": "x", "agent": "bad-agent", "score": 0.3, "signals": ["trust"], "outcome": "fail"})

    result = _invoke(builder, "audience-suggest", {"topic": "x"})
    assert result["ok"] is True
    assert any("bad-agent" in s for s in result["suggestions"])


def test_suggest_identifies_effective_agent(builder):
    _invoke(builder, "audience-record", {"topic": "x", "agent": "star", "score": 0.9, "signals": ["capability"], "outcome": "success"})
    _invoke(builder, "audience-record", {"topic": "x", "agent": "star", "score": 0.95, "signals": ["capability"], "outcome": "success"})

    result = _invoke(builder, "audience-suggest", {"topic": "x"})
    assert any("star" in s for s in result["suggestions"])


def test_record_log_bounded(builder):
    for i in range(1100):
        _invoke(builder, "audience-record", {"topic": "stress", "agent": f"a{i}", "score": 0.5, "signals": [], "outcome": "success"})
    result = _invoke(builder, "audience-analyze", {})
    assert result["count"] < 1100
