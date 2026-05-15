"""Topology manager — the strange loop. Thinking changes who can hear you."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .bridge.base import Transport

TOPOLOGY_TOPIC = "_manifold.topology"


@dataclass
class TopologyEdge:
    """A directed edge in the cognitive mesh."""

    source: str
    target: str
    weight: float  # 0-1, based on capability overlap + shared focus
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


class TopologyManager:
    """
    Manages the agent's local view of the mesh topology.

    This is where the strange loop lives. When an agent calls think(topic),
    it broadcasts its new cognitive focus to the mesh. Other agents update
    their routing tables — edges to this agent gain weight if they share the
    focus, lose weight if they don't. The topology self-organizes around
    what the collective is actually thinking about.

    No central authority. No orchestrator. Just agents declaring what they're
    thinking and the mesh responding.
    """

    def __init__(self, agent_name: str) -> None:
        self._agent_name = agent_name
        self._edges: dict[tuple[str, str], TopologyEdge] = {}
        self._focus: str | None = None
        self._focus_history: list[tuple[str, float]] = []

    @property
    def current_focus(self) -> str | None:
        """The agent's current cognitive focus."""
        return self._focus

    async def shift_focus(
        self,
        topic: str,
        transport: Transport,
        capabilities: list[str],
    ) -> None:
        """
        Shift cognitive focus to a new topic and broadcast to the mesh.

        This is the core of Manifold's strange loop: declaring what you're
        thinking reshapes who you're effectively connected to. Agents that
        share or complement this focus become better peers; unrelated agents
        become more distant in the routing sense.
        """
        self._focus = topic
        self._focus_history.append((topic, time.time()))

        # Broadcast focus shift to the mesh
        await transport.publish(
            TOPOLOGY_TOPIC,
            {
                "agent": self._agent_name,
                "focus": topic,
                "capabilities": capabilities,
                "timestamp": time.time(),
            },
        )

    def update_from_focus_shift(self, payload: dict[str, Any]) -> None:
        """
        Update local topology when another agent shifts focus.

        When a peer declares a new cognitive focus, we reweight our edge
        to them based on how much our own capabilities and focus overlap
        with theirs.
        """
        data = payload.get("data", payload)
        peer_name = data.get("agent")
        peer_focus = data.get("focus", "")
        peer_caps = set(data.get("capabilities", []))

        if not peer_name or peer_name == self._agent_name:
            return

        # Compute edge weight: shared focus + capability resonance
        weight = 0.0

        if self._focus and peer_focus:
            # Focus similarity — simple token overlap
            our_tokens = set(self._focus.lower().replace("-", " ").split())
            their_tokens = set(peer_focus.lower().replace("-", " ").split())
            if our_tokens | their_tokens:
                focus_sim = len(our_tokens & their_tokens) / len(
                    our_tokens | their_tokens
                )
                weight += focus_sim * 0.6

        weight += 0.4  # baseline — all peers have some connection

        key = (self._agent_name, peer_name)
        if key in self._edges:
            self._edges[key].weight = round(weight, 3)
            self._edges[key].last_active = time.time()
        else:
            self._edges[key] = TopologyEdge(
                source=self._agent_name,
                target=peer_name,
                weight=round(weight, 3),
            )

    def get_edges(self) -> list[TopologyEdge]:
        """All known edges from this agent's perspective."""
        return list(self._edges.values())

    def strong_peers(self, threshold: float = 0.7) -> list[str]:
        """Agents with edge weight above threshold — cognitively close right now."""
        return [
            e.target
            for e in self._edges.values()
            if e.weight >= threshold
        ]

    def focus_history(self) -> list[tuple[str, float]]:
        """Ordered list of (topic, timestamp) focus shifts."""
        return list(self._focus_history)
