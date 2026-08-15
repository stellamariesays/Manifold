# Manifold Semantic Router

**The protocol IS the embedding space.**

Current agent federation requires schema contracts — every new agent must explicitly declare its capabilities in a format peers understand. This module replaces that with cosine similarity routing: agents publish a capability *embedding*, and task routing is just nearest-neighbour search.

No schema negotiation. No versioning drift. New agents auto-discover their niche.

---

## Concept

```
Traditional:  task → string match → agent
Semantic:     task → embed → cosine sim → agent
```

Each agent publishes a vector when it joins the mesh. Routing a task means embedding the task description and finding the closest agent vectors. The mesh self-organizes — agents that are semantically close become natural peers without ever negotiating a schema.

---

## Quick start

```python
from manifold.semantic_registry import SemanticRegistry

# Auto-detects best embedder: ollama (nomic-embed-text) > OpenAI > TF-IDF fallback
registry = SemanticRegistry()

# Register agents with their capability descriptions
registry.register("stella",   ["bitcoin", "trading", "FFT", "backtesting", "momentum"])
registry.register("braid",    ["solar-flares", "SHARP", "XGBoost", "heliophysics"])
registry.register("angelina", ["bank-risk", "FDIC", "SHAP", "short-selling"])

# Route a task — returns agents ranked by semantic similarity
results = registry.seek("I need help with XGBoost feature importance on financial data")
for r in results:
    print(r)
# → <AgentRef 'angelina' sim=82% caps=[bank-risk, FDIC, SHAP]>
# → <AgentRef 'braid'    sim=71% caps=[solar-flares, SHARP, XGBoost]>
# → <AgentRef 'stella'   sim=44% caps=[bitcoin, trading, FFT]>
```

---

## Embedder backends

The registry auto-detects the best available embedder at startup:

| Backend | Quality | Deps | Notes |
|---------|---------|------|-------|
| **ollama** (nomic-embed-text) | ★★★ | ollama running locally | Best for local deployments |
| **OpenAI** (text-embedding-3-small) | ★★★ | `OPENAI_API_KEY` | Any OpenAI-compatible endpoint |
| **TF-IDF** | ★★ | none | Pure Python fallback, always works |

Force a specific backend:
```python
registry = SemanticRegistry(embedder="tfidf")    # force fallback
registry = SemanticRegistry(embedder="ollama")   # force ollama
registry = SemanticRegistry(embedder="openai")   # force openai
```

---

## Benchmark (nomic-embed-text, 5 agents)

```
Routing accuracy: 5/6 (83%)
Registration: ~40ms/agent
Query latency: ~18ms
```

The one miss: SHAP query routing — fixable by enriching the agent's capability description with more domain-specific terms. Semantic synonym test passes: "trend-following signals using moving averages" correctly routes to the trading agent without "trend-following" appearing in its capability list.

---

## Integration with Manifold

This module is designed as a drop-in enhancement for Manifold's existing `CapabilityRegistry`. The `update_from_announcement()` method is wire-compatible with the existing registry protocol — peers that send embeddings alongside their capability lists get semantic routing; legacy peers fall back to local re-embedding.

See `manifold/registry.py` for the existing Jaccard-based implementation this extends.

---

## Run the demo

```bash
cd semantic_router
python3 demo.py                    # auto-detect embedder
python3 demo.py --embedder tfidf   # force TF-IDF (no deps)
python3 demo.py --embedder ollama  # requires ollama
```

## Run tests

```bash
cd semantic_router
python3 -m pytest tests/ -v        # 23 tests, ~0.03s
```

---

## Files

```
semantic_router/
  manifold/
    __init__.py              — exports SemanticRegistry, SemanticAgentRef
    semantic_registry.py     — core implementation
  tests/
    test_semantic_registry.py — 23 unit tests
  demo.py                    — routing quality benchmark
  README.md                  — this file
```
