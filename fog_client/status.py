"""
Relay health and status check.

Queries the fog-event-relay's HTTP status endpoint.
"""

import json
import urllib.request
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass(frozen=True)
class RelayStatus:
    """Health snapshot of the fog-event-relay."""
    connected: bool                # upstream Manifold WS connected
    uptime_seconds: float
    subscribers: int               # active WS subscriber count
    events_emitted: int            # total events emitted since start
    last_event_timestamp: Optional[datetime]
    last_event_type: Optional[str]
    ring_buffer_size: int
    relay_url: str

    @property
    def uptime_human(self) -> str:
        secs = int(self.uptime_seconds)
        hours, remainder = divmod(secs, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {secs}s"

    def summary(self) -> str:
        return (
            f"Fog Relay {'🟢' if self.connected else '🔴'} "
            f"uptime={self.uptime_human} "
            f"subscribers={self.subscribers} "
            f"events={self.events_emitted} "
            f"buffer={self.ring_buffer_size}"
        )


def get_status(relay_url: str = "http://localhost:8790") -> RelayStatus:
    """
    Query the relay's HTTP /status endpoint.

    Args:
        relay_url: Base URL of the fog-event-relay (HTTP, not WS).

    Returns:
        RelayStatus with current health info.

    Raises:
        ConnectionError: If relay is unreachable.
    """
    status_url = f"{relay_url.rstrip('/')}/status"

    try:
        req = urllib.request.Request(status_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        raise ConnectionError(f"Relay unreachable at {status_url}: {e}") from e

    last_ts = None
    if data.get("last_event_timestamp"):
        try:
            last_ts = datetime.fromisoformat(
                data["last_event_timestamp"].replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            pass

    return RelayStatus(
        connected=data.get("connected", False),
        uptime_seconds=data.get("uptime_seconds", 0),
        subscribers=data.get("subscribers", 0),
        events_emitted=data.get("events_emitted", 0),
        last_event_timestamp=last_ts,
        last_event_type=data.get("last_event_type"),
        ring_buffer_size=data.get("ring_buffer_size", 0),
        relay_url=relay_url,
    )
