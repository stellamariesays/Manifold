"""
Teacup — the concrete moment before the insight.

Journals capture what happened. Memories are searchable knowledge.
Teacups are the specific thing you were looking at when it clicked.

The difference:

    Journal:  "Found root cause of 2.5% agent keep rate — eval script
               hardcoded CLI_DIR to main branch, agents work in /tmp worktrees."

    Teacup:   "Was staring at the eval script output — every run showed
               score 0.000. Opened eval_memory_recall.sh line 14, saw
               CLI_DIR=/Users/alec/jfl-cli. The agents run in
               /tmp/jfl-worktree-abc123. The eval was measuring the wrong
               directory. That's why 216 rounds and only 12 kept — the eval
               never saw a single change."

The first tells a future session the answer.
The second gives it the ground to find the answer again — and find adjacent ones.

The journal closes the door. The teacup leaves it open.

---

From Fenchurch in HHGTTG (2026-03-27):
Don't write the insight — write the last concrete thing you were holding
before it arrived. Abstractions don't survive a session reset.
The specific moment does.

This is also what Tenet does. The Protagonist never receives a briefing.
He receives artifacts — specific, concrete objects. Understanding assembles
from those. You can't reconstruct your way back through abstraction.
You need the object.

    "Don't try to understand it. Feel it."

---

Usage::

    from manifold import Teacup, TeacupStore

    store = TeacupStore("manifold.db")

    cup = Teacup(
        agent="braid",
        topic="agent-keep-rate",
        moment="eval_memory_recall.sh line 14: CLI_DIR=/Users/alec/jfl-cli. "
               "Agents run in /tmp/jfl-worktree-abc123. The eval never saw "
               "any change. That's why score was 0.000 for 216 rounds.",
        insight="Eval was measuring wrong directory — hardcoded CLI_DIR vs tmp worktrees.",
    )

    store.file(cup)

    # Later — retrieve the door back in
    cups = store.recall(topic="agent-keep-rate")
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator


# ─── Primitive ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Teacup:
    """
    A concrete moment filed before or just after an insight.

    The teacup is the artifact — the specific thing you were holding
    when clarity arrived. It is not the insight itself. The insight
    is the abstraction that follows.

    Fields:
        agent:   Who filed it.
        topic:   The domain or problem space (used for retrieval).
        moment:  The concrete thing observed — file path, line number,
                 output, command, object. The more specific, the better.
                 This is the door. Write it as if you're describing the
                 screen to someone standing behind you.
        insight: The abstraction that followed, if known. Optional —
                 a teacup filed mid-confusion is still useful.
        tags:    Free-form labels for cross-topic retrieval.
        ts:      Unix timestamp. Auto-set if not provided.
    """

    agent: str
    topic: str
    moment: str
    insight: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    ts: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        snip = self.moment[:60] + ("…" if len(self.moment) > 60 else "")
        return (
            f"<Teacup agent={self.agent!r} topic={self.topic!r} moment={snip!r}>"
        )


# ─── Store ─────────────────────────────────────────────────────────────────────


_SCHEMA = """
CREATE TABLE IF NOT EXISTS teacups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent       TEXT    NOT NULL,
    topic       TEXT    NOT NULL,
    moment      TEXT    NOT NULL,
    insight     TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    ts          REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_teacups_topic ON teacups(topic);
