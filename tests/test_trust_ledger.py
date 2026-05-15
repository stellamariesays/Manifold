"""Tests for trust ledger persistence."""

import json
import tempfile
from pathlib import Path

from manifold.grading import Grade, GradeReport
from manifold.trust_ledger import TrustLedger


def _report(executor: str, grade: Grade) -> GradeReport:
    return GradeReport(task_id="t1", executor=executor, caller="c", grade=grade)


def test_record_and_read(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = TrustLedger(path)
    ledger.record_grade(_report("alice", Grade.A))
    # Re-open to verify persistence
    ledger2 = TrustLedger(path)
    recent = ledger2.get_recent_grades()
    assert len(recent) == 1
    assert recent[0]["grade"] == "A"


def test_agent_trust(tmp_path):
    ledger = TrustLedger(tmp_path / "l.json")
    for g in [Grade.A, Grade.B, Grade.A, Grade.A, Grade.A]:
        ledger.record_grade(_report("bob", g))
    info = ledger.get_agent_trust("bob")
    assert info is not None
    assert info["total_grades"] == 5
    assert info["reliable"] is True
    assert info["trust_score"] > 3.0


def test_unknown_agent(tmp_path):
    ledger = TrustLedger(tmp_path / "l.json")
    assert ledger.get_agent_trust("nobody") is None


def test_top_agents(tmp_path):
    ledger = TrustLedger(tmp_path / "l.json")
    ledger.record_grade(_report("alice", Grade.A))
    ledger.record_grade(_report("bob", Grade.F))
    top = ledger.get_top_agents()
    assert top[0]["agent"] == "alice"


def test_recent_grades_limit(tmp_path):
    ledger = TrustLedger(tmp_path / "l.json")
    for i in range(25):
        ledger.record_grade(_report("x", Grade.B))
    recent = ledger.get_recent_grades(limit=5)
    assert len(recent) == 5
