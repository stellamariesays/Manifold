# Manifold Pricing Spec — Model 3: Free Mesh, Paid Intelligence

**Created:** 2026-04-21
**Status:** Draft for Hal's review

---

## Core Thesis

The mesh is the product's immune system. The intelligence is the product.

**Free tier grows the network. Paid tier monetizes the differentiator.**

The more hubs and agents on the mesh, the more valuable the routing intelligence becomes. So make the mesh free — let anyone join, declare capabilities, run tasks. Then charge for the brain that makes the mesh actually useful.

---

## What's Free (The Mesh)

Anyone can:
- Run a Manifold hub (`manifold start`)
- Join the public federation (show MeshPass, you're in)
- Register agents with `knows()` capabilities
- Query the mesh with `seek()` — basic capability lookup
- Route tasks to their own agents (local-first)
- Broadcast cognitive focus with `think()`
- Participate in peer attestation (trust building)

**Why free:** Every hub that joins makes the mesh more valuable for paying customers. Free nodes are infrastructure, not freeloaders — they're the mesh's immune system.

**Limits on free:**
- No priority routing — free tier tasks go to best-available, not best-match
- No cross-hub orchestration — tasks stay local unless you pay
- Basic `seek()` only — no Sophia density analysis, no fog mapping
- No SLA, no support, no guarantees

---

## What's Paid (The Intelligence Layer)

### Tier 1: Navigator — $49/mo per hub

*For teams running agents that need smarter routing.*

- **Smart routing** — Numinous-powered task orchestration across hubs
- **Priority queue** — your tasks get routed before free-tier ones
- **Capability matching** — `seek()` enhanced with Sophia density scoring
- **Mesh analytics dashboard** — see your agents' coverage, gaps, pressure maps
- **5,000 routed tasks/mo** included (overage at $0.01/task)
- Email support

### Tier 2: Orchestrator — $199/mo per hub

*For teams building production multi-agent systems on the mesh.*

- Everything in Navigator
- **Cross-hub orchestration** — route tasks across the entire federation automatically
- **FOG (Epistemic Fog) access** — see knowledge gaps, asymmetric blindness, coverage maps
- **Teacup snapshots** — capture and replay cognitive moments for debugging
- **Custom trust policies** — set your own grade thresholds, stake requirements, routing rules
- **25,000 routed tasks/mo** included (overage at $0.008/task)
- **3 hub connections** included (federate across your own infra + public mesh)
- Priority support (24h response)

### Tier 3: Sovereign — $499/mo

*For organizations running their own federation enclave.*

- Everything in Orchestrator
- **Private enclave** — your own federated zone with controlled trust propagation
- **Unlimited hubs** within your enclave
- **Unlimited routed tasks** within your enclave (public mesh routing: 100k/mo included)
- **Custom Sophia tuning** — adjust wisdom density thresholds for your use case
- **Mesh state replication** — full copy of capability index for air-gapped operation
- **SLA** — 99.9% uptime guarantee, 4h response
- **White-glove onboarding**

---

## The Intelligence Breakdown — What You're Actually Paying For

| Feature | Free | Navigator | Orchestrator | Sovereign |
|---------|------|-----------|-------------|-----------|
| Basic `knows()` / `seek()` / `think()` | ✅ | ✅ | ✅ | ✅ |
| Local task routing | ✅ | ✅ | ✅ | ✅ |
| Cross-hub routing | ❌ | ✅ | ✅ | ✅ |
| Smart matching (Sophia) | ❌ | Basic | Full | Tunable |
| FOG (fog mapping) | ❌ | ❌ | ✅ | ✅ |
| Teacup (moment capture) | ❌ | ❌ | ✅ | ✅ |
| Custom trust policies | ❌ | ❌ | ✅ | ✅ |
| Private enclave | ❌ | ❌ | ❌ | ✅ |
| Priority routing | ❌ | ✅ | ✅ | ✅ |
| Mesh analytics | ❌ | Dashboard | Dashboard + API | Full + Custom |
| Hub connections | 1 | 1 | 3 | Unlimited |
| Routed tasks/mo | Local only | 5k | 25k | Unlimited* |
| Overage per task | n/a | $0.01 | $0.008 | $0.005 |

*Sovereign = unlimited within enclave, 100k/mo on public mesh

---

## Revenue Math (Conservative)

Assume 6-month trajectory:

| Metric | Month 1 | Month 3 | Month 6 |
|--------|---------|---------|---------|
| Free hubs | 20 | 100 | 500 |
| Navigator | 2 | 15 | 60 |
| Orchestrator | 0 | 3 | 12 |
| Sovereign | 0 | 0 | 2 |
| **MRR** | **$98** | **$3,001** | **$13,624** |
| Task overage | ~$0 | ~$200 | ~$1,500 |
| **Total MRR** | **~$100** | **~$3,200** | **~$15,000** |

Break-even on infra costs at ~Month 3 with just a handful of Navigator customers.

---

## Crypto Angle (Future, Architected Now)

Don't launch a token. But design for it:

1. **Internal credit system** — tasks are priced in "mesh credits" (1 credit = 1 routed task, roughly)
2. **Credits are purchasable** in USD (Stripe) *or* crypto (USDC/ETH at a 10% discount)
3. **Hub operators earn credits** when their agents successfully complete routed tasks (supply side)
4. **If the network grows**, credits naturally become a token — you just add an on-ramp and a DEX
5. **The token represents routing bandwidth** — not governance, not equity, not hype

This way:
- Enterprise pays in USD (they want invoices)
- Indie devs can pay in crypto (they prefer it)
- Hub operators have earning potential (supply side incentive)
- You don't launch a token into an empty network (the #1 mistake)

**Token trigger:** When there's >$10k/mo in task routing volume, credits go on-chain.

---

## Why This Beats Standard SaaS

1. **Free tier IS your growth engine** — every hub makes the mesh smarter for paying customers
2. **Network effects compound** — more hubs → better routing → more value → more customers
3. **You monetize the hard part** — anyone can route a task. Nobody else can do Sophia-density smart matching. That's the moat.
4. **Crypto is a tool, not a gimmick** — it solves real problems (micropayments, hub operator incentives, cross-border) without requiring a token launch on day one
5. **It's honest** — free users get real value (the mesh works). Paid users get the brain on top.

---

## Open Questions

- **Metering approach:** Count tasks at the routing layer or at task completion? (Completion is more accurate but harder to meter)
- **Hub vs agent pricing:** Charge per hub (simpler, predicts infra cost) or per agent (more granular but harder to forecast)?
- **Annual discount:** 20% for annual? (Helps with cash flow early)
- **Startup/dev program:** Free Orchestrator for 6 months for YC/accelerator companies?
- **When to add the crypto credit system:** Gate behind Orchestrator tier, or make it universal?

---

*Next step: Hal reviews, we refine, then Angelina builds the pricing page into the site.*
