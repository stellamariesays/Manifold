"""Capability negotiation protocol — agents agree on terms before executing.

When agents want to collaborate, they need to negotiate: what inputs are
required, what outputs are expected, what trust level is needed, and how
long the task should take. The negotiation protocol formalizes this:

1. **Request**: Agent A asks Agent B to perform a capability
2. **Evaluation**: Agent B checks if it can fulfill the request
3. **Terms**: Both agents agree on timeout, input schema, trust requirements
4. **Contract**: A binding agreement is created with a deadline
5. **Execution**: The capability is invoked with the agreed terms
6. **Settlement**: Results are validated, trust is updated

This sits between the capability exchange (discovery) and the dispatch
layer (delivery), adding the negotiation layer that makes multi-agent
collaboration reliable and trust-aware.

Usage::

    from manifold.negotiation import Negotiator, CapabilityRequest

    negotiator = Negotiator(agent)

    # Request a capability from another agent
    request = CapabilityRequest(
        requester="alice",
        provider="bob",
        capability="orbit-calculation",
        inputs={"body": "mars", "epoch": "2026-05-16"},
        deadline_ms=5000,
    )

    contract = await negotiator.negotiate(request)
    if contract.accepted:
        result = await negotiator.execute(contract)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class NegotiationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTER_OFFERED = "counter_offered"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class RejectionReason(str, Enum):
    INSUFFICIENT_TRUST = "insufficient_trust"
    MISSING_INPUTS = "missing_inputs"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CAPACITY_FULL = "capacity_full"
    DEADLINE_TOO_TIGHT = "deadline_too_tight"
    POLICY_DENIED = "policy_denied"
    UNKNOWN = "unknown"


@dataclass
class CapabilityRequest:
    """A request for a specific capability from a specific agent."""
    requester: str
    provider: str
    capability: str
    inputs: dict[str, Any] = field(default_factory=dict)
    deadline_ms: float = 30_000
    priority: str = "normal"
    min_trust: float = 0.0
    required_outputs: list[str] = field(default_factory=list)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) * 1000 > self.deadline_ms

    def __repr__(self) -> str:
        return (
            f"<CapabilityRequest {self.request_id} "
            f"{self.requester}→{self.provider} "
            f"{self.capability!r}>"
        )


@dataclass
class NegotiationTerms:
    """Agreed terms for capability execution."""
    timeout_ms: float = 30_000
    max_retries: int = 1
    trust_requirement: float = 0.0
    input_schema: dict[str, str] = field(default_factory=dict)
    output_guarantees: list[str] = field(default_factory=list)
    penalty_on_failure: float = 0.0
    reward_on_success: float = 1.0


@dataclass
class Contract:
    """A binding agreement for capability execution."""
    contract_id: str = field(default_factory=lambda: f"ctr-{uuid.uuid4().hex[:10]}")
    request: CapabilityRequest | None = None
    terms: NegotiationTerms = field(default_factory=NegotiationTerms)
    status: NegotiationStatus = NegotiationStatus.PENDING
    rejection_reason: RejectionReason | None = None
    counter_offer: "Contract | None" = None
    created_at: float = field(default_factory=time.time)
    accepted_at: float | None = None
    executed_at: float | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    score: float | None = None

    @property
    def accepted(self) -> bool:
        return self.status in (NegotiationStatus.ACCEPTED, NegotiationStatus.EXECUTING,
                               NegotiationStatus.COMPLETED)

    @property
    def elapsed_ms(self) -> float:
        if self.executed_at and self.accepted_at:
            return (self.executed_at - self.accepted_at) * 1000
        return 0.0

    def __repr__(self) -> str:
        status = self.status.value
        rid = self.request.request_id if self.request else "none"
        return f"<Contract {self.contract_id} req={rid} [{status}]>"


@dataclass
class NegotiationPolicy:
    """Policy rules for accepting/rejecting requests."""
    min_trust: float = 0.0
    max_concurrent: int = 10
    blacklisted_requesters: set[str] = field(default_factory=set)
    whitelisted_capabilities: set[str] = field(default_factory=set)  # empty = all
    max_deadline_ms: float = 300_000
    require_all_inputs: bool = True
    require_known_capability: bool = True


class Negotiator:
    """
    Handles capability negotiation for an agent.

    Manages incoming requests, evaluates them against policy and
    trust, creates contracts, and executes agreed work.

    Args:
        agent:          The agent this negotiator acts for.
        policy:         Acceptance policy. Uses defaults if not provided.
        executor:       Optional custom executor (agent, cap, payload) -> result.
    """

    def __init__(
        self,
        agent: Any,
        policy: NegotiationPolicy | None = None,
        executor: Callable[[str, str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]] | None = None,
    ) -> None:
        self._agent = agent
        self._policy = policy or NegotiationPolicy()
        self._executor = executor
        self._builder: Any = None
        self._active_contracts: dict[str, Contract] = {}
        self._completed_contracts: list[Contract] = []
        self._history_limit = 500

    @property
    def policy(self) -> NegotiationPolicy:
        return self._policy

    @property
    def active_count(self) -> int:
        return len(self._active_contracts)

    # ─── Negotiation Flow ─────────────────────────────────────────────

    async def negotiate(
        self,
        request: CapabilityRequest,
        terms: NegotiationTerms | None = None,
    ) -> Contract:
        """
        Full negotiation: evaluate → accept/reject → create contract.

        If the agent is the *provider*, this evaluates the incoming request.
        If the agent is the *requester*, this creates an outgoing request.

        For self-negotiation (agent invoking its own capability), the
        contract is accepted immediately.
        """
        if request.is_expired():
            return Contract(
                request=request,
                status=NegotiationStatus.EXPIRED,
                rejection_reason=RejectionReason.DEADLINE_TOO_TIGHT,
            )

        is_provider = request.provider == self._agent.name
        is_self = request.requester == self._agent.name and is_provider

        if is_self:
            return self._create_contract(request, terms or NegotiationTerms(),
                                          NegotiationStatus.ACCEPTED)

        if is_provider:
            return self._evaluate_request(request, terms)

        # Requester side — create a pending contract for dispatch
        contract = self._create_contract(request, terms or NegotiationTerms(),
                                          NegotiationStatus.PENDING)
        return contract

    def _evaluate_request(
        self,
        request: CapabilityRequest,
        terms: NegotiationTerms | None,
    ) -> Contract:
        """Evaluate an incoming request against policy."""
        policy = self._policy

        # Check blacklist
        if request.requester in policy.blacklisted_requesters:
            return self._reject(request, RejectionReason.POLICY_DENIED)

        # Check trust
        trust = self._get_trust(request.requester, request.capability)
        min_trust = max(policy.min_trust, request.min_trust)
        if trust < min_trust:
            return self._reject(request, RejectionReason.INSUFFICIENT_TRUST)

        # Check capability exists
        if policy.require_known_capability:
            if not self._has_capability(request.capability):
                return self._reject(request, RejectionReason.CAPABILITY_UNAVAILABLE)

        # Check inputs
        if policy.require_all_inputs and self._get_builder():
            spec = self._builder.get(request.capability)
            if spec and spec.inputs:
                missing = [i for i in spec.inputs if i not in request.inputs]
                if missing:
                    return self._reject(request, RejectionReason.MISSING_INPUTS)

        # Check capacity
        if self.active_count >= policy.max_concurrent:
            return self._reject(request, RejectionReason.CAPACITY_FULL)

        # Check deadline
        if request.deadline_ms > policy.max_deadline_ms:
            return self._reject(request, RejectionReason.DEADLINE_TOO_TIGHT)

        # Accept
        final_terms = terms or NegotiationTerms(
            timeout_ms=min(request.deadline_ms, policy.max_deadline_ms),
            trust_requirement=min_trust,
        )
        return self._create_contract(request, final_terms, NegotiationStatus.ACCEPTED)

    async def execute(self, contract: Contract) -> Contract:
        """
        Execute an accepted contract.

        Invokes the capability, records timing, updates contract status.
        """
        if not contract.accepted:
            return contract

        if contract.request is None:
            contract.status = NegotiationStatus.FAILED
            contract.error = "No request in contract"
            return contract

        contract.status = NegotiationStatus.EXECUTING
        self._active_contracts[contract.contract_id] = contract
        t0 = time.monotonic()

        try:
            result = await self._invoke_capability(
                contract.request.capability,
                contract.request.inputs,
            )
            contract.result = result
            contract.status = NegotiationStatus.COMPLETED
            contract.executed_at = time.time()
            contract.score = 1.0  # successful execution
        except Exception as exc:
            contract.status = NegotiationStatus.FAILED
            contract.error = str(exc)
            contract.score = 0.0
        finally:
            elapsed = (time.monotonic() - t0) * 1000
            self._active_contracts.pop(contract.contract_id, None)
            self._completed_contracts.append(contract)
            if len(self._completed_contracts) > self._history_limit:
                self._completed_contracts = self._completed_contracts[-self._history_limit:]

        return contract

    # ─── Query ─────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Negotiation statistics."""
        total = len(self._completed_contracts)
        completed = sum(1 for c in self._completed_contracts
                        if c.status == NegotiationStatus.COMPLETED)
        failed = sum(1 for c in self._completed_contracts
                     if c.status == NegotiationStatus.FAILED)
        avg_elapsed = 0.0
        if completed:
            avg_elapsed = sum(c.elapsed_ms for c in self._completed_contracts
                             if c.status == NegotiationStatus.COMPLETED) / completed

        return {
            "active_contracts": self.active_count,
            "total_completed": total,
            "successes": completed,
            "failures": failed,
            "success_rate": round(completed / total, 3) if total else 0.0,
            "avg_execution_ms": round(avg_elapsed, 1),
        }

    def recent_contracts(self, limit: int = 20) -> list[Contract]:
        """Get recent completed contracts."""
        return list(self._completed_contracts[-limit:])

    def contracts_by_requester(self, requester: str) -> list[Contract]:
        """Get all contracts from a specific requester."""
        return [
            c for c in self._completed_contracts
            if c.request and c.request.requester == requester
        ]

    def summary(self) -> str:
        """Human-readable negotiation summary."""
        s = self.stats()
        lines = [
            f"Negotiator for {self._agent.name}:",
            f"  Active: {s['active_contracts']}  Completed: {s['total_completed']}",
            f"  Success rate: {s['success_rate']:.1%}  Avg time: {s['avg_execution_ms']:.0f}ms",
        ]
        if self._policy.blacklisted_requesters:
            lines.append(f"  Blacklisted: {', '.join(self._policy.blacklisted_requesters)}")
        return "\n".join(lines)

    # ─── Internals ─────────────────────────────────────────────────────

    def _reject(self, request: CapabilityRequest, reason: RejectionReason) -> Contract:
        return Contract(
            request=request,
            status=NegotiationStatus.REJECTED,
            rejection_reason=reason,
        )

    def _create_contract(
        self,
        request: CapabilityRequest,
        terms: NegotiationTerms,
        status: NegotiationStatus,
    ) -> Contract:
        contract = Contract(
            request=request,
            terms=terms,
            status=status,
        )
        if status == NegotiationStatus.ACCEPTED:
            contract.accepted_at = time.time()
        return contract

    async def _invoke_capability(
        self, capability: str, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Invoke a capability — try builder first, then custom executor."""
        # Try builder
        builder = self._get_builder()
        if builder:
            spec = builder.get(capability)
            if spec and spec.is_invocable:
                result = await builder.invoke(capability, inputs)
                # InvocationResult has .ok and .output
                if hasattr(result, "ok") and result.ok:
                    return result.output
                elif hasattr(result, "output"):
                    return result.output
                return {"result": result}

        # Try custom executor
        if self._executor:
            return await self._executor(self._agent.name, capability, inputs)

        raise RuntimeError(f"Cannot invoke capability: {capability!r}")

    def _has_capability(self, capability: str) -> bool:
        """Check if agent has a capability."""
        if capability in self._agent.capabilities:
            return True
        builder = self._get_builder()
        if builder and builder.get(capability):
            return True
        return False

    def _get_trust(self, agent: str, domain: str) -> float:
        """Get trust score."""
        try:
            score = self._agent._ledger.domain_score(agent, domain)
            return score if score is not None else 0.0
        except Exception:
            return 0.0

    def _get_builder(self):
        """Get the capability builder if available."""
        if self._builder is not None:
            return self._builder
        return getattr(self._agent, "_builder", None)
