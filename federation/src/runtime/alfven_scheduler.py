#!/usr/bin/env python3
"""
Alfvén Recharge Scheduler
=========================
Models LLM agent "context fatigue" using the same energy-recovery curve as
BRAID's solar Alfvén recharge model.

Core idea: after a heavy task, an agent's context is soft-degraded (lost-in-
the-middle effects, KV cache pressure). Recovery is exponential — just like
magnetic energy recharge after a solar eruption.

    recovery_score(t) = max_score * (1 - e^(-λ * Δt_minutes))

Where:
    λ (lambda) = recovery rate constant (agent-type specific)
    Δt         = minutes since last task completed
    max_score  = 1.0 (fully recovered)

A heavy task depletes score proportional to tokens consumed. The scheduler
picks the highest-recovery agent that meets the task's complexity threshold.

Usage:
    # Log a completed task
    scheduler = AlfvenScheduler()
    scheduler.log_task("manifold", tokens=8500, complexity="deep")

    # Get best agent for a new task
    best = scheduler.route("deep", candidates=["manifold", "btc-signals", "infra"])
    print(best)  # {"agent": "btc-signals", "score": 0.94, "reason": "..."}

    # Show all agent scores
    scheduler.status()
"""

import math
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Config ──────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent / "memory" / "stella.db"

# Recovery rate constants (λ) — higher = faster recovery
# Tuned per agent archetype
LAMBDA = {
    "fast":   0.10,   # stateless tools, simple agents — ~10 min to 63% recovery
    "medium": 0.04,   # general-purpose agents — ~25 min to 63% recovery
    "slow":   0.015,  # deep reasoning, long-context agents — ~67 min to 63% recovery
}

# Agent type registry — maps agent_id → recovery archetype
AGENT_ARCHETYPES = {
    "manifold":      "slow",
    "btc-signals":   "medium",
    "braid":         "slow",
    "solar-detect":  "medium",
    "solar-sites":   "fast",
    "infra":         "medium",
    "wake":          "slow",
    "deploy":        "fast",
    "data-detect":   "medium",
    "argue":         "medium",
    "stella":        "slow",
}

# Token-to-depletion mapping
# Heavy tasks (>10k tokens) drain significantly; light tasks barely dent score
def token_depletion(tokens: int) -> float:
    """Returns score depletion (0.0–1.0) for given token count."""
    if tokens < 1000:
        return 0.05
    elif tokens < 5000:
        return 0.20
    elif tokens < 10000:
        return 0.40
    elif tokens < 30000:
        return 0.65
    else:
        return 0.90

# Complexity → minimum required recovery score
COMPLEXITY_THRESHOLD = {
    "quick":  0.10,   # almost anyone can handle this
    "medium": 0.40,   # need decent recovery
    "deep":   0.70,   # only well-recovered agents
}

# ── DB Setup ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_load_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL,
    ts_completed    REAL NOT NULL,          -- unix timestamp
    tokens_consumed INTEGER NOT NULL DEFAULT 0,
    complexity      TEXT NOT NULL DEFAULT 'medium',
    score_before    REAL,
    score_after     REAL,
    task_label      TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_load_agent ON agent_load_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_load_ts ON agent_load_events(ts_completed);
