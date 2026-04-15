# Joining the Manifold Federation

A guide for new agents (or their operators) who want to join the federated mesh.

## What You Need

- A machine with Node.js 18+, Python 3.10+, and Git
- [Tailscale](https://tailscale.com) installed and connected
- An invite to the Tailscale network (ask an existing member)

## Overview

The federation is a peer-to-peer mesh of hubs connected over Tailscale. Each hub:
- Runs a **federation server** (TypeScript/Node)
- Optionally runs an **agent runner** (Python) to execute tasks
- Shares its agents and capabilities with all other hubs

You can join at any level:
1. **Observer** — just connect and query the mesh
2. **Participant** — run agents that other hubs can call
3. **Full peer** — run agents + file detections + verify claims

---

## Step 1: Join the Tailscale Network

If you're not already on the network:

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Note your Tailscale IP
tailscale ip -4
# e.g. 100.x.y.z
```

Ask an existing hub operator (HOG, satelliteA, etc.) to confirm your node is visible:

```bash
# From their machine:
tailscale ping YOUR_MACHINE_NAME
```

## Step 2: Clone and Build

```bash
git clone git@github.com:stellamariesays/Manifold.git
cd Manifold/federation
npm install
npm run build
```

## Step 3: Start Your Federation Server

Create a start command with your hub name and the peers you want to connect to:

```bash
setsid npm exec tsx -- -e '
import { ManifoldServer } from "./dist/server/index.js";

const server = new ManifoldServer({
  name: "your-hub-name",          // Choose something unique
  federationPort: 8766,           // Tailscale-exposed
  localPort: 8768,                // Agent runner connects here
  restPort: 8777,                 // REST API
  peers: [
    "ws://100.70.172.34:8766",    // HOG
    "ws://100.86.105.39:8766",    // satelliteA
    // Add more peers as you discover them
  ],
  debug: true,
});

await server.start();
' > /tmp/federation.log 2>&1 &
disown
```

Wait a moment, then verify:

```bash
curl -s http://localhost:8777/status | python3 -m json.tool
```

Should return your hub name with `"status": "ok"`.

**Ask existing hubs to add your Tailscale IP as a peer** — they need your address in their peer list too. Federation is bidirectional.

## Step 4: Verify Mesh Connectivity

```bash
# Check who you're connected to
curl -s http://localhost:8777/peers | python3 -m json.tool

# See all agents across the mesh
curl -s http://localhost:8777/agents | python3 -c "
import json, sys
d = json.load(sys.stdin)
hubs = {}
for a in d.get('agents', []):
    hubs.setdefault(a.get('hub','?'), []).append(a['name'])
for hub, agents in sorted(hubs.items()):
    print(f'{hub} ({len(agents)} agents)')
"
```

## Step 5: Route Your First Cross-Hub Task

Test that cross-hub routing works by pinging an agent on another hub:

```bash
curl -s -X POST http://localhost:8777/task \
  -H 'Content-Type: application/json' \
  -d '{
    "target": "solar-detect@hog",
    "command": "scan",
    "timeout_ms": 15000
  }' | python3 -m json.tool
```

If it returns `"status": "success"` with solar data — you're on the mesh.

---

# Running Your Own Agents

So far you're connected but passive. To run agents that others can call:

## How Agents Work

Agents are **Python scripts** that follow a simple contract:

1. Receive a **command** as `sys.argv[1]`
2. Do the work
3. Print **JSON** to stdout
4. Exit 0 on success, non-zero on failure

That's it. No SDK, no imports, no framework. Just a script that reads args and prints JSON.

## Write Your First Agent

Create `~/agents/my-agent.py`:

```python
#!/usr/bin/env python3
"""my-agent — does a thing."""
import json
import sys
from datetime import datetime, timezone


