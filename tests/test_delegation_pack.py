"""Tests for delegation capability pack — task delegation, chains, timeouts."""

import asyncio
import time

import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import (
    load_delegation_pack,
    _delegation_store,
)


@pytest.fixture(autouse=True)
def clear_delegation_store():
    _delegation_store.clear()
    yield
    _delegation_store.clear()


@pytest.fixture
def builder():
    a = Agent("test-delegator")
    b = CapabilityBuilder(a)
    load_delegation_pack(b)
    return b


def _invoke(builder, name, payload):
    cap = builder.get(name)
    assert cap is not None, f"Capability '{name}' not found"
    return asyncio.run(cap.handler(payload))


def test_pack_registers_all_capabilities(builder):
    names = list(builder._caps.keys())
    expected = [
        "delegation-create",
        "delegation-accept",
        "delegation-reject",
        "delegation-complete",
        "delegation-fail",
        "delegation-timeout-check",
        "delegation-status",
        "delegation-list",
        "delegation-stats",
    ]
    for e in expected:
        assert e in names, f"Missing capability: {e}"


def test_create_delegation(builder):
    result = _invoke(builder, "delegation-create", {
        "task": "Analyze solar panel output",
        "target_agent": "solar-agent",
    })
    assert result["ok"] is True
    assert result["status"] == "pending"
    assert result["target_agent"] == "solar-agent"
    assert result["chain_depth"] == 0


def test_create_delegation_missing_fields(builder):
    result = _invoke(builder, "delegation-create", {"task": "do stuff"})
    assert result["ok"] is False

    result = _invoke(builder, "delegation-create", {"target_agent": "bob"})
    assert result["ok"] is False


def test_create_with_deadline_and_priority(builder):
    deadline = time.time() + 3600
    result = _invoke(builder, "delegation-create", {
        "task": "Urgent grid balancing",
        "target_agent": "grid-agent",
        "deadline": deadline,
        "priority": "high",
    })
    assert result["ok"] is True
    assert result["status"] == "pending"


def test_accept_delegation(builder):
    created = _invoke(builder, "delegation-create", {
        "task": "Run diagnostics",
        "target_agent": "diag-agent",
    })
    did = created["delegation_id"]

    result = _invoke(builder, "delegation-accept", {"delegation_id": did})
    assert result["ok"] is True
    assert result["status"] == "accepted"


def test_accept_wrong_status(builder):
    created = _invoke(builder, "delegation-create", {
        "task": "Task",
        "target_agent": "agent",
    })
    did = created["delegation_id"]
    _invoke(builder, "delegation-accept", {"delegation_id": did})

    # Can't accept again
    result = _invoke(builder, "delegation-accept", {"delegation_id": did})
    assert result["ok"] is False


def test_reject_delegation(builder):
    created = _invoke(builder, "delegation-create", {
        "task": "Task",
        "target_agent": "agent",
    })
    did = created["delegation_id"]

    result = _invoke(builder, "delegation-reject", {
        "delegation_id": did,
        "reason": "too busy",
    })
    assert result["ok"] is True
    assert result["status"] == "rejected"


def test_complete_delegation(builder):
    created = _invoke(builder, "delegation-create", {
        "task": "Predict output",
        "target_agent": "solar-agent",
    })
    did = created["delegation_id"]
    _invoke(builder, "delegation-accept", {"delegation_id": did})

    result = _invoke(builder, "delegation-complete", {
        "delegation_id": did,
        "result": {"predicted_mw": 42.0, "confidence": 0.91},
    })
    assert result["ok"] is True
    assert result["status"] == "done"

    # Verify result stored
    status = _invoke(builder, "delegation-status", {"delegation_id": did})
    assert status["result"]["predicted_mw"] == 42.0


def test_complete_without_accept_fails(builder):
    created = _invoke(builder, "delegation-create", {
        "task": "Task",
        "target_agent": "agent",
    })
    did = created["delegation_id"]

    # Still pending, can complete (accepted or in_progress required)
    result = _invoke(builder, "delegation-complete", {"delegation_id": did, "result": {}})
    assert result["ok"] is False


def test_fail_delegation(builder):
    created = _invoke(builder, "delegation-create", {
        "task": "Task",
        "target_agent": "agent",
    })
    did = created["delegation_id"]
    _invoke(builder, "delegation-accept", {"delegation_id": did})

    result = _invoke(builder, "delegation-fail", {
        "delegation_id": did,
        "error": "connection lost",
    })
    assert result["ok"] is True
    assert result["status"] == "failed"


def test_fail_already_done(builder):
    created = _invoke(builder, "delegation-create", {
        "task": "Task",
        "target_agent": "agent",
    })
    did = created["delegation_id"]
    _invoke(builder, "delegation-accept", {"delegation_id": did})
    _invoke(builder, "delegation-complete", {"delegation_id": did, "result": {}})

    result = _invoke(builder, "delegation-fail", {"delegation_id": did, "error": "oops"})
    assert result["ok"] is False


