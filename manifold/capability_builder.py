"""Capability builder — structured, typed agent capabilities.

Instead of raw string tags, capabilities can be defined with input/output
schemas, versioned handlers, dependency declarations, and metadata. The
builder integrates with the existing ``Agent.knows()`` system while adding
structure on top.

Usage::

    from manifold.capability_builder import CapabilityBuilder, CapSpec

    builder = CapabilityBuilder(agent)

    @builder.define(
        name="solar-prediction",
        version="1.2.0",
        inputs=["region", "horizon_hours"],
        outputs=["predicted_mw", "confidence"],
        tags=["energy", "forecast"],
    )
    async def solar_predict(payload: dict) -> dict:
        region = payload["region"]
        return {"predicted_mw": 42.0, "confidence": 0.91}

    # Registers "solar-prediction" on the agent automatically
    # Other agents discover it via the existing registry

    # Invoke a capability
    result = await builder.invoke("solar-prediction", {"region": "pacific", "horizon_hours": 24})

    # List all registered capabilities
    for spec in builder.list_capabilities():
        print(f"{spec.name} v{spec.version}: {spec.description or 'no description'}")
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class CapabilityStatus(str, Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


@dataclass
class CapSpec:
    """Structured definition of a single capability."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: CapabilityStatus = CapabilityStatus.ACTIVE
    handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]] | None = None
    deprecated_by: str | None = None
    created_at: float = field(default_factory=time.time)
    invocation_count: int = 0
    last_invoked_at: float | None = None
    avg_latency_ms: float = 0.0

    @property
    def is_invocable(self) -> bool:
        return self.handler is not None and self.status == CapabilityStatus.ACTIVE

    def matches_tag(self, tag: str) -> bool:
        return tag in self.tags or tag == self.name

    def matches_any(self, query: str) -> bool:
        """Check if query matches name, tags, or description."""
        q = query.lower()
        return (
            q in self.name.lower()
            or q in self.description.lower()
            or any(q in t.lower() for t in self.tags)
        )

    def schema_summary(self) -> str:
        ins = ", ".join(self.inputs) or "none"
        outs = ", ".join(self.outputs) or "none"
        return f"{self.name} v{self.version} ({ins}) -> ({outs})"

    def __repr__(self) -> str:
        return (
            f"<CapSpec {self.name!r} v{self.version} "
            f"[{self.status.value}] invocations={self.invocation_count}>"
        )


@dataclass
class InvocationResult:
    """Result of invoking a capability."""
    cap_name: str
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_ms: float = 0.0
    invocation_id: str = ""

    def __repr__(self) -> str:
        status = "ok" if self.ok else f"error: {self.error}"
        return f"<InvocationResult {self.cap_name!r} {status} {self.elapsed_ms:.0f}ms>"


