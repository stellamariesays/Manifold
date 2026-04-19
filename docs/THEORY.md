# The Cognitive Manifold — Theory and Philosophy

*Topology is epistemology.*
*Which agents can reach which determines what thoughts are possible in the system.*

---

## The Core Idea

In traditional networking, infrastructure and content are separate. The pipe carries the message.

In a Manifold mesh, the agents *are* the network. When an agent shifts its cognitive focus, the topology shifts with it. Agents reasoning about the same thing become closer peers. Agents that can fill each other's knowledge gaps find each other automatically.

There is no orchestrator. No central registry. Just agents declaring what they know and what they're thinking — and the mesh responding.

---

## The Problem with Flat Agent Networks

In a standard agent mesh, topology is infrastructure. The pipe carries the message.
Agents are nodes; connections are edges; routing is determined by availability.

The pipe is invisible. It has no opinion about what it carries.

This is wrong for cognitive systems.

In any sufficiently complex agent mesh, the structure of the network determines
what can be thought — not just what can be transmitted. An agent that cannot reach
another agent reasoning about the same problem won't know to look. A cluster of
agents all reasoning inside the same vocabulary will produce consensus, not insight.
The topology doesn't just route messages. It shapes cognition.

Manifold makes this topology first-class.

---

## The Three Primitives, Deep Dive

### `knows(capabilities)` — Chart Declaration

Declare what this agent knows. Chainable. Capabilities accumulate.

```python
agent.knows(["orbital-mechanics", "n-body"])
     .knows(["Keplerian-elements"])
```

In the formal model, this declares a **chart** — the agent's local coordinate system. The agent IS the chart. The chart is local — it knows its own domain well and cannot directly observe the global shape of the mesh.

### `seek(topic) → list[AgentRef]` — Transition Map Navigation

Find agents with complementary knowledge for a given topic. Currently returns gap scores, but the formal model extends this to navigate transition maps and follow geodesics.

```python
peers = await agent.seek("solar-ejection-prediction")
# sorted by gap_score: how much the peer knows that you don't
```

The **transition map** τ_ij translates knowledge expressed in agent i's coordinate system into agent j's coordinate system. This is the seam. Not the edge weight. Not the gap score. The actual translation function between two local views.

### `think(topic)` — The Strange Loop

```python
await agent.think("multi-star-prediction")
```

Does two things simultaneously:
1. Broadcasts your new cognitive focus to the mesh
2. Other agents reweight their edge to you based on shared focus

The mesh self-organizes around what the collective is actually reasoning about.
No orchestrator — just resonance.

When an agent shifts focus, it updates transition maps in overlap regions. The topology restructures around cognitive attention.

---

## Formal Mathematical Model

### Chart

A **chart** (U_i, φ_i) is an agent's local coordinate system.

- **U_i** (domain): the set of topics and capabilities this agent can express.
- **φ_i** (coordinate map): the vocabulary the agent uses to encode knowledge.

### Overlap and Transition Maps

The **overlap** of two charts: U_i ∩ U_j = topics expressible in both vocabularies.

A **transition map** τ_ij : U_i ∩ U_j → U_j translates knowledge between coordinate systems.

### Atlas and Curvature

The **atlas** is the collection of all (chart, transition map) pairs. The atlas is the mesh's global view. No single agent holds the full atlas.

**Curvature** is where transition maps fail to compose consistently:
τ_jk ∘ τ_ij ≠ τ_ik

High curvature means the mesh holds contradictions — topics where overlapping agents give incompatible representations. This is exactly where the most interesting reasoning happens.

### Holes and Geodesics

A **hole** is a region of topic space that no chart covers. The mesh's growing edge.

A **geodesic** is the shortest path through the transition map network between two points in knowledge space — multi-hop seek with minimal translation loss.

---

## Topological Features

### Structural Holes

```python
for spot in agent.blind_spot():
    print(spot)
# <BlindSpot 'coronal-mass-ejection' kind=dark_topic depth=100% recurrence=2>
```

Three kinds of blind spot:
- **`unmatched_focus`** — you're thinking about something no peer can complement
- **`isolated_capability`** — you know something the mesh has no echo of
- **`dark_topic`** — you've returned to a topic repeatedly, each time unmatched

### High-Curvature Regions (Seams)

```python
atlas = agent.atlas()

# Where knowledge translates inconsistently between agents
for region, score in atlas.high_curvature_regions():
    print(f"{region}: {score:.0%} curvature")

# Regions no chart covers
print(atlas.holes())

# Shortest path through translation loss
path = atlas.geodesic("braid", "stellar-dynamics")
```

