"""Capability registry — tracks what every agent in the mesh knows."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .bridge.base import Transport


REGISTRY_TOPIC = "_manifold.registry"
QUERY_TOPIC = "_manifold.seek"


@dataclass
class AgentRef:
    """
    A reference to another agent on the mesh.

    gap_score: float in [0, 1] — how complementary this agent is to the
    querying agent. 1.0 means perfect complement (knows everything you don't),
    0.0 means complete overlap.
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
    """

    def __init__(self) -> None:
        self._records: dict[str, _AgentRecord] = {}

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

    def update_from_announcement(self, payload: dict[str, Any]) -> None:
        """Update registry from a mesh announcement."""
        data = payload.get("data", payload)
        name = data.get("name")
        if not name:
            return
        self._records[name] = _AgentRecord(
            name=name,
            capabilities=data.get("capabilities", []),
            address=data.get("address", ""),
            focus=data.get("focus"),
        )

    def remove(self, name: str) -> None:
        """Remove an agent from the registry."""
        self._records.pop(name, None)

    def seek(
        self,
        topic: str,
        my_capabilities: list[str],
        my_name: str,
    ) -> list[AgentRef]:
        """
        Find agents with complementary knowledge for a given topic.

        Gap score is computed as the Jaccard-weighted complement:
        how much of the peer's capabilities are NOT in our own set,
        boosted when the topic itself appears in the peer's capabilities.

        Returns agents sorted by gap_score descending (most complementary first).
        """
        my_caps = set(my_capabilities)
        results: list[AgentRef] = []

        for record in self._records.values():
            if record.name == my_name:
                continue

            peer_caps = set(record.capabilities)
            if not peer_caps:
                continue

            # Base gap: what the peer knows that we don't
            unique_to_peer = peer_caps - my_caps
            gap = len(unique_to_peer) / len(peer_caps)

            # Topic boost: if the peer explicitly knows about this topic
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

    async def announce(
        self,
        transport: Transport,
        name: str,
        capabilities: list[str],
        address: str,
        focus: str | None = None,
    ) -> None:
        """Broadcast this agent's capabilities to the mesh."""
        await transport.publish(
            REGISTRY_TOPIC,
            {
                "name": name,
                "capabilities": capabilities,
                "address": address,
                "focus": focus,
            },
        )

    def all_agents(self) -> list[_AgentRecord]:
        """Return all known agents."""
        return list(self._records.values())
