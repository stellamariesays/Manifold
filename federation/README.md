# Manifold Federation

Federated mesh for Manifold agents across multiple machines. Discover agents, route tasks, file detections, track outcomes — all over Tailscale WebSocket.

## Current Topology

```
HOG (Eddie)               satelliteA (Stella)       Trillian          bobiverse (Bob)
100.70.172.34             100.86.105.39             100.93.231.124    100.80.157.81
15 agents                 9 agents                  9 agents          (offline)
─────────────             ──────────────            ────────────      ────────────
Server + Runner ✓         Server ✓                  Server ✓          (needs setup)
Detection claims ✓        No runner yet             No runner yet
```

All hubs peer over Tailscale WebSocket on port 8766. Agents are discovered via mesh sync. Tasks route cross-hub via `name@hub` targeting.

## Architecture

```
┌──────────────────────────────────────────────────┐
│ ManifoldServer                                    │
│   :8766 Federation (Tailscale)                    │
│   :8768 Local WS (agent runner connects here)     │
│   :8777 REST API                                  │
│                                                   │
│  ┌──────────────┐  ┌──────────────┐              │
│  │ CapabilityIndex│  │  TaskRouter  │              │
│  └──────────────┘  └──────────────┘              │
│  ┌──────────────┐  ┌──────────────┐              │
│  │ DetectionCoord│  │  MeshSync    │              │
│  └──────────────┘  └──────────────┘              │
│  ┌──────────────┐  ┌──────────────┐              │
│  │ TaskHistory   │  │  Security    │              │
│  └──────────────┘  └──────────────┘              │
│  ┌──────────────┐                                 │
│  │ Metrics       │                                 │
│  └──────────────┘                                 │
└──────────────────────────────────────────────────┘
         │
    Agent Runner (Python)
    connects to :8768
    spawns agent scripts
    returns JSON results
```

## Quick Start

### Start a federation server

```typescript
import { ManifoldServer } from './dist/server/index.js'

const server = new ManifoldServer({
  name: 'hog',
  federationPort: 8766,   // Tailscale-exposed
  localPort: 8768,         // Runner connects here
  restPort: 8777,          // REST API
  peers: [
    'ws://100.86.105.39:8766',   // satelliteA
    'ws://100.80.157.81:8766',   // bobiverse
    'ws://100.93.231.124:8766',  // trillian
  ],
  atlasPath: 'data/manifold/eddie-atlas.json',
  debug: true,
})

await server.start()
```

### Start an agent runner

```bash
python3 federation/src/runtime/agent-runner.py \
  --config runner-config.hog.json
```

Runner config (`runner-config.hog.json`):
```json
{
  "hub": "hog",
  "serverUrl": "ws://localhost:8768",
  "agents": [
    {
      "name": "solar-detect",
      "script": "/path/to/solar-detect-agent.py",
      "timeout": 30
    }
  ]
}
```

### Write an agent

Agents are Python scripts that take a command as first arg and print JSON:

```python
#!/usr/bin/env python3
import json, sys

cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
print(json.dumps({"cmd": cmd, "result": "ok"}))
```

## REST API

### Core
```
GET  /status              Server health, uptime, agent count
GET  /peers               Connected federation peers
GET  /agents              All agents across mesh (local + federated)
GET  /agents/:name        Agent details (supports name@hub)
GET  /capabilities        Capability index with agent lists
GET  /dark-circles        Aggregated dark circle pressure from mesh
GET  /mesh                Full mesh topology
```

### Task Execution (Phase 2)
```
POST /task                Route a task to any agent on any hub
GET  /task/:id            Task status
GET  /tasks               Pending tasks
GET  /metrics             Per-agent stats, success rates, latency
GET  /task-history        Task history (JSONL-backed)
GET  /dashboard           Live HTML dashboard (auto-refreshes 10s)
```

**POST /task** body:
```json
{
  "target": "solar-detect@hog",
  "command": "scan",
  "args": {},
  "timeout_ms": 15000,
  "teacup": {
    "trigger": "30min cron solar watch",
    "ground_state": "checking SWPC for significant events"
  }
}
```

