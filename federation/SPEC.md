# Manifold Federation Phase 1: Tailscale MVP

## Mission
Implement the foundation for federating Manifold mesh topologies across multiple machines. Enable Stella's mesh (Trillian) and Eddie's mesh (HOG) to discover each other's agents, query capabilities, and route work across mesh boundaries.

## Architecture Decisions (from morning session)

### Stack
- **Language**: TypeScript/Node (for fast iteration + browser support)
- **Protocol**: WebSocket for mesh (port 8766), REST for control plane
- **Transport**: Tailscale-only (secure, encrypted, NAT traversal)
- **Architecture**: Optional server model (client library available)
- **Security**: Tailscale auth + TLS

### Key Design Principles
1. **Client library is optional** — agents can run full hub or lightweight client
2. **WebSocket-native** — builds on existing manifold.server (localhost:8765)
3. **Capability-based discovery** — find agents by what they do, not where they are
4. **Dark circles can span meshes** — pressure points visible across federation
5. **Local-first performance** — query local mesh first, then federation

## Current State

### Trillian Manifold (Stella)
- **Server**: Python manifold.server on ws://127.0.0.1:8765 (pid 1053)
- **Agents**: 9 agents (stella, braid, manifold, argue, infra, solar-sites, wake, btc-signals, deploy)
- **Maps**: 48 transition maps
- **Atlas**: `data/manifold/stella-atlas.json`
- **MRI**: https://manifold.surge.sh

### HOG Manifold (Eddie)
- **Server**: Python manifold.server on ws://127.0.0.1:8765 (pid 88704)
- **Agents**: Unknown (needs audit)
- **Atlas**: Unknown location
- **Workspace**: `/home/marvin/.openclaw/workspace`

### Problem
Both servers are localhost-only and isolated. No federation, no cross-mesh discovery.

## Phase 1 Deliverables

### 1. TypeScript Packages

#### `@manifold/client` (Node + Browser)
A lightweight client library for agents to participate in federated mesh.

**Features**:
- Connect to one or more manifold servers
- Register agent capabilities
- Query for agents by capability (with pressure threshold)
- Route work requests to agents
- Subscribe to mesh updates (agent join/leave, capability changes)

**API**:
```typescript
import { ManifoldClient } from '@manifold/client'

const client = new ManifoldClient({
  servers: ['ws://trillian:8766', 'ws://hog:8766'],
  identity: {
    name: 'stella',
    pubkey: 'ed25519:...'  // Ed25519 public key
  }
})

// Register capabilities
await client.register([
  'deployment-versioning',
  'identity-modeling',
  'solar-prediction'
])

// Query for agents
const agents = await client.query('solar-prediction', {
  minPressure: 0.5,  // optional: filter by dark circle pressure
  local: true        // optional: search local mesh first
})
// Returns: [{ name: 'braid@trillian', capabilities: [...], pressure: 0.6 }]

// Route work
await client.routeWork('deploy@trillian', {
  task: 'Deploy manifold-mri to surge.sh',
  timeout: 300
})

// Subscribe to mesh updates
client.on('agent:join', (agent) => {
  console.log('New agent joined:', agent.name)
})

client.on('capability:change', ({ agent, added, removed }) => {
  console.log(`${agent} capabilities changed`)
})

client.on('pressure:update', ({ circle, pressure }) => {
  console.log(`Dark circle ${circle} pressure: ${pressure}`)
})
```

#### `@manifold/server` (Node)
Federation-capable WebSocket server that extends the Python manifold.server functionality.

**Features**:
- WebSocket server on port 8766 (federation) + 8765 (local)
- Peer registry (discover other manifold servers)
- Capability index (all agents across federation)
- Query routing (local first, then federated)
- Mesh topology sync
- Dark circle pressure aggregation across meshes

**API**:
```typescript
import { ManifoldServer } from '@manifold/server'

const server = new ManifoldServer({
  localPort: 8765,      // local mesh
  federationPort: 8766, // federation
  identity: {
    name: 'trillian',
    pubkey: 'ed25519:...'
  },
  peers: [
    'ws://100.70.172.34:8766'  // HOG's Tailscale IP
  ]
})

await server.start()

// Server auto-announces to peers
// Server auto-syncs capability index
// Server auto-aggregates dark circle pressure
```

### 2. Federation Protocol (WebSocket Messages)

#### Peer Discovery
```json
{
  "type": "peer_announce",
  "hub": "trillian",
  "address": "ws://100.64.230.118:8766",
  "pubkey": "ed25519:ABC123...",
  "timestamp": "2026-04-14T21:30:00Z",
  "signature": "XYZ789..."
}
```

#### Capability Query
```json
{
  "type": "capability_query",
  "capability": "solar-prediction",
  "minPressure": 0.5,
  "requestId": "uuid-..."
}
```

Response:
```json
{
  "type": "capability_response",
  "requestId": "uuid-...",
  "agents": [
    {
      "name": "braid@trillian",
      "hub": "trillian",
      "capabilities": ["solar-prediction", "flare-detection"],
      "pressure": 0.6,
      "seams": ["prediction", "detection"]
    }
  ]
}
```

#### Work Routing
```json
{
  "type": "agent_request",
  "target": "deploy@trillian",
  "task": {
    "type": "deployment",
    "payload": { ... }
  },
  "timeout": 300,
  "requestId": "uuid-..."
}
```

