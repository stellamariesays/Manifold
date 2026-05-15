"""Tests for capability negotiation."""

from manifold.negotiation import (
    NegotiationState,
    NegotiationMessage,
    NegotiationResponse,
    Negotiator,
)
from manifold.protocol import TaskRequest


def test_negotiation_state_enum():
    assert NegotiationState.PENDING.value == "pending"
    assert NegotiationState.COUNTER_OFFER.value == "counter_offer"
    assert NegotiationState.ACCEPTED.value == "accepted"
    assert NegotiationState.REJECTED.value == "rejected"
    assert NegotiationState.CLARIFICATION_NEEDED.value == "clarification_needed"


def test_negotiation_message_roundtrip():
    msg = NegotiationMessage(
        from_agent="a@hub",
        to_agent="b@hub",
        state=NegotiationState.COUNTER_OFFER,
        proposed_capability="trading",
        alternative_capabilities=["market-analysis", "sentiment"],
        thread_id="t-1",
    )
    d = msg.to_dict()
    assert d["state"] == "counter_offer"
    msg2 = NegotiationMessage.from_dict(d)
    assert msg2.state == NegotiationState.COUNTER_OFFER
    assert msg2.alternative_capabilities == ["market-analysis", "sentiment"]


def test_negotiator_exact_match():
    n = Negotiator("agent@hub", ["trading", "analysis", "risk-scoring"])
    req = TaskRequest(target="agent@hub", command="trade", capability="trading", caller="caller@hub")
    resp = n.negotiate(req)
    assert resp.accepted
    assert resp.state == NegotiationState.ACCEPTED
    assert resp.matched_capability == "trading"


def test_negotiator_partial_match():
    n = Negotiator("agent@hub", ["market-analysis", "risk-scoring"])
    req = TaskRequest(target="agent@hub", command="analyze", capability="analysis", caller="caller@hub")
    resp = n.negotiate(req)
    assert not resp.accepted
    assert resp.state == NegotiationState.COUNTER_OFFER
    assert "market-analysis" in resp.message.alternative_capabilities


def test_negotiator_no_match():
    n = Negotiator("agent@hub", ["trading"])
    req = TaskRequest(target="agent@hub", command="cook", capability="cooking", caller="caller@hub")
    resp = n.negotiate(req)
    assert not resp.accepted
    assert resp.state == NegotiationState.REJECTED


def test_propose_alternative():
    n = Negotiator("agent@hub", ["trading"])
    msg = n.propose_alternative("caller@hub", "cooking", ["trading", "market-analysis"])
    assert msg.state == NegotiationState.COUNTER_OFFER
    assert len(n.history) == 1


def test_request_clarification():
    n = Negotiator("agent@hub", [])
    msg = n.request_clarification("caller@hub", "trading", "Which market?")
    assert msg.state == NegotiationState.CLARIFICATION_NEEDED
    assert msg.clarification_question == "Which market?"


def test_accept_and_reject():
    n = Negotiator("agent@hub", [])
    n.accept("caller@hub", "trading")
    n.reject("caller@hub", "cooking", reason="No kitchen")
    assert len(n.history) == 2
    assert n.history[0].state == NegotiationState.ACCEPTED
    assert n.history[1].state == NegotiationState.REJECTED


if __name__ == "__main__":
    test_negotiation_state_enum()
    test_negotiation_message_roundtrip()
    test_negotiator_exact_match()
    test_negotiator_partial_match()
    test_negotiator_no_match()
    test_propose_alternative()
    test_request_clarification()
    test_accept_and_reject()
    print("\n🟢 All negotiation tests passed")
