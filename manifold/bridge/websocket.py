"""WebSocket transport adapter for Manifold."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine
from urllib.parse import urlparse

from .base import Transport


class WebSocketTransport(Transport):
    """
    Connects a Manifold agent to a WebSocket pub/sub broker.

    URI scheme: ws://host:port  (default port 8765)

    Run the broker with:
        python -m manifold.server

    Agents, humans, and browser clients all connect the same way.
    No extra infrastructure — just the broker process.
    """

    def __init__(self, host: str, port: int = 8765) -> None:
        self._host = host
        self._port = port
        self._uri = f"ws://{host}:{port}"
        self._agent_name: str | None = None
        self._handlers: dict[str, list[Callable]] = {}
        self._ws: Any = None
        self._recv_task: asyncio.Task | None = None
        self._connected = False

    @classmethod
    def from_uri(cls, uri: str) -> "WebSocketTransport":
        parsed = urlparse(uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8765
        return cls(host=host, port=port)

    async def connect(self, agent_name: str) -> None:
        try:
            import websockets
        except ImportError as e:
            raise RuntimeError(
                "websockets not installed. pip install websockets"
            ) from e
        self._agent_name = agent_name
        self._ws = await websockets.connect(self._uri)
        await self._ws.send(json.dumps({"type": "connect", "agent": agent_name}))
        self._recv_task = asyncio.create_task(self._recv_loop())
        self._connected = True

    async def disconnect(self) -> None:
        if self._recv_task:
            self._recv_task.cancel()
        if self._ws:
            await self._ws.close()
        self._connected = False

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        assert self._ws, "Not connected"
        await self._ws.send(json.dumps({
            "type": "publish",
            "topic": topic,
            "from": self._agent_name,
            "data": data,
        }))

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[dict[str, Any]], Coroutine],
    ) -> None:
        assert self._ws, "Not connected"
        if topic not in self._handlers:
            self._handlers[topic] = []
            await self._ws.send(json.dumps({"type": "subscribe", "topic": topic}))
        self._handlers[topic].append(handler)

    async def unsubscribe(self, topic: str) -> None:
        assert self._ws, "Not connected"
        self._handlers.pop(topic, None)
        await self._ws.send(json.dumps({"type": "unsubscribe", "topic": topic}))

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                    topic = msg.get("topic")
                    if topic and topic in self._handlers:
                        for handler in self._handlers[topic]:
                            await handler(msg.get("data", msg))
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected
