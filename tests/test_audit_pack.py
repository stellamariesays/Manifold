"""Tests for the audit & compliance capability pack."""

import asyncio
import time

import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_audit_pack, _AuditLog


def _make_builder() -> tuple[Agent, CapabilityBuilder]:
    agent = Agent(name="test-audit-agent")
    builder = CapabilityBuilder(agent)
    return agent, builder


# ─── _AuditLog unit tests ───────────────────────────────────────────────


class TestAuditLog:
    def test_record_returns_entry(self):
        log = _AuditLog()
        entry = log.record(action="deploy", actor="alice", target="prod", outcome="success")
        assert entry["action"] == "deploy"
        assert entry["actor"] == "alice"
        assert entry["outcome"] == "success"
        assert "audit_id" in entry
        assert "timestamp" in entry

    def test_record_with_tags_and_metadata(self):
        log = _AuditLog()
        entry = log.record(
            action="login",
            actor="bob",
            metadata={"ip": "1.2.3.4"},
            tags=["auth", "security"],
        )
        assert entry["metadata"]["ip"] == "1.2.3.4"
        assert "security" in entry["tags"]

    def test_query_by_actor(self):
        log = _AuditLog()
        log.record(action="read", actor="alice")
        log.record(action="write", actor="bob")
        log.record(action="delete", actor="alice")
        results = log.query(actor="alice")
        assert len(results) == 2
        assert all(e["actor"] == "alice" for e in results)

    def test_query_by_action(self):
        log = _AuditLog()
        log.record(action="deploy-service", actor="alice")
        log.record(action="deploy-app", actor="bob")
        log.record(action="rollback", actor="alice")
        results = log.query(action="deploy")
        assert len(results) == 2

    def test_query_by_outcome(self):
        log = _AuditLog()
        log.record(action="x", outcome="success")
        log.record(action="y", outcome="failure")
        log.record(action="z", outcome="success")
        failures = log.query(outcome="failure")
        assert len(failures) == 1

    def test_query_by_tag(self):
        log = _AuditLog()
        log.record(action="a", tags=["security"])
        log.record(action="b", tags=["infra"])
        log.record(action="c", tags=["security", "infra"])
        results = log.query(tag="security")
        assert len(results) == 2

    def test_query_by_since(self):
        log = _AuditLog()
        log.record(action="old")
        cutoff = time.time()
        log.record(action="new1")
        log.record(action="new2")
        results = log.query(since=cutoff)
        assert len(results) == 2

    def test_query_limit(self):
        log = _AuditLog()
        for i in range(20):
            log.record(action=f"action-{i}")
        results = log.query(limit=5)
        assert len(results) == 5

    def test_stats(self):
        log = _AuditLog()
        log.record(action="a", outcome="success")
        log.record(action="b", outcome="success")
        log.record(action="c", outcome="failure")
        s = log.stats()
        assert s["total_events"] == 3
        assert s["outcomes"]["success"] == 2
        assert s["outcomes"]["failure"] == 1

    def test_span_lifecycle(self):
        log = _AuditLog()
        span = log.start_span(operation="task-route", actor="router")
        assert span["status"] == "running"
        assert span["duration_ms"] is None

        # Add event
        assert log.add_event(span["span_id"], "negotiation-started")
        assert log.add_event(span["span_id"], "negotiation-complete", metadata={"score": 0.85})

        # Finish
        finished = log.finish_span(span["span_id"], status="ok", result={"agent": "weather-bot"})
        assert finished is not None
        assert finished["status"] == "ok"
        assert finished["duration_ms"] is not None
        assert finished["duration_ms"] >= 0
        assert len(finished["events"]) == 2

    def test_span_nesting(self):
        log = _AuditLog()
        parent = log.start_span(operation="pipeline")
        child = log.start_span(operation="step-1", parent_span_id=parent["span_id"])
        assert child["parent_span_id"] == parent["span_id"]
        assert child["span_id"] in log.get_span(parent["span_id"])["children"]

    def test_active_spans(self):
        log = _AuditLog()
        s1 = log.start_span(operation="a")
        log.start_span(operation="b")
        log.finish_span(s1["span_id"])
        active = log.active_spans()
        assert len(active) == 1
        assert active[0]["operation"] == "b"

    def test_finish_nonexistent_span(self):
        log = _AuditLog()
        assert log.finish_span("nope") is None

    def test_add_event_nonexistent_span(self):
        log = _AuditLog()
        assert log.add_event("nope", "test") is False

    def test_get_span(self):
        log = _AuditLog()
        span = log.start_span(operation="x")
        assert log.get_span(span["span_id"]) is not None
        assert log.get_span("nope") is None


