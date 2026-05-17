"""Tests for the resilience capability pack."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import (
    load_resilience_pack,
    _circuit_breakers,
    _rate_limiter,
    _bulkheads,
)


@pytest.fixture(autouse=True)
def clear_state():
    _circuit_breakers.clear()
    _rate_limiter._buckets.clear()
    _bulkheads.clear()
    yield
    _circuit_breakers.clear()
    _rate_limiter._buckets.clear()
    _bulkheads.clear()


@pytest.fixture
def builder():
    a = Agent("test-resilience")
    b = CapabilityBuilder(a)
    load_resilience_pack(b)
    return b


def _invoke(builder, name, payload):
    return asyncio.run(builder.invoke(name, payload))


# ─── Circuit Breaker ─────────────────────────────────────────────────────


class TestCircuitBreaker:
    def test_starts_closed(self, builder):
        r = _invoke(builder, "resilience-circuit", {"name": "svc-a", "action": "check"})
        assert r.ok
        assert r.output["state"] == "closed"
        assert r.output["allow"] is True

    def test_opens_after_threshold(self, builder):
        for i in range(5):
            _invoke(builder, "resilience-circuit", {"name": "svc-b", "action": "failure"})
        r = _invoke(builder, "resilience-circuit", {"name": "svc-b", "action": "check"})
        assert r.output["state"] == "open"
        assert r.output["allow"] is False

    def test_success_resets_from_half_open(self, builder):
        # Drive to open
        for _ in range(5):
            _invoke(builder, "resilience-circuit", {"name": "svc-c", "action": "failure", "reset_timeout": 0.0})
        # Wait for half-open transition
        import time
        time.sleep(0.01)
        r = _invoke(builder, "resilience-circuit", {"name": "svc-c", "action": "check", "reset_timeout": 0.0})
        # Should transition to half_open and allow
        assert r.output["allow"] is True
        # Record success → closed
        _invoke(builder, "resilience-circuit", {"name": "svc-c", "action": "success"})
        r = _invoke(builder, "resilience-circuit", {"name": "svc-c", "action": "check"})
        assert r.output["state"] == "closed"

    def test_manual_reset(self, builder):
        for _ in range(5):
            _invoke(builder, "resilience-circuit", {"name": "svc-d", "action": "failure"})
        _invoke(builder, "resilience-circuit", {"name": "svc-d", "action": "reset"})
        r = _invoke(builder, "resilience-circuit", {"name": "svc-d", "action": "check"})
        assert r.output["state"] == "closed"

    def test_custom_threshold(self, builder):
        r = _invoke(builder, "resilience-circuit", {"name": "svc-e", "action": "check", "failure_threshold": 2})
        assert r.output["failure_threshold"] == 2
        _invoke(builder, "resilience-circuit", {"name": "svc-e", "action": "failure"})
        _invoke(builder, "resilience-circuit", {"name": "svc-e", "action": "failure"})
        r = _invoke(builder, "resilience-circuit", {"name": "svc-e", "action": "check"})
        assert r.output["state"] == "open"


# ─── Rate Limiter ────────────────────────────────────────────────────────


class TestRateLimiter:
    def test_allows_within_burst(self, builder):
        r = _invoke(builder, "resilience-rate-limit", {"key": "api", "action": "configure", "rate": 100, "burst": 5})
        assert r.output["ok"]
        for _ in range(5):
            r = _invoke(builder, "resilience-rate-limit", {"key": "api", "action": "check"})
            assert r.output["allowed"] is True
        # 6th should fail
        r = _invoke(builder, "resilience-rate-limit", {"key": "api", "action": "check"})
        assert r.output["allowed"] is False

    def test_default_config(self, builder):
        r = _invoke(builder, "resilience-rate-limit", {"key": "new-key", "action": "check"})
        assert r.output["allowed"] is True

    def test_status(self, builder):
        _invoke(builder, "resilience-rate-limit", {"key": "x", "action": "configure", "rate": 5})
        r = _invoke(builder, "resilience-rate-limit", {"key": "x", "action": "status"})
        assert r.output["ok"]
        assert any(b["key"] == "x" for b in r.output["buckets"])


# ─── Retry Backoff ───────────────────────────────────────────────────────


class TestRetryBackoff:
    def test_exponential(self, builder):
        r1 = _invoke(builder, "resilience-retry", {"attempt": 1, "base_delay": 1.0, "jitter": False, "strategy": "exponential"})
        assert r1.output["delay_seconds"] == 1.0
        r2 = _invoke(builder, "resilience-retry", {"attempt": 3, "base_delay": 1.0, "jitter": False, "strategy": "exponential"})
        assert r2.output["delay_seconds"] == 4.0

    def test_linear(self, builder):
        r = _invoke(builder, "resilience-retry", {"attempt": 4, "base_delay": 2.0, "strategy": "linear", "jitter": False})
        assert r.output["delay_seconds"] == 8.0

    def test_constant(self, builder):
        r = _invoke(builder, "resilience-retry", {"attempt": 5, "base_delay": 3.0, "strategy": "constant", "jitter": False})
        assert r.output["delay_seconds"] == 3.0

    def test_max_delay_cap(self, builder):
        r = _invoke(builder, "resilience-retry", {"attempt": 10, "base_delay": 1.0, "max_delay": 30.0, "jitter": False, "strategy": "exponential"})
        assert r.output["delay_seconds"] <= 30.0

    def test_jitter_varies(self, builder):
        delays = set()
        for _ in range(20):
            r = _invoke(builder, "resilience-retry", {"attempt": 2, "base_delay": 1.0, "strategy": "exponential"})
            delays.add(r.output["delay_seconds"])
        assert len(delays) > 1  # jitter introduces variation


# ─── Bulkhead ────────────────────────────────────────────────────────────


class TestBulkhead:
    def test_acquire_release(self, builder):
        _invoke(builder, "resilience-bulkhead", {"pool": "db", "action": "configure", "max_concurrent": 2})
        r1 = _invoke(builder, "resilience-bulkhead", {"pool": "db", "action": "acquire"})
        assert r1.output["acquired"] is True
        r2 = _invoke(builder, "resilience-bulkhead", {"pool": "db", "action": "acquire"})
        assert r2.output["acquired"] is True
        r3 = _invoke(builder, "resilience-bulkhead", {"pool": "db", "action": "acquire"})
        assert r3.output["acquired"] is False
        assert r3.output["reason"] == "at_capacity"

        _invoke(builder, "resilience-bulkhead", {"pool": "db", "action": "release"})
        r4 = _invoke(builder, "resilience-bulkhead", {"pool": "db", "action": "acquire"})
        assert r4.output["acquired"] is True

    def test_check(self, builder):
        _invoke(builder, "resilience-bulkhead", {"pool": "x", "action": "configure", "max_concurrent": 5})
        r = _invoke(builder, "resilience-bulkhead", {"pool": "x", "action": "check"})
        assert r.output["available"] == 5
        assert r.output["current"] == 0

    def test_status(self, builder):
        _invoke(builder, "resilience-bulkhead", {"pool": "a", "action": "configure", "max_concurrent": 3})
        r = _invoke(builder, "resilience-bulkhead", {"pool": "a", "action": "status"})
        assert "a" in r.output["pools"]

    def test_default_pool(self, builder):
        r = _invoke(builder, "resilience-bulkhead", {"pool": "auto-created", "action": "check"})
        assert r.output["ok"]


# ─── Health Summary ──────────────────────────────────────────────────────


class TestResilienceHealth:
    def test_healthy_when_empty(self, builder):
        r = _invoke(builder, "resilience-health", {})
        assert r.output["healthy"] is True
        assert r.output["open_circuits"] == []
        assert r.output["at_capacity_bulkheads"] == []

    def test_unhealthy_with_open_circuit(self, builder):
        for _ in range(5):
            _invoke(builder, "resilience-circuit", {"name": "failing", "action": "failure"})
        r = _invoke(builder, "resilience-health", {})
        assert r.output["healthy"] is False
        assert "failing" in r.output["open_circuits"]

    def test_unhealthy_with_full_bulkhead(self, builder):
        _invoke(builder, "resilience-bulkhead", {"pool": "full", "action": "configure", "max_concurrent": 1})
        _invoke(builder, "resilience-bulkhead", {"pool": "full", "action": "acquire"})
        _invoke(builder, "resilience-bulkhead", {"pool": "full", "action": "acquire"})
        r = _invoke(builder, "resilience-health", {})
        assert r.output["healthy"] is False


# ─── Load All Integration ───────────────────────────────────────────────


class TestResilienceInLoadAll:
    def test_included(self):
        from manifold.capability_pack import load_all_packs
        a = Agent("all-resilience")
        b = CapabilityBuilder(a)
        specs = load_all_packs(b)
        names = [s.name for s in specs]
        assert any(n.startswith("resilience-") for n in names)
