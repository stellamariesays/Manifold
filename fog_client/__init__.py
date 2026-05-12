"""
fog_client — subscriber library for the fog event bus.

Connects to the fog-event-relay (WS :8790) and provides:
- Typed event parsing
- Subscription filters
- Auto-reconnect with backoff
- Fallback to direct Manifold WS polling
- Timeseries query (reads recorder JSONL)
- Relay health/status

Usage::

    from fog_client import FogSubscriber

    client = FogSubscriber("ws://localhost:8790")
    client.subscribe(["seam.shift", "dark.pressure"])

    @client.on("seam.shift")
    async def handle_seam(event):
        print(f"{event.data['seam']}: {event.data['delta']:+.3f}")

    await client.run()
"""

from .types import FogEvent, EventType, SeamShiftData, DarkPressureData, FogVolumeData, MeshMutationData
from .subscriber import FogSubscriber
from .timeseries import query_timeseries, TimeseriesEntry
from .status import get_status, RelayStatus

__all__ = [
    "FogSubscriber",
    "FogEvent",
    "EventType",
    "SeamShiftData",
    "DarkPressureData",
    "FogVolumeData",
    "MeshMutationData",
    "query_timeseries",
    "TimeseriesEntry",
    "get_status",
    "RelayStatus",
]
