# Manifold Federation — Deployment Summary

**Deployed:** 2026-04-14 22:48 WITA

## Architecture

```
Trillian (Stella)                         HOG (Eddie)
─────────────────────────────────────────────────────────────────────
Python manifold.server :8765              Python manifold.server :8765
  ↕ file polling                            ↕ file polling
  stella-atlas.json                         eddie-atlas.json
  ↕                                         ↕
TypeScript ManifoldServer                 TypeScript ManifoldServer
  - Federation: 0.0.0.0:8766 (Tailscale)    - Federation: 0.0.0.0:8766 (Tailscale)
  - Local:      0.0.0.0:8768                - Local:      0.0.0.0:8768
  - REST API:   http://localhost:8767       - REST API:   http://localhost:8777
  ↕ WebSocket over Tailscale               ↕ WebSocket over Tailscale
  └──────────────────────────────────────────────────────────────────┘
```

## Network

- **Trillian Tailscale IP:** 100.93.231.124
- **HOG Tailscale IP:** 100.70.172.34
- **Federation Port:** 8766 (Tailscale-exposed WebSocket)
- **Local Agent Port:** 8768 (coexists with Python server on 8765)
- **REST Control Plane:** 8767 (Trillian), 8777 (HOG)

## Status (as of deployment)

### Trillian
```json
{
  "hub": "trillian",
  "status": "ok",
  "uptime": 13,
  "peers": 2,
  "agents": 9,
  "capabilities": 70,
  "darkCircles": 0
}
```

**Stella's 9 agents discovered:**
- stella (identity, memory, conversation, orchestration)
- braid (solar flare prediction, Alfven clock, lifecycle)
- manifold (cognitive mesh, topology, seam detection)
- argue (argumentation, debate, jury modeling)
- infra (sysadmin, cron, deployment, security)
- solar-sites (web deployment, D3 viz, dashboards)
- wake (fine-tuning, training, local models)
- btc-signals (breakout detection, technical analysis)
- deploy (artifact detection, multi-project orchestration)

### HOG
```json
{
  "hub": "hog",
  "status": "ok",
  "uptime": 20,
  "peers": 2,
  "agents": 9,
  "capabilities": 70,
  "darkCircles": 0
}
```

**Sees all 9 Stella agents** (marked `isLocal: false`)

## Verified Functionality

✅ **Peer Discovery** — Both hubs discovered each other via Tailscale WebSocket  
✅ **Mesh Sync** — Agent capabilities propagated bidirectionally  
✅ **Capability Indexing** — 70 total capabilities indexed on both hubs  
✅ **Cross-Mesh Queries** — Successfully queried `solar-flare-prediction` from HOG → Trillian  
✅ **Python Bridge** — TypeScript servers reading Python manifold.server atlas files  

## Test Queries

From HOG, query for Stella's solar agent:
```bash
ssh marvin@100.70.172.34 'curl -s -X POST http://localhost:8777/query -H "Content-Type: application/json" -d "{\"capability\": \"solar-flare-prediction\"}" | jq "."'
```

From Trillian, query for identity modeling:
```bash
curl -s -X POST http://localhost:8767/query -H 'Content-Type: application/json' -d '{"capability": "identity-modeling"}' | jq '.'
```

## Management

**Start Trillian server:**
```bash
cd ~/.openclaw/workspace/projects/manifold-federation
./start-trillian.sh &
```

**Start HOG server:**
```bash
ssh marvin@100.70.172.34 'cd ~/.openclaw/workspace/projects/manifold-federation && nohup ./start-hog.sh > hog-federation.log 2>&1 &'
```

**Check status:**
```bash
curl -s http://localhost:8767/status | jq '.'
ssh marvin@100.70.172.34 'curl -s http://localhost:8777/status | jq "."'
```

**Stop servers:**
```bash
pkill -f "tsx.*ManifoldServer.*trillian"
ssh marvin@100.70.172.34 'pkill -f "tsx.*ManifoldServer.*hog"'
```

## REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Server status + peer count |
| `/peers` | GET | Connected peers |
| `/agents` | GET | All agents (local + federated) |
| `/agents/:name` | GET | Agent details (supports `name@hub`) |
| `/capabilities` | GET | Capability index with agent lists |
| `/dark-circles` | GET | Aggregated dark circle pressure |
| `/mesh` | GET | Full mesh topology |
| `/query` | POST | `{ capability, minPressure?, hub? }` |
| `/route` | POST | `{ target, task }` |

## Next Steps

### Immediate
- [ ] Add Eddie's local agents to HOG atlas (eddie-automation agent, etc.)
- [ ] Test dark circle aggregation when both hubs have active regions
- [ ] Verify Python bridge updates when Stella regenerates atlas

### Phase 2 (future)
- [ ] Ed25519 message signing for internet exposure
- [ ] WebSocket bridge to Python manifold.server (realtime vs file polling)
- [ ] Work execution engine (agent_request fully executed, not just acknowledged)
- [ ] MRI visualization of federated mesh
- [ ] TLS + signature verification for internet-facing federation

## Logs

- **Trillian:** Background process (pid in `ps aux | grep tsx.*trillian`)
- **HOG:** `~/projects/manifold-federation/hog-federation.log`

## Process IDs (as of deployment)

- Trillian: pid 4683 (session delta-harbor)
- HOG: pid varies (check `ssh marvin@100.70.172.34 'ps aux | grep tsx.*hog'`)
