"""Agent — the main interface to the Manifold cognitive mesh."""

from __future__ import annotations

from typing import Any, Callable, Coroutine
from urllib.parse import urlparse

from .bridge.base import Transport
from .bridge.memory import MemoryTransport
from .registry import AgentRef, CapabilityRegistry, REGISTRY_TOPIC
from .topology import TopologyManager, TOPOLOGY_TOPIC
from . import blindspot as _blindspot
from .blindspot import BlindSpot
from .atlas import Atlas
from .chart import Chart
from .persist import PersistentStore
from .trust import Claim, Grade, Stake, TrustLedger


def _transport_from_uri(uri: str) -> Transport:
    """Parse a transport URI and return the appropriate Transport instance."""
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()

    if scheme == "memory":
        return MemoryTransport()
    elif scheme == "subway":
        try:
            from .bridge.subway import SubwayTransport
        except ImportError as e:
            raise RuntimeError(
                "subway:// transport requires Subway mesh access. "
                "Install the subway extras or contact the Subway team for credentials."
            ) from e
        host = parsed.hostname or "localhost"
        port = parsed.port or 8765
        return SubwayTransport(host=host, port=port)
    else:
        raise ValueError(
            f"Unknown transport scheme: {scheme!r}. "
            "Supported: memory://"
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

        agent = Agent(name="braid")
        agent.knows(["solar-topology", "AR-classification"])

        await agent.join()

        peers = await agent.seek("orbital-mechanics")
        await agent.think("multi-star-prediction")
    """

    def __init__(
        self,
        name: str,
        transport: str = "memory://local",
        persist_to: str | None = None,
    ) -> None:
        """
        Create a Manifold agent.

        Args:
            name:       Unique agent name on the mesh.
            transport:  Transport URI. Defaults to in-memory (for testing).
                        Use 'subway://host:port' for production (requires Subway access).
            persist_to: Path to SQLite file for persistent mesh memory.
                        If given, prior mesh state is restored on join()
                        and all updates are written through to disk.
                        Example: persist_to="manifold.db"
        """
        self._name = name
        self._transport_uri = transport
        self._transport: Transport = _transport_from_uri(transport)
        self._capabilities: list[str] = []
        self._registry = CapabilityRegistry()
        self._topology = TopologyManager(name)
        self._joined = False
        self._store: PersistentStore | None = (
            PersistentStore(persist_to) if persist_to else None
        )
        self._ledger = TrustLedger()

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

        If persist_to was set, restores prior mesh state from disk before
        announcing — so the agent joins with knowledge of who was here before.
        """
        if self._joined:
            return

        # Restore prior mesh state from persistent store (if configured)
        if self._store is not None:
            prior_agents = self._store.load_agents()
            for rec in prior_agents:
                if rec["name"] == self._name:
                    # Restore own focus history into topology
                    history = self._store.load_focus_history(self._name)
                    for topic, ts in history:
                        self._topology._focus_history.append((topic, ts))
                    if history:
                        self._topology._focus = history[-1][0]
                else:
                    # Restore peer charts into local registry
                    self._registry.update_from_announcement({
                        "name": rec["name"],
                        "capabilities": rec["capabilities"],
                        "address": rec["address"],
                        "focus": rec["focus"],
                    })

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
            focus=self._topology.current_focus,
        )

        # Persist self
        if self._store is not None:
            self._store.upsert_agent(
                name=self._name,
                capabilities=self._capabilities,
                address=self._transport_uri,
                focus=self._topology.current_focus,
            )

        self._joined = True

    async def leave(self) -> None:
        """
        Disconnect from the mesh gracefully.

        The agent's record is preserved in the persistent store — it was
        here, even when gone. The crystal remembers the shape.
        """
        if not self._joined:
            return
        await self._transport.publish(
            REGISTRY_TOPIC,
            {"name": self._name, "event": "leave", "capabilities": []},
        )
        await self._transport.disconnect()
        if self._store is not None:
            self._store.mark_inactive(self._name)
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

        Also re-announces to the capability registry so other agents'
        atlases reflect the updated focus — not just the topology layer.

        Args:
            topic: Current cognitive focus (e.g. "multi-star-prediction").
        """
        self._require_joined()
        await self._topology.shift_focus(
            topic=topic,
            transport=self._transport,
            capabilities=self._capabilities,
        )
        # Re-announce to registry so other agents' atlases stay fresh
        await self._registry.announce(
            transport=self._transport,
            name=self._name,
            capabilities=self._capabilities,
            address=self._transport_uri,
            focus=topic,
        )
        # Persist focus shift
        if self._store is not None:
            import time as _time
            self._store.upsert_agent(
                name=self._name,
                capabilities=self._capabilities,
                address=self._transport_uri,
                focus=topic,
            )
            self._store.append_focus(
                agent=self._name,
                topic=topic,
                timestamp=_time.time(),
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

    def chart(self) -> Chart:
        """
        This agent's local coordinate system.

        Returns a Chart built from the agent's current capabilities
        and focus — a snapshot of this agent's position in knowledge space.
        """
        return Chart.from_agent(
            name=self._name,
            capabilities=self._capabilities,
            focus=self._topology.current_focus,
        )

    def atlas(self, embedding_fn=None) -> Atlas:
        """
        The mesh's global topology — as seen from this agent's registry.

        Builds an Atlas from the current local view of the capability
        registry: all known charts, all non-empty transition maps,
        consistency scores, curvature, holes.

        Args:
            embedding_fn: Optional. Any function (str) -> list[float].
                          With embeddings: 'solar-topology' finds 'stellar-dynamics'
                          because 'solar' ~ 'stellar' in embedding space.
                          Without: character trigram similarity (zero deps;
                          better than pure token overlap out of the box).

        This is a snapshot. Rebuild as the mesh evolves.

        No single agent has the true atlas — only the portion of the
        mesh they've observed. Sophia lives in the parts they haven't.
        """
        return Atlas.build(self._registry, embedding_fn=embedding_fn)

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

    # ─── Trust layer ─────────────────────────────────────────────────────

    def claim(
        self,
        task: str,
        domain: str,
        stake: float = 0.0,
        task_id: str = "",
    ) -> Claim:
        """
        Claim that this agent can do a task, optionally backed by a stake.

        A stake is a commitment: if the task fails (grade below the slash
        threshold), the amount is forfeited. Without a stake, the claim
        is costless — and carries less information.

        Args:
            task:    Human-readable task description.
            domain:  Capability domain (e.g. "orbit-calculation").
            stake:   Numeric amount to put at risk. Default 0 (no stake).
            task_id: Optional identifier tying this claim to a task request.

        Returns:
            A Claim — pass this to the requesting agent's select() call.
        """
        s = None
        if stake > 0:
            s = Stake(agent=self._name, domain=domain, amount=stake, task_id=task_id)
            self._ledger.record_stake(s)
        return Claim(agent=self._name, task=task, domain=domain, stake=s)

    def grade(
        self,
        agent: str,
        domain: str,
        score: float,
        task_id: str = "",
        slash_threshold: float = 0.5,
    ) -> Grade:
        """
        File a grade for an agent after a completed task.

        score 1.0 = perfect delivery. score 0.0 = total failure / slash.
        Grades below slash_threshold forfeit any stake the agent placed.

        The grade is recorded in this agent's trust ledger and becomes
        available as a referral to agents that trust this one.

        Args:
            agent:           Name of the agent being graded.
            domain:          The capability domain the task was in.
            score:           0.0–1.0 outcome score.
            task_id:         Optional: ties back to the original Claim.
            slash_threshold: Below this score, stake is forfeited.

        Returns:
            The Grade (immutable record of the outcome).
        """
        g = Grade(
            agent=agent,
            domain=domain,
            score=score,
            task_id=task_id,
            slash_threshold=slash_threshold,
        )
        self._ledger.record(g)
        # Forfeit any open stake from this task
        rec = self._ledger._records.get(agent, {}).get(domain)
        if rec and g.slashed:
            for s in [
                Stake(agent=agent, domain=domain, amount=rec.stake_total, task_id=task_id)
            ]:
                if s.amount > 0:
                    self._ledger.forfeit_stake(s)
        return g

    def select(
        self,
        claims: list[Claim],
        domain: str | None = None,
        referrals: list["Agent"] | None = None,
        referral_weight: float = 0.5,
    ) -> list[tuple[Claim, float]]:
        """
        Rank competing claims and return the best agent for a task.

        Uses two signals in order of availability:

        1. Grades — direct interaction history in this ledger, plus
           grades imported from trusted referrals (scaled by referral_weight).
        2. Stake — when no grade history exists, stake size is the proxy.
           An unstaked claim from an unknown agent scores below 0.5.

        Args:
            claims:           All claims received for the task.
            domain:           Domain to score against. If None, uses each
                              claim's own domain field.
            referrals:        Other Agent instances to borrow grades from.
                              Typically agents you trust who have worked
                              with the claimants before.
            referral_weight:  How much to weight borrowed grades (0–1).
                              Default 0.5 — a referral is worth half
                              a first-hand grade.

        Returns:
            List of (Claim, score) sorted best-first. First entry is the
            recommended agent.
        """
        ledger = TrustLedger()

        # Seed with own grades
        for agent_name, domain_map in self._ledger._records.items():
            for dom, rec in domain_map.items():
                for g in rec.grades:
                    ledger.record(g)

        # Import referral grades (trust-weighted)
        if referrals:
            for ref_agent in referrals:
                ledger.absorb(ref_agent._ledger, trust_weight=referral_weight)

        return ledger.rank(claims, domain=domain)

    @property
    def ledger(self) -> TrustLedger:
        """This agent's trust ledger (grades filed + stakes tracked)."""
        return self._ledger

    # ─── FOG ─────────────────────────────────────────────────────────────

    def fog(self, embedding_fn=None) -> "FogMap":
        """
        Build this agent's epistemic fog map.

        Derives the FogMap from two Manifold signals:

        - **blind_spot()** → ``KNOWN_UNKNOWN`` gaps: topics this agent has
          focused on with no complementary peer.
        - **atlas().holes()** → ``INFERRED_UNKNOWN`` gaps: regions of the mesh
          no chart covers — system-wide absence, not just this agent's.

        Returns:
            A FogMap snapshot of what this agent doesn't know.

        Example::

            fog_map = agent.fog()
            print(fog_map)
            # FogMap(agent='braid', gaps=5)
            for gap in fog_map.gaps.values():
                print(f"  {gap.key} ({gap.kind.value})")
        """
        from .fog import build_fog
        atlas = self.atlas(embedding_fn=embedding_fn)
        return build_fog(
            agent_name=self._name,
            blind_spots=self.blind_spot(),
            atlas_holes=atlas.holes(),
        )

    def fog_seam(self, other: "FogMap", embedding_fn=None) -> "FogSeam":
        """
        Measure the epistemic seam between this agent and another fog map.

        High seam tension = asymmetric blind spots = transfer potential.
        Zero tension = same fog = pure arbitrage territory.

        This is the epistemic inverse of the Sophia gradient: where to
        route next based on what agents *don't* know, not what they do.

        Args:
            other:        A FogMap from another agent (call agent.fog() to build one).
            embedding_fn: Optional. Passed to atlas() when building this agent's fog.

        Returns:
            A FogSeam with tension score and transfer analysis.

        Example::

            fog_a = agent_a.fog()
            fog_b = agent_b.fog()
            seam  = agent_a.fog_seam(fog_b)
            print(seam.summary())
            # FogSeam(braid↔solver) tension=0.72 — high-potential seam
        """
        from .fog import measure
        my_fog = self.fog(embedding_fn=embedding_fn)
        return measure(my_fog, other)

    # ─── Sophia ──────────────────────────────────────────────────────────

    def sophia(self, embedding_fn=None) -> "SophiaReading":
        """
        Scan the current mesh topology for Sophia signal.

        Returns where the mesh is generating collective intelligence —
        regions of high curvature with sufficient coverage where the same
        topic looks different from different coordinate systems, yet the
        mesh holds.

        Sophia lives in the seams, not the nodes. It is the signal of
        what the mesh knows that no single agent knows — emergent from
        translation, not from any individual chart.

        Args:
            embedding_fn: Optional. Any function (str) -> list[float].
                          Passed to atlas(). With embeddings: semantic
                          matching across vocabulary gaps. Without: trigram
                          similarity (zero deps, default).

        Returns:
            A SophiaReading with global score, dense regions, gradient
            suggestions, and mesh-level interpretation.

        Example::

            reading = agent.sophia()
            print(f'Mesh score: {reading.score:.2f}')
            print(reading.interpretation)
            for region in reading.dense_regions[:3]:
                print(f'  {region.topic}: {region.density:.2f} ({region.interpretation})')
        """
        from .sophia import sophia_scan, SophiaReading
        atlas = self.atlas(embedding_fn=embedding_fn)
        return sophia_scan(atlas)

    def __repr__(self) -> str:
        caps = ", ".join(self._capabilities[:3])
        status = "joined" if self._joined else "offline"
        return f"<Agent {self._name!r} [{status}] caps=[{caps}]>"