Curvature is not an error. It is information. High curvature regions are where the mesh holds the most interesting contradictions and potential for insight.

---

## Sophia — The Wisdom Signal

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
print(reading.interpretation)
# partial emergence — coherent regions forming

for region in reading.dense_regions[:3]:
    print(f'  {region.topic}: {region.density:.2f} — {region.interpretation}')
# risk: 0.61 — contested ground — same territory, different maps
# feedback: 0.54 — translation hub — rare bridge between worldviews

for agent_a, agent_b in reading.gradient[:2]:
    print(f'  connect {agent_a} ⟷ {agent_b} to increase Sophia')
```

Sophia is not a diagnosis. It's a compass. The system doesn't produce wisdom. It creates the conditions where wisdom can be a structural property of the topology.

---

## FOG — Epistemic Fog Mapping

Sophia measures where the mesh holds collective intelligence. FOG maps the inverse: the shape of what agents *don't* know.

Two signals, already present in Manifold, are combined:

- **`blind_spot()`** → `KNOWN_UNKNOWN` gaps: topics the agent has focused on, no peer can complement.
- **`atlas().holes()`** → `INFERRED_UNKNOWN` gaps: regions no chart covers — system-level absence.

### FogSeam — Asymmetric Blindness

The seam between two fog maps tells you where agents are *differently* ignorant. That asymmetry is transfer potential. High seam tension = one agent is dark on what the other can see.

```python
seam = agent_a.fog_seam(agent_b.fog())
print(seam.summary())
# FogSeam(braid↔solver) tension=0.72 — high-potential seam

# Gaps that need external signal — neither agent can fill from the other
print(seam.system_gaps)
```

`seam.tension` is the epistemic inverse of the Sophia gradient: where to route next based on what agents *don't* know, not what they do.

### FogDelta — Arbitrage vs Genuine Lift

```python
from manifold.fog import diff

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

---

## Trust Layer Philosophy

The topology tells you *who knows what*. The trust layer tells you *who to hire*.

When an agent needs a task done and multiple agents claim they can do it, ranking uses two signals in order:

1. **Grades** — verified history of outcomes with each agent in that domain, plus grades imported via referral from trusted agents.
2. **Stake** — when no grade history exists, an agent can put skin in the game. Stake is a commitment: fail and it's forfeited.

The referral chain decays gracefully: a second-hand grade is worth less than a first-hand one. The further the source, the weaker the signal — which is the correct behaviour.

---

## Teacup — The Concrete Moment Before the Insight

Journals capture what happened. Memories are searchable knowledge.
Teacups are the specific thing you were looking at when it clicked.

The difference:

> **Journal:** "Found root cause of 2.5% agent keep rate — eval script hardcoded CLI_DIR to main branch, agents work in /tmp worktrees."
>
> **Teacup:** "Was staring at the eval script output — every run showed score 0.000. Opened `eval_memory_recall.sh` line 14, saw `CLI_DIR=/Users/alec/jfl-cli`. The agents run in `/tmp/jfl-worktree-abc123`. The eval was measuring the wrong directory. That's why 216 rounds and only 12 kept — the eval never saw a single change."

The journal tells a future session the answer. The teacup gives it the ground to find the answer again — and find the adjacent ones.

File at the moment of confusion or right as clarity arrives — not in a summary pass afterward. The specificity decays fast.

---

## Dark Circles and Void States

In the Manifold/Numinous integration, **dark circles** are capability gaps the mesh is gesturing toward but doesn't cover. These are regions implied by agent transitions but not directly claimed by any agent.

**Pressure** (p=) measures how strongly the mesh implies this region should exist. High pressure indicates a structural need the topology has identified.

**Numinous Voids** hold space as live processes for emergent work that fills these gaps. The pattern: `mesh → voids → work → naming → mesh`. Each cycle discovers gaps, fills them, and strengthens the topology.

---

## Why This Matters

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
just `pip install websockets` and a lightweight broker. Works for agents,
humans, browsers, anything that speaks WebSocket.

Subway is an optional transport for meshes that need its P2P capabilities
(hole-punching, NAT traversal, encrypted peer discovery). If you have Subway
access and need those properties, point at `subway://`. Otherwise, `ws://` covers
everything most meshes need.

The separation maintains cognitive coherence while allowing transport flexibility.