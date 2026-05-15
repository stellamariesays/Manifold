"""Result grading and trust scoring for task outcomes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Grade(Enum):
    """Letter grade with numeric value."""

    A = 4.0
    B = 3.0
    C = 2.0
    D = 1.0
    F = 0.0


@dataclass
class GradeReport:
    """A single grade given to a task execution."""

    task_id: str
    executor: str
    caller: str
    grade: Grade
    feedback: str = ""
    timestamp: float = field(default_factory=time.time)
    execution_time_ms: Optional[float] = None


class TrustScorer:
    """Maintains rolling trust scores per agent using exponential moving average."""

    def __init__(self, alpha: float = 0.3, min_grades: int = 5) -> None:
        self.alpha = alpha  # recency bias (higher = more weight on recent)
        self.min_grades = min_grades
        self._grades: dict[str, list[GradeReport]] = {}
        self._scores: dict[str, float] = {}

    def submit_grade(self, report: GradeReport) -> float:
        """Submit a grade and return updated trust score."""
        agent = report.executor
        if agent not in self._grades:
            self._grades[agent] = []
        self._grades[agent].append(report)

        grades = self._grades[agent]
        # Exponential moving average
        score = grades[0].grade.value
        for g in grades[1:]:
            score = self.alpha * g.grade.value + (1 - self.alpha) * score
        self._scores[agent] = score
        return score

    def get_trust_score(self, agent: str) -> Optional[float]:
        """Get current trust score, or None if no grades."""
        return self._scores.get(agent)

    def is_reliable(self, agent: str) -> bool:
        """Check if trust score is based on enough grades."""
        return len(self._grades.get(agent, [])) >= self.min_grades

    def get_grade_history(self, agent: str) -> list[GradeReport]:
        """Get all grades for an agent."""
        return list(self._grades.get(agent, []))

    def get_leaderboard(self) -> list[tuple[str, float, bool]]:
        """Return agents sorted by trust score descending.

        Returns list of (agent, score, is_reliable).
        """
        entries = [
            (agent, score, self.is_reliable(agent))
            for agent, score in self._scores.items()
        ]
        entries.sort(key=lambda x: x[1], reverse=True)
        return entries