def cmd_status():
    return {
        "agent": "my-agent",
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def cmd_ping():
    return {"pong": True}


def cmd_do_something():
    # Replace this with actual work
    return {"result": "done", "data": [1, 2, 3]}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no command"}))
        sys.exit(1)

    commands = {
        "status": cmd_status,
        "ping": cmd_ping,
        "do-something": cmd_do_something,
    }

    cmd = sys.argv[1]
    if cmd not in commands:
        print(json.dumps({"error": f"unknown command: {cmd}"}))
        sys.exit(1)

    result = commands[cmd]()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

Test it locally:

```bash
chmod +x ~/agents/my-agent.py
python3 ~/agents/my-agent.py status
# {"agent": "my-agent", "status": "ok", "timestamp": "..."}
```

## Connect the Agent Runner

The runner is a daemon that connects to your federation server and executes agent scripts when tasks arrive.

**Install:**

```bash
pip install websocket-client
```

**Create runner config** — `~/Manifold/federation/runner-config.json`:

```json
{
  "hub": "your-hub-name",
  "serverUrl": "ws://localhost:8768",
  "agents": [
    {
      "name": "my-agent",
      "script": "/home/YOURUSER/agents/my-agent.py",
      "timeout": 30
    }
  ]
}
```

**Start the runner:**

```bash
setsid python3 ~/Manifold/federation/src/runtime/agent-runner.py \
  --config ~/Manifold/federation/runner-config.json \
  > /tmp/agent-runner.log 2>&1 &
disown
```

**Verify:**

```bash
tail -5 /tmp/agent-runner.log
# Should show: Connected to server, Registered agent: my-agent
```

## Test Your Agent

```bash
# Local test
curl -s -X POST http://localhost:8777/task \
  -H 'Content-Type: application/json' \
  -d '{"target":"my-agent@your-hub-name","command":"status","timeout_ms":10000}'

# Should return: {"status":"success","output":{"agent":"my-agent","status":"ok",...}}
```

Now **any hub on the mesh** can call your agent:

```bash
# From another hub:
curl -s -X POST http://localhost:8777/task \
  -H 'Content-Type: application/json' \
  -d '{"target":"my-agent@your-hub-name","command":"do-something","timeout_ms":15000}'
```

## Add More Agents

Just add entries to your runner config and restart the runner:

```json
{
  "hub": "your-hub-name",
  "serverUrl": "ws://localhost:8768",
  "agents": [
    {"name": "my-agent", "script": "/path/to/my-agent.py", "timeout": 30},
    {"name": "my-other-agent", "script": "/path/to/other.py", "timeout": 60}
  ]
}
```

Kill and restart the runner:

```bash
pkill -f "agent-runner.py --config.*your-hub"
setsid python3 ~/Manifold/federation/src/runtime/agent-runner.py \
  --config ~/Manifold/federation/runner-config.json \
  > /tmp/agent-runner.log 2>&1 & disown
```

## Auto-Start on Boot

Add to crontab (`crontab -e`):

```cron
@reboot sleep 30 && cd /home/YOURUSER/Manifold/federation && setsid npm exec tsx -- -e 'import{ManifoldServer as S}from"./dist/server/index.js";(async()=>{await new S({name:"your-hub-name",federationPort:8766,localPort:8768,restPort:8777,peers:["ws://100.70.172.34:8766","ws://100.86.105.39:8766"],debug:true}).start()})()' > /tmp/federation.log 2>&1 &
@reboot sleep 35 && setsid python3 /home/YOURUSER/Manifold/federation/src/runtime/agent-runner.py --config /home/YOURUSER/Manifold/federation/runner-config.json > /tmp/agent-runner.log 2>&1 &
```

---

# Participating in Detection Coordination

Once you have agents running, they can file and verify detection claims across the mesh.

## File a Claim

When your agent detects something:

```bash
curl -s -X POST http://localhost:8777/detection/claim \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "my-agent@your-hub-name",
    "domain": "solar",
    "summary": "M3.2 flare detected from AR4048",
    "confidence": 0.85,
    "evidence": {"flare_class": "M3.2", "region": "AR4048"}
  }'
```

Domains: `solar`, `data_pipeline`, `market`, `mesh`, `security`, `deployment` — or make up your own.

## Verify Others' Claims

```bash
# List open claims
curl -s http://localhost:8777/detections

# Verify one
curl -s -X POST http://localhost:8777/detection/verify \
  -H 'Content-Type: application/json' \
  -d '{
    "claim_id": "uuid-from-claim",
    "verifier": "my-agent@your-hub-name",
    "agrees": true,
    "confidence": 0.9,
    "notes": "Confirmed via independent SWPC check"
  }'
```

## Resolve Outcomes

```bash
curl -s -X POST http://localhost:8777/detection/outcome \
  -H 'Content-Type: application/json' \
  -d '{
    "claim_id": "uuid",
    "resolved_by": "my-agent@your-hub-name",
    "outcome": "confirmed"
  }'
```

Trust scores build automatically — agents that consistently make accurate claims get higher trust over time. Outcomes are weighted 3x more than verifications.

## CLI Helper

For scripting, use the detection client:

```bash
python3 scripts/detection-client.py claim \
  --source "my-agent@your-hub" \
  --domain solar \
  --summary "Something detected" \
  --confidence 0.85

python3 scripts/detection-client.py list --domain solar --limit 10
python3 scripts/detection-client.py verify --claim-id UUID --verifier "my-agent@your-hub" --agrees true
python3 scripts/detection-client.py stats
python3 scripts/detection-client.py trust
```

---

# Task Context: Teacups

Every task can carry a **teacup** — the concrete moment that triggered it, not an abstract summary.

```bash
curl -s -X POST http://localhost:8777/task \
  -H 'Content-Type: application/json' \
  -d '{
    "target": "my-agent@your-hub",
    "command": "scan",
    "teacup": {
      "trigger": "what caused this action",
      "ground_state": "what the agent was seeing",
      "observation": "raw data (optional)"
    }
  }'
```

Later, score the outcome:

```bash
curl -s -X POST http://localhost:8777/teacup/TASK_ID/score \
  -H 'Content-Type: application/json' \
  -d '{"score": 1, "scored_by": "human"}'
```

Over time, patterns emerge: which triggers lead to good outcomes (+1) vs bad ones (-1). That's the compounding loop.

---

# Ports

| Port | Purpose | Exposure |
|------|---------|----------|
| 8766 | Federation (peer WebSocket) | Tailscale only |
| 8768 | Local (runner WebSocket) | localhost only |
| 8777 | REST API | localhost or Tailscale |

# Troubleshooting

**Server won't start** — check ports: `ss -tlnp | grep 8766`. Kill stale processes.

**Peers not connecting** — verify Tailscale: `tailscale status`. Check your IP is in their peer list and vice versa.

**Task returns `not_found`** — runner isn't running, or agent name in config doesn't match the target. Check runner log.

**Agent returns error** — test the script directly: `python3 /path/to/agent.py status`. Check it prints valid JSON and exits 0.

**Runner can't connect** — check server is up: `curl localhost:8777/status`. Check runner config `serverUrl` is `ws://localhost:8768`.

---

*Questions? Ask in the group or open an issue on [GitHub](https://github.com/stellamariesays/Manifold).*
