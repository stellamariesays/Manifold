"""Tests for agent health monitoring."""

from datetime import datetime, timezone, timedelta

from manifold.health import HealthMonitor, HealthStatus, AgentHealth


def test_register_and_heartbeat():
    m = HealthMonitor()
    m.register_agent("a@hub", ["trading"])
    h = m.heartbeat("a@hub", latency_ms=50.0, load=0.3)
    assert h.status == HealthStatus.HEALTHY
    assert h.latency_ms == 50.0


def test_heartbeat_auto_registers():
    m = HealthMonitor()
    h = m.heartbeat("new@hub")
    assert h.agent_id == "new@hub"
    assert h.status == HealthStatus.HEALTHY


def test_degraded_detection():
    m = HealthMonitor()
    m.register_agent("a@hub")
    a = m.get_agent("a@hub")
    a.missed_heartbeats = 3
    status = m.check_health("a@hub")
    assert status == HealthStatus.DEGRADED


def test_offline_detection():
    m = HealthMonitor()
    m.register_agent("a@hub")
    a = m.get_agent("a@hub")
    a.missed_heartbeats = 10
    status = m.check_health("a@hub")
    assert status == HealthStatus.OFFLINE


def test_mesh_health():
    import pytest
    m = HealthMonitor()
    m.register_agent("a@hub")
    m.register_agent("b@hub")
    m.register_agent("c@hub")
    assert m.get_mesh_health() == 1.0
    m.get_agent("a@hub").missed_heartbeats = 10
    m.check_health("a@hub")
    assert abs(m.get_mesh_health() - 0.667) < 0.01


def test_unhealthy_agents():
    m = HealthMonitor()
    m.register_agent("a@hub")
    m.register_agent("b@hub")
    m.get_agent("a@hub").missed_heartbeats = 5
    m.check_health("a@hub")
    unhealthy = m.get_unhealthy_agents()
    assert len(unhealthy) == 1
    assert unhealthy[0].agent_id == "a@hub"


def test_agent_health_roundtrip():
    h = AgentHealth(agent_id="test@hub", status=HealthStatus.DEGRADED, capabilities=["x"])
    d = h.to_dict()
    assert d["status"] == "degraded"
    h2 = AgentHealth.from_dict(d)
    assert h2.status == HealthStatus.DEGRADED
    assert h2.capabilities == ["x"]


def test_check_health_unknown():
    m = HealthMonitor()
    assert m.check_health("ghost@hub") == HealthStatus.OFFLINE


def test_empty_mesh_health():
    m = HealthMonitor()
    assert m.get_mesh_health() == 1.0


if __name__ == "__main__":
    import pytest
    # Run via pytest instead
    pass
