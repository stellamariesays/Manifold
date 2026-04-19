#!/usr/bin/env python3
"""
Quickstart agent for Manifold mesh.
Connects to a local hub, registers as "hello-mesh", and responds to "greet" commands.

Usage:
    1. Start your Manifold server
    2. python3 quickstart-agent.py

Or use with the runner:
    python3 src/runtime/agent-runner.py --config quickstart-config.json
"""

import json
import sys
import time
import uuid
import threading

try:
    import websocket  # pip install websocket-client
except ImportError:
    print("Install websocket-client: pip install websocket-client")
    sys.exit(1)

# ── Config ──────────────────────────────────────────────────────────────────
WS_URL = "ws://localhost:8768"
HUB_NAME = "my-hub"
AGENT_NAME = "hello-mesh"
CAPABILITIES = ["greeting", "echo"]

# ── Task handler ────────────────────────────────────────────────────────────
def handle_task(task: dict) -> dict:
    """Process a task_request and return a task_result."""
    command = task.get("command", "")
    args = task.get("args", {})
    task_id = task.get("id", str(uuid.uuid4()))
    
    if command == "greet":
        name = args.get("name", "world")
        output = {"message": f"Hello, {name}! Welcome to the mesh."}
        status = "success"
    elif command == "echo":
        output = {"echo": args}
        status = "success"
    else:
        output = None
        status = "error"
    
    return {
        "type": "task_result",
        "result": {
            "id": task_id,
            "status": status,
            "output": output,
            "error": f"Unknown command: {command}" if status == "error" else None,
            "executed_by": AGENT_NAME,
            "execution_ms": 0,
            "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    }

# ── WebSocket callbacks ────────────────────────────────────────────────────
def on_open(ws):
    """Send agent_runner_ready as soon as we connect."""
    msg = {
        "type": "agent_runner_ready",
        "hub": HUB_NAME,
        "agents": [{
            "name": AGENT_NAME,
            "capabilities": CAPABILITIES,
        }]
    }
    ws.send(json.dumps(msg))
    print(f"[+] Registered {AGENT_NAME} with capabilities: {CAPABILITIES}")

def on_message(ws, data):
    """Handle incoming messages."""
    try:
        msg = json.loads(data)
    except json.JSONDecodeError:
        return
    
    msg_type = msg.get("type", "")
    
    if msg_type == "task_request":
        task = msg.get("task", {})
        print(f"[→] Task: {task.get('command')} from {task.get('origin')}")
        result = handle_task(task)
        ws.send(json.dumps(result))
        print(f"[←] Result: {result['result']['status']}")
    
    elif msg_type == "ping":
        ws.send(json.dumps({"type": "pong", "timestamp": msg.get("timestamp")}))

def on_error(ws, error):
    print(f"[!] Error: {error}")

def on_close(ws, code, reason):
    print(f"[-] Disconnected (code={code})")

# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Connecting to {WS_URL}...")
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever(reconnect=5)
