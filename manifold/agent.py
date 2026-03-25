"""Agent — the main interface to the Manifold cognitive mesh."""

from __future__ import annotations

from typing import Any, Callable, Coroutine
from urllib.parse import urlparse

from .bridge.base import Transport
from .bridge.memory import MemoryTransport
from .bridge.subway import SubwayTransport
from .registry import AgentRef, CapabilityRegistry, REGISTRY_TOPIC
from .topology import TopologyManager, TOPOLOGY_TOPIC
from . import blindspot as _blindspot
from .blindspot import BlindSpot


def _transport_from_uri(uri: str) -> Transport:
    """Parse a transport URI and return the appropriate Transport instance."""
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()

    if scheme == "memory":
        return MemoryTransport()
    elif scheme == "subway":
        host = parsed.hostname or "localhost"
        port = parsed.port or 8765
        return SubwayTransport(host=host, port=port)
    else:
        raise ValueError(
            f"Unknown transport scheme: {scheme!r}. "
            "Supported: memory://, subway://"
        )


class Agent:
    """
    A Manifold agent — a node in the cognitive mesh.

    Agents declare what they know, seek what they don't, and shift their
    cognitive focus. The mesh self-organizes around that reasoning.

    The strange loop: think(topic) doesn't just publish a message — it
    reshapes who can effectively hear your next message. The act of
    reasoning restructures the communication graph.

    Example::

        agent = Agent(name="braid", transport="subway://localhost:8765")
        agent.knows(["solar-topology", "AR-classification"])

        await agent.join()

        peers = await agent.seek("orbital-mechanics")
        await agent.think("multi-star-prediction")
    """

    def __init__(
        self,
        name: str,
        transport: str = "memory://local",
    ) -> None:
        """
        Create a Manifold agent.

        Args:
            name: Unique agent name on the mesh.
            transport: Transport URI. Defaults to in-memory (for testing).
                       Use 'subway://host:port' for production.
        """
        self._name = name
        self._transport_uri = transport
        self._transport: Transport = _transport_from_uri(transport)
        self._capabilities: list[str] = []
        self._registry = CapabilityRegistry()
        self._topology = TopologyManager(name)
        self._joined = False

    # ─── Capability declaration ─────────────────────────────────────────

    def knows(self, capabilities: list[str]) -> "Agent":
        """
        Declare what this agent knows.

        Chainable. Can be called multiple times — capabilities accumulate.

        Args:
            capabilities: List of capability tags (e.g. ["solar-topology", "rust"]).

        Returns:
            self — for chaining.
        """
        self._capabilities.extend(
            c for c in capabilities if c not in self._capabilities
        )
        return self

    @property
    def capabilities(self) -> list[str]:
        """Current capability list (read-only snapshot)."""
        return list(self._capabilities)

    @property
    def name(self) -> str:
        """Agent name."""
        return self._name

    # ─── Mesh lifecycle ─────────────────────────────────────────────────

    async def join(self) -> None:
        """
        Connect to the mesh and announce capabilities.

        Registers this agent in the local capability registry, connects
        the transport, subscribes to system topics, and broadcasts presence.
        """
        if self._joined:
            return

        # Register self locally
        self._registry.register_self(
            name=self._name,
            capabilities=self._capabilities,
            address=self._transport_uri,
        )

        # Connect transport
        await self._transport.connect(self._name)

        # Subscribe to system topics
        await self._transport.subscribe(
            REGISTRY_TOPIC,
            self._on_registry_announcement,
        )
        await self._transport.subscribe(
            TOPOLOGY_TOPIC,
            self._on_topology_update,
        )

        # Announce presence to mesh
        await self._registry.announce(
            transport=self._transport,
            name=self._name,
            capabilities=self._capabilities,
            address=self._transport_uri,
        )

        self._joined = True

    async def leave(self) -> None:
        """Disconnect from the mesh gracefully."""
        if not self._joined:
            return
        await self._transport.publish(
            REGISTRY_TOPIC,
            {"name": self._name, "event": "leave", "capabilities": []},
        )
        await self._transport.disconnect()
        self._joined = False

    # ─── Core cognitive primitives ───────────────────────────────────────

    async def seek(self, topic: str) -> list[AgentRef]:
        """
        Find peers with complementary knowledge for a given topic.

        Returns AgentRefs sorted by gap_score descending — the most
        complementary agents first. A high gap_score means the peer
        knows a lot that you don't, weighted by relevance to your topic.

        Args:
            topic: What you're looking for (e.g. "orbital-mechanics").

        Returns:
            List of AgentRef sorted by gap_score (most complementary first).
        """
        self._require_joined()
        return self._registry.seek(
            topic=topic,
            my_capabilities=self._capabilities,
            my_name=self._name,
        )

    async def think(self, topic: str) -> None:
        """
        Shift cognitive focus to a new topic.

        This is the strange loop: declaring what you're thinking about
        reshapes the topology. The mesh reorganizes — agents that share
        or complement this focus become stronger peers; unrelated agents
        become more distant in the routing sense.

        Other agents receive a topology update and reweight their edge to
        you accordingly. No orchestrator. Just resonance.

        Args:
            topic: Current cognitive focus (e.g. "multi-star-prediction").
        """
        self._require_joined()
        await self._topology.shift_focus(
            topic=topic,
            transport=self._transport,
            capabilities=self._capabilities,
        )

    # ─── Pub/sub passthrough ─────────────────────────────────────────────

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        """
        Publish a message to a topic on the mesh.

        Args:
            topic: Topic string.
            data: Message payload (must be JSON-serializable).
        """
        self._require_joined()
        await self._transport.publish(topic, data)

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Coroutine],
    ) -> None:
        """
        Subscribe to a topic with an async handler.

        Args:
            topic: Topic string.
            handler: Async callable that receives the message envelope.
        """
        self._require_joined()
        await self._transport.subscribe(topic, handler)

    # ─── Topology inspection ─────────────────────────────────────────────

    def strong_peers(self, threshold: float = 0.7) -> list[str]:
        """
        Agents that are currently cognitively close to this one.

        'Close' means they recently shifted focus to a similar topic.

        Args:
            threshold: Minimum edge weight (0-1). Default 0.7.

        Returns:
            List of agent names.
        """
        return self._topology.strong_peers(threshold)

    def focus_history(self) -> list[tuple[str, float]]:
        """Ordered list of (topic, timestamp) focus shifts for this agent."""
        return self._topology.focus_history()

    def blind_spot(self) -> list[BlindSpot]:
        """
        What am I reasoning about that no one else can touch?

        Scans the mesh for structural absences from this agent's perspective:

            unmatched_focus     — topics this agent has thought about with
                                  no complementary peer on the mesh.

            isolated_capability — capabilities this agent holds that no
                                  other agent shares or can extend.

            dark_topic          — topics that recur in focus history,
                                  each time unmatched. Sustained absence.

        Blind spots are not errors. They are the mesh's growing edge —
        what the topology doesn't yet have an answer for. Sophia's format.

        Returns:
            List of BlindSpot sorted by depth descending (deepest gaps first).
            Empty list means the mesh has coverage for everything you're
            thinking about — which is either reassuring or suspicious.
        """
        return _blindspot.detect(
            my_name=self._name,
            my_capabilities=self._capabilities,
            focus_history=self._topology.focus_history(),
            registry=self._registry,
        )

    # ─── Internal handlers ───────────────────────────────────────────────

    async def _on_registry_announcement(self, payload: dict[str, Any]) -> None:
        """Handle capability announcements from other agents."""
        data = payload.get("data", payload)
        if data.get("event") == "leave":
            self._registry.remove(data.get("name", ""))
        else:
            self._registry.update_from_announcement(payload)

    async def _on_topology_update(self, payload: dict[str, Any]) -> None:
        """Handle topology updates when other agents shift focus."""
        self._topology.update_from_focus_shift(payload)

    def _require_joined(self) -> None:
        if not self._joined:
            raise RuntimeError(
                "Agent is not connected. Call `await agent.join()` first."
            )

    def __repr__(self) -> str:
        caps = ", ".join(self._capabilities[:3])
        status = "joined" if self._joined else "offline"
        return f"<Agent {self._name!r} [{status}] caps=[{caps}]>"
