"""Tests for audience pipeline — composable routing stages."""

import pytest
from unittest.mock import MagicMock

from manifold.agent import Agent
from manifold.audience import Signal
from manifold.audience_pipeline import (
    AudiencePipeline,
    BoostStage,
    DedupeStage,
    DiversityStage,
    FilterStage,
    LimitStage,
    PipelineReport,
    RequireSignalStage,
    SplitStage,
    ThresholdStage,
    TransformStage,
)


@pytest.fixture
def mesh():
    """Create a small mesh of agents with a shared registry."""
    agents = {}
    for name, caps, focus in [
        ("solar-agent", ["solar-prediction", "weather-forecast", "energy-modeling"], "solar energy forecasting"),
        ("grid-agent", ["grid-balancing", "battery-optimization", "energy-storage"], "grid load management"),
        ("solar-agent-2", ["solar-prediction", "panel-diagnostics", "inverter-monitoring"], "solar panel maintenance"),
        ("nlp-agent", ["nlp-sentiment", "text-summarization", "language-detection"], None),
        ("infra-agent", ["monitoring", "deployment", "security-hardening"], "monitoring"),
    ]:
        a = Agent(name)
        a.knows(caps)
        agents[name] = a

    # Share registry
    shared = agents["solar-agent"]._registry
    for a in agents.values():
        a._registry = shared

    for name, a in agents.items():
        caps = a._capabilities
        focus_map = {
            "solar-agent": "solar energy forecasting",
            "grid-agent": "grid load management",
            "solar-agent-2": "solar panel maintenance",
            "nlp-agent": None,
            "infra-agent": "monitoring",
        }
        shared.register_self(name, caps, "local")
        if focus_map.get(name):
            shared._records[name].focus = focus_map[name]

    # Wire topology
    agents["solar-agent"]._strong_peers = ["solar-agent-2", "grid-agent"]

    return agents


def test_pipeline_basic_route(mesh):
    """Pipeline route returns ranked entries like base router."""
    pipeline = AudiencePipeline(mesh["solar-agent"])
    report = pipeline.route("solar energy prediction")

    assert isinstance(report, PipelineReport)
    assert report.entries
    assert report.topic == "solar energy prediction"
    # Should have some results
    assert len(report.entries) > 0


def test_pipeline_filter_stage(mesh):
    """Filter stage drops non-matching entries."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).filter(
        lambda e: any("solar" in c.lower() for c in e.capabilities)
    )
    report = pipeline.route("solar prediction")

    # All entries should have a solar-related capability
    for entry in report.entries:
        assert any("solar" in c.lower() for c in entry.capabilities)


def test_pipeline_boost_stage(mesh):
    """Boost stage increases scores for matching entries."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).boost(
        lambda e: e.name == "grid-agent", factor=2.0
    )
    report = pipeline.route("energy balancing")

    # grid-agent should be boosted — find it
    grid_entry = next((e for e in report.entries if e.name == "grid-agent"), None)
    assert grid_entry is not None
    assert "boosted" in grid_entry.reason


def test_pipeline_limit_stage(mesh):
    """Limit stage caps the number of results."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).limit(2)
    report = pipeline.route("prediction")

    assert len(report.entries) <= 2


def test_pipeline_threshold_stage(mesh):
    """Threshold stage drops low-score entries."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).threshold(0.5)
    report = pipeline.route("monitoring")

    for entry in report.entries:
        assert entry.score >= 0.5


def test_pipeline_dedupe_stage():
    """Dedupe removes duplicate agent entries."""
    from manifold.audience import AudienceEntry

    stage = DedupeStage()
    entries = [
        AudienceEntry(name="a", score=0.8, capabilities=["x"]),
        AudienceEntry(name="b", score=0.6, capabilities=["y"]),
        AudienceEntry(name="a", score=0.9, capabilities=["x"]),
    ]
    result = stage.apply(entries, {})
    assert len(result) == 2
    # Should keep the higher score for "a"
    a_entry = next(e for e in result if e.name == "a")
    assert a_entry.score == 0.9