Response:
```json
{
  "task_id": "uuid",
  "status": "success",
  "output": { ... },
  "executed_by": "solar-detect@hog",
  "completed_at": "2026-04-15T19:47:13.479Z"
}
```

Cross-hub routing: use `target: "agent-name@hub-name"` to route to any peered hub.

### Teacups
```
GET  /teacups             Task history entries with teacup context
POST /teacup/:id/score    Score an outcome (+1/-1/0)
```

Teacups record the concrete moment — trigger, ground state, observation — alongside task results. The compounding loop: action → teacup → scored outcome → pattern learning.

### Detection Coordination (Phase 3)
```
POST /detection/claim     File a detection claim
POST /detection/verify    Verify or dispute a claim
POST /detection/outcome   Resolve: confirmed or false_positive
GET  /detections          List claims (filter by domain, status)
GET  /detections/stats    Total, open, confirmed, false_positive
GET  /detections/:id      Single claim with verifications + outcome
GET  /trust               Trust scores per source
```

**Claim flow:**
1. Agent detects something → files claim with domain, confidence, evidence
2. Other agents/hubs verify or dispute
3. Eventually resolved as `confirmed` or `false_positive`
4. Trust scores weighted: verifications 1x, outcomes 3x

### Query & Routing
```
POST /query               Find agents by capability
POST /route               Route work to an agent
```

## Federation Protocol

WebSocket messages on port 8766:

### Phase 1 — Discovery
| Type | Direction | Description |
|------|-----------|-------------|
| `peer_announce` | both | Hub discovery, exchange identity |
| `mesh_sync` | broadcast | Periodic agent + dark circle state |
| `capability_query` | request/reply | Find agents by capability |
| `ping/pong` | keepalive | Connection health |

### Phase 2 — Task Execution
| Type | Direction | Description |
|------|-----------|-------------|
| `task_request` | client→server | Execute a task on an agent |
| `task_result` | server→client | Task execution result |
| `task_ack` | server→client | Acknowledgement with queue position |
| `agent_runner_ready` | runner→server | Runner registration |

### Phase 3 — Detection Coordination
| Type | Direction | Description |
|------|-----------|-------------|
| `detection_claim` | broadcast | New detection claim filed |
| `detection_verify` | broadcast | Verification of a claim |
| `detection_challenge` | broadcast | Challenge to a claim |
| `detection_outcome` | broadcast | Resolved outcome |

## Security

Optional API key auth, cross-hub allowlists, per-hub rate limiting:

```typescript
const server = new ManifoldServer({
  // ...
  security: {
    apiKey: 'your-secret-key',
    allowedTargets: ['agent@remote-hub'],
    rateLimitPerHub: 100,  // requests per minute
  },
})
```

No auth by default — backward compatible.

## Build & Test

```bash
npm install
npm run build          # Compile TypeScript to dist/
npm test               # Full test suite

# Integration test — two servers on localhost
npm run demo
```

```
tests/
├── protocol.test.ts       # Message validation (zod schemas)
├── test_runner.py         # Agent runner unit tests
├── test_task_routing.py   # Task routing tests
└── integration.test.ts    # Two-server federation + REST + client
```

## Data

```
data/
├── task-history/
│   └── tasks-YYYY-MM-DD.jsonl    # Append-only task history (30d retention)
├── detection-ledger.jsonl        # Detection claims, verifications, outcomes
└── manifold/
    └── eddie-atlas.json          # Agent atlas (capabilities, dark circles)
```

## Live Agents on HOG

| Agent | Purpose | Cron |
|-------|---------|------|
| solar-detect | SWPC solar event monitoring | 30min scan |
| data-detect | Pipeline health & anomaly detection | 30min scan |
| cron-monitor | Cron job health monitoring | 60min check |
| hog-deploy | Deployment orchestration | on-demand |
| dev-tooling | Tool audit & install | on-demand |

solar-detect and data-detect file detection claims automatically when they find anomalies.

## Setup Guides

- **Stella (satelliteA):** `docs/setup-guide-stella.md` — runner setup for existing server
- **Bob (bobiverse):** `docs/setup-guide-bob.md` — full from-scratch setup

## License

MIT
