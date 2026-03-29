"""
Manifold WebSocket broker.

Run with:
    python -m manifold.server
    python -m manifold.server --host 0.0.0.0 --port 8765

Agents, humans, and browser clients connect to ws://host:port.
The broker fans out published messages to all subscribers on a topic.

Protocol (JSON over WebSocket):
    {"type": "connect",     "agent": "<name>"}
    {"type": "subscribe",   "topic": "<topic>"}
    {"type": "unsubscribe", "topic": "<topic>"}
    {"type": "publish",     "topic": "<topic>", "from": "<name>", "data": {...}}

Incoming messages to subscribers:
    {"topic": "<topic>", "from": "<name>", "data": {...}}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict

try:
    import websockets
except ImportError:
    raise RuntimeError("websockets not installed. pip install websockets")

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger("manifold.server")

# topic -> connected websockets
_subscriptions: dict[str, set] = defaultdict(set)
# ws -> agent name
_agents: dict = {}


async def _handler(ws, path: str = "/") -> None:
    _agents[ws] = f"anon-{id(ws)}"
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
                kind = msg.get("type")

                if kind == "connect":
                    name = msg.get("agent") or _agents[ws]
                    _agents[ws] = name
                    log.info(f"[+] {name}")

                elif kind == "subscribe":
                    topic = msg.get("topic")
                    if topic:
                        _subscriptions[topic].add(ws)

                elif kind == "unsubscribe":
                    topic = msg.get("topic")
                    if topic:
                        _subscriptions[topic].discard(ws)

                elif kind == "publish":
                    topic = msg.get("topic")
                    if topic:
                        envelope = json.dumps({
                            "topic": topic,
                            "from": msg.get("from") or _agents.get(ws),
                            "data": msg.get("data", {}),
                        })
                        dead = set()
                        for sub in list(_subscriptions.get(topic, set())):
                            if sub is ws:
                                continue  # don't echo to sender
                            try:
                                await sub.send(envelope)
                            except Exception:
                                dead.add(sub)
                        if dead:
                            _subscriptions[topic] -= dead

            except Exception:
                pass
    finally:
        name = _agents.pop(ws, None)
        for subs in _subscriptions.values():
            subs.discard(ws)
        if name:
            log.info(f"[-] {name}")


async def main(host: str = "0.0.0.0", port: int = 8765) -> None:
    log.info(f"Manifold broker  ws://{host}:{port}")
    async with websockets.serve(_handler, host, port):
        await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manifold WebSocket broker")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8765, help="Port")
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port))