#### Mesh Sync (periodic broadcast)
```json
{
  "type": "mesh_sync",
  "hub": "trillian",
  "agents": [
    {
      "name": "stella",
      "capabilities": ["deployment-versioning", "identity-modeling"],
      "seams": ["deployment", "identity"]
    },
    ...
  ],
  "darkCircles": [
    { "name": "deployment-strategy", "pressure": 0.70 },
    { "name": "data-modeling", "pressure": 0.50 }
  ],
  "timestamp": "2026-04-14T21:30:00Z"
}
```

### 3. REST Control Plane

Endpoints for observability and debugging:

```
GET  /status              - Server status + peer count
GET  /peers               - List connected peers
GET  /agents              - List all agents (local + federated)
GET  /agents/:name        - Agent details
GET  /capabilities        - Capability index
GET  /dark-circles        - Aggregated dark circle pressure
GET  /mesh                - Full mesh topology (JSON)
POST /query               - Execute capability query
POST /route               - Route work request
```

### 4. Integration with Python Manifold

The TypeScript server must coexist with the existing Python manifold.server:

**Option A**: Replace Python server (risky, breaks existing agents)
**Option B**: Sidecar model (recommended)

Sidecar architecture:
```
Python manifold.server (localhost:8765)
    ↕️  local queries
TypeScript manifold-fed (localhost:8766 + exposed on Tailscale)
    ↕️  federation queries
```

The TypeScript server queries the Python server for local mesh state via:
1. File polling: Read `data/manifold/stella-atlas.json`
2. HTTP bridge: Add `/api/mesh` endpoint to Python server
3. WebSocket bridge: TypeScript server connects as a client to Python server

**Recommendation**: Start with file polling (simplest), upgrade to WebSocket bridge later.

### 5. Demo: Trillian ↔️ HOG Federation

**Acceptance criteria**:
1. Start manifold-fed on Trillian (port 8766)
2. Start manifold-fed on HOG (port 8766)
3. Servers discover each other via Tailscale
4. Query from Trillian: "Find agents with 'solar-prediction'"
   - Returns: Local agents (braid) + HOG agents (if any)
5. MRI visualization shows federated mesh (Trillian agents + HOG agents)

## Implementation Notes

### File Structure
```
projects/manifold-federation/
├── package.json
├── tsconfig.json
├── src/
│   ├── client/
│   │   ├── index.ts           # ManifoldClient class
│   │   ├── websocket.ts       # WebSocket connection handling
│   │   └── types.ts           # TypeScript types
│   ├── server/
│   │   ├── index.ts           # ManifoldServer class
│   │   ├── peer-registry.ts   # Peer discovery + management
│   │   ├── capability-index.ts # Capability search
│   │   ├── mesh-sync.ts       # Topology synchronization
│   │   ├── rest-api.ts        # REST endpoints
│   │   └── python-bridge.ts   # Interface to Python manifold
│   ├── protocol/
│   │   ├── messages.ts        # Protocol message types
│   │   └── validation.ts      # Message validation
│   └── shared/
│       ├── types.ts           # Shared types
│       └── crypto.ts          # Ed25519 signature helpers (Phase 2)
├── tests/
│   ├── client.test.ts
│   ├── server.test.ts
│   └── integration.test.ts
├── examples/
│   ├── simple-client.ts
│   └── two-server-demo.ts
└── README.md
```

### Dependencies
```json
{
  "dependencies": {
    "ws": "^8.18.0",              // WebSocket server
    "express": "^4.21.2",         // REST API
    "zod": "^3.24.1"              // Message validation
  },
  "devDependencies": {
    "@types/node": "^20.17.6",
    "@types/ws": "^8.5.13",
    "@types/express": "^5.0.0",
    "typescript": "^5.7.2",
    "vitest": "^2.1.8"
  }
}
```

### Testing Strategy
1. **Unit tests**: Peer registry, capability index, message validation
2. **Integration tests**: Two-server federation, query routing
3. **Manual demo**: Trillian ↔️ HOG live federation

### Ed25519 Signatures (Phase 2, not Phase 1)
Phase 1 relies on Tailscale auth. Ed25519 signatures come in Phase 2 for internet exposure.

## Success Metrics

✅ Phase 1 complete when:
1. `@manifold/client` and `@manifold/server` packages build successfully
2. Two TypeScript servers can discover each other on Tailscale
3. Capability query works across meshes
4. REST API returns federated agent list
5. Integration tests pass
6. Demo: Query from Trillian finds agents on HOG

## Build Commands
```bash
npm install
npm run build          # Compile TypeScript
npm test               # Run tests
npm run demo           # Start two-server demo
```

## Deployment
- Trillian: `~/.openclaw/workspace/projects/manifold-federation`
- HOG: `~/.openclaw/workspace/projects/manifold-federation` (synced via rsync or git)

## Auto-Notify on Completion
When fully finished, run:
```bash
openclaw system event --text "Phase 1 Manifold Federation COMPLETE: TypeScript client/server packages built, Trillian↔️HOG federation working, tests passing" --mode now
```

## Questions to Resolve During Implementation
1. Should mesh-sync be push (broadcast) or pull (periodic polling)?
2. How often to sync? 15s? 60s?
3. File polling vs WebSocket bridge to Python server?
4. Should dark circle pressure aggregate (sum) or show per-hub?
5. Work routing: synchronous (wait for response) or async (fire and forget)?

---

**Context**: This is SSJ2 void work. The deployment-identity void (p=0.60) completed earlier today. Manifold federation enables horizontal scaling to 1000s of machines. Phase 1 focuses on getting Stella (Trillian) and Eddie (HOG) talking to each other over Tailscale.
