"""
FogSubscriber — async client for the fog event bus.

Connects to the fog-event-relay (WS :8790), subscribes to event types,
and dispatches typed events to registered handlers.

Features:
- Auto-reconnect with exponential backoff
- Fallback to direct Manifold WS polling if relay is down
- Ring buffer replay for late subscribers
- Clean async API with type hints
"""

import asyncio
import json
import logging
import random
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from collections import deque

import websockets
from websockets.asyncio.client import connect as ws_connect

from .types import EventType, FogEvent

logger = logging.getLogger("fog_client")

# Type aliases
Handler = Callable[[FogEvent], Awaitable[None]]


class FogSubscriber:
    """
    Async subscriber for the fog event relay.

    Usage::

        client = FogSubscriber("ws://localhost:8790")
        client.subscribe(["seam.shift", "dark.pressure"])

        @client.on("seam.shift")
        async def handle(event):
            print(event.data.seam, event.data.delta)

        await client.run()
    """

    def __init__(
        self,
        relay_url: str = "ws://localhost:8790",
        *,
        manifold_url: str = "ws://localhost:8768",
        subscriptions: Optional[List[str]] = None,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
        backoff_jitter: float = 0.1,
        ring_buffer_size: int = 100,
        reconnect_timeout: float = 30.0,
    ):
        self._relay_url = relay_url
        self._manifold_url = manifold_url
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._backoff_jitter = backoff_jitter
        self._reconnect_timeout = reconnect_timeout

        # Subscriptions
        self._subscriptions: Set[EventType] = set()
        if subscriptions:
            self._subscriptions = {EventType(s) for s in subscriptions}

        # Handlers: event type → list of async callables
        self._handlers: Dict[EventType, List[Handler]] = {}
        # Wildcard handlers (called for every event)
        self._wildcard_handlers: List[Handler] = []

        # Ring buffer for late subscriber replay
        self._ring_buffer: deque[FogEvent] = deque(maxlen=ring_buffer_size)

        # State
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_attempts = 0

    # ── Public API ──────────────────────────────────────────────────────────

    def subscribe(self, event_types: List[str]) -> "FogSubscriber":
        """Add event types to subscribe to. Chainable."""
        for et in event_types:
            self._subscriptions.add(EventType(et))
        return self

    def unsubscribe(self, event_types: List[str]) -> "FogSubscriber":
        """Remove event types. Chainable."""
        for et in event_types:
            self._subscriptions.discard(EventType(et))
        return self

    def on(self, event_type: str) -> Callable:
        """
        Decorator to register an async handler for an event type.

            @client.on("seam.shift")
            async def handle_seam(event: FogEvent):
                ...
        """
        et = EventType(event_type)

        def decorator(func: Handler) -> Handler:
            self._handlers.setdefault(et, []).append(func)
            return func

        return decorator

    def on_any(self, func: Handler) -> Handler:
        """Register a handler called for every event."""
        self._wildcard_handlers.append(func)
        return func

    def recent_events(self, limit: int = 50) -> List[FogEvent]:
        """Return the last N events from the ring buffer."""
        events = list(self._ring_buffer)
        return events[-limit:]

    async def run(self) -> None:
        """
        Main entry point. Connects to relay and dispatches events.
        Reconnects automatically with backoff.
        Falls back to direct Manifold WS if relay is persistently unavailable.
        """
        self._running = True
        while self._running:
            try:
                await self._connect_relay()
            except Exception as e:
                logger.warning(f"Relay connection failed: {e}")
                self._reconnect_attempts += 1
                delay = self._compute_backoff()
                logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})")

                # After many failures, try direct Manifold WS
                if self._reconnect_attempts >= 5:
                    logger.warning("Relay persistent failure — falling back to direct Manifold WS")
                    try:
                        await self._connect_manifold_fallback()
                        # If fallback exits normally, reset and retry relay
                        self._reconnect_attempts = 0
                        continue
                    except Exception as fallback_err:
                        logger.error(f"Manifold fallback also failed: {fallback_err}")

                await asyncio.sleep(delay)

    async def stop(self) -> None:
        """Gracefully shut down the subscriber."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()

    # ── Connection ──────────────────────────────────────────────────────────

    async def _connect_relay(self) -> None:
        """Connect to fog-event-relay and process events."""
        async with ws_connect(
            self._relay_url,
            close_timeout=self._reconnect_timeout,
        ) as ws:
            self._ws = ws
            self._reconnect_attempts = 0
            logger.info(f"Connected to relay at {self._relay_url}")

            # Send subscription filter
            if self._subscriptions:
                sub_msg = json.dumps({
                    "subscribe": [et.value for et in self._subscriptions]
                })
                await ws.send(sub_msg)
                logger.debug(f"Subscribed to: {[et.value for et in self._subscriptions]}")

            # Request ring buffer replay for late start
            await ws.send(json.dumps({"replay": True}))

            # Dispatch loop
            async for raw_message in ws:
                await self._handle_raw(raw_message)

    async def _connect_manifold_fallback(self) -> None:
        """
        Fallback: connect directly to Manifold's WS and synthesize fog events
        from raw mesh mutations.

        This is less efficient (no precomputed fog deltas) but works when the
        relay is down. We watch for mesh_sync and mesh_delta messages and
        emit mesh.mutation events.
        """
        logger.info(f"Falling back to direct Manifold WS at {self._manifold_url}")
        async with ws_connect(self._manifold_url) as ws:
            # Manifold doesn't need subscription filters — we filter locally
            async for raw_message in ws:
                try:
                    payload = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue

                msg_type = payload.get("type", "")

                # Synthesize mesh.mutation from relevant Manifold messages
                if msg_type in ("peer_announce", "peer_bye", "mesh_sync", "mesh_delta"):
                    from .types import MeshMutationData, FogEvent
                    from datetime import datetime, timezone

                    mutation = MeshMutationData(
                        mutation_type=msg_type,
                        agent=payload.get("hub"),
                        hub=payload.get("hub"),
                        details=payload,
                    )
                    event = FogEvent(
                        type=EventType.MESH_MUTATION,
                        timestamp=datetime.now(timezone.utc),
                        data=mutation,
                        raw=payload,
                    )

                    # Only dispatch if subscribed to mesh.mutation
                    if EventType.MESH_MUTATION in self._subscriptions or not self._subscriptions:
                        await self._dispatch(event)

    # ── Event Processing ────────────────────────────────────────────────────

    async def _handle_raw(self, raw: str | bytes) -> None:
        """Parse a raw WS message and dispatch to handlers."""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug(f"Skipping non-JSON message: {raw[:100]}")
            return

        # Handle replay batch (array of events)
        if isinstance(payload, list):
            for item in payload:
                await self._process_event(item)
            return

        # Single event
        await self._process_event(payload)

    async def _process_event(self, payload: Dict[str, Any]) -> None:
        """Parse and dispatch a single event."""
        try:
            event = FogEvent.from_dict(payload)
        except (KeyError, ValueError) as e:
            logger.debug(f"Skipping malformed event: {e} — {payload}")
            return

        # Filter: skip if not subscribed
        if self._subscriptions and event.type not in self._subscriptions:
            return

        self._ring_buffer.append(event)
        await self._dispatch(event)

    async def _dispatch(self, event: FogEvent) -> None:
        """Run all matching handlers for an event."""
        handlers = self._handlers.get(event.type, []) + self._wildcard_handlers
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Handler {handler.__name__} failed: {e}", exc_info=True)

    # ── Backoff ─────────────────────────────────────────────────────────────

    def _compute_backoff(self) -> float:
        """Exponential backoff with jitter."""
        delay = min(
            self._backoff_base * (2 ** self._reconnect_attempts),
            self._backoff_max,
        )
        jitter = delay * self._backoff_jitter * random.random()
        return delay + jitter