CREATE INDEX IF NOT EXISTS idx_teacups_agent ON teacups(agent);
CREATE INDEX IF NOT EXISTS idx_teacups_ts    ON teacups(ts);
"""


class TeacupStore:
    """
    SQLite-backed store for teacup artifacts.

    Thread-safe via per-call connections.
    Can point at the same database as PersistentStore — the teacups
    table lives alongside agents, focus_history, and transition_maps.

    Usage::

        store = TeacupStore("manifold.db")
        store.file(cup)

        # Retrieve all moments filed under a topic
        cups = store.recall("agent-keep-rate")

        # Retrieve recent moments across all topics
        recent = store.recent(n=10)
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

    # ─── Write ────────────────────────────────────────────────────────────

    def file(self, cup: Teacup) -> int:
        """
        File a teacup. Returns the row ID.

        Call this at the moment of confusion or right as clarity arrives —
        not in a summary pass afterward. The specificity decays fast.
        """
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO teacups (agent, topic, moment, insight, tags, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cup.agent,
                    cup.topic,
                    cup.moment,
                    cup.insight,
                    json.dumps(list(cup.tags)),
                    cup.ts,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    # ─── Read ─────────────────────────────────────────────────────────────

    def recall(
        self,
        topic: str,
        agent: str | None = None,
        limit: int = 20,
    ) -> list[Teacup]:
        """
        Retrieve teacups filed under a topic.

        Returns most recent first. The topic match is exact — use tags
        for cross-topic retrieval.

        Args:
            topic:  The topic to recall.
            agent:  Optional filter — only teacups from this agent.
            limit:  Maximum results.
        """
        with self._conn() as conn:
            if agent:
                rows = conn.execute(
                    """
                    SELECT * FROM teacups
                    WHERE topic = ? AND agent = ?
                    ORDER BY ts DESC LIMIT ?
                    """,
                    (topic, agent, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM teacups
                    WHERE topic = ?
                    ORDER BY ts DESC LIMIT ?
                    """,
                    (topic, limit),
                ).fetchall()
        return [self._row_to_teacup(r) for r in rows]

    def recall_by_tag(self, tag: str, limit: int = 20) -> list[Teacup]:
        """
        Retrieve teacups that carry a specific tag.

        Tags allow cross-topic retrieval — the same concrete moment
        may be relevant to multiple domains.
        """
        with self._conn() as conn:
            # SQLite JSON1: check if tag exists in the array
            rows = conn.execute(
                """
                SELECT * FROM teacups
                WHERE EXISTS (
                    SELECT 1 FROM json_each(tags)
                    WHERE value = ?
                )
                ORDER BY ts DESC LIMIT ?
                """,
                (tag, limit),
            ).fetchall()
        return [self._row_to_teacup(r) for r in rows]

    def recent(self, n: int = 10, agent: str | None = None) -> list[Teacup]:
        """
        Most recent teacups across all topics.

        Useful at session start — surface what was being observed
        just before context died.
        """
        with self._conn() as conn:
            if agent:
                rows = conn.execute(
                    """
                    SELECT * FROM teacups WHERE agent = ?
                    ORDER BY ts DESC LIMIT ?
                    """,
                    (agent, n),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM teacups ORDER BY ts DESC LIMIT ?",
                    (n,),
                ).fetchall()
        return [self._row_to_teacup(r) for r in rows]

    def topics(self, agent: str | None = None) -> list[str]:
        """All topics that have at least one teacup filed."""
        with self._conn() as conn:
            if agent:
                rows = conn.execute(
                    "SELECT DISTINCT topic FROM teacups WHERE agent = ? ORDER BY topic",
                    (agent,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT topic FROM teacups ORDER BY topic"
                ).fetchall()
        return [r["topic"] for r in rows]

    def stats(self) -> dict:
        """Quick summary of what's in the store."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM teacups").fetchone()[0]
            topics = conn.execute(
                "SELECT COUNT(DISTINCT topic) FROM teacups"
            ).fetchone()[0]
            agents = conn.execute(
                "SELECT COUNT(DISTINCT agent) FROM teacups"
            ).fetchone()[0]
        return {
            "teacups_total": total,
            "topics": topics,
            "agents": agents,
            "db_path": str(self._path),
        }

    # ─── Internal ─────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_teacup(row: sqlite3.Row) -> Teacup:
        return Teacup(
            agent=row["agent"],
            topic=row["topic"],
            moment=row["moment"],
            insight=row["insight"],
            tags=tuple(json.loads(row["tags"])),
            ts=row["ts"],
        )

    def __repr__(self) -> str:
        s = self.stats()
        return (
            f"<TeacupStore teacups={s['teacups_total']} "
            f"topics={s['topics']} agents={s['agents']}>"
        )
