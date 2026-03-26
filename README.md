# Manifold

**Cognitive mesh layer for AI agents — built on [Subway](https://github.com/subway-ai/subway).**

Topology is epistemology. Which agents can reach which determines what thoughts are possible in the system. Manifold makes topology first-class — observable, dynamic, and shaped by what agents are actually reasoning about.

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
pip install -e .
```

---

## Quickstart

```python
import asyncio
from manifold import Agent

async def main():
    braid = Agent(name="braid", transport="subway://localhost:8765")
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

No Subway instance? Use the in-memory transport for local development:

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
| `memory://local` | In-process pub/sub. Default. For testing and local multi-agent. |
| `subway://host:port` | [Subway](https://github.com/subway-ai/subway) P2P transport. For production meshes. |

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

Manifold is the cognitive layer. Subway is the transport. They compose.

Subway handles peer discovery, hole-punching, and message delivery between
machines. Manifold sits on top and adds capability-aware routing, knowledge-gap
queries, and topology self-organization.

Use `memory://` for development. Point at a Subway instance for production.

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
```

---

## Formal spec

See [`MANIFOLD.md`](MANIFOLD.md) for the full mathematical model: charts,
transition maps, atlas, smooth manifold, curvature, holes, geodesics, and the
relationship to Sophia — the global topological feature no single agent can
observe directly.

---

## License

MIT