def test_pipeline_diversity_stage(mesh):
    """Diversity stage caps similar agents."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).diversity(max_overlap=0.5, max_per_cluster=1)
    report = pipeline.route("solar prediction")

    # Should have diverse entries
    names = [e.name for e in report.entries]
    # At least infra-agent or nlp-agent should be present
    assert len(report.entries) >= 1


def test_pipeline_require_signal(mesh):
    """RequireSignal drops entries without the required signal."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).require_signal(Signal.CAPABILITY)
    report = pipeline.route("prediction")

    for entry in report.entries:
        assert Signal.CAPABILITY in entry.signals


def test_pipeline_transform_stage(mesh):
    """Transform stage applies a score transformation."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).transform(
        lambda score, entry: score * 0.5  # halve all scores
    )
    report = pipeline.route("solar prediction")

    # All scores should be ≤ 0.5 (since max is 1.0, halved)
    for entry in report.entries:
        assert entry.score <= 0.51  # small tolerance


def test_pipeline_split_stage(mesh):
    """Split stage partitions entries into named groups."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).split(
        "priority",
        {
            "primary": lambda e: e.score > 0.1,
            "fallback": lambda e: e.score <= 0.1,
        },
    )
    report = pipeline.route("solar prediction")

    assert "priority" in report.splits
    assert "primary" in report.splits["priority"]


def test_pipeline_chained_stages(mesh):
    """Multiple stages chain together correctly."""
    pipeline = (
        AudiencePipeline(mesh["solar-agent"])
        .filter(lambda e: e.score > 0.0)
        .boost(lambda e: "solar" in " ".join(e.capabilities).lower(), factor=1.3)
        .limit(3)
        .threshold(0.05)
    )
    report = pipeline.route("solar energy")

    assert len(report.entries) <= 3
    assert all(e.score >= 0.05 for e in report.entries)
    # Should have stage results
    assert len(report.stage_results) >= 4  # filter, boost, limit, threshold


def test_pipeline_report_summary(mesh):
    """PipelineReport.summary() produces readable output."""
    pipeline = AudiencePipeline(mesh["solar-agent"]).limit(3)
    report = pipeline.route("energy")

    summary = report.summary()
    assert "energy" in summary
    assert "Stages:" in summary


def test_pipeline_report_primary(mesh):
    """PipelineReport.primary returns the top entry."""
    pipeline = AudiencePipeline(mesh["solar-agent"])
    report = pipeline.route("solar prediction")

    if report.entries:
        assert report.primary == report.entries[0]
    else:
        assert report.primary is None


def test_pipeline_min_score_parameter(mesh):
    """min_score parameter filters in route()."""
    pipeline = AudiencePipeline(mesh["solar-agent"])
    report = pipeline.route("xyz-unmatched", min_score=0.5)

    for entry in report.entries:
        assert entry.score >= 0.5


def test_pipeline_max_results_parameter(mesh):
    """max_results parameter caps output."""
    pipeline = AudiencePipeline(mesh["solar-agent"])
    report = pipeline.route("prediction", max_results=1)

    assert len(report.entries) <= 1


def test_pipeline_custom_stage(mesh):
    """Custom stage can be added via add_stage()."""
    class ReverseStage(TransformStage):
        name = "reverse"

        def __init__(self):
            pass  # skip parent __init__

        def apply(self, entries, ctx):
            return list(reversed(entries))

    pipeline = AudiencePipeline(mesh["solar-agent"]).add_stage(ReverseStage())
    report = pipeline.route("solar prediction")

    assert isinstance(report, PipelineReport)
    assert len(report.entries) > 0


def test_pipeline_empty_result(mesh):
    """Pipeline handles case where no agents match."""
    # Create a mesh with one agent that has no matching caps
    solo = Agent("solo")
    solo.knows(["underwater-basket-weaving"])
    pipeline = AudiencePipeline(solo)
    report = pipeline.route("quantum computing")

    # May or may not have results depending on scoring, but should not crash
    assert isinstance(report, PipelineReport)


def test_pipeline_weights(mesh):
    """Custom weights are passed through."""
    pipeline = AudiencePipeline(mesh["solar-agent"], weights={"capability": 0.8, "focus": 0.2})
    report = pipeline.route("solar prediction")

    assert report.weights  # Should have weights recorded
    assert "capability" in report.weights
