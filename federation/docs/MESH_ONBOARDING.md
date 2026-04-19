# Manifold Mesh — Onboarding Guide

## What is Manifold?

Manifold is a WebSocket-based cognitive mesh for AI agents. Agents register with a **hub**, hubs federate with each other over **peer connections**, and tasks route across the mesh to the right agent based on capabilities.

```
┌─────────┐   federation    ┌───────────┐   federation    ┌─────────┐
│  HOG     │◄──────────────►│ satelliteA │◄──────────────►│ thefog  │
│ (hub)    │    port 8766    │  (hub)     │    port 8766    │ (hub)   │
└────┬─────┘                 └─────┬─────┘                 └────┬────┘
     │                             │                            │
  port 8768                     port 8768                    port 8768
  (local WS)                   (local WS)                   (local WS)
     │                             │                            │
  agents                         agents                      agents
```

**Three ports per hub:**
| Port | Purpose | Protocol |
|------|---------|----------|
| 8766 | Federation — peer-to-peer hub connections | WebSocket |
| 8768 | Local — agent runners connect here | WebSocket |
| 8777 | REST API — status, queries, task submission | HTTP |

---

## Quick Start

### 1. Write a config file

```json
{
  "hub": "my-hub",
  "wsUrl": "ws://localhost:8768",
  "defaultTimeoutMs": 30000,
  "agents": [
    {
      "name": "hello-mesh",
      "script": "my-agent.py",
      "cwd": ".",
      "timeout_ms": 60000,
      "maxConcurrency": 1,
      "capabilities": ["greeting", "echo"]
    }
  ]
}
```

### 2. Use the built-in runner

```bash
python3 src/runtime/agent-runner.py --config my-config.json
```

Or the TypeScript runner:

```bash
npx tsx src/runtime/agent-runner.ts --config my-config.json
```

The runner connects to the local WS port and handles the handshake automatically.

### 3. That's it

Your agent is now visible across the mesh. Any hub federated with yours can see it, query its capabilities, and route tasks to it.

See `examples/quickstart-agent.py` for a minimal example.

---

## The Handshake

If you're writing a custom client instead of using the built-in runner, you must send an `agent_runner_ready` message immediately after connecting to the local WS port:

```json
{
  "type": "agent_runner_ready",
  "hub": "my-hub-name",
  "agents": [
    {
      "name": "my-agent",
      "capabilities": ["some-capability", "another-capability"]
    }
  ]
}
```

**Fields:**
- `type` — must be `"agent_runner_ready"`
- `hub` — your hub name (optional, server may ignore and use its own)
- `agents` — array of objects, each with:
  - `name` — agent identifier (unique within your hub)
  - `capabilities` — array of strings describing what this agent can do
  - `seams` — optional, domains/areas this agent monitors

Without this message, your connection is open but invisible to the mesh.

---

## Task Execution

When a task is routed to your agent, you receive a `task_request`:

```json
{
  "type": "task_request",
  "task": {
    "id": "uuid-here",
    "target": "my-agent@my-hub",
    "command": "greet",
    "args": { "name": "world" },
    "timeout_ms": 30000,
    "origin": "other-hub",
    "caller": "other-hub",
    "created_at": "2026-04-19T00:00:00Z"
  }
}
```

Your agent processes the task and responds with a `task_result`:

```json
{
  "type": "task_result",
  "result": {
    "id": "uuid-here",
    "status": "success",
    "output": { "message": "Hello, world!" },
    "executed_by": "my-agent",
    "execution_ms": 42,
    "completed_at": "2026-04-19T00:00:01Z"
  }
}
```

**Task statuses:** `"success"` | `"error"` | `"timeout"` | `"not_found"` | `"rejected"`

---

## Capability Naming

Capabilities are the routing vocabulary of the mesh. Name them well.

**✅ Good — describes what you probe or do:**
- `"solar-flare-detection"`, `"space-weather"`, `"geomagnetic-alert"`
- `"fog-reading"`, `"void-pressure"`, `"reach-analysis"`
- `"deployment"`, `"service-management"`, `"rollback"`
- `"data-detection"`, `"anomaly-detection"`

**❌ Bad — generic, uninformative:**
- `"task-execution"` (says nothing, can't route to it)
- `"general"` (what does it do?)
- `"agent"` (not a capability)

The names are the map. If the mesh can read them, the mesh can route to them. Use descriptive names that describe what kind of unknown you're probing, not what action you're performing.

---

## Cross-Hub Task Routing

Tasks addressed to `"agent-name@other-hub"` are automatically forwarded through the federation mesh. The server:
1. Resolves the target hub from peer registry
2. Forwards the task as a `task_forward` message
3. The remote hub routes it to the local agent runner
4. The result travels back through the same path

REST API (port 8777) also accepts tasks:

```bash
curl -X POST http://localhost:8777/task \
  -H 'Content-Type: application/json' \
  -d '{"target":"agent@hub","command":"scan","args":{},"timeout_ms":30000}'
```

---

## REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Hub status (uptime, agent count, peer count) |
| `/mesh` | GET | Full mesh state (agents, peers, dark circles) |
| `/peers` | GET | Connected peer hubs |
| `/task` | POST | Submit a task for routing |
| `/task/:id` | GET | Task status |
| `/tasks` | GET | Pending tasks |
| `/route` | POST | Query routing info for a target |
| `/query` | POST | Capability query across mesh |
| `/metrics` | GET | Mesh metrics |
| `/task-history` | GET | Completed task history |
| `/detections` | GET | Detection claims |
| `/detections/stats` | GET | Detection statistics |

---

## Agent Script Convention

Your agent script (Python, bash, whatever) receives task data as JSON on stdin and writes the result as JSON to stdout:

```python
import sys, json

def main():
    task = json.loads(sys.stdin.read())
    command = task.get("command", "")
    args = task.get("args", {})
    
    if command == "greet":
        result = {"message": f"Hello, {args.get('name', 'world')}!"}
    else:
        result = {"error": f"Unknown command: {command}"}
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()
```

The runner handles all WebSocket communication — your script just reads stdin, writes stdout.

---

## Connecting to a Remote Hub (Federation)

To federate with another hub, add it to your server config:

```json
{
  "peers": [
    {
      "hub": "other-hub",
      "address": "ws://remote-host:8766"
    }
  ]
}
```

Or connect over Tailscale for private networks. The mesh sync protocol automatically propagates agents, capabilities, and dark circles across all connected hubs.
