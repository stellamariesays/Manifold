"""Tests for grading system."""

from manifold.grading import Grade, GradeReport, TrustScorer


def _make_report(agent: str, grade: Grade, caller: str = "caller") -> GradeReport:
    return GradeReport(task_id=f"t-{agent}", executor=agent, caller=caller, grade=grade)


def test_grade_values():
    assert Grade.A.value == 4.0
    assert Grade.F.value == 0.0


def test_submit_single_grade():
    scorer = TrustScorer()
    report = _make_report("alice", Grade.A)
    score = scorer.submit_grade(report)
    assert score == 4.0


def test_ema_calculation():
    scorer = TrustScorer(alpha=0.5)
    scorer.submit_grade(_make_report("bob", Grade.A))  # 4.0
    score = scorer.submit_grade(_make_report("bob", Grade.F))  # 0.5*0 + 0.5*4 = 2.0
    assert score == 2.0


def test_reliable_after_5():
    scorer = TrustScorer(min_grades=5)
    assert not scorer.is_reliable("eve")
    for _ in range(4):
        scorer.submit_grade(_make_report("eve", Grade.B))
    assert not scorer.is_reliable("eve")
    scorer.submit_grade(_make_report("eve", Grade.B))
    assert scorer.is_reliable("eve")


def test_leaderboard():
    scorer = TrustScorer()
    scorer.submit_grade(_make_report("a1", Grade.A))
    scorer.submit_grade(_make_report("a2", Grade.C))
    lb = scorer.get_leaderboard()
    assert lb[0][0] == "a1"
    assert lb[1][0] == "a2"


def test_grade_history():
    scorer = TrustScorer()
    scorer.submit_grade(_make_report("x", Grade.A))
    scorer.submit_grade(_make_report("x", Grade.B))
    history = scorer.get_grade_history("x")
    assert len(history) == 2
    assert history[0].grade == Grade.A


def test_unknown_agent():
    scorer = TrustScorer()
    assert scorer.get_trust_score("nobody") is None
    assert scorer.get_grade_history("nobody") == []
