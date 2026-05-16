"""Tests for the network communication capability pack."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_network_pack


@pytest.fixture
def builder():
    agent = Agent(name="test-net-agent")
    builder = CapabilityBuilder(agent)
    load_network_pack(builder, agent)
    return builder


@pytest.fixture
def builder_no_agent():
    agent = Agent(name="test-net-solo")
    builder = CapabilityBuilder(agent)
    load_network_pack(builder, agent=None)
    return builder


# ─── net-compose ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_net_compose_basic(builder):
    result = await builder.invoke("net-compose", {
        "to": ["agent-b"],
        "subject": "status check",
        "body": {"query": "health"},
    })
    assert result.ok
    env = result.output["envelope"]
    assert env["to"] == ["agent-b"]
    assert env["subject"] == "status check"
    assert env["body"] == {"query": "health"}
    assert env["type"] == "inform"
    assert env["hops"] == 0
    assert env["priority"] == 0.5
    assert "message_id" in env
    assert "trace_id" in env
    assert "correlation_id" in env


@pytest.mark.asyncio
async def test_net_compose_with_priority(builder):
    result = await builder.invoke("net-compose", {
        "to": "agent-c",
        "subject": "urgent alert",
        "body": {"alert": "disk full"},
        "priority": 0.95,
        "type": "alert",
        "ttl_seconds": 60,
    })
    assert result.ok
    env = result.output["envelope"]
    assert env["priority"] == 0.95
    assert env["type"] == "alert"
    assert env["ttl_seconds"] == 60
    assert env["to"] == ["agent-c"]  # string auto-wrapped


@pytest.mark.asyncio
async def test_net_compose_clamps_priority(builder):
    result = await builder.invoke("net-compose", {
        "to": ["x"],
        "subject": "test",
        "body": {},
        "priority": 2.0,
    })
    assert result.ok
    assert result.output["envelope"]["priority"] == 1.0


# ─── net-relay ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_net_relay_chain(builder):
    compose = await builder.invoke("net-compose", {
        "to": ["alpha", "beta", "gamma"],
        "subject": "relay test",
        "body": {},
    })
    envelope = compose.output["envelope"]
    result = await builder.invoke("net-relay", {
        "chain": ["alpha", "beta", "gamma"],
        "envelope": envelope,
        "current_hop": 0,
    })
    assert result.ok
    assert result.output["current_agent"] == "alpha"
    assert result.output["next_hop"] == 1
    assert result.output["remaining"] == ["beta", "gamma"]
    assert not result.output["is_final"]
    assert result.output["total_hops"] == 1


@pytest.mark.asyncio
async def test_net_relay_final_hop(builder):
    compose = await builder.invoke("net-compose", {
        "to": ["alpha", "beta"],
        "subject": "relay test",
        "body": {},
    })
    envelope = compose.output["envelope"]
    result = await builder.invoke("net-relay", {
        "chain": ["alpha", "beta"],
        "envelope": envelope,
        "current_hop": 1,
    })
    assert result.ok
    assert result.output["current_agent"] == "beta"
    assert result.output["next_hop"] is None
    assert result.output["is_final"] is True
    assert result.output["remaining"] == []


@pytest.mark.asyncio
async def test_net_relay_with_envelope(builder):
    compose = await builder.invoke("net-compose", {
        "to": ["alpha", "beta"],
        "subject": "relay test",
        "body": {},
    })
    envelope = compose.output["envelope"]

    result = await builder.invoke("net-relay", {
        "envelope": envelope,
        "chain": ["alpha", "beta"],
        "current_hop": 0,
    })
    assert result.ok
    assert result.output["envelope"]["hops"] == 1
    assert len(result.output["envelope"]["visited"]) == 1
    assert result.output["envelope"]["visited"][0]["agent"] == "alpha"


@pytest.mark.asyncio
async def test_net_relay_empty_chain(builder):
    result = await builder.invoke("net-relay", {
        "chain": [],
        "envelope": {},
    })
    assert not result.output.get("ok", True)


# ─── net-broadcast ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_net_broadcast_basic(builder):
    result = await builder.invoke("net-broadcast", {
        "recipients": ["agent-a", "agent-b", "agent-c"],
        "subject": "mesh update",
        "body": {"version": "0.8.0"},
    })
    assert result.ok
    assert result.output["recipient_count"] == 3
    assert "envelope" in result.output
    assert result.output["acks"]["agent-a"] == "pending"
    assert result.output["acks"]["agent-b"] == "pending"


@pytest.mark.asyncio
async def test_net_broadcast_string_recipients(builder):
    result = await builder.invoke("net-broadcast", {
        "recipients": "agent-x",
        "subject": "ping",
        "body": {},
    })
    assert result.ok
    assert result.output["recipients"] == ["agent-x"]


@pytest.mark.asyncio
async def test_net_broadcast_no_recipients(builder):
    result = await builder.invoke("net-broadcast", {
        "recipients": [],
        "subject": "ping",
        "body": {},
    })
    assert not result.output.get("ok", True)


# ─── net-request ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_net_request_basic(builder):
    result = await builder.invoke("net-request", {
        "target": "solver-agent",
        "capability": "solar-prediction",
        "body": {"region": "pacific"},
        "timeout_seconds": 120,
        "max_retries": 3,
    })
    assert result.ok
    contract = result.output["contract"]
    assert contract["target"] == "solver-agent"
    assert contract["capability"] == "solar-prediction"
    assert contract["timeout_seconds"] == 120
    assert contract["max_retries"] == 3
    assert contract["status"] == "pending"
    assert contract["attempts"] == 0
    assert "request_id" in result.output


@pytest.mark.asyncio
async def test_net_request_missing_fields(builder):
    result = await builder.invoke("net-request", {
        "target": "solver",
    })
    assert not result.ok  # input validation catches missing 'capability'


@pytest.mark.asyncio
async def test_net_request_with_priority(builder):
    result = await builder.invoke("net-request", {
        "target": "solver",
        "capability": "compute",
        "priority": 0.9,
    })
    assert result.ok
    assert result.output["contract"]["priority"] == 0.9


# ─── net-ack ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_net_ack_basic(builder):
    result = await builder.invoke("net-ack", {
        "message_id": "msg-abc123",
    })
    assert result.ok
    ack = result.output["ack"]
    assert ack["message_id"] == "msg-abc123"
    assert ack["status"] == "received"
    assert ack["response"] == {}


@pytest.mark.asyncio
async def test_net_ack_with_response(builder):
    result = await builder.invoke("net-ack", {
        "message_id": "msg-xyz",
        "status": "completed",
        "response": {"prediction": 42.5},
        "latency_ms": 150.3,
    })
    assert result.ok
    ack = result.output["ack"]
    assert ack["status"] == "completed"
    assert ack["response"] == {"prediction": 42.5}
    assert ack["latency_ms"] == 150.3


@pytest.mark.asyncio
async def test_net_ack_missing_message_id(builder):
    result = await builder.invoke("net-ack", {})
    assert not result.ok  # input validation catches missing message_id


# ─── works without agent ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_network_pack_without_agent(builder_no_agent):
    result = await builder_no_agent.invoke("net-compose", {
        "to": ["agent-b"],
        "subject": "solo test",
        "body": {},
    })
    assert result.ok


# ─── load_all_packs includes network ───────────────────────────────────


def test_network_pack_registered(builder):
    names = [c.name for c in builder.list_capabilities()]
    assert "net-compose" in names
    assert "net-relay" in names
    assert "net-broadcast" in names
    assert "net-request" in names
    assert "net-ack" in names


def test_network_pack_tags(builder):
    net_caps = [c for c in builder.list_capabilities(tag="network")]
    assert len(net_caps) == 5
