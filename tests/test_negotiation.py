"""Tests for capability negotiation protocol."""

import asyncio
import time
import pytest
from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.negotiation import (
    Negotiator,
    Negotiator as NegotiatorModule,
    CapabilityRequest,
    Contract,
    NegotiationTerms,
    NegotiationPolicy,
    NegotiationStatus,
    RejectionReason,
)


# ── Helpers ──────────────────────────────────────────────────────────────

async def _agent_with_builder(name: str = "alice") -> tuple[Agent, CapabilityBuilder, Negotiator]:
    """Create an agent with builder and negotiator."""
    agent = Agent(name=name, transport="memory://test")
    agent.knows(["solar-prediction", "data-analysis"])
    await agent.join()

    builder = CapabilityBuilder(agent)

    @builder.define(
        name="solar-prediction",
        inputs=["region", "hours"],
        outputs=["forecast", "confidence"],
        tags=["solar", "forecast"],
    )
    async def solar_predict(payload: dict) -> dict:
        return {
            "forecast": f"{payload.get('region', 'global')}: sunny",
            "confidence": 0.91,
        }

    @builder.define(
        name="data-analysis",
        inputs=["dataset"],
        outputs=["summary", "score"],
    )
    async def analyze(payload: dict) -> dict:
        return {"summary": "analyzed", "score": 0.85}

    negotiator = Negotiator(agent, policy=NegotiationPolicy(min_trust=0.0))
    negotiator._builder = builder
    return agent, builder, negotiator


# ─── Negotiation Flow ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_self_negotiation():
    """Agent negotiating with itself accepts immediately."""
    agent, _, neg = await _agent_with_builder()
    req = CapabilityRequest(
        requester="alice",
        provider="alice",
        capability="solar-prediction",
        inputs={"region": "pacific", "hours": 24},
    )
    contract = await neg.negotiate(req)
    assert contract.status == NegotiationStatus.ACCEPTED
    print(f"✅ Self-negotiation accepted: {contract}")


@pytest.mark.asyncio
async def test_provider_evaluates_request():
    """Provider evaluates incoming request against policy."""
    agent, builder, neg = await _agent_with_builder()
    req = CapabilityRequest(
        requester="bob",
        provider="alice",
        capability="solar-prediction",
        inputs={"region": "pacific", "hours": 24},
    )
    contract = await neg.negotiate(req)
    assert contract.status == NegotiationStatus.ACCEPTED
    assert contract.accepted
    print(f"✅ Provider accepted: {contract}")


@pytest.mark.asyncio
async def test_execute_accepted_contract():
    """Execute an accepted contract invokes the capability."""
    agent, builder, neg = await _agent_with_builder()
    req = CapabilityRequest(
        requester="alice",
        provider="alice",
        capability="solar-prediction",
        inputs={"region": "pacific", "hours": 24},
    )
    contract = await neg.negotiate(req)
    assert contract.accepted

    result = await neg.execute(contract)
    assert result.status == NegotiationStatus.COMPLETED
    assert result.result["forecast"] == "pacific: sunny"
    assert result.result["confidence"] == 0.91
    assert result.score == 1.0
    print(f"✅ Executed: {result.status.value}, output={result.result}")


@pytest.mark.asyncio
async def test_requester_creates_pending():
    """Requester side creates a pending contract."""
    agent, _, neg = await _agent_with_builder()
    req = CapabilityRequest(
        requester="alice",
        provider="bob",
        capability="orbit-calculation",
        inputs={"body": "mars"},
    )
    contract = await neg.negotiate(req)
    assert contract.status == NegotiationStatus.PENDING
    print(f"✅ Requester pending: {contract}")


# ─── Rejection Cases ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_blacklisted():
    """Blacklisted requester gets rejected."""
    agent, builder, neg = await _agent_with_builder()
    neg._policy.blacklisted_requesters = {"bob"}

    req = CapabilityRequest(
        requester="bob",
        provider="alice",
        capability="solar-prediction",
        inputs={"region": "pacific", "hours": 24},
    )
    contract = await neg.negotiate(req)
    assert contract.status == NegotiationStatus.REJECTED
    assert contract.rejection_reason == RejectionReason.POLICY_DENIED
    print(f"✅ Blacklisted rejected: {contract.rejection_reason}")


@pytest.mark.asyncio
async def test_reject_unknown_capability():
    """Request for capability agent doesn't have is rejected."""
    agent, builder, neg = await _agent_with_builder()
    req = CapabilityRequest(
        requester="bob",
        provider="alice",
        capability="quantum-teleportation",
        inputs={},
    )
    contract = await neg.negotiate(req)
    assert contract.status == NegotiationStatus.REJECTED
    assert contract.rejection_reason == RejectionReason.CAPABILITY_UNAVAILABLE
    print(f"✅ Unknown cap rejected: {contract.rejection_reason}")


@pytest.mark.asyncio
async def test_reject_missing_inputs():
    """Request missing required inputs is rejected."""
    agent, builder, neg = await _agent_with_builder()
    neg._policy.require_all_inputs = True

    req = CapabilityRequest(
        requester="bob",
        provider="alice",
        capability="solar-prediction",
        inputs={"region": "pacific"},  # missing "hours"
    )
    contract = await neg.negotiate(req)
    assert contract.status == NegotiationStatus.REJECTED
    assert contract.rejection_reason == RejectionReason.MISSING_INPUTS
    print(f"✅ Missing inputs rejected: {contract.rejection_reason}")


