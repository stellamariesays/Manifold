"""Tests for result grading and trust ledger."""

import json
import tempfile
from pathlib import Path

from manifold.grading import Grade, GradeReport, TrustScorer, TrustLedger


def test_grade_numeric():
    assert Grade.A.numeric == 4.0
    assert Grade.F.numeric == 0.0
    assert Grade.C.numeric == 2.0


def test_grade_report_roundtrip():
    r = GradeReport(task_id="t1", executor="a@hub", caller="b@hub", grade=Grade.A, feedback="great")
    d = r.to_dict()
    assert d["grade"] == "A"
    r2 = GradeReport.from_dict(d)
    assert r2.grade == Grade.A
    assert r2.feedback == "great"


def test_trust_scorer_single():
    s = TrustScorer(min_grades=3)
    s.submit_grade("agent", Grade.A)
    assert s.get_raw_score("agent") == 4.0
    assert s.get_trust_score("agent") is None  # not enough grades


def test_trust_scorer_reliable():
    s = TrustScorer(alpha=0.5, min_grades=3)
    for _ in range(3):
        s.submit_grade("agent", Grade.A)
    score = s.get_trust_score("agent")
    assert score is not None
    assert score > 3.0


def test_trust_scorer_leaderboard():
    s = TrustScorer(min_grades=2)
    for _ in range(2):
        s.submit_grade("good", Grade.A)
    for _ in range(2):
        s.submit_grade("bad", Grade.F)
    lb = s.get_leaderboard()
    assert lb[0][0] == "good"
    assert lb[1][0] == "bad"


def test_trust_ledger_persistence():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ledger.json"
        ledger = TrustLedger(path)
        ledger.record_grade(GradeReport(task_id="t1", executor="a", caller="b", grade=Grade.A))
        ledger.record_grade(GradeReport(task_id="t2", executor="a", caller="b", grade=Grade.B))

        # Reload
        ledger2 = TrustLedger(path)
        assert len(ledger2.get_recent_grades()) == 2
        assert ledger2.get_agent_trust("a") is None  # min_grades=5 default

        # Add more to make reliable
        for i in range(3):
            ledger2.record_grade(GradeReport(task_id=f"t{i+3}", executor="a", caller="b", grade=Grade.A))
        score = ledger2.get_agent_trust("a")
        assert score is not None
        assert score > 2.0


def test_grade_history():
    with tempfile.TemporaryDirectory() as td:
        ledger = TrustLedger(Path(td) / "ledger.json")
        ledger.record_grade(GradeReport(task_id="t1", executor="alice", caller="bob", grade=Grade.A))
        ledger.record_grade(GradeReport(task_id="t2", executor="bob", caller="alice", grade=Grade.B))
        ledger.record_grade(GradeReport(task_id="t3", executor="alice", caller="bob", grade=Grade.C))
        history = ledger.get_grade_history("alice")
        assert len(history) == 2
        assert all(g.executor == "alice" for g in history)


if __name__ == "__main__":
    test_grade_numeric()
    test_grade_report_roundtrip()
    test_trust_scorer_single()
    test_trust_scorer_reliable()
    test_trust_scorer_leaderboard()
    test_trust_ledger_persistence()
    test_grade_history()
    print("\n🟢 All grading tests passed")
