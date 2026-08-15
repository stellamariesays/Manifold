"""
Live mesh demo — semantic routing vs Jaccard routing.

The real win for semantic routing isn't "find the one peer" (Jaccard
also finds complementary peers) — it's RANKING when there are 3+ agents
with different specializations. Jaccard gives every peer the same max
gap-score when query tokens don't appear anywhere. Semantic actually
differentiates by query topic.

This demo:
  - 3 agents on the mesh: stella (trading), braid (solar), foghorn (NLP/audio)
  - stella.seek() queries that should rank braid above foghorn (and vice versa)
  - Shows semantic correctly discriminates; Jaccard returns 1.0 for all peers
"""

import asyncio
import sys
sys.path.insert(0, "/home/marvin/Manifold")

from core.agent import Agent


async def flush():
    for _ in range(10):
        await asyncio.sleep(0)


async def run_demo(semantic: bool):
    import core.bridge.memory as _mem
    _mem._BUS.clear()

    label = "SEMANTIC" if semantic else "JACCARD "

    stella  = Agent(name="stella",  semantic=semantic)
    braid   = Agent(name="braid",   semantic=semantic)
    foghorn = Agent(name="foghorn", semantic=semantic)

    stella.knows(["momentum-trading", "bitcoin", "time-series-forecasting", "backtesting"])
    braid.knows(["heliophysics", "solar-flare-classification", "SHARP-parameters", "XGBoost"])
    foghorn.knows(["podcast-production", "audio-processing", "NLP", "speaker-diarization"])

    await stella.join()
    await braid.join()
    await foghorn.join()

    # Re-announce all so everyone's registry is populated
    for agent in [stella, braid, foghorn]:
        await agent._registry.announce(
            agent._transport,
            agent._name,
            agent._capabilities,
            agent._transport_uri,
        )
    await flush()

    # stella.seek() — should rank braid #1 for solar queries, foghorn #1 for audio queries
    # With Jaccard: all non-self agents score 1.0 (100% complementary caps) → random order
    # With semantic: actual cosine differentiates by topic
    queries = [
        # (query, expected_rank1, expected_rank2)
        ("solar wind coronal activity",       "braid",   "foghorn"),
        ("podcast transcription speaker ID",  "foghorn", "braid"),
        ("sunspot AR region classification",  "braid",   "foghorn"),
        ("audio waveform voice synthesis",    "foghorn", "braid"),
    ]

    print(f"\n[{label}] registry: {stella._registry}")
    print(f"{'─'*70}")
    print(f"{'QUERY':<42} {'#1':<10} {'#2':<10} {'RANKED?'}")
    print(f"{'─'*70}")

    passed = 0
    for query, exp1, exp2 in queries:
        refs = await stella.seek(query)
        r1 = refs[0].name if len(refs) > 0 else "—"
        r2 = refs[1].name if len(refs) > 1 else "—"
        s1 = refs[0].gap_score if refs else 0.0
        s2 = refs[1].gap_score if refs else 0.0
        ok = "✓" if r1 == exp1 else "✗"
        if r1 == exp1:
            passed += 1
        print(f"{query:<42} {r1:<6}({s1:.2f})  {r2:<6}({s2:.2f})  {ok}")

    print(f"{'─'*70}")
    print(f"Result: {passed}/{len(queries)}\n")

    for agent in [stella, braid, foghorn]:
        await agent.leave()

    return passed, len(queries)


async def main():
    print("=" * 70)
    print("Manifold Live Demo — 3-Agent Semantic vs Jaccard Routing")
    print("(TF-IDF fallback — no ollama; for full semantic accuracy run with ollama)")
    print("=" * 70)

    sem_pass, total = await run_demo(semantic=True)
    jac_pass, _     = await run_demo(semantic=False)

    print(f"Semantic: {sem_pass}/{total}   Jaccard: {jac_pass}/{total}")
    if sem_pass > jac_pass:
        print("✓ Semantic routing outperforms Jaccard on query discrimination")
    elif sem_pass == jac_pass:
        print("→ Tied (TF-IDF fallback limited — run with ollama for full results)")
    else:
        print("✗ Jaccard wins — unexpected, check query design")


asyncio.run(main())
