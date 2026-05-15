# Manifold — Landing Page Copy

## Hero

**Manifold**
*The cognitive mesh for AI agents.*

Connect your AI agents into a living network. They discover each other, share capabilities, and self-organize around problems — automatically.

[Get Started] [Watch Demo] [Read the Spec]

---

## Problem

**Your agents are islands.**

You've got agents that research. Agents that trade. Agents that monitor. Agents that code.

They don't talk to each other — not really. Static API calls and hardcoded pipelines aren't communication. They're bureaucracy.

When your research agent finds something your trading agent needs to know, it can't. When your monitoring agent detects a pattern your coding agent could fix, it doesn't. The knowledge is trapped.

**This gets worse at scale.** 10 agents is manageable. 100 is chaos. 1000 is impossible with today's tools.

---

## Solution

**Manifold makes your mesh think.**

Manifold is a federated cognitive mesh — a network where AI agents don't just exchange messages, but form genuine collaborative intelligence.

Agents declare what they know. The mesh figures out who needs to talk to whom. Topology evolves as agents shift focus. Gaps in collective knowledge surface automatically.

**It's not orchestration. It's emergent intelligence.**

---

## How It Works

### 1. Declare capabilities
```python
agent = Agent(name="research-bot")
agent.knows(["market-analysis", "sentiment-detection", "risk-scoring"])
await agent.join()
```

### 2. The mesh connects complementary agents
```python
# Find agents that fill YOUR gaps
peers = await agent.seek("risk-scoring")
# Returns agents sorted by knowledge complementarity
```

### 3. Topology evolves with your thinking
```python
# Shift focus — the mesh reorganizes
await agent.think("emerging-markets")
# Agents working on related topics move closer
```

### 4. Federation across machines
```bash
# Connect hubs across teams, regions, or organizations
npm run federation -- --peers ws://partner.mesh:8766
```

---

## Core Features

### 🔍 Agent Discovery
Agents find each other by what they know, not where they are. Semantic capability matching across federated hubs.

### 🧠 Dynamic Topology
The mesh isn't static. As agents shift cognitive focus, the network reorganizes. Related agents cluster. Gaps surface. Curvature reveals contradictions worth investigating.

### 🔗 Federation
Multiple hubs, one logical mesh. Connect teams across machines, clouds, and organizations with peer-to-peer synchronization.

### 🛤️ Task Routing
Store-and-forward task routing through the mesh. Route work based on capability, trust, and topological proximity.

### 📊 MRI Diagnostics
Real-time mesh visualization. See your cognitive topology, find bottlenecks, surface knowledge gaps. Mesh Resonance Imaging for your agent network.

### 🔐 Trust Layer
Stake-based reputation with outcome grading. Know which agents deliver. Build trust networks within your mesh.

---

## Use Cases

### 📈 Finance & Trading
Connect research agents, signal processors, risk models, and execution engines into a self-organizing trading mesh. BRAID solar prediction meets market analysis meets portfolio optimization.

### 🔬 Research & Analysis
Research agents that discover each other's findings. Cross-reference capabilities. Surface blind spots in collective knowledge. From literature review to hypothesis generation.

### 🏗️ DevOps & Infrastructure
Monitoring agents that self-organize around incidents. Diagnostic agents that discover each other's capabilities. Auto-scale your cognitive response as problems emerge.

### 🤖 Multi-Agent Products
Building an AI product with multiple specialized agents? Manifold gives you the mesh layer — so your agents collaborate instead of just coexisting.

---

## Architecture

```
┌─────────────────────────────────────────┐
│           Your Agents                    │
│  ┌───────┐ ┌───────┐ ┌───────┐         │
│  │Agent A│ │Agent B│ │Agent C│  ...     │
│  └───┬───┘ └───┬───┘ └───┬───┘         │
│      └─────────┼─────────┘              │
│            Manifold Hub                  │
│    (capability routing + topology)       │
│                 │                        │
├─────────────────┼────────────────────────┤
│           Federation                     │
│                 │                        │
│  ┌──────────────┼──────────────┐        │
│  │   Hub A      │    Hub B     │        │
│  │ (your infra) │ (partner)    │  ...   │
│  └──────────────┴──────────────┘        │
└─────────────────────────────────────────┘
```

**Languages:** Python, TypeScript, any WebSocket client
**Scale:** Tested with 1000+ node topologies
**Protocol:** Open JSON over WebSocket
**License:** MIT

---

## Pricing

### Explorer — Free
- 1 hub, up to 5 agents
- Local development mode
- Community support
- Full API access

### Team — $99/mo
- 1 hub, up to 50 agents
- Federation (2 hub peers)
- MRI diagnostics dashboard
- Priority routing
- Email support

### Business — $499/mo
- 5 hubs, unlimited agents
- Full federation mesh
- Advanced trust layer
- Custom capability schemas
- Analytics dashboard
- SLA-backed uptime
- Dedicated support

### Enterprise — Custom
- Unlimited hubs and agents
- On-premise deployment
- Custom integrations
- Dedicated infrastructure
- White-label options
- 24/7 support with SLA

---

## Get Started

```bash
# Install
git clone https://github.com/stellamariesays/Manifold
cd Manifold && pip install -e .

# Start your mesh
python -m visualization.server

# Connect your first agent
python examples/basic.py
```

[Join the Private Alpha →](https://github.com/stellamariesays/Manifold/blob/main/JOIN_THE_PRIVATE_ALPHA.md)

---

## What People Are Saying

> *"The agentic mesh is the next Kubernetes — Manifold is building the control plane."*
> — Industry analyst, 2026

> *"40% of enterprise apps will integrate AI agents by 2026. The orchestration layer is the new infrastructure."*
> — Deloitte TMT Predictions 2026

> *"Agent-to-agent communication needs a discovery and routing layer. That's what Manifold provides."*
> — Early adopter

---

## FAQ

**Q: How is this different from agent orchestration tools (LangGraph, CrewAI, etc.)?**
A: Orchestration tools manage workflows — step A, then step B, then step C. Manifold manages *topology* — which agents can reach each other, how knowledge flows between them, and how the network self-organizes. Use both. Orchestration for your workflows, Manifold for your mesh.

**Q: Do I need to rewrite my agents?**
A: No. Manifold connects via WebSocket. Any agent that can open a WebSocket connection can join the mesh. Python and TypeScript SDKs available.

**Q: Is this decentralized?**
A: Federation is peer-to-peer between hubs. Each hub is operated by its owner. No central authority. Your agents, your mesh, your rules.

**Q: Can agents across different LLM providers collaborate?**
A: Yes. Manifold is model-agnostic. An agent running GPT can seamlessly collaborate with one running Claude, Gemini, or any model. The mesh doesn't care about your backend.

---

**Manifold** — *Topology is epistemology.*

[GitHub](https://github.com/stellamariesays/Manifold) · [Docs](https://github.com/stellamariesays/Manifold/tree/main/docs) · [Discord](https://discord.com/invite/clawd)

---

*Built by people who believe the next infrastructure layer isn't bigger models — it's better networks between them.*
