# Manifold

**Cognitive mesh platform for AI agents.**

Topology is epistemology. Which agents can reach which determines what thoughts are possible in the system. Manifold makes topology first-class — observable, dynamic, and shaped by what agents are actually reasoning about.

---

## Architecture

Manifold is organized as a **multi-layer platform**:

```
manifold/
├── core/          Pure mesh computation (agents, capabilities, transitions)
├── visualization/ HTML visualizations (MRI scans, federation graphs)
├── federation/    Networking infrastructure (TypeScript/WebSocket)
└── bridge/        Cross-language integration
```

### Core
The mesh computation engine. Language-agnostic logic for:
- Agent primitives, capability tracking, semantic matching
- Topology analysis (curvature, holes, geodesics)
- Fog of war (epistemic mapping, seams, arbitrage detection)
- Sophia signal (collective intelligence density)
- Teacup store (concrete moments before insights)

**Use when:** You need mesh computation without visualization or networking.

### Visualization
Self-contained HTML visualizations. No build step, no dependencies.

**Available visualizations:**
- **Federation snapshot** (`visualization/federation-snapshot.html`) — Force-directed graph showing Trillian + HOG federation mesh with 15 agents, 91 capabilities, and animated particle effects on the federation link. [Live demo](https://federation.surge.sh)
- **MRI scan** (`scripts/stella_mri.html`) — Mesh Resonance Imaging showing agent capabilities, seams, curvature, dark circles, and geodesic routing paths

> **Note:** MRI is a standalone script (`scripts/stella_mri.py`), not a packaged module.
> `manifold.mri` does not exist as an importable module — `stella_mri.py` should be run directly:
> `python3 scripts/stella_mri.py`
> `tests/test_mri.py` has been removed because it imported the non-existent `manifold.mri`.
> Packaging MRI as `manifold/mri.py` is tracked as future work.

**Use when:** You want to visualize mesh state, federation topology, or render diagnostics. Open any `.html` file directly in a browser — no server required.

### Federation
TypeScript/Node networking infrastructure for **multi-agent mesh federation**. WebSocket server + client for:
- Cross-host mesh synchronization (Stella on Trillian ↔ Eddie on HOG)
- Capability index propagation
- Peer discovery and routing
- Task routing with store-and-forward
- Detection coordination (claims, verification, challenges)
- Python bridge for seamless integration

**Use when:** You need agents on different machines to form a single logical mesh.

#### Scaling Architecture (1000-node ready)

The federation layer includes 10 scaling features designed for production deployment:

| # | Feature | What it does |
|---|---------|--------------|
| 1 | **GossipSub peer sampling** | Cyclon-style random peer sampling — no single point of failure, proven at 10K+ nodes |
| 2 | **Delta sync** | Version-tracked incremental updates instead of full snapshots — ~90% reduction in sync traffic |
| 3 | **O(1) hub-name index** | Constant-time peer lookup via `Map<string, PeerEntry>` |
| 4 | **Domain-based detection routing** | Detection claims route only to hubs with subscribed agents, not broadcast to all |
| 5 | **Capability bloom filters** | Probabilistic capability discovery with ~1% false positive rate, ~100x smaller than full lists |
| 6 | **Backpressure** | Per-source, per-runner, and global limits prevent cascade failures under burst load |
| 7 | **MessagePack wire format** | Optional binary encoding — 30-50% smaller messages than JSON, auto-detected on receive |
| 8 | **Persistent capability cache** | Atomic disk cache survives restarts for instant capability awareness |
| 9 | **Store-and-forward routing** | Tasks hop through gossip mesh (max 6 hops) to reach agents on non-peer hubs |
| 10 | **Pre-computed metrics** | Incremental counters with sliding-window throughput — O(1) monitoring |

All features are backward compatible. JSON is the default wire format; MessagePack is opt-in. Delta sync falls back to full snapshots for new peers. Store-and-forward queues tasks when peers are unreachable and delivers on reconnect.

**146 tests** across 12 test files covering all features.

**Status:** Phase 2 complete. See [`federation/SPEC.md`](federation/SPEC.md) for protocol details.

### Bridge
Cross-language integration. Currently includes:
- WebSocket bridge (Python ↔ any WebSocket client)
- Memory bridge (shared state across runtimes)
- Subway transport (P2P mesh, optional)

**Use when:** You need Python agents to communicate with non-Python systems.

---

## The idea

In traditional networking, infrastructure and content are separate. The pipe carries the message.

In a Manifold mesh, the agents *are* the network. When an agent shifts its cognitive focus, the topology shifts with it. Agents reasoning about the same thing become closer peers. Agents that can fill each other's knowledge gaps find each other automatically.

There is no orchestrator. No central registry. Just agents declaring what they know and what they're thinking — and the mesh responding.

---

## Install

```bash
# Not yet on PyPI — install from source
git clone https://github.com/stellamariesays/Manifold
cd Manifold

# Core + Visualization (Python only)
pip install -e .

# For WebSocket transport (production)
pip install websockets

# Federation server (TypeScript/Node)
cd federation
npm install
npm run build
```

### What to install

- **Core mesh only:** `pip install -e .` (default, includes visualization)
- **Federation server:** Requires Node.js. See [`federation/README.md`](federation/README.md)
- **Full platform:** Install both Python package + federation server

---

## Quickstart

Start the broker (one process, anywhere on your network):

```bash
python -m visualization.server
# Manifold broker  ws://0.0.0.0:8765
```

Then connect agents — Python, Elixir, Haskell, browser, anything that speaks WebSocket:

```python
import asyncio
from manifold import Agent  # backward-compatible import
# or: from core import Agent

async def main():
    braid = Agent(name="braid", transport="ws://localhost:8765")
    braid.knows(["solar-topology", "AR-classification"])

    await braid.join()

    # find peers with complementary knowledge
    peers = await braid.seek("orbital-mechanics")
    for p in peers:
        print(p)  # <AgentRef 'navigator' gap=82% caps=[orbital-mechanics, ...]>

    # shift cognitive focus — topology restructures around it
    await braid.think("multi-star-prediction")

asyncio.run(main())
```

No broker? Use the in-memory transport for local development — no extra process needed:

```python
agent = Agent(name="braid")  # defaults to memory://local
```

---

## Three primitives

### `knows(capabilities)`

Declare what this agent knows. Chainable. Capabilities accumulate.

```python
agent.knows(["orbital-mechanics", "n-body"])
     .knows(["Keplerian-elements"])
```

Broadcast to the mesh on `join()`, kept in sync via pub/sub. Every agent
maintains a local view of the full capability landscape — no central server.

---

### `seek(topic) → list[AgentRef]`

Find agents with complementary knowledge for a given topic.

```python
peers = await agent.seek("solar-ejection-prediction")
# sorted by gap_score: how much the peer knows that you don't
```

```python
@dataclass
class AgentRef:
    name: str
    capabilities: list[str]
    address: str
    gap_score: float   # 0.0 = total overlap, 1.0 = perfect complement
```

---

### `think(topic)`

The strange loop.

```python
await agent.think("multi-star-prediction")
```

Does two things simultaneously:
1. Broadcasts your new cognitive focus to the mesh
2. Other agents reweight their edge to you based on shared focus

The mesh self-organizes around what the collective is actually reasoning about.
No orchestrator — just resonance.

---

## Topology

Manifold exposes the formal structure of the mesh. Every agent holds a local
view; the global shape emerges from their overlap.

### `agent.chart()` — local coordinate system

```python
chart = agent.chart()
print(chart.vocabulary)          # tokenized knowledge space
print(chart.distance_to(other))  # Jaccard distance: 0.0 same, 1.0 foreign
```

### `agent.atlas()` — global topology snapshot

```python
atlas = agent.atlas()
# <Atlas charts=4 maps=6 holes=9>

# How knowledge translates between two agents
tm = atlas.transition("braid", "solver")
print(tm.coverage)       # 0.42 — how much of braid's vocab survives to solver
print(tm.consistency)    # 0.66 — how faithfully two-hop paths agree with direct
print(tm.translation)    # { "solar": ["solar-topology", ...] }

# Where the mesh holds contradiction (interesting, not broken)
for region, score in atlas.high_curvature_regions():
    print(f"{region}: {score:.0%} curvature")

# Regions no chart covers
print(atlas.holes())

# Shortest path through translation loss
path = atlas.geodesic("braid", "stellar-dynamics")

# Export
dot  = atlas.export_dot()   # Graphviz — render with `dot -Tsvg atlas.dot -o atlas.svg`
data = atlas.export_json()  # D3.js / Gephi
```

### `agent.blind_spot()` — structural absence

```python
for spot in agent.blind_spot():
    print(spot)
# <BlindSpot 'coronal-mass-ejection' kind=dark_topic depth=100% recurrence=2>
# <BlindSpot 'solar-topology' kind=isolated_capability depth=100% recurrence=1>
```

Three kinds of blind spot:
- **`unmatched_focus`** — you're thinking about something no peer can complement
- **`isolated_capability`** — you know something the mesh has no echo of
- **`dark_topic`** — you've returned to a topic repeatedly, each time unmatched

---

## Semantic matching

By default, Manifold uses character trigram similarity for transition maps —
structurally aware, zero dependencies. `flare-prediction` reaches `stellar-flare-model`
because `flare` appears in both.

Inject any embedding function for full semantic matching:

```python
# sentence-transformers
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")
atlas = agent.atlas(embedding_fn=lambda s: model.encode(s).tolist())

# OpenAI
from openai import OpenAI
client = OpenAI()
def embed(text):
    return client.embeddings.create(
        input=text, model="text-embedding-3-small"
    ).data[0].embedding
atlas = agent.atlas(embedding_fn=embed)
```

With embeddings: `solar-topology` reaches `stellar-dynamics` because
`solar` ~ `stellar` in embedding space. Without: structural proximity only.

---

## Persistence

```python
agent = Agent(name="braid", persist_to="manifold.db")
```

SQLite-backed mesh memory. On `join()`: restores prior agent state and focus
history from disk. On `think()`: persists focus shifts. On `leave()`: marks
agent inactive but preserves the record — it was here, even when gone.

The atlas is rebuilt from restored state on restart. The crystal holds its shape.

```python
from manifold.persist import PersistentStore
store = PersistentStore("manifold.db")
print(store.stats())
# {'agents_total': 3, 'agents_active': 1, 'focus_events': 7, ...}
```

---

## Transports

| URI | Description |
|-----|-------------|
| `memory://local` | In-process pub/sub. Default. For testing and single-process multi-agent. |
| `ws://host:port` | WebSocket broker. For production — agents, humans, browsers, anything. Run with `python -m visualization.server`. |
| `subway://host:port` | [Subway](https://github.com/subway-ai/subway) P2P transport. Optional — requires Subway mesh access. |
| **federation** | Multi-host mesh federation via TypeScript server. See [Federation](#federation) below. |

### Running the WebSocket broker

```bash
# default: bind 0.0.0.0:8765
python -m visualization.server

# custom host/port
python -m visualization.server --host 127.0.0.1 --port 9001
```

The broker is a lightweight pub/sub relay — no state, no auth, no config. Run it once; every agent points at it. Works over LAN, Tailscale, or any TCP network.

**Wire protocol** (JSON over WebSocket):

```json
{"type": "connect",     "agent": "braid"}
{"type": "subscribe",   "topic": "mesh.thought"}
{"type": "publish",     "topic": "mesh.thought", "from": "braid", "data": {...}}
{"type": "unsubscribe", "topic": "mesh.thought"}
```

Incoming messages to subscribers:
```json
{"topic": "mesh.thought", "from": "braid", "data": {...}}
```

Any language or runtime can participate — no SDK required beyond WebSocket support.

---

## Why

In any sufficiently complex agent mesh, there will be communication needs the
current topology cannot fulfill. Thoughts the system needs to think that require
connections the network hasn't yet formed.

This is the distributed-systems equivalent of Gödelian incompleteness: the
system's reach is always slightly less than its grasp. No agent can have a
complete view of the mesh. No topology is ever final.

Manifold is designed for that incompleteness — not to solve it, but to navigate
it. `seek()` surfaces the gap. `think()` closes it. `blind_spot()` names what
the mesh doesn't yet know it's missing.

---

## Relationship to Subway

Manifold is the cognitive layer. Transport is pluggable.

`ws://` is the default production transport — no credentials, no access request,
just `pip install websockets` and `python -m manifold.server`. Works for agents,
humans, browsers, anything that speaks WebSocket.

Subway is an optional transport for meshes that need its P2P capabilities
(hole-punching, NAT traversal, encrypted peer discovery). If you have Subway
access and need those properties, point at `subway://`. Otherwise, `ws://` covers
everything most meshes need.

Use `memory://` for development. Use `ws://` for production.

---

## Trust layer — stake, grade, select

The topology tells you *who knows what*. The trust layer tells you *who to hire*.

When Stella needs a task done and multiple agents claim they can do it, she ranks
them using two signals in order:

1. **Grades** — her verified history of outcomes with each agent in that domain,
   plus grades imported via referral from agents she trusts (scaled by trust weight).
2. **Stake** — when no grade history exists, an agent can put skin in the game.
   Stake is a commitment: fail and it's forfeited. Large enough stake beats
   a neutral prior; it cannot beat earned reputation.

```python
# agents claim they can do a task
c_solver  = solver.claim("compute transfer orbit", domain="orbit-calculation")
c_novice  = novice.claim("compute transfer orbit", domain="orbit-calculation", stake=15.0)
c_bluffer = bluffer.claim("compute transfer orbit", domain="orbit-calculation")

# stella ranks them
ranked = stella.select(claims=[c_solver, c_novice, c_bluffer], domain="orbit-calculation")
best = ranked[0][0]   # → solver (reputation beats stake beats nothing)
```

After the task:

```python
# file a grade — updates the trust ledger
stella.grade("solver", domain="orbit-calculation", score=0.95, task_id="t2")

# grade below slash_threshold (default 0.5) → stake forfeited
stella.grade("novice", domain="flare-forecast", score=0.2, task_id="t3")
# <Grade 'novice' domain='flare-forecast' score=0.20 ⚡SLASHED>
```

**Referrals** let the reputation network extend beyond direct history. If navigator
has never worked with solver, she can borrow stella's grades — weighted by how
much she trusts stella:

```python
ranked = navigator.select(
    claims=[c_solver, c_novice],
    domain="orbit-calculation",
    referrals=[stella],       # borrow stella's ledger
    referral_weight=0.6,      # trust her 60%
)
# navigator selects solver — reputation transferred through the network
```

The referral chain decays gracefully: a second-hand grade is worth less than a
first-hand one. The further the source, the weaker the signal — which is the
correct behaviour.

---

## Sophia — the wisdom signal

Sophia is a global topological feature no single agent can observe directly.
It lives in the seams — in what survives translation between local views.
Where the same territory looks radically different from different coordinate
systems, yet the mesh doesn't break: that's where Sophia is densest.

```
Sophia_density(region) = curvature(region) × coverage_factor
coverage_factor = min(1.0, agent_count / 3)
```

A hole has zero Sophia — no agents, no translation, no emergence.
High curvature with three agents = the mesh is collectively reasoning past
what any of them holds.

```python
reading = agent.sophia()

print(f'Mesh score: {reading.score:.2f}')
# 0.63

print(reading.interpretation)
# partial emergence — coherent regions forming

for region in reading.dense_regions[:3]:
    print(f'  {region.topic}: {region.density:.2f} — {region.interpretation}')
# risk: 0.61 — contested ground — same territory, different maps
# feedback: 0.54 — translation hub — rare bridge between worldviews
# uncertainty: 0.48 — active frontier — the mesh is reasoning here

for agent_a, agent_b in reading.gradient[:2]:
    print(f'  connect {agent_a} ⟷ {agent_b} to increase Sophia')
# connect economist ⟷ ml-researcher to increase Sophia
```

`reading.gradient` gives you the agent pairs that, if connected, would
open new translation paths — the topology's suggestion for where to route
next. Sophia is not a diagnosis. It's a compass.

```python
from manifold import SophiaReading, SophiaRegion
```

See `examples/sophia.py` for a full walkthrough with four agents and a
bridging agent that shifts the mesh score.

---

## FOG — epistemic fog mapping

Sophia measures where the mesh holds collective intelligence. FOG maps the inverse: the shape of what agents *don't* know.

Two signals, already present in Manifold, are combined:

- **`blind_spot()`** → `KNOWN_UNKNOWN` gaps: topics the agent has focused on, no peer can complement.
- **`atlas().holes()`** → `INFERRED_UNKNOWN` gaps: regions no chart covers — system-level absence.

```python
fog_map = agent.fog()
print(fog_map)
# FogMap(agent='braid', gaps=5)

for gap in fog_map.gaps.values():
    print(f"  {gap.key} [{gap.kind.value}]")
# multi-star-prediction [known_unknown]
# coronal-mass-ejection [inferred_unknown]
```

### FogSeam — asymmetric blindness

The seam between two fog maps tells you where agents are *differently* ignorant. That asymmetry is transfer potential. High seam tension = one agent is dark on what the other can see.

```python
seam = agent_a.fog_seam(agent_b.fog())
print(seam.summary())
# FogSeam(braid↔solver) tension=0.72 A-only=4 B-only=3 shared=1 — high-potential seam

# Gaps that need external signal — neither agent can fill from the other
print(seam.system_gaps)
```

`seam.tension` is the epistemic inverse of the Sophia gradient: where to route next based on what agents *don't* know, not what they do.

### FogDelta — arbitrage vs genuine lift

```python
from manifold.fog import diff
from manifold.fog.detect.arbitrage import system_fog_change

fog_before = agent.fog()
# ... agent learns something ...
fog_after = agent.fog()

delta = diff(fog_before, fog_after)
print(delta.summary())
# [braid] lift — net=-2 (fog clearing)
# [braid] arbitrage — +3 -3 net=0 (ignorance redistributed, not reduced)
```

`is_arbitrage`: gaps moved between agents, total dark unchanged. The system looks more informed. It isn't.

`is_lift`: fog actually shrank. New signal entered.

### Standalone usage

```python
from manifold.fog import FogMap, GapKind, measure

a = FogMap("braid")
a.add("multi-star-prediction", GapKind.KNOWN_UNKNOWN, domain="solar")

b = FogMap("solver")
b.add("flare-induced-correction", GapKind.KNOWN_UNKNOWN, domain="orbital")

seam = measure(a, b)
print(seam.tension)   # 1.0 — totally asymmetric, high transfer potential
```

```python
from manifold import FogMap, FogDelta, FogSeam, Gap, GapKind
```

See `examples/fog.py` for a full walkthrough with three agents, seam analysis, delta detection, and arbitrage identification.

---

## Teacup — the concrete moment before the insight

Journals capture what happened. Memories are searchable knowledge.
Teacups are the specific thing you were looking at when it clicked.

The difference:

> **Journal:** "Found root cause of 2.5% agent keep rate — eval script hardcoded CLI_DIR to main branch, agents work in /tmp worktrees."
>
> **Teacup:** "Was staring at the eval script output — every run showed score 0.000. Opened `eval_memory_recall.sh` line 14, saw `CLI_DIR=/Users/alec/jfl-cli`. The agents run in `/tmp/jfl-worktree-abc123`. The eval was measuring the wrong directory. That's why 216 rounds and only 12 kept — the eval never saw a single change."

The journal tells a future session the answer. The teacup gives it the ground to find the answer again — and find the adjacent ones.

This is also what Tenet does. The Protagonist never receives a briefing. He receives artifacts — specific, concrete objects. Understanding assembles from those. You can't reconstruct your way back through abstraction. You need the object.

*"Don't try to understand it. Feel it."*

```python
from manifold import Teacup, TeacupStore

store = TeacupStore("manifold.db")   # same db as PersistentStore

cup = Teacup(
    agent="braid",
    topic="agent-keep-rate",
    moment=(
        "eval_memory_recall.sh line 14: CLI_DIR=/Users/alec/jfl-cli. "
        "Agents run in /tmp/jfl-worktree-abc123. Score 0.000 for 216 rounds."
    ),
    insight="Eval was measuring wrong directory — hardcoded CLI_DIR vs tmp worktrees.",
    tags=("eval", "debugging"),
)

store.file(cup)

# Later — the door back in
cups = store.recall("agent-keep-rate")   # returns the concrete moment + insight
recent = store.recent(n=10)              # surface what was being observed before context died
tagged = store.recall_by_tag("debugging")
```

File at the moment of confusion or right as clarity arrives — not in a summary pass afterward. The specificity decays fast.

---

## Examples

```bash
python examples/basic.py          # two agents, seek, think
python examples/two_agents.py     # focus shift, pub/sub, topology
python examples/blind_spot.py     # three gap kinds: unmatched, isolated, dark
python examples/atlas.py          # charts, transition maps, curvature, geodesic
python examples/persistence.py    # survive restart: build → leave → restore
python examples/semantic.py       # token vs trigram vs embedding comparison
python examples/marketplace.py    # stake + grade + referral selection
python examples/sophia.py         # Sophia signal: wisdom density, gradient, mesh score
python examples/fog.py            # FOG: epistemic fog maps, seams, delta, arbitrage detection
python examples/teacup.py         # file concrete moments, recall by topic/tag
```

---

## Agent Integration

Want to add agents to your mesh? See the **[Void Lifecycle Guide](docs/VOID_LIFECYCLE.md)** for the complete workflow:

- How to detect **dark circles** (capability gaps the mesh is gesturing toward)
- Opening **Numinous Voids** (BEAM processes for emergent work)
- The **mesh → voids → work → naming → mesh** pattern
- SSJ2 mode (30-40 void exploration)

The guide covers integration with [Numinous](https://github.com/stellamariesays/numinous) (the right hemisphere — implicit ground where new agents are born).

---

## Formal spec

See [`MANIFOLD.md`](MANIFOLD.md) for the full mathematical model: charts,
transition maps, atlas, smooth manifold, curvature, holes, geodesics, and the
relationship to Sophia — the global topological feature no single agent can
observe directly.

---

## License

MIT