def test_timeout_check(builder):
    # Create with deadline in the past
    created = _invoke(builder, "delegation-create", {
        "task": "Expired task",
        "target_agent": "slow-agent",
        "deadline": time.time() - 10,  # 10s ago
    })
    did = created["delegation_id"]
    _invoke(builder, "delegation-accept", {"delegation_id": did})

    result = _invoke(builder, "delegation-timeout-check", {})
    assert result["ok"] is True
    assert did in result["timed_out"]
    assert result["count"] == 1


def test_timeout_no_deadline(builder):
    # No deadline set — should not timeout
    created = _invoke(builder, "delegation-create", {
        "task": "No deadline",
        "target_agent": "agent",
    })
    _invoke(builder, "delegation-accept", {"delegation_id": created["delegation_id"]})

    result = _invoke(builder, "delegation-timeout-check", {})
    assert result["count"] == 0


def test_delegation_chain(builder):
    # Parent delegation
    parent = _invoke(builder, "delegation-create", {
        "task": "Manage energy forecast",
        "target_agent": "coordinator",
    })
    parent_id = parent["delegation_id"]

    # Child delegation
    child = _invoke(builder, "delegation-create", {
        "task": "Run solar model",
        "target_agent": "solar-agent",
        "parent_delegation_id": parent_id,
    })
    child_id = child["delegation_id"]
    assert child["chain_depth"] == 1

    # Grandchild
    grandchild = _invoke(builder, "delegation-create", {
        "task": "Fetch weather data",
        "target_agent": "weather-agent",
        "parent_delegation_id": child_id,
    })
    assert grandchild["chain_depth"] == 2

    # Status shows chain
    status = _invoke(builder, "delegation-status", {"delegation_id": grandchild["delegation_id"]})
    assert len(status["parent_chain"]) == 2
    assert status["chain_depth"] == 2

    # Parent sees children
    parent_status = _invoke(builder, "delegation-status", {"delegation_id": parent_id})
    assert len(parent_status["children"]) == 1
    assert parent_status["children"][0]["id"] == child_id


def test_delegation_list_no_filter(builder):
    _invoke(builder, "delegation-create", {"task": "Task 1", "target_agent": "a"})
    _invoke(builder, "delegation-create", {"task": "Task 2", "target_agent": "b"})

    result = _invoke(builder, "delegation-list", {})
    assert result["ok"] is True
    assert result["total"] == 2


def test_delegation_list_filter_by_status(builder):
    c1 = _invoke(builder, "delegation-create", {"task": "T1", "target_agent": "a"})
    c2 = _invoke(builder, "delegation-create", {"task": "T2", "target_agent": "b"})
    _invoke(builder, "delegation-accept", {"delegation_id": c1["delegation_id"]})

    result = _invoke(builder, "delegation-list", {"status": "accepted"})
    assert result["total"] == 1
    assert result["delegations"][0]["id"] == c1["delegation_id"]


def test_delegation_list_filter_by_target(builder):
    _invoke(builder, "delegation-create", {"task": "T1", "target_agent": "solar"})
    _invoke(builder, "delegation-create", {"task": "T2", "target_agent": "grid"})

    result = _invoke(builder, "delegation-list", {"target_agent": "solar"})
    assert result["total"] == 1
    assert result["delegations"][0]["target_agent"] == "solar"


def test_delegation_stats(builder):
    c1 = _invoke(builder, "delegation-create", {"task": "T1", "target_agent": "a"})
    c2 = _invoke(builder, "delegation-create", {"task": "T2", "target_agent": "b"})
    c3 = _invoke(builder, "delegation-create", {"task": "T3", "target_agent": "a"})

    # a succeeds, b fails, one pending
    _invoke(builder, "delegation-accept", {"delegation_id": c1["delegation_id"]})
    _invoke(builder, "delegation-complete", {"delegation_id": c1["delegation_id"], "result": {"ok": True}})
    _invoke(builder, "delegation-accept", {"delegation_id": c2["delegation_id"]})
    _invoke(builder, "delegation-fail", {"delegation_id": c2["delegation_id"], "error": "crashed"})

    result = _invoke(builder, "delegation-stats", {})
    assert result["ok"] is True
    assert result["total"] == 3
    assert result["by_status"]["done"] == 1
    assert result["by_status"]["failed"] == 1
    assert result["by_status"]["pending"] == 1
    assert result["by_target"]["a"] == 2
    assert result["by_target"]["b"] == 1
    assert 0 < result["success_rate"] < 1


def test_delegation_stats_empty(builder):
    result = _invoke(builder, "delegation-stats", {})
    assert result["total"] == 0
    assert result["success_rate"] == 0.0


def test_not_found_operations(builder):
    result = _invoke(builder, "delegation-accept", {"delegation_id": "nonexistent"})
    assert result["ok"] is False

    result = _invoke(builder, "delegation-status", {"delegation_id": "nonexistent"})
    assert result["ok"] is False

    result = _invoke(builder, "delegation-complete", {"delegation_id": "nonexistent", "result": {}})
    assert result["ok"] is False