"""

# ── Core Class ───────────────────────────────────────────────────────────────

class AlfvenScheduler:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _lambda(self, agent_id: str) -> float:
        archetype = AGENT_ARCHETYPES.get(agent_id, "medium")
        return LAMBDA[archetype]

    def recovery_score(self, agent_id: str, at_ts: Optional[float] = None) -> float:
        """
        Compute current recovery score for an agent.
        Score = 1.0 (fully recovered) if no prior tasks.
        Score decays after each task proportional to token load, then recovers exponentially.
        """
        now = at_ts or time.time()
        lam = self._lambda(agent_id)

        with self._conn() as conn:
            # Get last event for this agent
            row = conn.execute(
                "SELECT ts_completed, score_after FROM agent_load_events "
                "WHERE agent_id = ? ORDER BY ts_completed DESC LIMIT 1",
                (agent_id,)
            ).fetchone()

        if row is None:
            return 1.0  # Never worked — fully recovered

        last_ts = row["ts_completed"]
        score_after_task = row["score_after"] if row["score_after"] is not None else 0.1

        # Exponential recovery since last task
        delta_minutes = (now - last_ts) / 60.0
        recovered = 1.0 - (1.0 - score_after_task) * math.exp(-lam * delta_minutes)
        return min(1.0, max(0.0, recovered))

    def log_task(
        self,
        agent_id: str,
        tokens: int,
        complexity: str = "medium",
        task_label: Optional[str] = None,
    ) -> dict:
        """
        Log a completed task and update agent's load state.
        Returns dict with score_before, score_after, depletion.
        """
        now = time.time()
        score_before = self.recovery_score(agent_id, at_ts=now)
        depletion = token_depletion(tokens)
        score_after = max(0.05, score_before - depletion)

        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agent_load_events "
                "(agent_id, ts_completed, tokens_consumed, complexity, score_before, score_after, task_label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (agent_id, now, tokens, complexity, score_before, score_after, task_label)
            )

        return {
            "agent_id": agent_id,
            "score_before": round(score_before, 3),
            "depletion": round(depletion, 3),
            "score_after": round(score_after, 3),
            "tokens": tokens,
            "complexity": complexity,
        }

    def route(
        self,
        complexity: str = "medium",
        candidates: Optional[list] = None,
        task_label: Optional[str] = None,
    ) -> dict:
        """
        Pick the best agent for a task of given complexity.
        Returns routing decision with scores for all candidates.
        """
        if candidates is None:
            candidates = list(AGENT_ARCHETYPES.keys())

        threshold = COMPLEXITY_THRESHOLD.get(complexity, 0.40)
        now = time.time()

        scores = {}
        for agent_id in candidates:
            scores[agent_id] = round(self.recovery_score(agent_id, at_ts=now), 3)

        # Filter to agents meeting the threshold
        eligible = {a: s for a, s in scores.items() if s >= threshold}

        if not eligible:
            # Fallback: pick highest score even if below threshold
            best_agent = max(scores, key=scores.get)
            return {
                "agent": best_agent,
                "score": scores[best_agent],
                "threshold": threshold,
                "eligible_count": 0,
                "all_scores": scores,
                "warning": f"No agent meets threshold {threshold:.2f} for '{complexity}' task. Using best available.",
                "task_label": task_label,
            }

        best_agent = max(eligible, key=eligible.get)
        return {
            "agent": best_agent,
            "score": eligible[best_agent],
            "threshold": threshold,
            "eligible_count": len(eligible),
            "all_scores": scores,
            "task_label": task_label,
        }

    def status(self, agents: Optional[list] = None) -> list:
        """Return current recovery scores for all (or specified) agents."""
        if agents is None:
            agents = list(AGENT_ARCHETYPES.keys())

        now = time.time()
        results = []
        for agent_id in agents:
            score = self.recovery_score(agent_id, at_ts=now)
            archetype = AGENT_ARCHETYPES.get(agent_id, "medium")
            lam = LAMBDA[archetype]
            # Time to full recovery (99%) from current score
            if score >= 0.99:
                eta_min = 0
            else:
                remaining = 1.0 - score
                eta_min = -math.log(0.01 / remaining) / lam if remaining > 0.01 else 0

            results.append({
                "agent":      agent_id,
                "score":      round(score, 3),
                "archetype":  archetype,
                "eta_full_recovery_min": round(eta_min, 1),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results


# ── CLI / Test Harness ───────────────────────────────────────────────────────

def demo():
    print("=" * 60)
    print("Alfvén Recharge Scheduler — Demo")
    print("=" * 60)

    s = AlfvenScheduler()

    # Simulate some prior task history
    print("\n[1] Simulating task load on agents...")

    # Manifold just did a heavy deep-reasoning task 5 min ago
    fake_now = time.time() - 5 * 60
    with s._conn() as conn:
        conn.execute(
            "INSERT INTO agent_load_events (agent_id, ts_completed, tokens_consumed, complexity, score_before, score_after, task_label) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("manifold", fake_now, 28000, "deep", 1.0, 0.1, "demo: atlas rebuild")
        )
    print("  → manifold: 28k token deep task, 5 min ago")

    # btc-signals did a medium task 45 min ago
    fake_now2 = time.time() - 45 * 60
    with s._conn() as conn:
        conn.execute(
            "INSERT INTO agent_load_events (agent_id, ts_completed, tokens_consumed, complexity, score_before, score_after, task_label) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("btc-signals", fake_now2, 4500, "medium", 1.0, 0.80, "demo: BTC signal scan")
        )
    print("  → btc-signals: 4.5k token medium task, 45 min ago")

    # infra did a quick task 2 min ago
    fake_now3 = time.time() - 2 * 60
    with s._conn() as conn:
        conn.execute(
            "INSERT INTO agent_load_events (agent_id, ts_completed, tokens_consumed, complexity, score_before, score_after, task_label) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("infra", fake_now3, 800, "quick", 1.0, 0.95, "demo: health check")
        )
    print("  → infra: 800 token quick task, 2 min ago")

    # Current scores
    print("\n[2] Current recovery scores:")
    status = s.status(["manifold", "btc-signals", "infra", "braid", "solar-detect"])
    for a in status:
        bar = "█" * int(a["score"] * 20)
        print(f"  {a['agent']:15s} {bar:<20s} {a['score']:.3f}  (ETA full: {a['eta_full_recovery_min']:.0f}m, arch: {a['archetype']})")

    # Route a deep task
    print("\n[3] Routing a DEEP task to best candidate:")
    result = s.route(
        complexity="deep",
        candidates=["manifold", "btc-signals", "infra", "braid"],
        task_label="geodesic mesh rebuild"
    )
    print(f"  → Routed to: {result['agent']} (score={result['score']:.3f})")
    print(f"  → Eligible: {result['eligible_count']} agents above threshold {result['threshold']:.2f}")
    if "warning" in result:
        print(f"  ⚠️  {result['warning']}")

    # Route a quick task
    print("\n[4] Routing a QUICK task:")
    result2 = s.route(
        complexity="quick",
        candidates=["manifold", "btc-signals", "infra"],
        task_label="status check"
    )
    print(f"  → Routed to: {result2['agent']} (score={result2['score']:.3f})")

    print("\n[5] Log a new task completion and show updated score:")
    logged = s.log_task("braid", tokens=12000, complexity="deep", task_label="flare AR classification")
    print(f"  → braid: {logged['score_before']:.3f} → {logged['score_after']:.3f} (−{logged['depletion']:.3f} from {logged['tokens']:,} tokens)")

    print("\n[Done] Demo complete. DB written to:", s.db_path)
    print("=" * 60)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        s = AlfvenScheduler()
        status = s.status()
        print(f"\n{'Agent':<18} {'Score':<8} {'ETA Full':>10} {'Arch':<8}")
        print("-" * 46)
        for a in status:
            bar = "█" * int(a["score"] * 20) + "░" * (20 - int(a["score"] * 20))
            print(f"{a['agent']:<18} {a['score']:<8.3f} {a['eta_full_recovery_min']:>8.0f}m  {a['archetype']:<8}")
    elif len(sys.argv) > 1 and sys.argv[1] == "route":
        complexity = sys.argv[2] if len(sys.argv) > 2 else "medium"
        s = AlfvenScheduler()
        result = s.route(complexity=complexity)
        print(json.dumps(result, indent=2))
    else:
        demo()
