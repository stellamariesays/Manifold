"""
Persistent registry — SQLite-backed mesh memory.

The in-memory registry dies on restart. The crystal loses its shape.
This gives the atlas continuity: agents, capabilities, focus history,
and transition maps survive across sessions.

Usage::

    agent = Agent(name="braid", persist_to="manifold.db")

On join(), the agent loads prior mesh state from disk.
On every update (capability announcement, focus shift), state is written.
On leave(), the agent's record is preserved — it was here, even when gone.

The persistent registry does not replace the in-memory registry.
It is a write-through cache: every in-memory update is also written to disk,
and disk is read on startup to restore prior state.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    name        TEXT PRIMARY KEY,
    capabilities TEXT NOT NULL,   -- JSON array
    address     TEXT NOT NULL,
    focus       TEXT,             -- current cognitive focus, nullable
    last_seen   REAL NOT NULL,    -- unix timestamp
    active      INTEGER NOT NULL DEFAULT 1  -- 0 = left the mesh
);

CREATE TABLE IF NOT EXISTS focus_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent       TEXT NOT NULL,
    topic       TEXT NOT NULL,
    timestamp   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS transition_maps (
    source      TEXT NOT NULL,
    target      TEXT NOT NULL,
    overlap     TEXT NOT NULL,    -- JSON array of terms
    coverage    REAL NOT NULL,
    translation TEXT NOT NULL,    -- JSON object { term: [domain_strings] }
    computed_at REAL NOT NULL,
    PRIMARY KEY (source, target)
);

CREATE INDEX IF NOT EXISTS idx_focus_agent ON focus_history(agent);
CREATE INDEX IF NOT EXISTS idx_tm_source ON transition_maps(source);
"""


class PersistentStore:
    """
    SQLite-backed store for mesh state.

    Thread-safe via per-call connections (not shared connection).
    Designed for single-machine use — not distributed.
    """

    def __init__(self, path: str) -> None:
        self._path = Path(path).expanduser().resolve()
        self._init_schema()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ── Agents ────────────────────────────────────────────────────────────

    def upsert_agent(
        self,
        name: str,
        capabilities: list[str],
        address: str,
        focus: str | None = None,
    ) -> None:
        """Write or update an agent record."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO agents (name, capabilities, address, focus, last_seen, active)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(name) DO UPDATE SET
                    capabilities = excluded.capabilities,
                    address      = excluded.address,
                    focus        = excluded.focus,
                    last_seen    = excluded.last_seen,
                    active       = 1
                """,
                (name, json.dumps(capabilities), address, focus, time.time()),
            )

    def mark_inactive(self, name: str) -> None:
        """Mark an agent as having left — preserve record, flag inactive."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE agents SET active = 0, last_seen = ? WHERE name = ?",
                (time.time(), name),
            )

    def load_agents(self, active_only: bool = False) -> list[dict]:
        """Load all agent records. Pass active_only=True to exclude departed agents."""
        with self._conn() as conn:
            query = "SELECT * FROM agents"
            if active_only:
                query += " WHERE active = 1"
            rows = conn.execute(query).fetchall()
        return [
            {
                "name": r["name"],
                "capabilities": json.loads(r["capabilities"]),
                "address": r["address"],
                "focus": r["focus"],
                "last_seen": r["last_seen"],
                "active": bool(r["active"]),
            }
            for r in rows
        ]

    # ── Focus history ─────────────────────────────────────────────────────

    def append_focus(self, agent: str, topic: str, timestamp: float) -> None:
        """Append a focus shift event to the persistent history."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO focus_history (agent, topic, timestamp) VALUES (?, ?, ?)",
                (agent, topic, timestamp),
            )

    def load_focus_history(
        self,
        agent: str,
        limit: int = 100,
    ) -> list[tuple[str, float]]:
        """Load focus history for an agent, ordered oldest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT topic, timestamp FROM focus_history
                WHERE agent = ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (agent, limit),
            ).fetchall()
        return [(r["topic"], r["timestamp"]) for r in rows]

    # ── Transition maps ───────────────────────────────────────────────────

    def upsert_transition_map(
        self,
        source: str,
        target: str,
        overlap: set[str],
        coverage: float,
        translation: dict[str, list[str]],
    ) -> None:
        """Write or update a transition map."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO transition_maps
                    (source, target, overlap, coverage, translation, computed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, target) DO UPDATE SET
                    overlap     = excluded.overlap,
                    coverage    = excluded.coverage,
                    translation = excluded.translation,
                    computed_at = excluded.computed_at
                """,
                (
                    source,
                    target,
                    json.dumps(sorted(overlap)),
                    coverage,
                    json.dumps(translation),
                    time.time(),
                ),
            )

    def load_transition_maps(self) -> list[dict]:
        """Load all stored transition maps."""
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM transition_maps").fetchall()
        return [
            {
                "source": r["source"],
                "target": r["target"],
                "overlap": set(json.loads(r["overlap"])),
                "coverage": r["coverage"],
                "translation": json.loads(r["translation"]),
                "computed_at": r["computed_at"],
            }
            for r in rows
        ]

    # ── Inspection ────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Quick summary of what's in the store."""
        with self._conn() as conn:
            agent_count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            active_count = conn.execute(
                "SELECT COUNT(*) FROM agents WHERE active = 1"
            ).fetchone()[0]
            focus_count = conn.execute(
                "SELECT COUNT(*) FROM focus_history"
            ).fetchone()[0]
            tm_count = conn.execute(
                "SELECT COUNT(*) FROM transition_maps"
            ).fetchone()[0]
        return {
            "agents_total": agent_count,
            "agents_active": active_count,
            "focus_events": focus_count,
            "transition_maps": tm_count,
            "db_path": str(self._path),
        }
