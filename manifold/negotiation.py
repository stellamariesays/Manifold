"""Capability negotiation — agents handle partial capability matches."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from manifold.protocol import TaskRequest


class NegotiationState(str, Enum):
    PENDING = "pending"
    COUNTER_OFFER = "counter_offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CLARIFICATION_NEEDED = "clarification_needed"


@dataclass
class NegotiationMessage:
    from_agent: str
    to_agent: str
    state: NegotiationState = NegotiationState.PENDING
    proposed_capability: str = ""
    alternative_capabilities: list[str] = field(default_factory=list)
    clarification_question: str | None = None
    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_request_id: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> NegotiationMessage:
        if "state" in data and isinstance(data["state"], str):
            data["state"] = NegotiationState(data["state"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class NegotiationResponse:
    accepted: bool
    state: NegotiationState
    message: NegotiationMessage | None = None
    matched_capability: str | None = None
    reason: str | None = None


class Negotiator:
    """Handles capability negotiation for an agent."""

    def __init__(self, agent_id: str, capabilities: list[str] | None = None):
        self.agent_id = agent_id
        self.capabilities: list[str] = capabilities or []
        self._history: list[NegotiationMessage] = []

    def propose_alternative(
        self,
        to_agent: str,
        original_capability: str,
        alternatives: list[str],
        request_id: str | None = None,
    ) -> NegotiationMessage:
        msg = NegotiationMessage(
            from_agent=self.agent_id,
            to_agent=to_agent,
            state=NegotiationState.COUNTER_OFFER,
            proposed_capability=original_capability,
            alternative_capabilities=alternatives,
            original_request_id=request_id,
        )
        self._history.append(msg)
        return msg

    def request_clarification(
        self,
        to_agent: str,
        capability: str,
        question: str,
        request_id: str | None = None,
    ) -> NegotiationMessage:
        msg = NegotiationMessage(
            from_agent=self.agent_id,
            to_agent=to_agent,
            state=NegotiationState.CLARIFICATION_NEEDED,
            proposed_capability=capability,
            clarification_question=question,
            original_request_id=request_id,
        )
        self._history.append(msg)
        return msg

    def accept(self, to_agent: str, capability: str, request_id: str | None = None) -> NegotiationMessage:
        msg = NegotiationMessage(
            from_agent=self.agent_id,
            to_agent=to_agent,
            state=NegotiationState.ACCEPTED,
            proposed_capability=capability,
            original_request_id=request_id,
        )
        self._history.append(msg)
        return msg

    def reject(self, to_agent: str, capability: str, reason: str = "", request_id: str | None = None) -> NegotiationMessage:
        msg = NegotiationMessage(
            from_agent=self.agent_id,
            to_agent=to_agent,
            state=NegotiationState.REJECTED,
            proposed_capability=capability,
            clarification_question=reason,
            original_request_id=request_id,
        )
        self._history.append(msg)
        return msg

    def negotiate(self, request: TaskRequest) -> NegotiationResponse:
        """Evaluate a task request against known capabilities."""
        requested = request.capability or request.command

        # Exact match
        if requested in self.capabilities:
            return NegotiationResponse(
                accepted=True,
                state=NegotiationState.ACCEPTED,
                matched_capability=requested,
            )

        # Partial / prefix match
        partials = [c for c in self.capabilities if requested in c or c in requested]
        if partials:
            msg = self.propose_alternative(
                to_agent=request.caller,
                original_capability=requested,
                alternatives=partials,
                request_id=request.id,
            )
            return NegotiationResponse(
                accepted=False,
                state=NegotiationState.COUNTER_OFFER,
                message=msg,
                reason=f"Partial match. Alternatives: {partials}",
            )

        # No match — reject
        msg = self.reject(
            to_agent=request.caller,
            capability=requested,
            reason="No matching capability",
            request_id=request.id,
        )
        return NegotiationResponse(
            accepted=False,
            state=NegotiationState.REJECTED,
            message=msg,
            reason="No matching capability",
        )

    @property
    def history(self) -> list[NegotiationMessage]:
        return list(self._history)
