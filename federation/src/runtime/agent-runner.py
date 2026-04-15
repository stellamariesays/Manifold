#!/usr/bin/env python3
"""
Agent Runner (Python) — executes agent scripts and connects to federation.

Connects to the local federation WebSocket, listens for task_request messages,
spawns agent scripts, captures JSON stdout, returns task_result.

Usage:
    python3 agent-runner.py --config runner-config.json --ws ws://localhost:8768

Config format (JSON):
    {
        "hub": "hog",
        "wsUrl": "ws://localhost:8768",
        "defaultTimeoutMs": 30000,
        "agents": [
            {
                "name": "cron-monitor",
                "script": "projects/cron-monitor-void/cron-monitor-agent.py",
                "cwd": "/home/marvin/.openclaw/workspace",
                "timeout_ms": 600,
                "maxConcurrency": 1
            }
        ]
    }
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Minimal deps — only stdlib + websocket-client
try:
    import websocket  # type: ignore
except ImportError:
    print("pip install websocket-client")
    sys.exit(1)


# ── Config ──────────────────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ── Runner ──────────────────────────────────────────────────────────────────────

class AgentRunner:
    def __init__(self, config: dict):
        self.hub = config["hub"]
        self.ws_url = config.get("wsUrl", "ws://localhost:8768")
        self.default_timeout = config.get("defaultTimeoutMs", 30000)
        self.agents = {a["name"]: a for a in config.get("agents", [])}
        self.ws: websocket.WebSocketApp | None = None
        self.running_tasks: dict[str, subprocess.Popen] = {}

    def start(self) -> None:
        self.log(f"Connecting to {self.ws_url}")
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_close=self._on_close,
            on_error=self._on_error,
        )
        self.ws.run_forever(reconnect=5)

    def stop(self) -> None:
        if self.ws:
            self.ws.close()
        for task_id, proc in self.running_tasks.items():
            proc.kill()
        self.running_tasks.clear()

    # ── WebSocket handlers ──────────────────────────────────────────────────

    def _on_open(self, ws) -> None:
        self.log(f"Connected to federation at {self.ws_url}")
        # Register
        self._send({
            "type": "agent_runner_ready",
            "hub": self.hub,
            "agents": list(self.agents.keys()),
        })

    def _on_message(self, ws, data: str) -> None:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return

        if msg.get("type") == "task_request":
            task = msg.get("task", {})
            self._execute_task(task)

    def _on_close(self, ws, code, reason) -> None:
        self.log(f"Disconnected (code={code})")
        # run_forever with reconnect handles reconnection

    def _on_error(self, ws, error) -> None:
        self.log(f"WebSocket error: {error}")

    # ── Task execution ──────────────────────────────────────────────────────

    def _execute_task(self, task: dict) -> None:
        target = task.get("target", "")
        agent_name = target.split("@")[0] if "@" in target else target

        if agent_name not in self.agents:
            self._send_result({
                "id": task.get("id", ""),
                "status": "not_found",
                "error": f"Agent not found: {agent_name}",
                "executed_by": f"{agent_name}@{self.hub}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            return

        agent_cfg = self.agents[agent_name]
        timeout_ms = task.get("timeout_ms") or agent_cfg.get("timeout_ms") or self.default_timeout
        command = task.get("command", "")
        args = task.get("args", {})

        self.log(f"Executing: {agent_name} {command} (task {task.get('id', '?')[:8]}...)")

        start_time = time.monotonic()

        # Build command line
        cmd = [sys.executable or "python3", agent_cfg["script"], command]
        if args:
            cmd.append(json.dumps(args))

        cwd = agent_cfg.get("cwd")

        # Send ack
        self._send({
            "type": "task_ack",
            "task_id": task.get("id", ""),
            "queue_position": 0,
        })

        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000,
            )
            execution_ms = int((time.monotonic() - start_time) * 1000)

            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    output = json.loads(proc.stdout.strip())
                except json.JSONDecodeError:
                    output = {"text": proc.stdout.strip()}

                self._send_result({
                    "id": task["id"],
                    "status": "success",
                    "output": output,
                    "executed_by": f"{agent_name}@{self.hub}",
                    "execution_ms": execution_ms,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                self.log(f"Success: {agent_name} ({execution_ms}ms)")
            else:
                error = proc.stderr.strip() or f"Exit code {proc.returncode}"
                self._send_result({
                    "id": task["id"],
                    "status": "error",
                    "error": error,
                    "output": {"raw": proc.stdout.strip()} if proc.stdout.strip() else None,
                    "executed_by": f"{agent_name}@{self.hub}",
                    "execution_ms": execution_ms,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                self.log(f"Error: {agent_name} — {error} ({execution_ms}ms)")

        except subprocess.TimeoutExpired:
            execution_ms = int((time.monotonic() - start_time) * 1000)
            self._send_result({
                "id": task["id"],
                "status": "timeout",
                "error": f"Agent timed out after {timeout_ms}ms",
                "executed_by": f"{agent_name}@{self.hub}",
                "execution_ms": execution_ms,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            self.log(f"Timeout: {agent_name} ({timeout_ms}ms)")

        except Exception as e:
            execution_ms = int((time.monotonic() - start_time) * 1000)
            self._send_result({
                "id": task["id"],
                "status": "error",
                "error": str(e),
                "executed_by": f"{agent_name}@{self.hub}",
                "execution_ms": execution_ms,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _send(self, msg: dict) -> None:
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self.ws.send(json.dumps(msg))

    def _send_result(self, result: dict) -> None:
        self._send({"type": "task_result", "result": result})

    def log(self, msg: str) -> None:
        print(f"[AgentRunner:{self.hub}] {msg}", flush=True)


# ── CLI ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manifold Agent Runner")
    parser.add_argument("--config", default="runner-config.json", help="Path to config JSON")
    parser.add_argument("--ws", default=None, help="Override WebSocket URL")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.ws:
        config["wsUrl"] = args.ws

    runner = AgentRunner(config)

    def shutdown(sig, frame):
        runner.log("Shutting down...")
        runner.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    runner.start()
