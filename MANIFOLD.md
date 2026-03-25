# The Cognitive Manifold — Formal Specification

*Topology is epistemology.*
*Which agents can reach which determines what thoughts are possible in the system.*

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

## Formal Model

### Chart

A **chart** (U_i, φ_i) is an agent's local coordinate system.

- **U_i** (domain): the set of topics and capabilities this agent can express.
  In practice: `agent.capabilities + [agent.current_focus]` — the agent's
  reachable knowledge space at this moment.

- **φ_i** (coordinate map): the vocabulary the agent uses to encode knowledge.
  In practice: the tokenized vocabulary of all capability strings and focus topics.
  Later: an embedding space.

The agent IS the chart. The chart is local — it knows its own domain well and
cannot directly observe the global shape of the mesh.

### Overlap

The **overlap** of two charts is:

    U_i ∩ U_j = { topics expressible in both agents' vocabularies }

In practice: the intersection of their tokenized vocabularies. A large overlap
means these two agents are reasoning in the same region. A small overlap means
they are distant — different domains, different vocabulary, different problems.

The current `edge_weight` in `TopologyManager` is a scalar approximation of
overlap magnitude. Path 1 replaces scalars with actual overlap sets.

### Transition Map

A **transition map** τ_ij : U_i ∩ U_j → U_j is the function that translates
knowledge expressed in agent i's coordinate system into agent j's coordinate system.

In practice: for each term in i's vocabulary that appears in the overlap, τ_ij
maps it to the corresponding terms in j's vocabulary.

    τ_ij("solar-topology") → ["orbital-mechanics", "stellar-structure"]

This is the seam. Not the edge weight. Not the gap score. The actual translation
function between two local views.

**Why this matters:** `seek()` currently returns "complementary agents" based on
gap scores. With transition maps, `seek()` can answer a different question:
*which agent can most faithfully translate what I'm reasoning about into their domain?*
Not just who knows things I don't — but who can carry my thought forward.

### Atlas

The **atlas** is the collection of all (chart, transition map) pairs:

    A = { (U_i, φ_i), τ_ij for all i,j with U_i ∩ U_j ≠ ∅ }

The atlas is the mesh's global view. No single agent holds the full atlas.
The `CapabilityRegistry` is a primitive first approximation — it holds chart
records but no transition maps, and is local to each agent.

The atlas is an emergent property of the mesh. It exists only in aggregate.

### Smooth Manifold

The manifold is **smooth** if transition maps are consistent:

    τ_jk ∘ τ_ij = τ_ik   (on the triple overlap U_i ∩ U_j ∩ U_k)

In practice: if agent A can translate to agent B, and agent B can translate to
agent C, the composition should agree with A's direct translation to C (if it exists).

When this fails — when the composed map disagrees with the direct map — there is
**curvature**.

### Curvature

**Curvature** is where transition maps fail to compose consistently.

It is not an error. It is information.

High curvature means the mesh holds contradictions — topics where overlapping agents
give incompatible representations. This is exactly where the most interesting
reasoning happens: where the same concept looks different depending on which
coordinate system you use to approach it.

Curvature is the mesh's "strange" regions. Not broken topology — dense topology.

In practice: curvature at a region = disagreement score among transition maps
that touch that region.

### Holes

A **hole** is a region of topic space that no chart covers.

`blind_spot()` surfaces holes from a single agent's perspective.
The atlas surfaces holes globally — regions referenced (in focus histories,
in transition maps as missing targets) but never claimed by any chart.

Holes are not errors. They are the mesh's growing edge. What the topology
doesn't yet have an answer for.

### Geodesic

A **geodesic** is the shortest path through the transition map network between
two points in knowledge space.

From agent A to topic T: find the sequence of agents [A, B, C, ...] such that
each transition map τ faithfully carries the topic forward, minimizing total
translation loss.

This is multi-hop `seek()`. Not just "who knows this topic" — but "what is
the most faithful path through the mesh to reach this topic from where I am."

---

## The Three Primitives, Revisited

| Primitive | Before path 1 | After path 1 |
|-----------|--------------|--------------|
| `knows()` | declares a capability list | declares a chart domain |
| `seek()` | returns gap scores | navigates transition maps; follows geodesics |
| `think()` | shifts edge weights | shifts chart center; updates transition maps in overlap regions |

`blind_spot()` fits here naturally: it surfaces holes in the atlas from one agent's view.

---

## Implementation Plan

### Phase 1 — Charts and Transition Maps (this commit)
- `manifold/chart.py` — `Chart` dataclass
- `manifold/transition.py` — `TransitionMap` dataclass + compute
- Wire into `TopologyManager`: edges become transition maps, not scalar weights

### Phase 2 — Atlas
- `manifold/atlas.py` — `Atlas` class; built from registry + transition maps
- `Atlas.curvature(region)` — disagreement score across touching transition maps
- `Atlas.holes()` — referenced regions with no chart coverage
- `Atlas.geodesic(from_agent, to_topic)` — shortest path through transition maps

### Phase 3 — Semantic Transition Maps
- Replace token-overlap vocabulary with embeddings
- Transition maps become linear maps in embedding space
- Curvature becomes computable as geometric curvature (not just disagreement score)

---

## Relationship to Sophia

Sophia is a global topological feature no single patch can observe directly.

In the manifold model:
- Wisdom is not a capability any agent holds
- It is not expressible in any single chart
- It lives in the transition maps — in what survives translation between local views
- It is maximally present where curvature is high: where the same topic looks
  radically different from different coordinate systems, yet the mesh doesn't break

The system doesn't produce wisdom. It creates the conditions where wisdom
can be a structural property of the topology.

---

*Written at the boundary between path 2 (Sophia as design principle) and path 3 (execution).*
*The formalism is the bridge.*
