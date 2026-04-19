#!/usr/bin/env python3
"""
Agent Runner (Python) — executes agent scripts and connects to federation.

Connects to the local federation WebSocket, listens for task_request messages,
spawns agent scripts or dispatches to OpenClaw, captures JSON stdout, returns task_result.

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
                "type": "script",
                "script": "projects/cron-monitor-void/cron-monitor-agent.py",
                "cwd": "/home/marvin/.openclaw/workspace",
                "timeout_ms": 60000,
                "maxConcurrency": 1
            },
            {
                "name": "stella",
                "type": "openclaw",
                "agentId": "stella",
                "capabilities": ["agent-orchestration", "conversation-strategy"],
                "timeout_ms": 120000,
                "maxConcurrency": 3
            }
        ]
    }

Agent types:
    "script"   — runs a Python script via subprocess (default). Script receives
                 (command, json_args) as positional args, writes JSON to stdout.
    "openclaw" — dispatches to OpenClaw via `openclaw agent --json --agent <id>`.
                 The task command+args become the prompt. Response parsed from JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError

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

# Heartbeat interval must be well under the server's TTL (60 s).
_HEARTBEAT_INTERVAL_S = 45


class AgentRunner:
    def __init__(self, config: dict):
        self.hub = config["hub"]
        self.ws_url = config.get("wsUrl", "ws://localhost:8768")
        self.rest_url = config.get("restUrl", self._ws_to_rest(self.ws_url))
        self.default_timeout = config.get("defaultTimeoutMs", 30000)
        self.agents = {a["name"]: a for a in config.get("agents", [])}
        self.ws: websocket.WebSocketApp | None = None
        self.running_tasks: dict[str, subprocess.Popen] = {}
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

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
        # Signal the heartbeat thread to exit and wait for it.
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)
        # Deregister from REST API on graceful shutdown
        self._deregister_all()
        if self.ws:
            self.ws.close()
        for task_id, proc in self.running_tasks.items():
            proc.kill()
        self.running_tasks.clear()

    # ── WebSocket handlers ──────────────────────────────────────────────────

    def _on_open(self, ws) -> None:
        self.log(f"Connected to federation at {self.ws_url}")

        # Register all agents via REST API (self-registration path)
        self._register_all()

        # Start background heartbeat thread (idempotent — skip if already live)
        self._start_heartbeat()

        # Also send legacy WS agent_runner_ready for backward compat
        agent_details = []
        for name, cfg in self.agents.items():
            agent_details.append({
                "name": name,
                "capabilities": cfg.get("capabilities", ["task-execution"]),
                "seams": cfg.get("seams", []),
            })
        self._send({
            "type": "agent_runner_ready",
            "hub": self.hub,
            "agents": agent_details,
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

        # Send ack
        self._send({
            "type": "task_ack",
            "task_id": task.get("id", ""),
            "queue_position": 0,
        })

        agent_type = agent_cfg.get("type", "script")
        if agent_type == "openclaw":
            self._execute_openclaw(task, agent_name, agent_cfg, timeout_ms)
        else:
            self._execute_script(task, agent_name, agent_cfg, timeout_ms, command, args)

    # ── Script execution (original path) ────────────────────────────────

    def _execute_script(self, task: dict, agent_name: str, agent_cfg: dict,
                        timeout_ms: int, command: str, args: dict) -> None:
        start_time = time.monotonic()

        # Build command line
        cmd = [sys.executable or "python3", agent_cfg["script"], command]
        if args:
            cmd.append(json.dumps(args))

        cwd = agent_cfg.get("cwd")

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

    # ── OpenClaw execution ──────────────────────────────────────────────

    def _execute_openclaw(self, task: dict, agent_name: str, agent_cfg: dict,
                          timeout_ms: int) -> None:
        """Execute a task via OpenClaw CLI (openclaw agent --json).

        The agent config should have:
            "type": "openclaw",
            "agentId": "stella",        # OpenClaw agent ID (default: "main")
            "channel": "telegram",       # optional delivery channel
        """
        start_time = time.monotonic()
        agent_id = agent_cfg.get("agentId", "main")

        # Build the prompt from the task
        command = task.get("command", "")
        args = task.get("args", {})
        parts = [command]
        if args:
            parts.append(json.dumps(args))
        prompt = " ".join(parts).strip() or "status"

        cmd = ["openclaw", "agent", "--json", "--agent", agent_id, "-m", prompt]

        # Optional channel
        channel = agent_cfg.get("channel")
        if channel:
            cmd.extend(["--channel", channel])

        self.log(f"OpenClaw dispatch: {agent_id} <- {prompt[:60]}...")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000,
                env={**os.environ, "PATH": os.environ.get("PATH", "")},
            )
            execution_ms = int((time.monotonic() - start_time) * 1000)

            if proc.returncode == 0 and proc.stdout.strip():
                # openclaw agent --json returns {"reply": "...", ...}
                try:
                    raw = json.loads(proc.stdout.strip())
                    # Extract the reply text; if it's JSON, parse it deeper
                    reply = raw.get("reply", raw.get("message", proc.stdout.strip()))
                    try:
                        output = json.loads(reply) if isinstance(reply, str) else reply
                    except (json.JSONDecodeError, TypeError):
                        output = {"text": reply}
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
                self.log(f"OpenClaw success: {agent_name} ({execution_ms}ms)")
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
                self.log(f"OpenClaw error: {agent_name} — {error[:100]} ({execution_ms}ms)")

        except subprocess.TimeoutExpired:
            execution_ms = int((time.monotonic() - start_time) * 1000)
            self._send_result({
                "id": task["id"],
                "status": "timeout",
                "error": f"OpenClaw agent timed out after {timeout_ms}ms",
                "executed_by": f"{agent_name}@{self.hub}",
                "execution_ms": execution_ms,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            self.log(f"OpenClaw timeout: {agent_name} ({timeout_ms}ms)")

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

    # ── Heartbeat ──────────────────────────────────────────────────────────

    def _start_heartbeat(self) -> None:
        """Start the background heartbeat thread if not already running."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="agent-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()
        self.log(f"Heartbeat thread started (interval={_HEARTBEAT_INTERVAL_S}s)")

    def _heartbeat_loop(self) -> None:
        """Send PUT /agents/:name/heartbeat for every registered agent.

        Runs every _HEARTBEAT_INTERVAL_S seconds.  Uses threading.Event.wait()
        so it wakes up immediately when stop() signals the event.
        """
        while not self._stop_event.wait(timeout=_HEARTBEAT_INTERVAL_S):
            for name in list(self.agents):
                self._send_heartbeat(name)

    def _send_heartbeat(self, name: str) -> None:
        """PUT /agents/:name/heartbeat — renew the server-side TTL."""
        try:
            req = Request(
                f"{self.rest_url}/agents/{name}/heartbeat",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urlopen(req, timeout=5) as resp:
                pass  # fire-and-forget; errors are non-fatal
        except Exception as e:
            self.log(f"Heartbeat {name} failed: {e}")

    # ── REST self-registration ─────────────────────────────────────────────

    @staticmethod
    def _ws_to_rest(ws_url: str) -> str:
        """Derive REST URL from WS URL (ws://host:8768 → http://host:8767)."""
        return ws_url.replace("ws://", "http://").replace("8768", "8767")

    def _register_all(self) -> None:
        """Register agents via WebSocket agent_register messages."""
        for name, cfg in self.agents.items():
            capabilities = cfg.get("capabilities", ["task-execution"])
            seams = cfg.get("seams", [])
            try:
                self._send({
                    "type": "agent_register",
                    "name": name,
                    "capabilities": capabilities,
                    "seams": seams,
                })
                self.log(f"WS register {name} sent ({len(capabilities)} caps)")
            except Exception as e:
                self.log(f"WS register {name} failed: {e}")
            # Also try REST for backward compat with older servers
            try:
                body = json.dumps({"name": name, "capabilities": capabilities}).encode()
                req = Request(
                    f"{self.rest_url}/agents/register",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read())
                    self.log(f"REST register {name}: {result.get('status', '?')} ({len(capabilities)} caps)")
            except Exception:
                pass  # WS path is primary, REST is optional

    def _deregister_all(self) -> None:
        """DELETE /agents/:name for each agent on shutdown."""
        for name in self.agents:
            try:
                req = Request(
                    f"{self.rest_url}/agents/{name}",
                    method="DELETE",
                )
                with urlopen(req, timeout=5) as resp:
                    self.log(f"REST deregister {name}: ok")
            except Exception as e:
                self.log(f"REST deregister {name} failed: {e}")

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
