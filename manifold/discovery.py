"""Capability discovery — mesh-wide search for agents and capabilities.

While ``audience()`` routes to agents you already know, and ``seek()`` finds
gaps in your local view, **discovery** asks a different question: *what
capabilities exist across the entire mesh?*

Discovery works in two modes:

- **Local**: search the registry for capabilities matching a query (no network
  traffic, instant). Good for agents you've already seen via announcements.
- **Mesh-wide**: broadcast a discovery request, collect responses from peers
  who match, and return a unified result set. Good for finding agents you
  haven't encountered yet.

Usage::

    from manifold.discovery import Discovery

    disco = Discovery(agent)

    # Local search (instant, no network)
    results = disco.search_local("solar")
    for r in results:
        print(f"{r.agent_name}: {r.capability} (score={r.relevance:.2f})")

    # Mesh-wide discovery (async, collects from peers)
    results = await disco.search_mesh("bitcoin-analysis", timeout_s=5.0)

    # Browse all known capabilities grouped by agent
    catalog = disco.catalog()
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import Agent


class DiscoveryMode(str, Enum):
    LOCAL = "local"
    MESH = "mesh"


@dataclass
class DiscoveryHit:
    """A single capability match from a discovery search."""
    agent_name: str
    capability: str
    relevance: float  # 0–1 match score
    tags: list[str] = field(default_factory=list)
    description: str = ""
    address: str = ""
    agent_focus: str | None = None

    def __repr__(self) -> str:
        return (
            f"<DiscoveryHit {self.agent_name!r}.{self.capability!r} "
            f"relevance={self.relevance:.2f}>"
        )


@dataclass
class DiscoveryResult:
    """Complete result set from a discovery search."""
    query: str
    mode: DiscoveryMode
    hits: list[DiscoveryHit] = field(default_factory=list)
    elapsed_ms: float = 0.0
    agents_queried: int = 0
    request_id: str = ""

    @property
    def best(self) -> DiscoveryHit | None:
        """Top hit, if any."""
        return self.hits[0] if self.hits else None

    @property
    def agent_names(self) -> list[str]:
        """Unique agent names that matched, ranked by best relevance."""
        seen: dict[str, float] = {}
        for h in self.hits:
            seen[h.agent_name] = max(seen.get(h.agent_name, 0.0), h.relevance)
        return sorted(seen, key=lambda n: seen[n], reverse=True)

    def top(self, n: int = 5) -> list[DiscoveryHit]:
        """Return the top-n hits by relevance."""
        return self.hits[:n]

    def by_agent(self) -> dict[str, list[DiscoveryHit]]:
        """Group hits by agent name."""
        groups: dict[str, list[DiscoveryHit]] = {}
        for h in self.hits:
            groups.setdefault(h.agent_name, []).append(h)
        return groups

    def summary(self) -> str:
        mode_label = "local" if self.mode == DiscoveryMode.LOCAL else "mesh-wide"
        lines = [
            f"Discovery '{self.query}' [{mode_label}] "
            f"{len(self.hits)} hits from {self.agents_queried} agents "
            f"({self.elapsed_ms:.0f}ms)"
        ]
        for h in self.top(10):
            focus = f" (focus: {h.agent_focus})" if h.agent_focus else ""
            lines.append(
                f"  {h.agent_name}: {h.capability} [{h.relevance:.2f}]{focus}"
            )
        if len(self.hits) > 10:
            lines.append(f"  ... and {len(self.hits) - 10} more")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<DiscoveryResult query={self.query!r} "
            f"hits={len(self.hits)} mode={self.mode.value}>"
        )


# ─── Trigram similarity (shared with audience.py, kept local) ───────────

def _trigrams(text: str) -> set[str]:
    t = f"  {text.lower()}  "
    return {t[i:i + 3] for i in range(len(t) - 2)}


def _trigram_similarity(a: str, b: str) -> float:
    ta = _trigrams(a)
    tb = _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _compute_relevance(query: str, capability: str, description: str = "", tags: list[str] | None = None) -> float:
    """Compute a relevance score for a capability against a query.

    Considers: exact match, substring match, trigram similarity to name/desc/tags.
    Returns the highest score from any signal.
    """
    q = query.lower()
    cap_lower = capability.lower()

    # Exact match
    if q == cap_lower:
        return 1.0

    # Substring match (query in capability or capability in query)
    if q in cap_lower or cap_lower in q:
        return 0.85

    # Trigram similarity with capability name
    score = _trigram_similarity(query, capability)

    # Also check description
    if description:
        score = max(score, _trigram_similarity(query, description))

    # Also check tags
    if tags:
        for tag in tags:
            tag_score = _trigram_similarity(query, tag)
            if tag_score > score:
                score = tag_score

    return score


class Discovery:
    """
    Mesh-wide capability discovery.

    Wraps an ``Agent`` and provides search over the local registry
    (instant) or mesh-wide broadcast (async).
    """

    DISCOVERY_TOPIC = "manifold:discovery"

    def __init__(self, agent: Agent, min_relevance: float = 0.15) -> None:
        self._agent = agent
        self._min_relevance = min_relevance
        self._pending: dict[str, asyncio.Future[DiscoveryResult]] = {}
        self._collected: dict[str, list[DiscoveryHit]] = {}
        self._subscribed = False

    async def _ensure_subscribed(self) -> None:
        """Subscribe to discovery responses if not already."""
        if self._subscribed:
            return
        try:
            await self._agent.subscribe(
                self.DISCOVERY_TOPIC,
                self._handle_response,
            )
            self._subscribed = True
        except Exception:
            pass

    async def _handle_response(self, payload: dict[str, Any]) -> None:
        """Handle incoming discovery response."""
        request_id = payload.get("request_id", "")
        if request_id not in self._pending:
            return

        hits_data = payload.get("hits", [])
        for h in hits_data:
            hit = DiscoveryHit(
                agent_name=h.get("agent_name", ""),
                capability=h.get("capability", ""),
                relevance=h.get("relevance", 0.0),
                tags=h.get("tags", []),
                description=h.get("description", ""),
                address=h.get("address", ""),
                agent_focus=h.get("agent_focus"),
            )
            if hit.relevance >= self._min_relevance:
                self._collected.setdefault(request_id, []).append(hit)

    def search_local(
        self,
        query: str,
        min_relevance: float | None = None,
    ) -> DiscoveryResult:
        """
        Search the local registry for matching capabilities.

        Fast, no network traffic. Only sees agents that have announced
        themselves to this agent's registry.

        Args:
            query:          What to search for.
            min_relevance:  Minimum match score (0–1). Overrides default.

        Returns:
            DiscoveryResult with matching hits.
        """
        threshold = min_relevance if min_relevance is not None else self._min_relevance
        t0 = time.monotonic()
        hits: list[DiscoveryHit] = []

        registry = self._agent._registry
        for name, rec in registry._records.items():
            for cap in rec.capabilities:
                rel = _compute_relevance(query, cap)
                if rel >= threshold:
                    hits.append(DiscoveryHit(
                        agent_name=name,
                        capability=cap,
                        relevance=rel,
                        address=rec.address,
                        agent_focus=rec.focus,
                    ))

        hits.sort(key=lambda h: h.relevance, reverse=True)

        return DiscoveryResult(
            query=query,
            mode=DiscoveryMode.LOCAL,
            hits=hits,
            elapsed_ms=(time.monotonic() - t0) * 1000,
            agents_queried=len(registry._records),
            request_id=f"local-{uuid.uuid4().hex[:8]}",
        )

    async def search_mesh(
        self,
        query: str,
        timeout_s: float = 5.0,
        min_relevance: float | None = None,
        include_local: bool = True,
    ) -> DiscoveryResult:
        """
        Broadcast a discovery query to the mesh and collect responses.

        Sends a discovery request via the agent's transport, waits for
        peer responses up to ``timeout_s`` seconds, then returns merged
        results.

        Args:
            query:           What to search for.
            timeout_s:       How long to wait for responses.
            min_relevance:   Minimum match score.
            include_local:   Also include local registry results.

        Returns:
            DiscoveryResult with hits from local + mesh peers.
        """
        await self._ensure_subscribed()

        threshold = min_relevance if min_relevance is not None else self._min_relevance
        request_id = f"mesh-{uuid.uuid4().hex[:8]}"
        t0 = time.monotonic()

        # Collect local results first
        all_hits: list[DiscoveryHit] = []
        if include_local:
            local = self.search_local(query, min_relevance=threshold)
            all_hits.extend(local.hits)

        # Broadcast discovery request
        request_payload = {
            "type": "discovery_request",
            "request_id": request_id,
            "query": query,
            "min_relevance": threshold,
            "requester": self._agent._name,
        }

        self._collected[request_id] = []
        future: asyncio.Future[DiscoveryResult] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._agent.publish(self.DISCOVERY_TOPIC, request_payload)

            # Wait for responses
            await asyncio.wait_for(future, timeout=timeout_s)
        except asyncio.TimeoutError:
            pass  # Return whatever we collected
        finally:
            # Collect mesh hits
            mesh_hits = self._collected.pop(request_id, [])
            all_hits.extend(mesh_hits)
            self._pending.pop(request_id, None)

        # Deduplicate: same agent+capability, keep highest relevance
        seen: dict[tuple[str, str], DiscoveryHit] = {}
        for h in all_hits:
            key = (h.agent_name, h.capability)
            if key not in seen or h.relevance > seen[key].relevance:
                seen[key] = h

        hits = sorted(seen.values(), key=lambda h: h.relevance, reverse=True)

        agents_queried = len({h.agent_name for h in hits})
        if include_local:
            agents_queried = max(agents_queried, len(self._agent._registry._records))

        return DiscoveryResult(
            query=query,
            mode=DiscoveryMode.MESH,
            hits=hits,
            elapsed_ms=(time.monotonic() - t0) * 1000,
            agents_queried=agents_queried,
            request_id=request_id,
        )

    def catalog(self) -> dict[str, list[str]]:
        """
        Browse all known capabilities grouped by agent.

        Returns:
            Dict mapping agent name to list of capability strings.
        """
        result: dict[str, list[str]] = {}
        registry = self._agent._registry
        for name, rec in registry._records.items():
            result[name] = list(rec.capabilities)
        return result

    def handle_request(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Handle an incoming discovery request. Called when another agent
        broadcasts a search.

        Returns a list of hit dicts to send back (empty if no match).
        """
        query = payload.get("query", "")
        min_rel = payload.get("min_relevance", 0.15)
        hits: list[dict[str, Any]] = []

        my_caps = self._agent._capabilities
        for cap in my_caps:
            rel = _compute_relevance(query, cap)
            if rel >= min_rel:
                hits.append({
                    "agent_name": self._agent._name,
                    "capability": cap,
                    "relevance": round(rel, 3),
                    "address": getattr(self._agent, "_address", ""),
                    "agent_focus": getattr(self._agent, "_focus", None),
                })

        return hits
