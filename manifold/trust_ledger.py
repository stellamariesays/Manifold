"""Persistent trust ledger for grades and trust scores."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from manifold.grading import Grade, GradeReport


class TrustLedger:
    """File-backed store for grades and computed trust scores."""

    def __init__(self, path: str | Path = "trust_ledger.json") -> None:
        self.path = Path(path)
        self._grades: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self._grades = data.get("grades", [])

    def _save(self) -> None:
        self.path.write_text(json.dumps({"grades": self._grades}, indent=2))

    def record_grade(self, report: GradeReport) -> dict:
        """Persist a grade report and return the stored entry."""
        entry = {
            "task_id": report.task_id,
            "executor": report.executor,
            "caller": report.caller,
            "grade": report.grade.name,
            "grade_value": report.grade.numeric,
            "feedback": report.feedback,
            "timestamp": report.timestamp,
            "execution_time_ms": report.execution_time_ms,
        }
        self._grades.append(entry)
        self._save()
        return entry

    def get_agent_trust(self, agent: str) -> Optional[dict]:
        """Compute trust info for an agent from stored grades."""
        agent_grades = [g for g in self._grades if g["executor"] == agent]
        if not agent_grades:
            return None
        # EMA calculation
        score = agent_grades[0]["grade_value"]
        alpha = 0.3
        for g in agent_grades[1:]:
            score = alpha * g["grade_value"] + (1 - alpha) * score
        return {
            "agent": agent,
            "trust_score": round(score, 4),
            "total_grades": len(agent_grades),
            "reliable": len(agent_grades) >= 5,
            "last_grade": agent_grades[-1]["grade"],
        }

    def get_top_agents(self, limit: int = 10) -> list[dict]:
        """Return agents sorted by trust score descending."""
        agents = set(g["executor"] for g in self._grades)
        scored = []
        for a in agents:
            info = self.get_agent_trust(a)
            if info:
                scored.append(info)
        scored.sort(key=lambda x: x["trust_score"], reverse=True)
        return scored[:limit]

    def get_recent_grades(self, limit: int = 20) -> list[dict]:
        """Return most recent grades."""
        return list(reversed(self._grades[-limit:]))
