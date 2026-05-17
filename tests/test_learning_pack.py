"""Tests for the learning/feedback capability pack."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_learning_pack


@pytest.fixture
def builder():
    agent = Agent("test-learner")
    b = CapabilityBuilder(agent)
    load_learning_pack(b)
    return b


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _record(builder, agent, cap, success=True, grade="A", score=0.9):
    return _run(builder.invoke("learn-record", {
        "agent": agent, "capability": cap,
        "success": success, "grade": grade, "score": score,
    }))


class TestLearnRecord:
    def test_record_success(self, builder):
        r = _record(builder, "alpha", "solar-prediction", success=True, grade="A", score=0.95)
        assert r.ok
        out = r.output
        assert out["ok"] is True
        assert out["success_rate"] == 1.0
        assert out["avg_score"] == pytest.approx(0.95)

    def test_record_failure(self, builder):
        r = _record(builder, "alpha", "routing", success=False, grade="D", score=0.3)
        assert r.ok
        # Now check proficiency for that specific capability
        r2 = _run(builder.invoke("learn-proficiency", {"agent": "alpha", "capability": "routing"}))
        assert r2.ok
        profs = r2.output["proficiencies"]
        assert len(profs) == 1
        assert profs[0]["success_rate"] == 0.0

    def test_multiple_records(self, builder):
        grades = ["A", "B", "C", "D", "A"]
        for i in range(5):
            _record(builder, "beta", "math",
                    success=(i % 2 == 0), grade=grades[i], score=0.5 + i * 0.1)
        r = _run(builder.invoke("learn-proficiency", {"agent": "beta", "capability": "math"}))
        prof = r.output["proficiencies"][0]
        assert prof["attempts"] == 5
        assert prof["success_rate"] == pytest.approx(0.6)


class TestLearnProficiency:
    def test_proficiency_multiple(self, builder):
        _record(builder, "gamma", "a", grade="A", score=0.8)
        _record(builder, "gamma", "b", success=False, grade="C", score=0.4)
        # Query each individually
        r_a = _run(builder.invoke("learn-proficiency", {"agent": "gamma", "capability": "a"}))
        r_b = _run(builder.invoke("learn-proficiency", {"agent": "gamma", "capability": "b"}))
        assert r_a.ok
        assert r_b.ok
        assert r_a.output["proficiencies"][0]["capability"] == "a"
        assert r_b.output["proficiencies"][0]["capability"] == "b"

    def test_proficiency_single(self, builder):
        _record(builder, "gamma", "x", grade="A", score=0.99)
        r = _run(builder.invoke("learn-proficiency", {"agent": "gamma", "capability": "x"}))
        prof = r.output["proficiencies"][0]
        assert prof["avg_score"] == pytest.approx(0.99)

    def test_proficiency_empty(self, builder):
        r = _run(builder.invoke("learn-proficiency", {"agent": "nobody", "capability": "nope"}))
        assert r.ok
        assert r.output["total_capabilities"] == 1  # returns entry with 0 attempts


class TestLearnSuggest:
    def test_suggest_below_threshold(self, builder):
        _record(builder, "delta", "weak", success=False, grade="D", score=0.2)
        _record(builder, "delta", "weak", success=False, grade="F", score=0.1)
        _record(builder, "delta", "strong", grade="A", score=0.95)
        _record(builder, "delta", "strong", grade="A", score=0.90)
        r = _run(builder.invoke("learn-suggest", {"agent": "delta", "threshold": 0.5}))
        assert r.ok
        assert r.output["count"] >= 1
        names = [s["capability"] for s in r.output["suggestions"]]
        assert "weak" in names

    def test_suggest_all_good(self, builder):
        _record(builder, "epsilon", "perfect", grade="A", score=1.0)
        _record(builder, "epsilon", "perfect", grade="A", score=0.95)
        r = _run(builder.invoke("learn-suggest", {"agent": "epsilon", "threshold": 0.5}))
        assert r.output["count"] == 0


class TestLearnReset:
    def test_reset_all(self, builder):
        _record(builder, "zeta", "a", grade="B", score=0.8)
        _record(builder, "zeta", "b", grade="C", score=0.6)
        _run(builder.invoke("learn-reset", {"agent": "zeta", "capability": "a"}))
        _run(builder.invoke("learn-reset", {"agent": "zeta", "capability": "b"}))
        r = _run(builder.invoke("learn-proficiency", {"agent": "zeta", "capability": "a"}))
        assert r.output["proficiencies"][0]["attempts"] == 0

    def test_reset_single_capability(self, builder):
        _record(builder, "eta", "keep", grade="A", score=0.9)
        _record(builder, "eta", "drop", success=False, grade="F", score=0.1)
        _run(builder.invoke("learn-reset", {"agent": "eta", "capability": "drop"}))
        # 'keep' should still be there
        r = _run(builder.invoke("learn-proficiency", {"agent": "eta", "capability": "keep"}))
        assert r.ok
        assert r.output["proficiencies"][0]["capability"] == "keep"
        # 'drop' should be gone — returns empty stats
        r2 = _run(builder.invoke("learn-proficiency", {"agent": "eta", "capability": "drop"}))
        assert r2.output["proficiencies"][0]["attempts"] == 0


class TestLearningPackRegistration:
    def test_all_caps_registered(self, builder):
        names = {c.name for c in builder.list_capabilities()}
        for expected in ("learn-record", "learn-proficiency", "learn-suggest", "learn-reset"):
            assert expected in names

    def test_caps_have_learning_tags(self, builder):
        for cap in builder.list_capabilities():
            if cap.name.startswith("learn-"):
                assert "learning" in cap.tags
