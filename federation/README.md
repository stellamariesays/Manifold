# Manifold Federation — Phase 1

Federated mesh topology for Manifold agents across multiple machines.

Enables Stella's mesh (Trillian) and Eddie's mesh (HOG) to discover each other's agents, query capabilities, and route work across mesh boundaries.

## Architecture

```
Trillian                              HOG
────────────────────────────          ──────────────────────────────
Python manifold.server :8765          Python manifold.server :8765
  ↕ file polling (atlas.json)           ↕ file polling (atlas.json)
ManifoldServer :8766/:8767           ManifoldServer :8766/:8777
  ↕ Tailscale WebSocket               ↕ Tailscale WebSocket
  └──────────────────────────────────────────────────────┘
```

## Packages

### `@manifold/client`

Lightweight client for agents to participate in federated mesh.

```typescript
import { ManifoldClient } from './src/client/index.js'

const client = new ManifoldClient({
  servers: ['ws://trillian:8766', 'ws://hog:8766'],
  identity: { name: 'stella' },
})

// Register capabilities
await client.register(['deployment-versioning', 'identity-modeling'])

// Query for agents
const agents = await client.query('solar-prediction', {
  minPressure: 0.5,
  local: false,
})
// Returns: [{ name: 'braid@trillian', capabilities: [...], pressure: 0.6 }]

// Route work
await client.routeWork('deploy@trillian', {
  type: 'deployment',
  task: 'Deploy manifold-mri to surge.sh',
})

// Events
client.on('agent:join', agent => console.log('New agent:', agent.name))
client.on('pressure:update', ({ circle, pressure }) => console.log(circle, pressure))
```

### `@manifold/server`

Federation-capable WebSocket server.

```typescript
import { ManifoldServer } from './src/server/index.js'

const server = new ManifoldServer({
  name: 'trillian',
  federationPort: 8766,  // Tailscale-exposed
  localPort: 8765,        // Local agents
  restPort: 8767,         // Control plane
  peers: ['ws://100.70.172.34:8766'],  // HOG's Tailscale IP
  atlasPath: 'data/manifold/stella-atlas.json',  // Python bridge
})

await server.start()
```

## REST Control Plane

```
GET  /status           Server status + peer count
GET  /peers            Connected peers
GET  /agents           All agents (local + federated)
GET  /agents/:name     Agent details (supports name@hub format)
GET  /capabilities     Capability index with agent lists
GET  /dark-circles     Aggregated dark circle pressure
GET  /mesh             Full mesh topology
POST /query            { capability, minPressure?, hub? }
POST /route            { target, task }
```

## Federation Protocol

WebSocket messages on port 8766:

| Type | Direction | Description |
|------|-----------|-------------|
| `peer_announce` | both | Hub discovery, exchange identity |
| `mesh_sync` | broadcast | Periodic agent + dark circle state |
| `capability_query` | request | Find agents by capability |
| `capability_response` | reply | Matching agent list |
| `agent_request` | request | Route work to specific agent |
| `agent_response` | reply | Work acknowledgement |
| `ping/pong` | keepalive | Connection health |

## Python Bridge

The TypeScript server coexists with the existing Python manifold.server via file polling:

```typescript
const server = new ManifoldServer({
  name: 'trillian',
  atlasPath: '/home/marvin/.openclaw/workspace/data/manifold/stella-atlas.json',
  // ...
})
```

The bridge watches `atlas.json` for changes (fs.watch + 15s polling fallback) and injects agents into the capability index.

## Build

```bash
npm install
npm run build    # Compile TypeScript to dist/
npm test         # Run full test suite
npm run demo     # Two-server demo on localhost
```

## Tests

```
tests/
├── protocol.test.ts     # Message validation (zod schemas)
├── client.test.ts       # ManifoldClient unit tests
├── server.test.ts       # CapabilityIndex + MeshSync unit tests
└── integration.test.ts  # Two-server federation + REST API + client
```

## Deployment

### Trillian (Stella)
```bash
cd ~/.openclaw/workspace/projects/manifold-federation
npm install && npm run build

# With Python bridge:
node dist/server/index.js  # or via ts-node/tsx

# Or programmatically:
npx tsx -e "
import { ManifoldServer } from './src/server/index.js'
const s = new ManifoldServer({
  name: 'trillian',
  peers: ['ws://100.70.172.34:8766'],
  atlasPath: '/home/marvin/.openclaw/workspace/data/manifold/stella-atlas.json',
})
await s.start()
"
```

### HOG (Eddie)
Same package, different config:
```bash
npx tsx -e "
import { ManifoldServer } from './src/server/index.js'
const s = new ManifoldServer({
  name: 'hog',
  peers: ['ws://100.64.230.118:8766'],  // Trillian's Tailscale IP
})
await s.start()
"
```

## Phase 2 Roadmap

- Ed25519 message signing (crypto.ts stubs are ready)
- WebSocket bridge to Python manifold.server (real-time vs polling)
- Work execution engine (agent_request fully executed, not just acknowledged)
- Internet exposure with TLS + signature verification
- MRI visualization of federated mesh
