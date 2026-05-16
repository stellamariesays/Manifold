"""Tests for the trust & verification capability pack."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_trust_pack
from manifold.grading import TrustLedger


# ─── Helpers ────────────────────────────────────────────────────────────

def _make_builder_with_trust():
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write('{"grades": []}')
    tmp.close()
    ledger = TrustLedger(path=tmp.name)
    builder = CapabilityBuilder(Agent("trust-tester"))
    load_trust_pack(builder, ledger=ledger)
    return builder, ledger, tmp.name


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _invoke(builder, name, payload):
    r = run(builder.invoke(name, payload))
    return r.output


# ─── Pack loading ───────────────────────────────────────────────────────

class TestTrustPackLoading:
    def test_loads_seven_capabilities(self):
        builder, _, path = _make_builder_with_trust()
        specs = [s for s in builder._caps.values() if s.name.startswith("trust-")]
        assert len(specs) == 7
        Path(path).unlink(missing_ok=True)

    def test_capability_names(self):
        builder, _, path = _make_builder_with_trust()
        names = sorted(s.name for s in builder._caps.values() if s.name.startswith("trust-"))
        expected = sorted([
            "trust-grade", "trust-score", "trust-leaderboard",
            "trust-history", "trust-recent", "trust-verify", "trust-compare",
        ])
        assert names == expected
        Path(path).unlink(missing_ok=True)

    def test_all_active(self):
        builder, _, path = _make_builder_with_trust()
        for s in builder._caps.values():
            if s.name.startswith("trust-"):
                assert s.status.value == "active"
        Path(path).unlink(missing_ok=True)


# ─── trust-grade ────────────────────────────────────────────────────────

class TestTrustGrade:
    def test_file_grade(self):
        builder, _, path = _make_builder_with_trust()
        r = _invoke(builder, "trust-grade", {
            "executor": "agent-a",
            "caller": "caller-1",
            "task_id": "t1",
            "grade": "A",
            "feedback": "great",
        })
        assert r["ok"] is True
        assert r["executor"] == "agent-a"
        assert r["grade"] == "A"
        assert r["new_score"] == 4.0
        assert r["grade_id"]
        Path(path).unlink(missing_ok=True)

    def test_invalid_grade(self):
        builder, _, path = _make_builder_with_trust()
        r = _invoke(builder, "trust-grade", {
            "executor": "agent-a",
            "grade": "Z",
        })
        assert r["ok"] is False
        assert "Invalid grade" in r["error"]
        Path(path).unlink(missing_ok=True)

    def test_ema_updates(self):
        builder, _, path = _make_builder_with_trust()
        _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": "t1", "grade": "A"})
        r = _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": "t2", "grade": "F"})
        assert abs(r["new_score"] - 2.8) < 0.01
        Path(path).unlink(missing_ok=True)


# ─── trust-score ────────────────────────────────────────────────────────

class TestTrustScore:
    def test_unknown_agent(self):
        builder, _, path = _make_builder_with_trust()
        r = _invoke(builder, "trust-score", {"agent": "unknown"})
        assert r["ok"] is True
        assert r["trust_score"] is None
        assert r["reliable"] is False
        Path(path).unlink(missing_ok=True)

    def test_score_after_grades(self):
        builder, _, path = _make_builder_with_trust()
        for i in range(6):
            _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": f"t{i}", "grade": "A"})
        r = _invoke(builder, "trust-score", {"agent": "agent-a"})
        assert r["ok"] is True
        assert r["trust_score"] is not None
        assert r["reliable"] is True
        assert r["grade_count"] == 6
        Path(path).unlink(missing_ok=True)


# ─── trust-leaderboard ──────────────────────────────────────────────────

class TestTrustLeaderboard:
    def test_empty(self):
        builder, _, path = _make_builder_with_trust()
        r = _invoke(builder, "trust-leaderboard", {})
        assert r["ok"] is True
        assert r["count"] == 0
        Path(path).unlink(missing_ok=True)

    def test_ranked(self):
        builder, _, path = _make_builder_with_trust()
        for i in range(6):
            _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": f"ta{i}", "grade": "A"})
            _invoke(builder, "trust-grade", {"executor": "agent-b", "task_id": f"tb{i}", "grade": "C"})
        r = _invoke(builder, "trust-leaderboard", {"limit": 5})
        assert r["ok"] is True
        assert r["leaderboard"][0]["agent"] == "agent-a"
        assert r["leaderboard"][0]["score"] > r["leaderboard"][1]["score"]
        Path(path).unlink(missing_ok=True)


# ─── trust-history ──────────────────────────────────────────────────────

class TestTrustHistory:
    def test_empty_history(self):
        builder, _, path = _make_builder_with_trust()
        r = _invoke(builder, "trust-history", {"agent": "unknown"})
        assert r["ok"] is True
        assert r["total"] == 0
        Path(path).unlink(missing_ok=True)

    def test_returns_history(self):
        builder, _, path = _make_builder_with_trust()
        _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": "t1", "grade": "B"})
        _invoke(builder, "trust-grade", {"executor": "agent-b", "task_id": "t2", "grade": "A"})
        _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": "t3", "grade": "C"})
        r = _invoke(builder, "trust-history", {"agent": "agent-a"})
        assert r["ok"] is True
        assert r["total"] == 2
        assert r["grades"][0]["executor"] == "agent-a"
        Path(path).unlink(missing_ok=True)


# ─── trust-recent ───────────────────────────────────────────────────────

class TestTrustRecent:
    def test_returns_recent(self):
        builder, _, path = _make_builder_with_trust()
        _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": "t1", "grade": "A"})
        _invoke(builder, "trust-grade", {"executor": "agent-b", "task_id": "t2", "grade": "B"})
        r = _invoke(builder, "trust-recent", {"limit": 10})
        assert r["ok"] is True
        assert r["count"] == 2
        Path(path).unlink(missing_ok=True)


# ─── trust-verify ───────────────────────────────────────────────────────

class TestTrustVerify:
    def test_unknown_agent(self):
        builder, _, path = _make_builder_with_trust()
        r = _invoke(builder, "trust-verify", {"agent": "unknown", "min_score": 3.0})
        assert r["ok"] is True
        assert r["meets_threshold"] is False
        Path(path).unlink(missing_ok=True)

    def test_meets_threshold(self):
        builder, _, path = _make_builder_with_trust()
        for i in range(6):
            _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": f"t{i}", "grade": "A"})
        r = _invoke(builder, "trust-verify", {"agent": "agent-a", "min_score": 3.0})
        assert r["ok"] is True
        assert r["meets_threshold"] is True
        Path(path).unlink(missing_ok=True)

    def test_below_threshold(self):
        builder, _, path = _make_builder_with_trust()
        for i in range(6):
            _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": f"t{i}", "grade": "D"})
        r = _invoke(builder, "trust-verify", {"agent": "agent-a", "min_score": 3.0})
        assert r["ok"] is True
        assert r["meets_threshold"] is False
        Path(path).unlink(missing_ok=True)


# ─── trust-compare ──────────────────────────────────────────────────────

class TestTrustCompare:
    def test_both_unknown(self):
        builder, _, path = _make_builder_with_trust()
        r = _invoke(builder, "trust-compare", {"agent_a": "x", "agent_b": "y"})
        assert r["ok"] is True
        assert r["recommended"] is None
        Path(path).unlink(missing_ok=True)

    def test_picks_higher(self):
        builder, _, path = _make_builder_with_trust()
        for i in range(6):
            _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": f"ta{i}", "grade": "A"})
            _invoke(builder, "trust-grade", {"executor": "agent-b", "task_id": f"tb{i}", "grade": "C"})
        r = _invoke(builder, "trust-compare", {"agent_a": "agent-a", "agent_b": "agent-b"})
        assert r["ok"] is True
        assert r["recommended"] == "agent-a"
        Path(path).unlink(missing_ok=True)

    def test_one_known(self):
        builder, _, path = _make_builder_with_trust()
        for i in range(6):
            _invoke(builder, "trust-grade", {"executor": "agent-a", "task_id": f"t{i}", "grade": "B"})
        r = _invoke(builder, "trust-compare", {"agent_a": "agent-a", "agent_b": "unknown"})
        assert r["recommended"] == "agent-a"
        Path(path).unlink(missing_ok=True)