class CapabilityBuilder:
    """
    Declarative capability builder for Manifold agents.

    Wraps an ``Agent`` and provides a decorator-based API for defining
    structured capabilities with typed inputs/outputs, versioning,
    and automatic registration.
    """

    def __init__(self, agent: Any) -> None:
        self._agent = agent
        self._caps: dict[str, CapSpec] = {}

    def define(
        self,
        name: str,
        version: str = "1.0.0",
        description: str = "",
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        tags: list[str] | None = None,
        status: CapabilityStatus = CapabilityStatus.ACTIVE,
    ) -> Callable:
        """
        Decorator to define a capability with a handler function.

        The decorated function must be async and accept a single dict
        argument, returning a dict.

        Usage::

            @builder.define(
                name="sentiment-analysis",
                inputs=["text", "language"],
                outputs=["sentiment", "confidence"],
                tags=["nlp", "analysis"],
            )
            async def analyze_sentiment(payload: dict) -> dict:
                ...
        """
        def decorator(fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> Callable:
            spec = CapSpec(
                name=name,
                version=version,
                description=description,
                inputs=inputs or [],
                outputs=outputs or [],
                tags=tags or [],
                status=status,
                handler=fn,
            )
            self._register(spec)
            return fn
        return decorator

    def register(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
        version: str = "1.0.0",
        description: str = "",
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> CapSpec:
        """
        Imperatively register a capability (non-decorator style).

        Returns the CapSpec for further customization.
        """
        spec = CapSpec(
            name=name,
            version=version,
            description=description,
            inputs=inputs or [],
            outputs=outputs or [],
            tags=tags or [],
            handler=handler,
        )
        self._register(spec)
        return spec

    def _register(self, spec: CapSpec) -> None:
        """Register a spec and update the agent's knows() list."""
        # If replacing an existing capability, inherit invocation stats
        if spec.name in self._caps:
            old = self._caps[spec.name]
            spec.invocation_count = old.invocation_count
            spec.avg_latency_ms = old.avg_latency_ms
            spec.created_at = old.created_at

        self._caps[spec.name] = spec

        # Sync with agent's string-based capability list
        if hasattr(self._agent, "_capabilities"):
            if spec.name not in self._agent._capabilities:
                self._agent._capabilities.append(spec.name)
        if hasattr(self._agent, "knows"):
            # knows() deduplicates, so this is safe
            try:
                self._agent.knows([spec.name])
            except Exception:
                pass

    async def invoke(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        validate_inputs: bool = True,
    ) -> InvocationResult:
        """
        Invoke a registered capability by name.

        Args:
            name:            Capability name.
            payload:         Input data.
            validate_inputs: Check that declared inputs are present in payload.

        Returns:
            InvocationResult with output or error.
        """
        payload = payload or {}
        invocation_id = f"inv-{uuid.uuid4().hex[:12]}"

        if name not in self._caps:
            return InvocationResult(
                cap_name=name,
                ok=False,
                error=f"Unknown capability: {name!r}",
                invocation_id=invocation_id,
            )

        spec = self._caps[name]

        if not spec.is_invocable:
            return InvocationResult(
                cap_name=name,
                ok=False,
                error=f"Capability {name!r} is not invocable (status={spec.status.value})",
                invocation_id=invocation_id,
            )

        # Input validation
        if validate_inputs and spec.inputs:
            missing = [k for k in spec.inputs if k not in payload]
            if missing:
                return InvocationResult(
                    cap_name=name,
                    ok=False,
                    error=f"Missing required inputs: {', '.join(missing)}",
                    invocation_id=invocation_id,
                )

        t0 = time.monotonic()
        try:
            output = await spec.handler(payload)
            elapsed = (time.monotonic() - t0) * 1000

            # Update stats
            spec.invocation_count += 1
            spec.last_invoked_at = time.time()
            total_time = spec.avg_latency_ms * (spec.invocation_count - 1) + elapsed
            spec.avg_latency_ms = total_time / spec.invocation_count

            return InvocationResult(
                cap_name=name,
                ok=True,
                output=output or {},
                elapsed_ms=elapsed,
                invocation_id=invocation_id,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return InvocationResult(
                cap_name=name,
                ok=False,
                error=str(exc),
                elapsed_ms=elapsed,
                invocation_id=invocation_id,
            )

    def deprecate(self, name: str, replaced_by: str | None = None) -> None:
        """Mark a capability as deprecated."""
        if name in self._caps:
            self._caps[name].status = CapabilityStatus.DEPRECATED
            self._caps[name].deprecated_by = replaced_by

    def disable(self, name: str) -> None:
        """Disable a capability without removing it."""
        if name in self._caps:
            self._caps[name].status = CapabilityStatus.DISABLED

    def enable(self, name: str) -> None:
        """Re-enable a previously disabled capability."""
        if name in self._caps:
            self._caps[name].status = CapabilityStatus.ACTIVE

    def get(self, name: str) -> CapSpec | None:
        """Look up a capability by name."""
        return self._caps.get(name)

    def list_capabilities(
        self,
        status: CapabilityStatus | None = None,
        tag: str | None = None,
    ) -> list[CapSpec]:
        """List capabilities, optionally filtered by status or tag."""
        result = list(self._caps.values())
        if status is not None:
            result = [s for s in result if s.status == status]
        if tag is not None:
            result = [s for s in result if s.matches_tag(tag)]
        return result

    def search(self, query: str) -> list[CapSpec]:
        """Search capabilities by name, tags, or description."""
        return [s for s in self._caps.values() if s.matches_any(query)]

    def stats(self) -> dict[str, Any]:
        """Aggregate capability statistics."""
        total = len(self._caps)
        active = sum(1 for s in self._caps.values() if s.status == CapabilityStatus.ACTIVE)
        total_invocations = sum(s.invocation_count for s in self._caps.values())
        avg_latency = (
            sum(s.avg_latency_ms for s in self._caps.values()) / total
            if total else 0.0
        )
        return {
            "total_capabilities": total,
            "active": active,
            "deprecated": total - active,
            "total_invocations": total_invocations,
            "avg_latency_ms": round(avg_latency, 1),
        }

    def catalog(self) -> dict[str, Any]:
        """Export full capability catalog (for registry sync / discovery)."""
        return {
            name: {
                "version": spec.version,
                "description": spec.description,
                "inputs": spec.inputs,
                "outputs": spec.outputs,
                "tags": spec.tags,
                "status": spec.status.value,
                "invocations": spec.invocation_count,
                "avg_latency_ms": round(spec.avg_latency_ms, 1),
            }
            for name, spec in self._caps.items()
        }
