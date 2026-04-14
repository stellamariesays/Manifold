"""Subway transport adapter — connects Manifold agents over Subway's P2P mesh."""

import asyncio
import json
from typing import Any, Callable, Coroutine
from urllib.parse import urlparse

import httpx

from .base import Transport


class SubwayTransport(Transport):
    """
    Adapts Manifold's pub/sub interface to Subway's REST bridge.

    Subway provides P2P networking with a local REST bridge. This adapter
    translates Manifold topic pub/sub to Subway POST /publish and GET /subscribe
    endpoints.

    URI scheme: subway://host:port
                subway://localhost:8765

    Subway REST bridge endpoints used:
        POST /publish   — body: {topic, data}
        GET  /subscribe — query: topic=<topic> (SSE stream)
    """

    def __init__(self, host: str, port: int = 8765) -> None:
        self._host = host
        self._port = port
        self._base_url = f"http://{host}:{port}"
        self._agent_name: str | None = None
        self._subscriptions: dict[str, asyncio.Task] = {}
        self._connected = False
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_uri(cls, uri: str) -> "SubwayTransport":
        """Parse a subway:// URI and return a configured transport."""
        parsed = urlparse(uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8765
        return cls(host=host, port=port)

    async def connect(self, agent_name: str) -> None:
        """Open HTTP client and announce agent to the Subway mesh."""
        self._agent_name = agent_name
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)
        # Announce agent presence
        await self._client.post(
            "/agents/register",
            json={"name": agent_name},
        )
        self._connected = True

    async def disconnect(self) -> None:
        """Cancel all subscription pollers and close HTTP client."""
        for task in self._subscriptions.values():
            task.cancel()
        self._subscriptions.clear()
        if self._client:
            await self._client.aclose()
        self._connected = False

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        """POST a message to a Subway topic."""
        assert self._client, "Not connected"
        await self._client.post(
            "/publish",
            json={"topic": topic, "from": self._agent_name, "data": data},
        )

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Coroutine],
    ) -> None:
        """Subscribe to a Subway topic via SSE stream."""
        assert self._client, "Not connected"
        task = asyncio.create_task(self._poll(topic, handler))
        self._subscriptions[topic] = task

    async def unsubscribe(self, topic: str) -> None:
        """Cancel the subscription poller for a topic."""
        task = self._subscriptions.pop(topic, None)
        if task:
            task.cancel()

    async def _poll(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Coroutine],
    ) -> None:
        """Long-poll the Subway SSE stream for a topic."""
        assert self._client
        url = f"/subscribe?topic={topic}&agent={self._agent_name}"
        try:
            async with self._client.stream("GET", url) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        payload = json.loads(line[5:].strip())
                        await handler(payload)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            # Log and retry — real impl would use exponential backoff
            print(f"[Subway] stream error on {topic}: {exc}")

    @property
    def is_connected(self) -> bool:
        return self._connected
