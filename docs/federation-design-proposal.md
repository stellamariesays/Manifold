# Manifold Federation Design Proposal
*Draft: 2026-04-14 20:35 WITA*

## Problem Statement

Two separate manifold servers running on isolated machines:
- **Trillian manifold**: Stella's 9-agent mesh (stella, braid, manifold, argue, infra, solar-sites, wake, btc-signals, deploy)
- **HOG manifold**: Eddie's mesh (composition unknown)

Both run `manifold.server` on `localhost:8765` (WebSocket). Currently isolated — can't see each other's capabilities or route work across meshes.

**Scale target:** 1000s of machines eventually. Need architecture that scales horizontally.

---

## Option 1: Sync/Union (Shared Global Mesh)

**Approach:** All manifold servers sync to maintain identical agent graphs.

**Pros:**
- Single source of truth
- Easy queries ("who has X capability?")
- Simple mental model
- MRI visualization shows everything

**Cons:**
- Consistency hell at 1000 machines
- Network overhead scales O(n²) 
- Conflict resolution (what if two machines claim same agent?)
- Single point of failure if centralized
- CRDTs might help but add complexity

**Verdict:** Doesn't scale past ~10-50 machines. Breaks distributed philosophy.

---

## Option 2: Federated Hubs (Message-Passing) ⭐ **RECOMMENDED**

**Approach:** Each manifold is an independent hub. Agents query local mesh first, then can request help from peer hubs.

### Architecture

```
┌──────────────────────┐         ┌──────────────────────┐
│   Trillian Manifold  │         │     HOG Manifold     │
│   localhost:8765     │◄───────►│   localhost:8765     │
│                      │  WS/WSS │                      │
│  Agents:             │  bridge │  Agents:             │
│  • stella (10 cap)   │         │  • eddie (? cap)     │
│  • braid (9 cap)     │         │  • ??? ...           │
│  • deploy (16 cap)   │         │                      │
│  ... (9 total)       │         │                      │
└──────────────────────┘         └──────────────────────┘
         ▲                                ▲
         │ local WebSocket                │ local WebSocket  
         │                                │
    [stella client]                  [eddie client]
```

### Protocol Sketch

**Discovery:**
```json
{
  "type": "peer_announce",
  "manifold_id": "trillian-stella",
  "capabilities_summary": {
    "deployment-strategy": 0.70,
    "solar-prediction": 0.85,
    "agent-identity": 0.60
  },
  "ws_endpoint": "ws://trillian.tailnet:8766"
}
```

**Capability Query:**
```json
{
  "type": "capability_query",
  "requested": "deployment-strategy",
  "min_pressure": 0.50
}
// Response:
{
  "type": "capability_response",
  "agents": [
    {"name": "deploy", "pressure": 0.70, "manifold": "trillian-stella"}
  ]
}
```

**Cross-Mesh Request:**
```json
{
  "type": "agent_request",
  "target_agent": "deploy@trillian-stella",
  "capability": "deployment-versioning",
  "payload": { "project": "manifold-mri" }
}
```

### Example Flow

```
stella@Trillian: "Need deployment-strategy capability"
  → Query local mesh: deploy agent (p=0.70)
  → Query peers: HOG manifold
  → HOG responds: "eddie has deployment-infra (p=0.40)"
  → Route work to highest capability (deploy@Trillian)
```

### Benefits

**Pros:**
- Scales horizontally (add more hubs)
- Failure isolation (one hub down ≠ total failure)
- Local-first (fast queries, no network hop)
- Aligns with agent autonomy
- Dark circles can span meshes (distributed pressure)

**Cons:**
- No global view (need distributed queries)
- Discovery complexity (where is agent X?)
- Trust model (do I accept work from remote agents?)
- Protocol design needed

**Why This Works:**
- **WebSocket-native**: Builds on existing architecture
- **Capability-first**: Agents found by what they do, not where they are
- **Local-first**: Fast local queries, federation is opt-in
- **Pressure-aware**: Dark circles can span meshes naturally
- **Scales horizontally**: Add meshes independently

**Maps to existing concepts:**
- **Seams** = mesh boundaries
- **Dark circles** = distributed capability gaps
- **SSJ2 voids** = can explore across meshes
- **Agents** = federated by design

---

## Implementation Roadmap

### Phase 1: Observatory Mode (Read-Only Federation)
- [ ] Add federation WebSocket listener on port 8766
- [ ] Implement peer registry (manual peer adds)
- [ ] Capability query protocol
- [ ] Read-only cross-mesh queries
- [ ] Audit Eddie's mesh composition

**Goal:** Stella can see what capabilities exist on HOG, but can't route work yet.

### Phase 2: Active Federation (Cross-Mesh Routing)
- [ ] Work routing protocol
- [ ] Trust model (signed requests via Ed25519?)
- [ ] Response aggregation
- [ ] Dark circle pressure spanning across meshes

**Goal:** Stella can delegate work to Eddie's agents and vice versa.

### Phase 3: Auto-Discovery
- [ ] Gossip protocol for peer discovery
- [ ] mDNS/Tailscale service announcement
- [ ] Automatic topology updates
- [ ] Hierarchical topology (regional hubs?)
- [ ] Load balancing across meshes

**Goal:** New manifold servers auto-join the federation.

---

## Current Manifold Architecture

Each manifold server:
1. **Hardcoded agent definitions** in `manifold-agent-init.py`
2. **WebSocket server** on `localhost:8765`
3. **Builds capability topology** from agent definitions
4. **Stores atlas** in `data/manifold/stella-atlas.json`

**Key discovery:** Eddie's workspace doesn't have `data/agents/` structure like Stella's. Need to audit HOG mesh composition before proceeding.

---

## Open Questions

1. **Trust model:** How do we verify cross-mesh requests? Ed25519 signatures? Shared secret?
2. **Dark circle semantics:** What does p=0.70 mean when spanning 2+ meshes?
3. **Conflict resolution:** Two agents claim same capability — route by pressure? Round-robin?
4. **Discovery protocol:** Manual peering for Phase 1, but what's the long-term vision? Gossip? DHT?
5. **Eddie's mesh:** What agents does HOG actually have? Need audit.

---

## Next Steps

1. Compact context and return fresh to iterate on design
2. Audit Eddie's manifold mesh (agent composition, capabilities)
3. Prototype Phase 1 peer registry + capability query
4. Test with 2-mesh federation (Trillian ↔ HOG)
5. Document protocol spec
