"""Agent health monitoring — heartbeat tracking and mesh health scoring."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNRESPONSIVE = "unresponsive"
    OFFLINE = "offline"


@dataclass
class AgentHealth:
    agent_id: str
    status: HealthStatus = HealthStatus.HEALTHY
    last_heartbeat: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    capabilities: list[str] = field(default_factory=list)
    load: float = 0.0  # 0.0 - 1.0
    latency_ms: float = 0.0
    uptime_seconds: int = 0
    missed_heartbeats: int = 0
    task_success_rate: float = 1.0
    total_tasks: int = 0
    failed_tasks: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> AgentHealth:
        if "status" in data and isinstance(data["status"], str):
            data["status"] = HealthStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class HealthMonitor:
    """Tracks agent health across the mesh."""

    DEGRADED_THRESHOLD = 3   # missed heartbeats
    OFFLINE_THRESHOLD = 10
    HEARTBEAT_INTERVAL_S = 30  # expected seconds between heartbeats

    def __init__(self):
        self._agents: dict[str, AgentHealth] = {}

    def register_agent(self, agent_id: str, capabilities: list[str] | None = None) -> AgentHealth:
        health = AgentHealth(
            agent_id=agent_id,
            capabilities=capabilities or [],
        )
        self._agents[agent_id] = health
        return health

    def heartbeat(self, agent_id: str, latency_ms: float = 0.0, load: float = 0.0) -> AgentHealth:
        if agent_id not in self._agents:
            self.register_agent(agent_id)
        h = self._agents[agent_id]
        h.last_heartbeat = datetime.now(timezone.utc).isoformat()
        h.latency_ms = latency_ms
        h.load = load
        h.missed_heartbeats = 0
        h.status = HealthStatus.HEALTHY
        return h

    def check_health(self, agent_id: str) -> HealthStatus:
        if agent_id not in self._agents:
            return HealthStatus.OFFLINE
        h = self._agents[agent_id]
        if h.missed_heartbeats >= self.OFFLINE_THRESHOLD:
            h.status = HealthStatus.OFFLINE
        elif h.missed_heartbeats >= self.DEGRADED_THRESHOLD:
            h.status = HealthStatus.DEGRADED
        else:
            h.status = HealthStatus.HEALTHY
        return h.status

    def tick(self) -> None:
        """Call periodically to increment missed heartbeats for stale agents."""
        now = datetime.now(timezone.utc)
        for h in self._agents.values():
            last = datetime.fromisoformat(h.last_heartbeat)
            elapsed = (now - last).total_seconds()
            expected_missed = int(elapsed / self.HEARTBEAT_INTERVAL_S)
            if expected_missed > h.missed_heartbeats:
                h.missed_heartbeats = expected_missed
            self.check_health(h.agent_id)

    def get_mesh_health(self) -> float:
        if not self._agents:
            return 1.0
        healthy = sum(1 for h in self._agents.values() if h.status == HealthStatus.HEALTHY)
        return round(healthy / len(self._agents), 3)

    def get_unhealthy_agents(self) -> list[AgentHealth]:
        return [h for h in self._agents.values() if h.status != HealthStatus.HEALTHY]

    def get_agent(self, agent_id: str) -> AgentHealth | None:
        return self._agents.get(agent_id)

    @property
    def agents(self) -> dict[str, AgentHealth]:
        return dict(self._agents)
