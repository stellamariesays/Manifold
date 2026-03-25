"""
semantic.py — 'solar-topology' finds 'stellar-dynamics'.

Before: token overlap only. 'solar' ∩ 'stellar' = ∅. No connection.
After:  trigram similarity. 'solar' ~ 'stellar' (share 'lar'). Bridge found.

This example runs three comparisons:
  1. Token-only atlas  — the old behaviour, for reference
  2. Trigram atlas     — built-in, zero deps, structurally aware
  3. Injected embeddings (optional, skipped if not installed)
"""

import asyncio
from manifold import Agent
from manifold.semantic import phrase_trigram_similarity


async def main() -> None:
    # Show trigram similarities first so the improvement is clear
    print("━━━ Trigram similarities ━━━")
    pairs = [
        ("solar", "stellar"),
        ("solar-topology", "stellar-dynamics"),
        ("flare-prediction", "stellar-flare-model"),
        ("time-series-analysis", "temporal-sequence"),
        ("n-body-dynamics", "orbital-mechanics"),
        ("anomaly-detection", "outlier-analysis"),
        ("solar-topology", "orbital-mechanics"),   # should be low
        ("knowledge-graphs", "solar-topology"),    # should be very low
    ]
    for a, b in pairs:
        sim = phrase_trigram_similarity(a, b)
        bar = "█" * int(sim * 20)
        print(f"  {a!r:35} ~ {b!r:35} {sim:.2f} {bar}")

    # ── Build the mesh ────────────────────────────────────────────────────

    braid = Agent(name="braid")
    braid.knows(["solar-topology", "flare-prediction", "time-series-analysis"])

    astro = Agent(name="astro")
    astro.knows(["stellar-dynamics", "stellar-flare-model", "orbital-period"])

    linguist = Agent(name="linguist")
    linguist.knows(["knowledge-graphs", "semantic-embedding", "natural-language"])

    for agent in [braid, astro, linguist]:
        await agent.join()
    await asyncio.sleep(0.05)

    # ── Token-only atlas ──────────────────────────────────────────────────

    print("\n━━━ Token-only atlas (old behaviour) ━━━")

    # Temporarily build with no semantic matcher
    # by patching: use exact intersection only
    from manifold.atlas import Atlas
    from manifold.transition import TransitionMap
    from manifold.chart import Chart

    token_atlas = Atlas()
    for record in braid._registry.all_agents():
        chart = Chart.from_agent(record.name, record.capabilities, record.focus)
        token_atlas._charts[record.name] = chart
    names = list(token_atlas._charts.keys())
    for i, s in enumerate(names):
        for t in names[i+1:]:
            sc, tc = token_atlas._charts[s], token_atlas._charts[t]
            fwd = TransitionMap.between(sc, tc, matcher=None)  # no semantic
            rev = TransitionMap.between(tc, sc, matcher=None)
            if not fwd.is_empty():
                token_atlas._maps[(s, t)] = fwd
            if not rev.is_empty():
                token_atlas._maps[(t, s)] = rev

    print(f"  {token_atlas}")
    for (src, tgt), tm in token_atlas._maps.items():
        print(f"  {tm}")

    path = token_atlas.geodesic("braid", "stellar-dynamics")
    print(f"  geodesic braid→stellar-dynamics: {'→'.join(s.agent for s in path) if path else 'UNREACHABLE'}")

    # ── Trigram atlas ─────────────────────────────────────────────────────

    print("\n━━━ Trigram atlas (built-in, zero deps) ━━━")
    tri_atlas = braid.atlas()   # default: trigram matcher
    print(f"  {tri_atlas}")

    for (src, tgt), tm in tri_atlas._maps.items():
        print(f"  {tm}")
        if tm.translation:
            for term, targets in list(tm.translation.items())[:2]:
                print(f"    {term!r} → {targets}")

    path = tri_atlas.geodesic("braid", "stellar-dynamics")
    print(f"\n  geodesic braid→stellar-dynamics:")
    if path:
        for step in path:
            if step.via_map:
                print(f"    via {step.via_map} → {step.agent!r} (loss {step.cumulative_loss:.2f})")
            else:
                print(f"    start: {step.agent!r}")
    else:
        print("    UNREACHABLE")

    path2 = tri_atlas.geodesic("braid", "knowledge-graphs")
    print(f"\n  geodesic braid→knowledge-graphs:")
    if path2:
        for step in path2:
            if step.via_map:
                print(f"    via {step.via_map} → {step.agent!r}")
            else:
                print(f"    start: {step.agent!r}")
    else:
        print("    UNREACHABLE (still a hole — correct, linguist is truly foreign)")

    # ── With injected embeddings (optional) ──────────────────────────────

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        print("\n━━━ Embedding atlas (sentence-transformers) ━━━")
        emb_atlas = braid.atlas(embedding_fn=lambda s: model.encode(s).tolist())
        print(f"  {emb_atlas}")
        for (src, tgt), tm in emb_atlas._maps.items():
            print(f"  {tm}")
        path = emb_atlas.geodesic("braid", "stellar-dynamics")
        print(f"  geodesic braid→stellar-dynamics: {'→'.join(s.agent for s in path) if path else 'UNREACHABLE'}")
    except ImportError:
        print("\n  (sentence-transformers not installed — skipping embedding demo)")
        print("  pip install sentence-transformers  to enable full semantic mode")

    for agent in [braid, astro, linguist]:
        await agent.leave()


if __name__ == "__main__":
    asyncio.run(main())
