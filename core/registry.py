"""Capability registry — tracks what every agent in the mesh knows.

The registry now supports two routing modes:

    Jaccard gap-score (default, zero deps):
        Measures how complementary a peer is by counting capabilities
        the peer has that you don't, boosted if the query topic appears
        in the peer's capability list.

    Semantic cosine routing (optional):
        Replaces gap-score with cosine similarity on agent capability
        embeddings. Embeddings are generated at registration time using
        the best available backend (ollama → OpenAI → TF-IDF fallback).
        Peers that share topic-space with the query score highly even
        when the tokens don't match.

To enable semantic routing::

    registry = CapabilityRegistry(semantic=True)
    # or pass an explicit embedder:
    registry = CapabilityRegistry(semantic="ollama")

Peers that include an ``"embedding"`` field in their announcement
payload are ingested directly (no re-embedding). Legacy peers without
embeddings are re-embedded locally using the configured backend.

The ``AgentRef`` returned in semantic mode carries a ``gap_score`` equal
to the cosine similarity (renamed for API compatibility, same field,
same sort order).
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Any

from .bridge.base import Transport

logger = logging.getLogger(__name__)

REGISTRY_TOPIC = "_manifold.registry"
QUERY_TOPIC = "_manifold.seek"


@dataclass
class AgentRef:
    """
    A reference to another agent on the mesh.

    gap_score: float in [0, 1]
        Jaccard mode  — how complementary this agent is (1.0 = perfect complement).
        Semantic mode — cosine similarity to the query (1.0 = identical embedding).
    """

    name: str
    capabilities: list[str]
    address: str
    gap_score: float = 0.0

    def __repr__(self) -> str:
        pct = int(self.gap_score * 100)
        caps = ", ".join(self.capabilities[:3])
        return f"<AgentRef {self.name!r} gap={pct}% caps=[{caps}]>"


@dataclass
class _AgentRecord:
    name: str
    capabilities: list[str]
    address: str
    focus: str | None = None


class CapabilityRegistry:
    """
    Local view of the mesh's capability landscape.

    Each agent maintains its own registry copy, kept in sync via pub/sub
    announcements on REGISTRY_TOPIC. This gives eventual consistency — no
    central server, no single point of failure.

    Args:
        semantic: Enable semantic cosine routing. Pass True for auto-detection,
                  or a string ("ollama", "openai", "tfidf") to force a backend.
                  Defaults to False (Jaccard gap-score routing).
        cache_path: Path to JSON file for embedding persistence. When set,
                    agent embeddings are saved on register and restored on
                    cold-start. Only active when semantic routing is enabled.
    """

    def __init__(self, semantic: bool | str = False, cache_path: str | None = None) -> None:
        self._records: dict[str, _AgentRecord] = {}
        self._semantic_router = None

        if semantic is not False:
            try:
                from .semantic_router import SemanticRegistry
                embedder = "auto" if semantic is True else str(semantic)
                self._semantic_router = SemanticRegistry(embedder=embedder, cache_path=cache_path)
                logger.debug(
                    "CapabilityRegistry: semantic routing enabled (%s)",
                    self._semantic_router,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "CapabilityRegistry: semantic routing unavailable (%s) — "
                    "falling back to Jaccard gap-score",
                    exc,
                )
                self._semantic_router = None

    # ─── Registration ────────────────────────────────────────────────────

    def register_self(
        self,
        name: str,
        capabilities: list[str],
        address: str,
    ) -> None:
        """Register this agent in the local registry."""
        self._records[name] = _AgentRecord(
            name=name,
            capabilities=capabilities,
            address=address,
        )
        if self._semantic_router is not None:
            self._semantic_router.register(name, capabilities, address=address)

    def update_from_announcement(self, payload: dict[str, Any]) -> None:
        """Update registry from a mesh announcement.

        Accepts an optional ``"embedding"`` field in the payload — when
        present it is stored directly (no re-embedding). When absent the
        semantic router re-embeds the peer's capability list locally.
        """
        data = payload.get("data", payload)
        name = data.get("name")
        if not name:
            return

        event = data.get("event")
        if event == "leave":
            self._records.pop(name, None)
            if self._semantic_router is not None:
                self._semantic_router.unregister(name)
            return

        capabilities = data.get("capabilities", [])
        address = data.get("address", "")
        focus = data.get("focus")

        self._records[name] = _AgentRecord(
            name=name,
            capabilities=capabilities,
            address=address,
            focus=focus,
        )

        if self._semantic_router is not None:
            embedding = data.get("embedding")  # pre-computed, may be None
            self._semantic_router.register(
                name,
                capabilities,
                address=address,
                embedding=embedding,  # None → router embeds locally
            )

    def remove(self, name: str) -> None:
        """Remove an agent from the registry."""
        self._records.pop(name, None)
        if self._semantic_router is not None:
            self._semantic_router.unregister(name)

    # ─── Routing ─────────────────────────────────────────────────────────

    def seek(
        self,
        topic: str,
        my_capabilities: list[str],
        my_name: str,
    ) -> list[AgentRef]:
        """
        Find agents with knowledge relevant to a given topic.

        Semantic mode (when enabled):
            Embeds the topic string and returns peers ranked by cosine
            similarity to their capability embeddings. gap_score = similarity.

        Jaccard mode (default):
            Measures how complementary each peer is — how much of their
            capability set is NOT in ours, boosted when the topic appears
            in the peer's capability list.

        Returns agents sorted by gap_score descending (best match first).
        """
        if self._semantic_router is not None:
            return self._seek_semantic(topic, my_name)
        return self._seek_jaccard(topic, my_capabilities, my_name)

    def _seek_semantic(self, topic: str, my_name: str) -> list[AgentRef]:
        """Cosine-similarity routing via SemanticRegistry."""
        results: list[AgentRef] = []
        for ref in self._semantic_router.seek(topic, exclude=my_name):
            record = self._records.get(ref.name)
            results.append(
                AgentRef(
                    name=ref.name,
                    capabilities=ref.capabilities,
                    address=record.address if record else ref.address,
                    gap_score=round(ref.similarity, 3),
                )
            )
        return results

    def _seek_jaccard(
        self,
        topic: str,
        my_capabilities: list[str],
        my_name: str,
    ) -> list[AgentRef]:
        """Original Jaccard gap-score routing."""
        my_caps = set(my_capabilities)
        results: list[AgentRef] = []

        for record in self._records.values():
            if record.name == my_name:
                continue

            peer_caps = set(record.capabilities)
            if not peer_caps:
                continue

            unique_to_peer = peer_caps - my_caps
            gap = len(unique_to_peer) / len(peer_caps)

            topic_tokens = set(topic.lower().replace("-", " ").split())
            peer_tokens = {c.lower().replace("-", " ") for c in peer_caps}
            overlap = sum(
                1
                for t in topic_tokens
                if any(t in p for p in peer_tokens)
            )
            if overlap:
                boost = min(0.3, overlap * 0.15)
                gap = min(1.0, gap + boost)

            results.append(
                AgentRef(
                    name=record.name,
                    capabilities=record.capabilities,
                    address=record.address,
                    gap_score=round(gap, 3),
                )
            )

        results.sort(key=lambda r: r.gap_score, reverse=True)
        return results

    # ─── Announcements ───────────────────────────────────────────────────

    async def announce(
        self,
        transport: Transport,
        name: str,
        capabilities: list[str],
        address: str,
        focus: str | None = None,
    ) -> None:
        """Broadcast this agent's capabilities to the mesh.

        When semantic routing is enabled, the agent's capability embedding
        is included in the announcement payload so peers can ingest it
        directly without re-embedding.
        """
        payload: dict[str, Any] = {
            "name": name,
            "capabilities": capabilities,
            "address": address,
            "focus": focus,
        }

        if self._semantic_router is not None:
            rec = self._semantic_router.get(name)
            if rec is not None and rec.embedding:
                payload["embedding"] = rec.embedding

        await transport.publish(REGISTRY_TOPIC, payload)

    # ─── Inspection ──────────────────────────────────────────────────────

    def all_agents(self) -> list[_AgentRecord]:
        """Return all known agents."""
        return list(self._records.values())

    @property
    def semantic_enabled(self) -> bool:
        """True when semantic cosine routing is active."""
        return self._semantic_router is not None

    def __repr__(self) -> str:
        mode = "semantic" if self.semantic_enabled else "jaccard"
        return f"<CapabilityRegistry agents={len(self._records)} mode={mode!r}>"
