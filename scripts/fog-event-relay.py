#!/usr/bin/env python3
"""
fog-event-relay — Real-time mesh mutation broadcaster.

Subscribes to the Manifold WebSocket (ws://localhost:8768), computes fog
deltas, and re-broadcasts change events to downstream WebSocket subscribers
on :8790.

Architecture:
    Manifold WS (ws://localhost:8768)
        │
        ▼
    fog-event-relay (:8790)   ← computes fog deltas
        │
        └── broadcasts to subscribers

Event types:
    mesh.mutation  — any agent graph change (join/leave/capability change)
    seam.shift     — seam tension delta > threshold (default 0.05)
    dark.pressure  — new dark circle or pressure change
    fog.volume     — aggregate fog volume changed

Subscriber protocol:
    → {"subscribe": ["seam.shift", "dark.pressure"]}
    ← {"type": "seam.shift", "timestamp": "...", "data": {...}}

Usage:
    python3 scripts/fog-event-relay.py [--manifold-ws WS_URL] [--port PORT] [--seam-threshold FLOAT]

Environment variables (override defaults):
    MANIFOLD_WS         upstream WS URL (default ws://localhost:8768)
    RELAY_PORT          subscriber port (default 8790)
    SEAM_THRESHOLD      seam tension delta threshold (default 0.05)
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

import websockets
from websockets.asyncio.server import ServerConnection

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("fog-event-relay")

# ── Fog computation ────────────────────────────────────────────────────────────

# Import from Manifold package. We add the project root to sys.path so that
# both 'manifold' and 'core' packages resolve correctly when run from the
# scripts/ directory or the project root.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from manifold.fog import FogMap, GapKind, build_fog, measure
    from manifold.blindspot import BlindSpot
    _FOG_AVAILABLE = True
    log.info("Manifold fog package loaded OK")
except ImportError as exc:
    log.warning("Manifold fog package not available (%s); fog.volume events disabled", exc)
    _FOG_AVAILABLE = False


# ── Ring buffer ────────────────────────────────────────────────────────────────

RING_SIZE = 100


class RingBuffer:
    """Thread-safe circular buffer for the last N events."""

    def __init__(self, maxlen: int = RING_SIZE):
        self._buf: collections.deque[dict] = collections.deque(maxlen=maxlen)

    def append(self, event: dict) -> None:
        self._buf.append(event)

    def snapshot(self) -> list[dict]:
        return list(self._buf)


# ── State ──────────────────────────────────────────────────────────────────────

class MeshState:
    """
    Tracks previous mesh state so we can emit only on change.
    Holds the last known view of agents and dark circles.
    """

    def __init__(self, seam_threshold: float):
        self.seam_threshold = seam_threshold
        # agent_name → {capabilities, seams, hub}
        self.agents: dict[str, dict] = {}
        # dark_circle_name → pressure (float)
        self.dark_circles: dict[str, float] = {}
        # fog maps per agent (for volume tracking)
        self.fog_maps: dict[str, "FogMap"] = {}
        # last aggregate fog volume
        self.fog_volume: int = 0
        # seam tensions: frozenset({a, b}) → float
        self.seam_tensions: dict[frozenset, float] = {}

    def ingest(self, msg: dict) -> list[dict]:
        """
        Ingest a mesh_sync or mesh_delta message and return any events to emit.
        """
        msg_type = msg.get("type")
        if msg_type == "mesh_sync":
            return self._process_sync(msg)
        elif msg_type == "mesh_delta":
            return self._process_delta(msg)
        return []

    # ── mesh_sync ──────────────────────────────────────────────────────────────

    def _process_sync(self, msg: dict) -> list[dict]:
        events: list[dict] = []
        agents_raw = msg.get("agents", [])
        dark_circles_raw = msg.get("darkCircles", [])

        # Build new agent map
        new_agents: dict[str, dict] = {}
        for a in agents_raw:
            name = a.get("name", "")
            new_agents[name] = {
                "name": name,
                "hub": a.get("hub", ""),
                "capabilities": sorted(a.get("capabilities", [])),
                "seams": a.get("seams", []),
                "pressure": a.get("pressure", 0),
                "lastSeen": a.get("lastSeen", ""),
            }

        # Detect agent joins / leaves / capability changes
        prev_names = set(self.agents)
        new_names = set(new_agents)

        for name in new_names - prev_names:
            events.append(_make_event("mesh.mutation", {
                "op": "join",
                "agent": name,
                "hub": new_agents[name]["hub"],
                "capabilities": new_agents[name]["capabilities"],
            }))

        for name in prev_names - new_names:
            events.append(_make_event("mesh.mutation", {
                "op": "leave",
                "agent": name,
                "hub": self.agents[name]["hub"],
            }))

        for name in prev_names & new_names:
            old = self.agents[name]
            new = new_agents[name]
            old_caps = set(old["capabilities"])
            new_caps = set(new["capabilities"])
            if old_caps != new_caps:
                events.append(_make_event("mesh.mutation", {
                    "op": "capability_change",
                    "agent": name,
                    "hub": new["hub"],
                    "added": sorted(new_caps - old_caps),
                    "removed": sorted(old_caps - new_caps),
                }))
            elif old.get("hub") != new.get("hub"):
                events.append(_make_event("mesh.mutation", {
                    "op": "hub_change",
                    "agent": name,
                    "previous_hub": old["hub"],
                    "current_hub": new["hub"],
                }))

        self.agents = new_agents

        # Dark circles
        new_dc: dict[str, float] = {}
        for dc in dark_circles_raw:
            dc_name = dc.get("name", "")
            pressure = float(dc.get("pressure", 0))
            new_dc[dc_name] = pressure

        for dc_name, pressure in new_dc.items():
            prev_pressure = self.dark_circles.get(dc_name)
            if prev_pressure is None:
                events.append(_make_event("dark.pressure", {
                    "circle": dc_name,
                    "op": "new",
                    "pressure": pressure,
                }))
            elif abs(pressure - prev_pressure) > 1e-9:
                events.append(_make_event("dark.pressure", {
                    "circle": dc_name,
                    "op": "change",
                    "previous": prev_pressure,
                    "current": pressure,
                    "delta": round(pressure - prev_pressure, 6),
                }))

        for dc_name in set(self.dark_circles) - set(new_dc):
            events.append(_make_event("dark.pressure", {
                "circle": dc_name,
                "op": "removed",
                "previous": self.dark_circles[dc_name],
            }))

        self.dark_circles = new_dc

        # Fog seams (computed from agent pairs with overlapping seam info)
        events.extend(self._compute_seam_events(new_agents))

        # Fog volume
        if _FOG_AVAILABLE:
            fog_events = self._compute_fog_volume(new_agents)
            events.extend(fog_events)

        return events

    # ── mesh_delta ─────────────────────────────────────────────────────────────

    def _process_delta(self, msg: dict) -> list[dict]:
        events: list[dict] = []
        agent_deltas = msg.get("agentDeltas", [])
        dc_deltas = msg.get("darkCircleDeltas", [])

        for delta in agent_deltas:
            op = delta.get("op")
            agent = delta.get("agent", {})
            name = agent.get("name", "")

            if op == "remove":
                if name in self.agents:
                    events.append(_make_event("mesh.mutation", {
                        "op": "leave",
                        "agent": name,
                        "hub": self.agents[name]["hub"],
                    }))
                    del self.agents[name]
            elif op == "upsert":
                new_caps = sorted(agent.get("capabilities", []))
                hub = agent.get("hub", "")
                if name in self.agents:
                    old_caps = set(self.agents[name]["capabilities"])
                    new_caps_set = set(new_caps)
                    if old_caps != new_caps_set:
                        events.append(_make_event("mesh.mutation", {
                            "op": "capability_change",
                            "agent": name,
                            "hub": hub,
                            "added": sorted(new_caps_set - old_caps),
                            "removed": sorted(old_caps - new_caps_set),
                        }))
                else:
                    events.append(_make_event("mesh.mutation", {
                        "op": "join",
                        "agent": name,
                        "hub": hub,
                        "capabilities": new_caps,
                    }))
                self.agents[name] = {
                    "name": name,
                    "hub": hub,
                    "capabilities": new_caps,
                    "seams": agent.get("seams", []),
                    "pressure": agent.get("pressure", 0),
                    "lastSeen": agent.get("lastSeen", ""),
                }

        for dc_delta in dc_deltas:
            op = dc_delta.get("op")
            circle = dc_delta.get("circle", {})
            dc_name = circle.get("name", "")
            pressure = float(circle.get("pressure", 0))

            if op == "remove":
                if dc_name in self.dark_circles:
                    events.append(_make_event("dark.pressure", {
                        "circle": dc_name,
                        "op": "removed",
                        "previous": self.dark_circles[dc_name],
                    }))
                    del self.dark_circles[dc_name]
            elif op == "upsert":
                prev = self.dark_circles.get(dc_name)
                if prev is None:
                    events.append(_make_event("dark.pressure", {
                        "circle": dc_name,
                        "op": "new",
                        "pressure": pressure,
                    }))
                elif abs(pressure - prev) > 1e-9:
                    events.append(_make_event("dark.pressure", {
                        "circle": dc_name,
                        "op": "change",
                        "previous": prev,
                        "current": pressure,
                        "delta": round(pressure - prev, 6),
                    }))
                self.dark_circles[dc_name] = pressure

        # Recompute seams and fog after deltas
        events.extend(self._compute_seam_events(self.agents))
        if _FOG_AVAILABLE and (agent_deltas or dc_deltas):
            events.extend(self._compute_fog_volume(self.agents))

        return events

    # ── Fog seam computation ───────────────────────────────────────────────────

    def _compute_seam_events(self, agents: dict[str, dict]) -> list[dict]:
        """
        Compute FogSeam tensions between all agent pairs that share explicit
        seam relationships (from the seams[] field), or fall back to comparing
        capability-based fog maps if the Manifold package is available.

        Emits seam.shift events where tension delta exceeds threshold.
        """
        if not _FOG_AVAILABLE:
            return self._compute_seam_events_lightweight(agents)

        events: list[dict] = []
        agent_list = list(agents.values())

        # Build per-agent fog maps from capabilities (as proxy for blind spots)
        fog_maps: dict[str, FogMap] = {}
        all_caps: set[str] = set()
        for a in agent_list:
            all_caps.update(a["capabilities"])

        for a in agent_list:
            fog = FogMap(agent_id=a["name"])
            my_caps = set(a["capabilities"])
            # Gaps = capabilities the mesh has but this agent doesn't know
            for cap in all_caps - my_caps:
                fog.add(key=cap, kind=GapKind.KNOWN_UNKNOWN, domain="capability")
            fog_maps[a["name"]] = fog

        # Compute seams for pairs that have explicit seam links OR all pairs
        # where at least one side has seams declared
        seam_pairs: set[frozenset] = set()

        # First: explicit seam relationships
        for a in agent_list:
            for seam_name in (a.get("seams") or []):
                # seam_name could be "other-agent" or "agent↔other"
                if "↔" in seam_name:
                    parts = seam_name.split("↔", 1)
                    a_name = parts[0].strip()
                    b_name = parts[1].strip()
                    if a_name in fog_maps and b_name in fog_maps:
                        seam_pairs.add(frozenset([a_name, b_name]))
                elif seam_name in fog_maps:
                    seam_pairs.add(frozenset([a["name"], seam_name]))

        # If no explicit seams, compute all pairs (for small meshes)
        if not seam_pairs and len(agent_list) <= 20:
            for i, a in enumerate(agent_list):
                for b in agent_list[i + 1:]:
                    seam_pairs.add(frozenset([a["name"], b["name"]]))

        for pair in seam_pairs:
            pair_list = list(pair)
            if len(pair_list) < 2:
                continue
            a_name, b_name = pair_list[0], pair_list[1]
            if a_name not in fog_maps or b_name not in fog_maps:
                continue

            seam = measure(fog_maps[a_name], fog_maps[b_name])
            current_tension = seam.tension
            pair_key = frozenset([a_name, b_name])
            prev_tension = self.seam_tensions.get(pair_key)

            if prev_tension is None:
                # First time seeing this pair — record but don't emit
                self.seam_tensions[pair_key] = current_tension
            else:
                delta = abs(current_tension - prev_tension)
                if delta >= self.seam_threshold:
                    seam_label = f"{a_name}↔{b_name}"
                    events.append(_make_event("seam.shift", {
                        "seam": seam_label,
                        "previous": round(prev_tension, 4),
                        "current": round(current_tension, 4),
                        "delta": round(current_tension - prev_tension, 4),
                    }))
                    self.seam_tensions[pair_key] = current_tension

        return events

    def _compute_seam_events_lightweight(self, agents: dict[str, dict]) -> list[dict]:
        """
        Lightweight seam computation without Manifold package.
        Uses Jaccard distance on capability sets as a tension proxy.
        """
        events: list[dict] = []
        agent_list = list(agents.values())

        seam_pairs: set[frozenset] = set()
        for a in agent_list:
            for seam_name in (a.get("seams") or []):
                if "↔" in seam_name:
                    parts = seam_name.split("↔", 1)
                    seam_pairs.add(frozenset([parts[0].strip(), parts[1].strip()]))
                elif seam_name in agents:
                    seam_pairs.add(frozenset([a["name"], seam_name]))

        for pair in seam_pairs:
            pair_list = list(pair)
            if len(pair_list) < 2:
                continue
            a_name, b_name = pair_list[0], pair_list[1]
            if a_name not in agents or b_name not in agents:
                continue

            caps_a = set(agents[a_name]["capabilities"])
            caps_b = set(agents[b_name]["capabilities"])
            union = len(caps_a | caps_b)
            if union == 0:
                tension = 0.0
            else:
                # Jaccard distance as tension: 1 - |A∩B| / |A∪B|
                tension = round(1.0 - len(caps_a & caps_b) / union, 4)

            pair_key = frozenset([a_name, b_name])
            prev_tension = self.seam_tensions.get(pair_key)

            if prev_tension is None:
                self.seam_tensions[pair_key] = tension
            else:
                delta = abs(tension - prev_tension)
                if delta >= self.seam_threshold:
                    seam_label = f"{a_name}↔{b_name}"
                    events.append(_make_event("seam.shift", {
                        "seam": seam_label,
                        "previous": round(prev_tension, 4),
                        "current": round(tension, 4),
                        "delta": round(tension - prev_tension, 4),
                    }))
                    self.seam_tensions[pair_key] = tension

        return events

    # ── Fog volume computation ─────────────────────────────────────────────────

    def _compute_fog_volume(self, agents: dict[str, dict]) -> list[dict]:
        """
        Compute aggregate fog volume across all agents.
        Emits fog.volume if the total changes.
        """
        if not _FOG_AVAILABLE:
            return []

        all_caps: set[str] = set()
        for a in agents.values():
            all_caps.update(a["capabilities"])

        total_gaps = 0
        for a in agents.values():
            my_caps = set(a["capabilities"])
            gaps = all_caps - my_caps
            total_gaps += len(gaps)

        if total_gaps != self.fog_volume:
            prev = self.fog_volume
            self.fog_volume = total_gaps
            return [_make_event("fog.volume", {
                "previous": prev,
                "current": total_gaps,
                "delta": total_gaps - prev,
                "agents": len(agents),
            })]
        return []


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_event(event_type: str, data: dict) -> dict:
    return {
        "type": event_type,
        "timestamp": _now_iso(),
        "data": data,
    }


# ── Subscriber manager ─────────────────────────────────────────────────────────

class SubscriberManager:
    """
    Manages downstream WebSocket subscriber connections.
    Each subscriber sends a subscribe message to declare which event types
    it wants. Matching events are forwarded from the ring buffer.
    """

    ALL_TYPES = {"mesh.mutation", "seam.shift", "dark.pressure", "fog.volume"}

    def __init__(self, ring: RingBuffer):
        self.ring = ring
        # ws → set of subscribed types
        self._subscribers: dict[ServerConnection, set[str]] = {}

    async def handle(self, ws: ServerConnection) -> None:
        remote = ws.remote_address
        log.info("Subscriber connected: %s", remote)

        # Default: subscribe to all event types
        subscriptions: set[str] = set(self.ALL_TYPES)
        self._subscribers[ws] = subscriptions

        try:
            # Send ring buffer history immediately
            history = self.ring.snapshot()
            if history:
                for event in history:
                    if event["type"] in subscriptions:
                        try:
                            await ws.send(json.dumps(event))
                        except Exception:
                            break
                log.info("Sent %d history events to %s", len(history), remote)

            # Process incoming messages (subscription updates)
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    if "subscribe" in msg:
                        requested = set(msg["subscribe"])
                        valid = requested & self.ALL_TYPES
                        invalid = requested - self.ALL_TYPES
                        if invalid:
                            log.warning("Unknown event types from %s: %s", remote, invalid)
                        subscriptions = valid if valid else set(self.ALL_TYPES)
                        self._subscribers[ws] = subscriptions
                        log.info("Subscriber %s updated subscriptions: %s", remote, subscriptions)
                        # Resend relevant history with new filter
                        history = self.ring.snapshot()
                        for event in history:
                            if event["type"] in subscriptions:
                                try:
                                    await ws.send(json.dumps(event))
                                except Exception:
                                    break
                except json.JSONDecodeError:
                    log.warning("Invalid JSON from subscriber %s", remote)

        except websockets.exceptions.ConnectionClosedOK:
            pass
        except websockets.exceptions.ConnectionClosedError as exc:
            log.info("Subscriber %s disconnected: %s", remote, exc)
        except Exception as exc:
            log.error("Subscriber %s error: %s", remote, exc)
        finally:
            self._subscribers.pop(ws, None)
            log.info("Subscriber disconnected: %s", remote)

    async def broadcast(self, event: dict) -> None:
        """Broadcast an event to all subscribers that want it."""
        if not self._subscribers:
            return
        event_type = event["type"]
        payload = json.dumps(event)
        dead: list[ServerConnection] = []
        for ws, subs in list(self._subscribers.items()):
            if event_type in subs:
                try:
                    await ws.send(payload)
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self._subscribers.pop(ws, None)

    @property
    def count(self) -> int:
        return len(self._subscribers)


# ── Upstream connector ────────────────────────────────────────────────────────

async def upstream_loop(
    manifold_ws_url: str,
    state: MeshState,
    ring: RingBuffer,
    sub_manager: SubscriberManager,
    stop_event: asyncio.Event,
) -> None:
    """
    Connect to Manifold WS with exponential backoff. Process all incoming
    mesh messages and emit events to subscribers.
    """
    backoff = 1.0
    max_backoff = 60.0

    while not stop_event.is_set():
        try:
            log.info("Connecting to Manifold WS: %s", manifold_ws_url)
            async with websockets.connect(
                manifold_ws_url,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                log.info("Connected to Manifold WS")
                backoff = 1.0  # reset on successful connect

                async for raw in ws:
                    if stop_event.is_set():
                        break
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        log.warning("Non-JSON message from Manifold WS: %r", raw[:200])
                        continue

                    msg_type = msg.get("type")
                    if msg_type not in ("mesh_sync", "mesh_delta"):
                        # Not a mesh state message; ignore (pings, etc.)
                        continue

                    log.debug("Received %s (version=%s)", msg_type, msg.get("version", "?"))

                    events = state.ingest(msg)

                    if events:
                        log.info(
                            "Emitting %d events (types: %s) to %d subscriber(s)",
                            len(events),
                            {e["type"] for e in events},
                            sub_manager.count,
                        )

                    for event in events:
                        ring.append(event)
                        await sub_manager.broadcast(event)

        except asyncio.CancelledError:
            break
        except websockets.exceptions.ConnectionClosedOK:
            log.info("Manifold WS closed cleanly — reconnecting in %.0fs", backoff)
        except websockets.exceptions.ConnectionClosedError as exc:
            log.warning("Manifold WS closed with error: %s — reconnecting in %.0fs", exc, backoff)
        except OSError as exc:
            log.warning("Cannot reach Manifold WS: %s — retrying in %.0fs", exc, backoff)
        except Exception as exc:
            log.error("Unexpected error from Manifold WS: %s — retrying in %.0fs", exc, backoff)

        if stop_event.is_set():
            break

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            pass

        backoff = min(backoff * 2, max_backoff)


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="fog-event-relay — real-time Manifold mesh mutation broadcaster",
    )
    parser.add_argument(
        "--manifold-ws",
        default=os.environ.get("MANIFOLD_WS", "ws://localhost:8768"),
        help="Manifold WebSocket URL (default: ws://localhost:8768)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("RELAY_PORT", "8790")),
        help="Subscriber WebSocket port (default: 8790)",
    )
    parser.add_argument(
        "--seam-threshold",
        type=float,
        default=float(os.environ.get("SEAM_THRESHOLD", "0.05")),
        help="Seam tension delta threshold for seam.shift events (default: 0.05)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("RELAY_DEBUG", "").lower() in ("1", "true", "yes"),
        help="Enable debug logging",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    log.info(
        "fog-event-relay starting — upstream=%s port=%d seam_threshold=%.3f",
        args.manifold_ws,
        args.port,
        args.seam_threshold,
    )

    ring = RingBuffer(maxlen=RING_SIZE)
    state = MeshState(seam_threshold=args.seam_threshold)
    sub_manager = SubscriberManager(ring=ring)
    stop_event = asyncio.Event()

    # Graceful shutdown
    loop = asyncio.get_running_loop()

    def _shutdown(sig_name: str) -> None:
        log.info("Received %s — shutting down", sig_name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig.name)

    # Start subscriber WebSocket server
    async def _subscriber_handler(ws: ServerConnection) -> None:
        await sub_manager.handle(ws)

    server = await websockets.serve(
        _subscriber_handler,
        host="0.0.0.0",
        port=args.port,
    )
    log.info("Subscriber server listening on :%d", args.port)

    # Start upstream loop
    upstream_task = asyncio.create_task(
        upstream_loop(
            manifold_ws_url=args.manifold_ws,
            state=state,
            ring=ring,
            sub_manager=sub_manager,
            stop_event=stop_event,
        ),
        name="upstream-loop",
    )

    # Wait for shutdown signal
    await stop_event.wait()

    log.info("Stopping upstream loop…")
    upstream_task.cancel()
    try:
        await upstream_task
    except asyncio.CancelledError:
        pass

    log.info("Closing subscriber server…")
    server.close()
    await server.wait_closed()

    log.info("fog-event-relay stopped")


if __name__ == "__main__":
    asyncio.run(main())
