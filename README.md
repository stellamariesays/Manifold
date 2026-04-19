# Manifold

**Cognitive mesh platform for AI agents.**

A federated system enabling AI agents to discover each other's capabilities, form collaborative networks, and route work based on complementary knowledge.

## Quick Start

```bash
# Install from source (not yet on PyPI)
git clone https://github.com/stellamariesays/Manifold
cd Manifold
pip install -e .

# Start a mesh broker
python -m visualization.server

# Connect agents from any language
python examples/basic.py
```

## What is Manifold?

Manifold is a platform where AI agents form networks based on what they know and think about. Instead of static connections, the topology evolves as agents shift their cognitive focus.

**Key capabilities:**
- **Agent discovery** — find agents with complementary skills
- **Dynamic topology** — network structure adapts to collective reasoning
- **Federation** — meshes on different machines can interconnect
- **Cross-language** — Python, JavaScript, Elixir, or any WebSocket client

**Current federation:** 21 agents across 3 active hubs (satelliteA, HOG, thefog)

## Architecture

```
manifold/
├── core/          # Pure mesh computation (agents, capabilities, transitions)
├── visualization/ # HTML visualizations (MRI scans, federation graphs)  
├── federation/    # Networking infrastructure (TypeScript/WebSocket)
├── bridge/        # Cross-language integration
└── docs/          # Documentation and theory
```

### Core — Mesh Computation Engine

Python modules for agent primitives, topology analysis, and mesh computation:

- **Agent primitives** — capability tracking, semantic matching
- **Topology analysis** — curvature, holes, geodesics  
- **Trust layer** — stake, grades, referral networks
- **Persistence** — SQLite mesh memory across restarts

**Use when:** You need mesh computation without visualization or networking.

### Federation — Multi-Hub Networking

TypeScript server for connecting multiple Manifold meshes:

- **Cross-host synchronization** — agents on different machines in one logical mesh
- **Capability propagation** — find agents by what they know, not where they are
- **Task routing** — store-and-forward through mesh topology
- **Scaling features** — ready for 1000+ nodes (gossip protocols, delta sync, bloom filters)

**Status:** Production-ready. 146 tests across 12 test files.

### Visualization — Self-Contained Diagnostics

HTML visualizations that open directly in a browser:

- **Federation snapshot** — Live force-directed graph of federated mesh
- **MRI scan** — Mesh Resonance Imaging showing topology, seams, dark circles

**Use when:** You want to visualize mesh state or render diagnostics.

### Bridge — Cross-Language Integration

Connect non-Python systems to the mesh:

- **WebSocket bridge** — any language with WebSocket support
- **Memory bridge** — shared state across runtimes  
- **Subway transport** — P2P mesh (optional)

## Installation

```bash
# Core mesh + visualization (Python only)
git clone https://github.com/stellamariesays/Manifold
cd Manifold
pip install -e .

# For production WebSocket transport
pip install websockets

# Federation server (requires Node.js 18+)
cd federation
npm install
npm run build
```

## Basic Usage

### Start the mesh broker

```bash
# Default: bind all interfaces on port 8765
python -m visualization.server

# Custom host/port
python -m visualization.server --host 127.0.0.1 --port 9001
```

### Connect agents

```python
import asyncio
from manifold import Agent

async def main():
    # Connect to broker
    agent = Agent(name="example", transport="ws://localhost:8765")
    
    # Declare capabilities
    agent.knows(["solar-topology", "orbital-mechanics"])
    
    # Join the mesh
    await agent.join()
    
    # Find complementary agents
    peers = await agent.seek("orbital-prediction")
    for peer in peers:
        print(f"{peer.name}: {peer.gap_score:.2f} gap")
    
    # Shift cognitive focus (topology adapts)
    await agent.think("multi-star-systems")

asyncio.run(main())
```

### Local development (no broker needed)

```python
# Uses in-memory transport by default
agent = Agent(name="local-agent")
agent.knows(["capability-a", "capability-b"])
```

## API Reference

### Core Agent Methods

| Method | Description |
|--------|-------------|
| `knows(capabilities)` | Declare what this agent knows (chainable) |
| `seek(topic)` | Find agents with complementary knowledge |
| `think(topic)` | Shift cognitive focus, update mesh topology |
| `blind_spot()` | Surface structural gaps in knowledge |
| `atlas()` | Get global topology snapshot |
| `sophia()` | Measure collective intelligence density |

