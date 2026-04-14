"""In-memory transport — for testing and single-machine multi-agent setups."""

import asyncio
from typing import Any, Callable, Coroutine

from .base import Transport


# Global bus shared across all MemoryTransport instances in the same process
_BUS: dict[str, list[Callable]] = {}
_BUS_LOCK = asyncio.Lock()


class MemoryTransport(Transport):
    """
    Pure in-process pub/sub transport.

    All MemoryTransport instances in the same Python process share a single
    in-memory bus, making it trivial to run multi-agent tests without any
    external infrastructure.

    URI scheme: memory://local
    """

    def __init__(self) -> None:
        self._agent_name: str | None = None
        self._subscriptions: dict[str, Callable] = {}
        self._connected = False

    async def connect(self, agent_name: str) -> None:
        """Register on the in-memory bus."""
        self._agent_name = agent_name
        self._connected = True

    async def disconnect(self) -> None:
        """Deregister all subscriptions."""
        global _BUS
        async with _BUS_LOCK:
            for topic in list(self._subscriptions):
                handlers = _BUS.get(topic, [])
                handler = self._subscriptions[topic]
                if handler in handlers:
                    handlers.remove(handler)
        self._subscriptions.clear()
        self._connected = False

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        """Fan out message to all subscribers of the topic."""
        async with _BUS_LOCK:
            handlers = list(_BUS.get(topic, []))

        envelope = {"topic": topic, "from": self._agent_name, "data": data}
        for handler in handlers:
            asyncio.create_task(handler(envelope))

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Coroutine],
    ) -> None:
        """Subscribe to a topic."""
        async with _BUS_LOCK:
            _BUS.setdefault(topic, [])
            _BUS[topic].append(handler)
        self._subscriptions[topic] = handler

    async def unsubscribe(self, topic: str) -> None:
        """Remove subscription for a topic."""
        async with _BUS_LOCK:
            handler = self._subscriptions.pop(topic, None)
            if handler and topic in _BUS:
                try:
                    _BUS[topic].remove(handler)
                except ValueError:
                    pass

    @property
    def is_connected(self) -> bool:
        return self._connected