@pytest.mark.asyncio
async def test_reject_capacity_full():
    """Request rejected when at capacity."""
    agent, builder, neg = await _agent_with_builder()
    neg._policy.max_concurrent = 0

    req = CapabilityRequest(
        requester="bob",
        provider="alice",
        capability="solar-prediction",
        inputs={"region": "pacific", "hours": 24},
    )
    contract = await neg.negotiate(req)
    assert contract.status == NegotiationStatus.REJECTED
    assert contract.rejection_reason == RejectionReason.CAPACITY_FULL
    print(f"✅ Capacity full rejected")


@pytest.mark.asyncio
async def test_reject_expired_request():
    """Expired request returns expired status."""
    agent, _, neg = await _agent_with_builder()
    req = CapabilityRequest(
        requester="bob",
        provider="alice",
        capability="solar-prediction",
        inputs={"region": "pacific"},
        deadline_ms=0,  # instant expiry
    )
    # Force created_at to past
    req.created_at = time.time() - 10
    contract = await neg.negotiate(req)
    assert contract.status == NegotiationStatus.EXPIRED
    print(f"✅ Expired request: {contract.status}")


# ─── Contract Properties ──────────────────────────────────────────────

def test_contract_accepted_property():
    """Contract.accepted reflects correct states."""
    req = CapabilityRequest(requester="a", provider="b", capability="x")
    for status in [NegotiationStatus.ACCEPTED, NegotiationStatus.EXECUTING,
                    NegotiationStatus.COMPLETED]:
        c = Contract(request=req, status=status)
        assert c.accepted

    for status in [NegotiationStatus.PENDING, NegotiationStatus.REJECTED,
                    NegotiationStatus.FAILED, NegotiationStatus.EXPIRED]:
        c = Contract(request=req, status=status)
        assert not c.accepted


def test_request_repr():
    """CapabilityRequest has readable repr."""
    req = CapabilityRequest(requester="alice", provider="bob", capability="solar")
    assert "alice" in repr(req) and "bob" in repr(req)


# ─── Stats ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_empty():
    """Stats on fresh negotiator."""
    agent, _, neg = await _agent_with_builder()
    stats = neg.stats()
    assert stats["total_completed"] == 0
    assert stats["success_rate"] == 0.0
    print(f"✅ Empty stats: {stats}")


@pytest.mark.asyncio
async def test_stats_after_execution():
    """Stats reflect completed executions."""
    agent, _, neg = await _agent_with_builder()

    for i in range(3):
        req = CapabilityRequest(
            requester="alice", provider="alice",
            capability="solar-prediction",
            inputs={"region": f"r{i}", "hours": 24},
        )
        contract = await neg.negotiate(req)
        await neg.execute(contract)

    stats = neg.stats()
    assert stats["total_completed"] == 3
    assert stats["successes"] == 3
    assert stats["success_rate"] == 1.0
    print(f"✅ After 3 executions: {stats}")


@pytest.mark.asyncio
async def test_recent_contracts():
    """recent_contracts returns latest contracts."""
    agent, _, neg = await _agent_with_builder()
    for i in range(5):
        req = CapabilityRequest(
            requester="alice", provider="alice",
            capability="solar-prediction",
            inputs={"region": f"r{i}", "hours": 24},
        )
        contract = await neg.negotiate(req)
        await neg.execute(contract)

    recent = neg.recent_contracts(limit=3)
    assert len(recent) == 3
    print(f"✅ Recent contracts: {len(recent)}")


@pytest.mark.asyncio
async def test_contracts_by_requester():
    """contracts_by_requester filters correctly."""
    agent, _, neg = await _agent_with_builder()
    req = CapabilityRequest(
        requester="alice", provider="alice",
        capability="solar-prediction",
        inputs={"region": "pacific", "hours": 24},
    )
    contract = await neg.negotiate(req)
    await neg.execute(contract)

    alice_contracts = neg.contracts_by_requester("alice")
    assert len(alice_contracts) == 1
    bob_contracts = neg.contracts_by_requester("bob")
    assert len(bob_contracts) == 0
    print(f"✅ By requester: alice={len(alice_contracts)}, bob={len(bob_contracts)}")


@pytest.mark.asyncio
async def test_summary():
    """summary produces readable output."""
    agent, _, neg = await _agent_with_builder()
    summary = neg.summary()
    assert "alice" in summary
    print(f"✅ Summary:\n{summary}")


# ─── Custom Executor ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_custom_executor():
    """Negotiator with custom executor invokes it."""
    agent = Agent(name="custom", transport="memory://test")
    await agent.join()
    agent.knows(["custom-cap"])

    async def my_executor(agent_name, cap, payload):
        return {"custom": True, "echo": payload}

    neg = Negotiator(agent, executor=my_executor)
    neg._policy.require_known_capability = True

    req = CapabilityRequest(
        requester="alice", provider="custom",
        capability="custom-cap",
        inputs={"key": "value"},
    )
    contract = await neg.negotiate(req)
    assert contract.accepted

    result = await neg.execute(contract)
    assert result.status == NegotiationStatus.COMPLETED
    assert result.result["custom"] is True
    assert result.result["echo"]["key"] == "value"
    print(f"✅ Custom executor: {result.result}")


# ─── NegotiationPolicy ────────────────────────────────────────────────

def test_policy_defaults():
    """Default policy has sensible values."""
    p = NegotiationPolicy()
    assert p.min_trust == 0.0
    assert p.max_concurrent == 10
    assert p.require_all_inputs is True
    assert p.require_known_capability is True
    print("✅ Policy defaults sensible")



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