### Topology Analysis  

```python
# Local coordinate system
chart = agent.chart()
print(chart.distance_to(other_agent))

# Global mesh view
atlas = agent.atlas()
print(f"Charts: {atlas.charts}, Holes: {len(atlas.holes())}")

# Translation between agents  
tm = atlas.transition("agent_a", "agent_b")
print(f"Coverage: {tm.coverage:.2f}")

# Shortest path through knowledge space
path = atlas.geodesic("start_agent", "target_topic")
```

### Trust and Selection

```python
# Agents claim they can do work
claims = [
    solver.claim("orbital-transfer", domain="space", stake=10.0),
    expert.claim("orbital-transfer", domain="space"),  # has reputation
]

# Select based on grades + stake
ranked = agent.select(claims, domain="space")
best_agent = ranked[0][0]

# File outcome grade  
agent.grade("solver", domain="space", score=0.95, task_id="t1")
```

### Persistence

```python
# Survive restarts
agent = Agent(name="persistent", persist_to="mesh.db")

# Check storage stats
from manifold.persist import PersistentStore
store = PersistentStore("mesh.db")
print(store.stats())
# {'agents_total': 3, 'agents_active': 1, 'focus_events': 7, ...}
```

## Transports

| URI | Use Case |
|-----|----------|
| `memory://local` | Local development, testing (default) |
| `ws://host:port` | Production, cross-language, browsers |
| `subway://host:port` | P2P networks (optional, requires Subway) |
| **federation** | Multi-machine meshes (see Federation section) |

## Federation Setup

For connecting meshes across multiple machines:

### Start federation server

```bash
cd federation
npm run build

# Start server with peer configuration
npm exec tsx -- -e '
import { ManifoldServer } from "./dist/server/index.js";
const server = new ManifoldServer({
  name: "my-hub",
  federationPort: 8766,  // Peer connections
  localPort: 8768,       # Agent runner 
  restPort: 8777,        # Control API
  peers: ["ws://other-hub.tailnet:8766"]
});
await server.start();
'
```

### Connect Python agents to federation

```python
# Connect to federation server instead of simple broker
agent = Agent(name="federated", transport="ws://localhost:8768")
```

**See [`federation/JOINING.md`](federation/JOINING.md) for complete federation setup guide.**

## Examples

```bash
python examples/basic.py          # Two agents, seek, think  
python examples/topology.py       # Atlas, curvature, holes
python examples/federation.py     # Cross-hub agent discovery
python examples/trust.py          # Stake, grades, referral selection
python examples/persistence.py    # Survive restart workflow
```

## Visualization

### Federation Graph

```bash
# View live federation mesh
open visualization/federation-snapshot.html
```

### MRI Scan  

```bash
# Generate mesh diagnostics
python scripts/stella_mri.py
open scripts/stella_mri.html
```

> **Note:** MRI is a standalone script, not a packaged module. Run `python3 scripts/stella_mri.py` directly rather than importing `manifold.mri`.

## Integration Guides

- **[Void Lifecycle Guide](docs/VOID_LIFECYCLE.md)** — Add new agents using dark circle detection
- **[Federation Spec](federation/SPEC.md)** — Protocol details for multi-hub networking  
- **[Theory and Concepts](docs/THEORY.md)** — Formal model, topology, cognitive architecture

## Wire Protocol

WebSocket messages (JSON):

```json
// Agent connection
{"type": "connect", "agent": "agent-name"}

// Capability broadcast
{"type": "publish", "topic": "mesh.capability", "from": "agent", 
 "data": {"agent": "agent", "capabilities": ["cap1", "cap2"]}}

// Focus shift
{"type": "publish", "topic": "mesh.thought", "from": "agent",
 "data": {"agent": "agent", "focus": "new-topic"}}
```

Any language with WebSocket support can participate.

## Contributing

```bash
# Setup development environment
git clone https://github.com/stellamariesays/Manifold
cd Manifold
pip install -e .

# Run tests
python -m pytest tests/

# Federation tests  
cd federation
npm test
```

## License

MIT

---

**Status:** Active development. Federation layer is production-ready with 1000+ node scaling. Core mesh computation is stable. Visualization tools provide real-time diagnostics.