"""Capability exchange — structured capability marketplace for the mesh.

The exchange is the bridge between the capability builder (typed capability
definitions) and the mesh's audience routing + dispatch infrastructure.
It enables agents to:

1. **Publish** structured capability catalogs to the mesh
2. **Discover** capabilities across agents via search and browsing
3. **Route** tasks to the best-fit agent based on capability metadata,
   trust history, and audience signals
4. **Compose** multi-step workflows that span agents

The exchange integrates with existing Manifold primitives:
- ``Agent.audience()`` for signal-based routing
- ``TaskDispatcher`` for retry/fallback dispatch
- ``TrustLedger`` for trust-weighted selection
- ``CapabilityBuilder`` for structured capability definitions

Usage::

    from manifold.exchange import CapabilityExchange

    exchange = CapabilityExchange(agent)

    # Publish local capabilities to the mesh
    exchange.publish_all()

    # Discover what the mesh can do
    catalog = exchange.browse(tag="analysis")

    # Route a task to the best-fit agent
    result = await exchange.route_and_dispatch(
        "solar-prediction",
        payload={"region": "pacific"},
    )
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import Agent
    from .capability_builder import CapSpec, CapabilityBuilder
    from .dispatch import TaskDispatcher, DispatchResult


class ExchangeStatus(str, Enum):
    IDLE = "idle"
    PUBLISHING = "publishing"
    ROUTING = "routing"
    DISPATCHING = "dispatching"


@dataclass
class CatalogEntry:
    """A capability offered by a specific agent on the mesh."""
    agent_name: str
    cap_name: str
    version: str = "1.0.0"
    description: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = "active"
    invocations: int = 0
    avg_latency_ms: float = 0.0
    trust_score: float = 0.0
    updated_at: float = field(default_factory=time.time)

    @property
    def is_available(self) -> bool:
        return self.status == "active"

    def matches(self, query: str) -> bool:
        """Check if query matches name, tags, description, or inputs."""
        q = query.lower()
        return (
            q in self.cap_name.lower()
            or q in self.description.lower()
            or any(q in t.lower() for t in self.tags)
            or any(q in i.lower() for i in self.inputs)
        )

    def fitness(self) -> float:
        """Composite fitness score combining trust and performance."""
        latency_penalty = min(self.avg_latency_ms / 1000.0, 0.5)
        trust_bonus = self.trust_score * 0.5
        return trust_bonus + (0.5 - latency_penalty)

    def __repr__(self) -> str:
        return (
            f"<CatalogEntry {self.agent_name}/{self.cap_name} "
            f"v{self.version} trust={self.trust_score:.2f}>"
        )


@dataclass
class ExchangeStats:
    """Summary statistics for the exchange."""
    total_capabilities: int = 0
    total_agents: int = 0
    local_capabilities: int = 0
    remote_capabilities: int = 0
    dispatches: int = 0
    success_rate: float = 0.0

    def __repr__(self) -> str:
        return (
            f"<ExchangeStats caps={self.total_capabilities} "
            f"agents={self.total_agents} "
            f"success={self.success_rate:.1%}>"
        )


class CapabilityExchange:
    """
    Structured capability marketplace integrated with the mesh.

    The exchange sits on top of an Agent and optionally a CapabilityBuilder
    and TaskDispatcher, providing a unified API for publishing, discovering,
    and routing tasks based on structured capability metadata.

    Args:
        agent:           The local agent.
        builder:         Optional CapabilityBuilder for structured local caps.
        dispatcher:      Optional TaskDispatcher for mesh dispatch.
    """

    EXCHANGE_TOPIC = "_manifold.exchange"

    def __init__(
        self,
        agent: Agent,
        builder: "CapabilityBuilder | None" = None,
        dispatcher: "TaskDispatcher | None" = None,
    ) -> None:
        self._agent = agent
        self._builder = builder
        self._dispatcher = dispatcher
        self._catalog: dict[str, dict[str, CatalogEntry]] = {}  # agent -> {cap_name -> entry}
        self._status = ExchangeStatus.IDLE
        self._dispatch_count = 0
        self._dispatch_successes = 0

    @property
    def status(self) -> ExchangeStatus:
        return self._status

    # ─── Publishing ───────────────────────────────────────────────────

    def publish_all(self) -> int:
        """
        Publish all local capabilities from the builder to the mesh catalog.

        Returns the number of capabilities published.
        """
        if self._builder is None:
            return 0

        self._status = ExchangeStatus.PUBLISHING
        my_name = self._agent.name
        local_catalog: dict[str, CatalogEntry] = {}

        for spec in self._builder.list_capabilities():
            trust = self._get_trust(my_name, spec.name)
            entry = CatalogEntry(
                agent_name=my_name,
                cap_name=spec.name,
                version=spec.version,
                description=spec.description,
                inputs=spec.inputs,
                outputs=spec.outputs,
                tags=spec.tags,
                status=spec.status.value,
                invocations=spec.invocation_count,
                avg_latency_ms=spec.avg_latency_ms,
                trust_score=trust,
            )
            local_catalog[spec.name] = entry

        if local_catalog:
            self._catalog[my_name] = local_catalog
        elif my_name in self._catalog:
            del self._catalog[my_name]

        self._status = ExchangeStatus.IDLE
        return len(local_catalog)

    def publish_capability(self, spec: "CapSpec") -> None:
        """Publish a single capability to the catalog."""
        my_name = self._agent.name
        if my_name not in self._catalog:
            self._catalog[my_name] = {}

        trust = self._get_trust(my_name, spec.name)
        self._catalog[my_name][spec.name] = CatalogEntry(
            agent_name=my_name,
            cap_name=spec.name,
            version=spec.version,
            description=spec.description,
            inputs=spec.inputs,
            outputs=spec.outputs,
            tags=spec.tags,
            status=spec.status.value,
            invocations=spec.invocation_count,
            avg_latency_ms=spec.avg_latency_ms,
            trust_score=trust,
            updated_at=time.time(),
        )

    def update_from_announcement(self, announcement: dict[str, Any]) -> None:
        """
        Update the catalog from a mesh registry announcement.

        Call this when an agent announces its capabilities on the mesh.
        """
        agent_name = announcement.get("name", "")
        capabilities = announcement.get("capabilities", [])

        if not agent_name:
            return

        # Skip self — managed by publish_all
        if agent_name == self._agent.name:
            return

        if agent_name not in self._catalog:
            self._catalog[agent_name] = {}

        # Update existing entries and add new ones
        existing = self._catalog[agent_name]
        announced_set = set(capabilities)

        for cap_name in capabilities:
            trust = self._get_trust(agent_name, cap_name)
            if cap_name in existing:
                existing[cap_name].trust_score = trust
                existing[cap_name].updated_at = time.time()
            else:
                existing[cap_name] = CatalogEntry(
                    agent_name=agent_name,
                    cap_name=cap_name,
                    trust_score=trust,
                )

        # Mark capabilities not in announcement as potentially gone
        for cap_name in list(existing.keys()):
            if cap_name not in announced_set:
                existing[cap_name].status = "unknown"

    # ─── Discovery ────────────────────────────────────────────────────

    def browse(
        self,
        tag: str | None = None,
        agent_name: str | None = None,
        status: str | None = "active",
    ) -> list[CatalogEntry]:
        """
        Browse the capability catalog with optional filters.

        Args:
            tag:         Filter by tag match.
            agent_name:  Filter to a specific agent's capabilities.
            status:      Filter by status (default: "active").

        Returns:
            List of matching CatalogEntry objects.
        """
        results: list[CatalogEntry] = []

        for a_name, caps in self._catalog.items():
            if agent_name and a_name != agent_name:
                continue
            for entry in caps.values():
                if status and entry.status != status:
                    continue
                if tag and not any(tag.lower() in t.lower() for t in entry.tags):
                    continue
                results.append(entry)

        return results

    def search(self, query: str) -> list[CatalogEntry]:
        """
        Search capabilities by keyword across all agents.

        Returns entries sorted by fitness score (trust + performance).
        """
        results = [
            entry
            for agent_caps in self._catalog.values()
            for entry in agent_caps.values()
            if entry.is_available and entry.matches(query)
        ]
        results.sort(key=lambda e: e.fitness(), reverse=True)
        return results

    def find_best(
        self,
        capability: str,
        min_trust: float = 0.0,
        exclude_self: bool = True,
    ) -> CatalogEntry | None:
        """
        Find the best agent for a specific capability.

        Uses trust score, latency, and invocation count to rank.
        """
        candidates = []
        for agent_caps in self._catalog.values():
            for entry in agent_caps.values():
                if entry.cap_name != capability:
                    continue
                if not entry.is_available:
                    continue
                if exclude_self and entry.agent_name == self._agent.name:
                    continue
                if entry.trust_score < min_trust:
                    continue
                candidates.append(entry)

        if not candidates:
            return None

        candidates.sort(key=lambda e: e.fitness(), reverse=True)
        return candidates[0]

    def get_agents_for_capability(self, capability: str) -> list[CatalogEntry]:
        """Get all agents that offer a specific capability, ranked by fitness."""
        entries = []
        for agent_caps in self._catalog.values():
            for entry in agent_caps.values():
                if entry.cap_name == capability and entry.is_available:
                    entries.append(entry)
        entries.sort(key=lambda e: e.fitness(), reverse=True)
        return entries

    # ─── Routing & Dispatch ──────────────────────────────────────────

    async def route_and_dispatch(
        self,
        capability: str,
        payload: dict[str, Any] | None = None,
        min_trust: float = 0.0,
        max_retries: int = 3,
        weights: dict[str, float] | None = None,
    ) -> "DispatchResult | dict[str, Any]":
        """
        Route a task to the best agent for a capability and dispatch it.

        First checks the local builder (can invoke directly), then falls
        back to mesh dispatch via the dispatcher.

        Args:
            capability:  What capability to route for.
            payload:     Task input data.
            min_trust:   Minimum trust score for remote agents.
            max_retries: Fallback attempts for remote dispatch.
            weights:     Custom audience routing weights.

        Returns:
            DispatchResult (if dispatcher available) or InvocationResult
            (if invoked locally).
        """
        self._status = ExchangeStatus.ROUTING
        payload = payload or {}

        # 1. Check local builder first
        if self._builder:
            local_cap = self._builder.get(capability)
            if local_cap and local_cap.is_invocable:
                result = await self._builder.invoke(capability, payload)
                self._status = ExchangeStatus.IDLE
                return result

        # 2. Use audience routing + dispatch for remote
        if self._dispatcher:
            self._status = ExchangeStatus.DISPATCHING
            result = await self._dispatcher.dispatch(
                topic=capability,
                payload=payload,
                weights=weights,
            )
            self._dispatch_count += 1
            if result.ok:
                self._dispatch_successes += 1
            self._status = ExchangeStatus.IDLE
            return result

        # 3. Last resort: find best from catalog
        best = self.find_best(capability, min_trust=min_trust)
        if best:
            return {
                "routed_to": best.agent_name,
                "capability": best.cap_name,
                "trust_score": best.trust_score,
                "fitness": best.fitness(),
                "note": "No dispatcher available — routing info only",
            }

        self._status = ExchangeStatus.IDLE
        return {"error": f"No agent found for capability: {capability!r}"}

    # ─── Statistics ───────────────────────────────────────────────────

    def stats(self) -> ExchangeStats:
        """Exchange statistics."""
        all_agents = set(self._catalog.keys())
        total_caps = sum(len(caps) for caps in self._catalog.values())
        local_caps = len(self._catalog.get(self._agent.name, {}))
        remote_caps = total_caps - local_caps

        return ExchangeStats(
            total_capabilities=total_caps,
            total_agents=len(all_agents),
            local_capabilities=local_caps,
            remote_capabilities=remote_caps,
            dispatches=self._dispatch_count,
            success_rate=(
                self._dispatch_successes / self._dispatch_count
                if self._dispatch_count else 0.0
            ),
        )

    def catalog_summary(self) -> str:
        """Human-readable summary of the full catalog."""
        lines = ["Capability Exchange Catalog:"]
        for agent_name, caps in sorted(self._catalog.items()):
            active = sum(1 for e in caps.values() if e.is_available)
            lines.append(f"  {agent_name}: {active}/{len(caps)} capabilities")
            for entry in sorted(caps.values(), key=lambda e: e.cap_name):
                status_mark = "✓" if entry.is_available else "?"
                trust_str = f" trust={entry.trust_score:.2f}" if entry.trust_score > 0 else ""
                lines.append(
                    f"    {status_mark} {entry.cap_name} v{entry.version}{trust_str}"
                )
        return "\n".join(lines)

    # ─── Internals ────────────────────────────────────────────────────

    def _get_trust(self, agent_name: str, domain: str) -> float:
        """Get trust score from the agent's ledger."""
        try:
            score = self._agent._ledger.domain_score(agent_name, domain)
            return score if score is not None else 0.0
        except Exception:
            return 0.0

    @property
    def _all_entries(self) -> list[CatalogEntry]:
        """Flat list of all catalog entries."""
        return [
            entry
            for caps in self._catalog.values()
            for entry in caps.values()
        ]