# ─── Capability pack tests ──────────────────────────────────────────────


class TestAuditPack:
    @pytest.fixture
    def builder(self):
        agent, builder = _make_builder()
        load_audit_pack(builder)
        return builder

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_pack_registers_capabilities(self, builder):
        caps = builder.list_capabilities()
        names = [c.name for c in caps]
        assert "audit-record" in names
        assert "audit-query" in names
        assert "audit-span-start" in names
        assert "audit-span-finish" in names
        assert "audit-span-event" in names
        assert "audit-stats" in names
        assert len(names) == 6

    def test_record_and_query(self, builder):
        result = self._run(builder.invoke("audit-record", {
            "action": "deploy",
            "actor": "alice",
            "target": "prod",
            "outcome": "success",
            "tags": ["infra"],
        }))
        assert result.ok
        assert result.output["ok"] is True
        assert "audit_id" in result.output

        q = self._run(builder.invoke("audit-query", {"actor": "alice"}))
        assert q.ok
        assert q.output["count"] == 1
        assert q.output["entries"][0]["action"] == "deploy"

    def test_query_by_outcome(self, builder):
        self._run(builder.invoke("audit-record", {"action": "ok", "outcome": "success"}))
        self._run(builder.invoke("audit-record", {"action": "fail", "outcome": "failure"}))
        q = self._run(builder.invoke("audit-query", {"outcome": "failure"}))
        assert q.output["count"] == 1

    def test_span_start_finish(self, builder):
        s = self._run(builder.invoke("audit-span-start", {
            "operation": "research",
            "actor": "bot",
        }))
        assert s.ok
        span_id = s.output["span_id"]

        f = self._run(builder.invoke("audit-span-finish", {
            "span_id": span_id,
            "status": "ok",
            "result": {"answer": "42"},
        }))
        assert f.ok
        assert f.output["duration_ms"] is not None

    def test_span_event(self, builder):
        s = self._run(builder.invoke("audit-span-start", {"operation": "test"}))
        span_id = s.output["span_id"]

        ev = self._run(builder.invoke("audit-span-event", {
            "span_id": span_id,
            "event": "checkpoint",
            "metadata": {"progress": 50},
        }))
        assert ev.ok

    def test_span_finish_nonexistent(self, builder):
        f = self._run(builder.invoke("audit-span-finish", {"span_id": "nope"}))
        assert f.output["ok"] is False

    def test_span_event_nonexistent(self, builder):
        ev = self._run(builder.invoke("audit-span-event", {
            "span_id": "nope",
            "event": "test",
        }))
        assert ev.output["ok"] is False

    def test_stats(self, builder):
        self._run(builder.invoke("audit-record", {"action": "a", "outcome": "success"}))
        self._run(builder.invoke("audit-record", {"action": "b", "outcome": "failure"}))
        self._run(builder.invoke("audit-span-start", {"operation": "x"}))

        s = self._run(builder.invoke("audit-stats", {}))
        assert s.ok
        assert s.output["total_events"] == 2
        assert s.output["total_spans"] == 1
        assert s.output["active_spans"] == 1

    def test_shared_audit_log(self):
        """Two builders sharing the same _AuditLog see each other's events."""
        log = _AuditLog()
        agent1 = Agent(name="a1")
        agent2 = Agent(name="a2")
        b1 = CapabilityBuilder(agent1)
        b2 = CapabilityBuilder(agent2)
        load_audit_pack(b1, audit_log=log)
        load_audit_pack(b2, audit_log=log)

        self._run(b1.invoke("audit-record", {"action": "deploy", "actor": "a1"}))
        q = self._run(b2.invoke("audit-query", {"actor": "a1"}))
        assert q.output["count"] == 1


class TestAuditPackInLoadAll:
    """Verify load_all_packs includes audit pack."""

    def test_included(self):
        from manifold.capability_pack import load_all_packs
        agent = Agent(name="all-audit")
        builder = CapabilityBuilder(agent)
        specs = load_all_packs(builder)
        names = [s.name for s in specs]
        assert any(n.startswith("audit-") for n in names)
