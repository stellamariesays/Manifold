"""
Typed event models for the fog event bus.

Four event types from the relay:
- mesh.mutation — any agent graph change
- seam.shift — seam tension delta exceeds threshold
- dark.pressure — new dark circle or pressure change
- fog.volume — aggregate fog volume changed
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime


class EventType(str, Enum):
    MESH_MUTATION = "mesh.mutation"
    SEAM_SHIFT = "seam.shift"
    DARK_PRESSURE = "dark.pressure"
    FOG_VOLUME = "fog.volume"


@dataclass(frozen=True)
class SeamShiftData:
    """Seam tension changed between two agents."""
    seam: str                    # "void-watcher↔sentry"
    previous: float
    current: float
    delta: float
    agent_a: Optional[str] = None
    agent_b: Optional[str] = None

    @property
    def direction(self) -> str:
        if self.delta > 0:
            return "diverging"
        elif self.delta < 0:
            return "converging"
        return "stable"


@dataclass(frozen=True)
class DarkPressureData:
    """Dark circle pressure change or new circle detected."""
    circle_id: str
    pressure: float
    previous_pressure: Optional[float] = None
    delta: Optional[float] = None
    source: Optional[str] = None      # which agent/hub reported
    new: bool = False                  # True if newly discovered

    @property
    def is_new(self) -> bool:
        return self.new


@dataclass(frozen=True)
class FogVolumeData:
    """Aggregate fog volume changed across the mesh."""
    total_gaps: int
    previous_gaps: int
    delta: int
    by_domain: Dict[str, int] = field(default_factory=dict)

    @property
    def direction(self) -> str:
        if self.delta < 0:
            return "clearing"
        elif self.delta > 0:
            return "deepening"
        return "stable"


@dataclass(frozen=True)
class MeshMutationData:
    """Any agent graph change — capabilities, peers, topology."""
    mutation_type: str      # "peer_join", "peer_leave", "capability_change", "topology"
    agent: Optional[str] = None
    hub: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


# Map event type → data class
_EVENT_DATA_MAP = {
    EventType.SEAM_SHIFT: SeamShiftData,
    EventType.DARK_PRESSURE: DarkPressureData,
    EventType.FOG_VOLUME: FogVolumeData,
    EventType.MESH_MUTATION: MeshMutationData,
}


@dataclass(frozen=True)
class FogEvent:
    """A single fog event from the relay."""
    type: EventType
    timestamp: datetime
    data: Any  # One of SeamShiftData, DarkPressureData, FogVolumeData, MeshMutationData
    raw: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "FogEvent":
        """Parse a raw JSON event from the relay into a typed FogEvent."""
        event_type = EventType(payload["type"])
        ts = datetime.fromisoformat(
            payload["timestamp"].replace("Z", "+00:00")
        )
        raw_data = payload.get("data", {})

        data_cls = _EVENT_DATA_MAP.get(event_type)
        if data_cls:
            # Filter to fields the dataclass actually accepts
            import dataclasses
            valid_fields = {f.name for f in dataclasses.fields(data_cls)}
            filtered = {k: v for k, v in raw_data.items() if k in valid_fields}
            data = data_cls(**filtered)
        else:
            data = raw_data

        return cls(
            type=event_type,
            timestamp=ts,
            data=data,
            raw=payload,
        )
