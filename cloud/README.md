# Manifold Cloud

**Federated AI Agent Infrastructure** — the commercial layer on top of the Manifold federation protocol.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Manifold Cloud Gateway (:3000)        │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │   Auth    │  │  Rate    │  │   Billing         │  │
│  │  (API key)│  │ Limiter  │  │   (Stripe)        │  │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       │              │                  │             │
│  ┌────▼──────────────▼──────────────────▼──────────┐ │
│  │              Usage Tracking (Redis)              │ │
│  └──────────────────────────────────────────────────┘ │
│  ┌────────────┐  ┌────────────────────────────────┐  │
│  │ Model Router│  │       Hub Manager              │  │
│  │ (9+ models) │  │   (auto-scale, health)         │  │
│  └────────────┘  └────────────────────────────────┘  │
│                       │                               │
│            ┌──────────▼───────────┐                   │
│            │  /v1/ API (proxied)  │                   │
│            └──────────┬───────────┘                   │
└────────────────────────┼─────────────────────────────┘
                         │
              ┌──────────▼───────────┐
              │  Federation Hub      │
              │  (existing Manifold  │
              │   REST API :8767)    │
              └──────────────────────┘
```

## Quick Start

### Option 1: Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env with your keys (or leave empty for mock mode)

docker compose up -d

# Gateway → http://localhost:3000
# Landing page → http://localhost:3000
# Health check → http://localhost:3000/health
```

### Option 2: Local dev

```bash
# Start a federation hub (from the manifold-federation project)
cd ../manifold-federation-broken
npm start  # listens on :8767

# Start the cloud gateway
cd ../manifold-cloud
npm install
npm run dev  # listens on :3000
```

## API

### Registration

```bash
# Get an API key (no auth required)
curl -X POST http://localhost:3000/v1/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","tier":"free"}'

# Response:
# {
#   "success": true,
#   "data": {
#     "customerId": "uuid...",
#     "apiKey": "mk_test_abc123...",
#     "tier": "free",
#     "checkoutUrl": null
#   }
# }
```

### Authenticated API Calls

All endpoints under `/v1/` require an API key:

```bash
# Authorization: Bearer mk_test_...
# or
# X-API-Key: mk_test_...

# List agents
curl http://localhost:3000/v1/agents \
  -H "Authorization: Bearer mk_test_..."

# Submit a task
curl -X POST http://localhost:3000/v1/task \
  -H "Authorization: Bearer mk_test_..." \
  -H "Content-Type: application/json" \
  -d '{"task":"analyze BTC trends","capabilities":["reasoning"]}'

# Route a prompt
curl -X POST http://localhost:3000/v1/route \
  -H "Authorization: Bearer mk_test_..." \
  -H "Content-Type: application/json" \
  -d '{"prompt":"write a poem","capabilities":["chat"],"preferCheapest":true}'
```

### Cloud-Only Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/v1/register` | POST | Register customer, get API key |
| `/v1/usage` | GET | Current month usage stats |
| `/v1/upgrade` | POST | Upgrade tier (returns Stripe checkout URL) |
| `/v1/models` | GET | Available models + provider health |
| `/v1/route` | POST | Route a prompt to best model |
| `/v1/hubs` | GET | List federation hubs |
| `/v1/hubs/register` | POST | Register a new hub |
| `/v1/hubs/:id` | DELETE | Deregister a hub |
| `/v1/hubs/scale` | POST | Evaluate auto-scaling |
| `/webhook/stripe` | POST | Stripe webhook receiver |

### Proxied Federation Endpoints

All federation endpoints are available under `/v1/` with auth:

| Federation Endpoint | Cloud Endpoint |
|---|---|
| GET /status | GET /v1/status |
| GET /peers | GET /v1/peers |
| GET /agents | GET /v1/agents |
| GET /capabilities | GET /v1/capabilities |
| GET /mesh | GET /v1/mesh |
| GET /metrics | GET /v1/metrics |
| POST /agents/register | POST /v1/agents/register |
| POST /task | POST /v1/task |
| POST /query | POST /v1/query |
| GET /task/:id | GET /v1/task/:id |
| GET /tasks | GET /v1/tasks |
| GET /agents/:name | GET /v1/agents/:name |
| GET /attestation/* | GET /v1/attestation/* |
| POST /attestation/* | POST /v1/attestation/* |
| GET /detections/* | GET /v1/detections/* |
| GET /trust | GET /v1/trust |
| GET /gossip | GET /v1/gossip |

## Pricing Tiers

| Tier | Price | Requests/mo | Rate Limit |
|---|---|---|---|
| Free | $0 | 100 | 10/min |
| Pro | $29/mo | 10,000 | 100/min |
| Enterprise | $299/mo | 100,000 | Unlimited |

## Model Router

The router selects the best model based on:
- Required capabilities (chat, code, vision, reasoning, tool-use, long-context, fast)
- Cost optimization (cheapest model that meets requirements)
- Provider health and availability
- Automatic failover on provider errors

**Supported providers:**
- OpenAI (GPT-4o, GPT-4o-mini, o3-mini)
- Anthropic (Claude Sonnet 4, Claude Haiku 3.5)
- Google (Gemini 2.5 Pro, Gemini 2.5 Flash)
- Local (Llama 3.3 70B, Qwen 2.5 Coder — via Ollama/vLLM)

## Configuration

See `.env.example` for all environment variables. Key ones:

| Variable | Default | Description |
|---|---|---|
| `PORT` | 3000 | Gateway listen port |
| `FEDERATION_API_URL` | http://localhost:8767 | Underlying federation REST API |
| `REDIS_URL` | (empty) | Redis URL (falls back to in-memory) |
| `STRIPE_SECRET_KEY` | (empty) | Stripe key (mock mode if empty) |
| `OPENAI_API_KEY` | (empty) | OpenAI API key for router |
| `ANTHROPIC_API_KEY` | (empty) | Anthropic API key for router |
| `GOOGLE_API_KEY` | (empty) | Google API key for router |
| `LOCAL_MODEL_URL` | (empty) | Local model endpoint (Ollama etc.) |

## Development

```bash
npm run dev      # Hot-reload dev server
npm run build    # Compile TypeScript
npm run lint     # Type-check without emitting
```

## License

Commercial. © 2026 Manifold Cloud.
