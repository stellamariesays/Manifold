"""Tests for the adaptive routing module."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.adaptive import AdaptiveRouter, AdaptiveReport, TopicModel, Observation


# ─── Fixtures ─────────────────────────────────────────────────────────────

async def _make_mesh():
    """Create a small mesh with agents for adaptive routing tests."""
    alice = Agent(name="alice", transport="memory://test")
    alice.knows(["solar-prediction", "energy-forecast"])
    await alice.join()

    bob = Agent(name="bob", transport="memory://test")
    bob.knows(["orbit-calculation", "solar-analysis"])
    await bob.join()

    carol = Agent(name="carol", transport="memory://test")
    carol.knows(["weather-model", "climate-data"])
    await carol.join()

    # alice sees the others
    await alice._on_registry_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation", "solar-analysis"],
        "address": "memory://test",
        "focus": "solar-analysis",
    })
    await alice._on_registry_announcement({
        "name": "carol",
        "capabilities": ["weather-model", "climate-data"],
        "address": "memory://test",
        "focus": None,
    })

    return alice, bob, carol


@pytest.fixture
def mesh():
    return asyncio.get_event_loop().run_until_complete(_make_mesh())


def _make_router(mesh):
    alice, _, _ = mesh
    return AdaptiveRouter(alice, learning_rate=0.2, max_history=50)


# ─── Basic routing ────────────────────────────────────────────────────────

class TestAdaptiveRouting:
    def test_route_returns_adaptive_report(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        assert isinstance(report, AdaptiveReport)

    def test_route_finds_candidates(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        assert len(report.entries) >= 1

    def test_route_with_no_candidates(self, mesh):
        alice, _, _ = mesh
        # Create fresh router with empty registry
        from manifold.registry import CapabilityRegistry
        alice._registry = CapabilityRegistry()
        router = AdaptiveRouter(alice)
        report = router.route("solar-prediction")
        assert len(report.entries) == 0

    def test_applied_weights_are_normalized(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        total = sum(report.applied_weights.values())
        assert abs(total - 1.0) < 0.01

    def test_base_weights_used_initially(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        for sig in router.BASE_WEIGHTS:
            assert sig in report.applied_weights


# ─── Feedback and learning ────────────────────────────────────────────────

class TestFeedback:
    def test_feedback_records_observation(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        if report.entries:
            entry = report.entries[0]
            router.feedback(entry.name, "solar-prediction", success=True, entry=entry)
            assert len(router._history) == 1

    def test_feedback_creates_topic_model(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        if report.entries:
            entry = report.entries[0]
            router.feedback(entry.name, "solar-prediction", success=True, entry=entry)
            assert "solar prediction" in router._models

    def test_success_boosts_contributing_signals(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        if not report.entries:
            pytest.skip("no candidates")

        entry = report.entries[0]
        weights_before = router._get_weights("solar-prediction")
        router.feedback(entry.name, "solar-prediction", success=True, entry=entry)
        weights_after = router._get_weights("solar-prediction")

        changed = any(
            abs(weights_after.get(s.value, 0) - weights_before.get(s.value, 0)) > 0.001
            for s in entry.signals
        )
        assert changed

    def test_failure_dampens_signals(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        if not report.entries:
            pytest.skip("no candidates")

        entry = report.entries[0]
        router.feedback(entry.name, "solar-prediction", success=False, entry=entry)
        model = router._models.get("solar prediction")
        assert model is not None
        for sig in entry.signals:
            assert model.adjustments.get(sig.value, 0.0) < 0

    def test_feedback_without_entry(self, mesh):
        router = _make_router(mesh)
        router.feedback("bob", "solar-prediction", success=True)
        assert len(router._history) == 1
        assert router._history[0].agent_name == "bob"
        assert router._history[0].signals == []

    def test_latency_factor(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        if not report.entries:
            pytest.skip("no candidates")

        entry = report.entries[0]
        router.feedback(entry.name, "solar-prediction", success=True,
                        latency_ms=100.0, entry=entry)
        fast_adj = sum(abs(v) for v in router._models["solar prediction"].adjustments.values())

        router.reset()
        router.feedback(entry.name, "solar-prediction", success=True,
                        latency_ms=5000.0, entry=entry)
        slow_adj = sum(abs(v) for v in router._models["solar prediction"].adjustments.values())

        assert fast_adj > slow_adj


# ─── Topic key normalization ──────────────────────────────────────────────

class TestTopicKey:
    def test_simple_topic(self, mesh):
        router = _make_router(mesh)
        assert router._topic_key("solar-prediction") == "solar prediction"

    def test_single_word(self, mesh):
        router = _make_router(mesh)
        assert router._topic_key("energy") == "energy"

    def test_multi_word(self, mesh):
        router = _make_router(mesh)
        assert router._topic_key("solar-energy-forecast-daily") == "solar energy"


# ─── History management ──────────────────────────────────────────────────

class TestHistory:
    def test_history_capped(self, mesh):
        router = AdaptiveRouter(mesh[0], max_history=5)
        for i in range(10):
            router.feedback("bob", f"topic-{i}", success=True)
        assert len(router._history) <= 5

    def test_stats(self, mesh):
        router = _make_router(mesh)
        router.feedback("bob", "solar-prediction", success=True)
        router.feedback("carol", "orbit-calculation", success=False)
        stats = router.stats()
        assert stats["total_observations"] == 2
        assert stats["overall_success_rate"] == 0.5

    def test_topic_stats(self, mesh):
        router = _make_router(mesh)
        router.feedback("bob", "solar-prediction", success=True)
        ts = router.topic_stats("solar-prediction")
        assert ts is not None
        assert ts["observations"] == 1
        assert ts["success_rate"] == 1.0

    def test_topic_stats_missing(self, mesh):
        router = _make_router(mesh)
        assert router.topic_stats("nonexistent") is None


# ─── Decay ────────────────────────────────────────────────────────────────

class TestDecay:
    def test_model_decay(self):
        model = TopicModel(
            topic="test",
            adjustments={"capability": 1.0, "trust": 0.5, "focus": -0.3,
                          "fog_gap": 0.0, "topology": 0.2},
        )
        model.decay(0.9)
        assert abs(model.adjustments["capability"] - 0.9) < 0.001
        assert abs(model.adjustments["trust"] - 0.45) < 0.001

    def test_periodic_decay_triggered(self, mesh):
        router = AdaptiveRouter(mesh[0], learning_rate=0.2, max_history=50)
        report = router.route("solar-prediction")
        if not report.entries:
            pytest.skip("no candidates")
        entry = report.entries[0]

        router.feedback(entry.name, "solar-prediction", success=True, entry=entry)
        for _ in range(20):
            router.feedback("bob", "solar-prediction", success=True, entry=entry)
        assert "solar prediction" in router._models


# ─── Persistence ──────────────────────────────────────────────────────────

class TestPersistence:
    def test_export_import_roundtrip(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        if report.entries:
            router.feedback(report.entries[0].name, "solar-prediction",
                            success=True, entry=report.entries[0])

        state = router.export_state()
        assert "models" in state

        router2 = _make_router(mesh)
        router2.import_state(state)
        assert len(router2._models) == len(router._models)
        assert router2._learning_rate == router._learning_rate

    def test_export_empty(self, mesh):
        router = _make_router(mesh)
        state = router.export_state()
        assert state["models"] == {}


# ─── Reset ────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_specific_topic(self, mesh):
        router = _make_router(mesh)
        router.feedback("bob", "solar-prediction", success=True)
        router.feedback("carol", "orbit-calculation", success=True)
        assert len(router._models) == 2

        router.reset("solar-prediction")
        assert "solar prediction" not in router._models
        assert "orbit calculation" in router._models

    def test_reset_all(self, mesh):
        router = _make_router(mesh)
        router.feedback("bob", "solar-prediction", success=True)
        router.feedback("carol", "orbit-calculation", success=True)
        router.reset()
        assert len(router._models) == 0
        assert len(router._history) == 0


# ─── Learned weights ──────────────────────────────────────────────────────

class TestLearnedWeights:
    def test_learned_weights_structure(self, mesh):
        router = _make_router(mesh)
        router.feedback("bob", "solar-prediction", success=True)
        weights = router.learned_weights()
        for topic, w in weights.items():
            total = sum(w.values())
            assert abs(total - 1.0) < 0.01

    def test_weights_shift_after_repeated_success(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        if not report.entries:
            pytest.skip("no candidates")

        entry = report.entries[0]
        initial_weights = router._get_weights("solar-prediction")

        for _ in range(20):
            router.feedback(entry.name, "solar-prediction", success=True, entry=entry)

        final_weights = router._get_weights("solar-prediction")
        different = any(
            abs(final_weights.get(k, 0) - initial_weights.get(k, 0)) > 0.01
            for k in initial_weights
        )
        assert different


# ─── Display ──────────────────────────────────────────────────────────────

class TestDisplay:
    def test_adaptive_report_summary(self, mesh):
        router = _make_router(mesh)
        report = router.route("solar-prediction")
        s = report.summary()
        assert "solar" in s.lower()

    def test_topic_model_success_rate(self):
        model = TopicModel(topic="test", adjustments={"cap": 0.1})
        assert model.success_rate == 0.0
        model.observations = 4
        model.successes = 3
        assert abs(model.success_rate - 0.75) < 0.01
