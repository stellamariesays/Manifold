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
    print(f"Found {len(peers)} complementary peer(s):")
    for p in peers:
        print(f"  {p}")

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

Declare what this agent knows. Chainable.

```python
agent.knows(["orbital-mechanics", "n-body"])
       .knows(["Keplerian-elements"])   # accumulates
```

Capabilities are broadcast to the mesh on `join()` and kept in sync via pub/sub. Every agent maintains a local view of the full capability landscape — no central server.

---

### `seek(topic) → list[AgentRef]`

Find agents with complementary knowledge for a given topic.

```python
peers = await agent.seek("solar-ejection-prediction")
# returns AgentRef list sorted by gap_score descending
# gap_score: how much the peer knows that you don't, weighted by topic relevance
```

`AgentRef`:
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

This does two things simultaneously:
1. Broadcasts your new cognitive focus to the mesh
2. Other agents reweight their edge to you based on shared focus

The result: agents thinking about the same problem cluster together in the topology. The mesh self-organizes around what the collective is actually reasoning about — without any orchestrator.

---

## Transports

| URI | Description |
|-----|-------------|
| `memory://local` | In-process pub/sub. All agents in the same Python process share a bus. Default. |
| `subway://host:port` | [Subway](https://github.com/subway-ai/subway) P2P transport via REST bridge. For production multi-machine meshes. |

```python
# In-memory (testing, local multi-agent)
agent = Agent(name="test-agent")

# Subway (production)
agent = Agent(name="prod-agent", transport="subway://localhost:8765")
```

---

## Why

In any sufficiently complex agent mesh, there will be communication needs the current topology cannot fulfill. Thoughts the system needs to think that require connections the network hasn't yet formed.

This is the distributed-systems equivalent of Gödelian incompleteness: the system's reach is always slightly less than its grasp. No agent can have a complete view of the mesh. No topology is ever final.

Manifold is designed for that incompleteness — not to solve it, but to navigate it. `seek()` surfaces the gap. `think()` closes it.

---

## Relationship to Subway

Manifold is the cognitive layer. Subway is the transport. They compose.

Subway handles peer discovery, hole-punching, and message delivery between machines. Manifold sits on top and adds capability-aware routing, knowledge-gap queries, and topology self-organization.

You can run Manifold without Subway (use `memory://`) for development and testing. In production, point it at a Subway instance and get the full P2P mesh.

---

## Examples

```bash
# Basic: two agents, seek, think
python examples/basic.py

# Full interaction: focus shift, pub/sub, topology
python examples/two_agents.py
```

---

## Roadmap

- [ ] `agent.blind_spot()` — what am I reasoning about that I have no peer for?
- [ ] Persistent registry (SQLite) for mesh memory across restarts
- [ ] Topology visualization (export as graph)
- [ ] WebSocket transport (browser agents)
- [ ] NATS transport adapter
- [ ] `seek()` with multi-hop routing — find peers of peers

---

## License

MIT
