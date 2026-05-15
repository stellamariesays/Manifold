"""Result grading and trust scoring — outcome-based agent evaluation."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"

    @property
    def numeric(self) -> float:
        return {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}[self.value]


@dataclass
class GradeReport:
    task_id: str = ""
    executor: str = ""
    caller: str = ""
    grade: Grade = Grade.C
    feedback: str = ""
    execution_time_ms: int | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["grade"] = self.grade.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> GradeReport:
        if "grade" in data and isinstance(data["grade"], str):
            data["grade"] = Grade(data["grade"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TrustScorer:
    """Rolling trust score using exponential moving average."""

    def __init__(self, alpha: float = 0.3, min_grades: int = 5):
        self.alpha = alpha  # recency weight
        self.min_grades = min_grades
        self._scores: dict[str, float] = {}
        self._grade_counts: dict[str, int] = {}

    def submit_grade(self, agent: str, grade: Grade) -> float:
        count = self._grade_counts.get(agent, 0) + 1
        self._grade_counts[agent] = count
        if agent not in self._scores:
            self._scores[agent] = grade.numeric
        else:
            self._scores[agent] = (
                self.alpha * grade.numeric + (1 - self.alpha) * self._scores[agent]
            )
        return self._scores[agent]

    def get_trust_score(self, agent: str) -> float | None:
        if agent not in self._scores:
            return None
        if self._grade_counts.get(agent, 0) < self.min_grades:
            return None  # not reliable yet
        return round(self._scores[agent], 3)

    def get_raw_score(self, agent: str) -> float | None:
        return self._scores.get(agent)

    def is_reliable(self, agent: str) -> bool:
        return self._grade_counts.get(agent, 0) >= self.min_grades

    def get_leaderboard(self) -> list[tuple[str, float]]:
        """Return agents sorted by trust score (reliable only)."""
        reliable = {
            a: s for a, s in self._scores.items() if self.is_reliable(a)
        }
        return sorted(reliable.items(), key=lambda x: x[1], reverse=True)


class TrustLedger:
    """Persistent file-based store for grades and trust scores."""

    def __init__(self, path: str | Path = "trust_ledger.json"):
        self.path = Path(path)
        self.scorer = TrustScorer()
        self._grades: list[GradeReport] = []
        self._load()

    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text())
            for g in data.get("grades", []):
                report = GradeReport.from_dict(g)
                self._grades.append(report)
                self.scorer.submit_grade(report.executor, report.grade)

    def _save(self):
        data = {
            "grades": [g.to_dict() for g in self._grades],
        }
        self.path.write_text(json.dumps(data, indent=2))

    def record_grade(self, report: GradeReport) -> float:
        self._grades.append(report)
        score = self.scorer.submit_grade(report.executor, report.grade)
        self._save()
        return score

    def get_agent_trust(self, agent: str) -> float | None:
        return self.scorer.get_trust_score(agent)

    def get_top_agents(self, n: int = 10) -> list[tuple[str, float]]:
        return self.scorer.get_leaderboard()[:n]

    def get_recent_grades(self, n: int = 10) -> list[GradeReport]:
        return self._grades[-n:]

    def get_grade_history(self, agent: str) -> list[GradeReport]:
        return [g for g in self._grades if g.executor == agent]
