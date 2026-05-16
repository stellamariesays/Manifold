#!/usr/bin/env python3
"""
Manifold Capability Lifecycle — End-to-End Integration Demo

Demonstrates the complete flow of capabilities across a Manifold mesh:
1. Agents define structured capabilities via CapabilityBuilder
2. Agents discover peers via Discovery (local search)
3. Tasks are routed via Audience (multi-signal scoring)
4. Capabilities are negotiated via Negotiation (contracts + stakes)
5. Tasks are dispatched via TaskDispatcher (retry + fallback)
6. Results are graded and trust scores updated

This is the "full loop" — from registration to trust accumulation.

Usage:
    python3 examples/capability_lifecycle.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.discovery import Discovery
from manifold.grading import Grade, GradeReport
from manifold.trust_ledger import TrustLedger


async def main():
    print("=" * 60)
    print("Manifold Capability Lifecycle — Full Integration Demo")
    print("=" * 60)

    # ── 1. Create mesh agents ─────────────────────────────────────────
    print("\n📡 Step 1: Creating mesh agents...")

    coordinator = Agent(name="coordinator", transport="memory://mesh")
    coordinator.knows(["task-routing", "orchestration"])
    await coordinator.join()

    analyst = Agent(name="analyst", transport="memory://mesh")
    analyst.knows(["data-analysis", "sentiment", "nlp"])
    await analyst.join()

    researcher = Agent(name="researcher", transport="memory://mesh")
    researcher.knows(["data-analysis", "web-search", "fact-checking"])
    await researcher.join()

    writer = Agent(name="writer", transport="memory://mesh")
    writer.knows(["summarization", "report-writing", "nlp"])
    await writer.join()

    print(f"  ✓ {coordinator._name}: {coordinator._capabilities}")
    print(f"  ✓ {analyst._name}: {analyst._capabilities}")
    print(f"  ✓ {researcher._name}: {researcher._capabilities}")
    print(f"  ✓ {writer._name}: {writer._capabilities}")

    # ── 2. Define structured capabilities ─────────────────────────────
    print("\n🔧 Step 2: Defining structured capabilities...")

    analyst_builder = CapabilityBuilder(analyst)

    @analyst_builder.define(
        name="sentiment-analysis",
        version="2.1.0",
        description="Analyze sentiment of text data across multiple languages",
        inputs=["text", "language"],
        outputs=["sentiment", "confidence", "key_phrases"],
        tags=["nlp", "analysis", "sentiment"],
    )
    async def analyze_sentiment(payload: dict) -> dict:
        text = payload.get("text", "")
        # Simulated analysis
        score = 0.7 if "good" in text.lower() else 0.3
        return {
            "sentiment": "positive" if score > 0.5 else "negative",
            "confidence": score,
            "key_phrases": ["simulated phrase"],
        }

    researcher_builder = CapabilityBuilder(researcher)

    @researcher_builder.define(
        name="fact-check",
        version="1.0.0",
        description="Verify factual claims against knowledge base",
        inputs=["claim", "domain"],
        outputs=["verdict", "sources", "confidence"],
        tags=["research", "verification", "fact-checking"],
    )
    async def fact_check(payload: dict) -> dict:
        return {
            "verdict": "verified",
            "sources": ["knowledge-base"],
            "confidence": 0.85,
        }

    writer_builder = CapabilityBuilder(writer)

    @writer_builder.define(
        name="summarize",
        version="1.3.0",
        description="Generate concise summaries of complex documents",
        inputs=["text", "max_length", "style"],
        outputs=["summary", "word_count", "coverage"],
        tags=["nlp", "summarization", "writing"],
    )
    async def summarize(payload: dict) -> dict:
        text = payload.get("text", "")
        max_len = payload.get("max_length", 100)
        summary = text[:max_len] + "..." if len(text) > max_len else text
        return {
            "summary": summary,
            "word_count": len(summary.split()),
            "coverage": 0.9,
        }

    for builder, name in [(analyst_builder, "analyst"), (researcher_builder, "researcher"), (writer_builder, "writer")]:
        caps = builder.list_capabilities()
        for c in caps:
            print(f"  ✓ {name}: {c.schema_summary()}")

    # ── 3. Wire up the mesh (registry announcements) ──────────────────
    print("\n🌐 Step 3: Connecting mesh via registry announcements...")

    for src in [analyst, researcher, writer]:
        for target in [coordinator, analyst, researcher, writer]:
            if src._name != target._name:
                await target._on_registry_announcement({
                    "name": src._name,
                    "capabilities": src._capabilities,
                    "address": src._address,
                    "focus": src._capabilities[0] if src._capabilities else None,
                })

    print("  ✓ All agents registered with each other")

    # ── 4. Discovery — find relevant capabilities ─────────────────────
    print("\n🔍 Step 4: Discovering capabilities...")

    disco = Discovery(coordinator, min_relevance=0.15)

    search_queries = ["sentiment", "data-analysis", "summarization", "fact-checking"]
    for query in search_queries:
        result = disco.search_local(query)
        if result.hits:
            best = result.best
            print(f"  '{query}' → {best.agent_name}.{best.capability} (relevance={best.relevance:.2f})")
        else:
            print(f"  '{query}' → no matches")

    # ── 5. Audience routing — who should handle this? ─────────────────
    print("\n🎯 Step 5: Audience routing...")

    topics = ["nlp-analysis", "data-analysis", "report-writing"]
    for topic in topics:
        report = coordinator.audience(topic)
        if report.entries:
            top = report.entries[0]
            sigs = "+".join(s.value for s in top.signals)
            print(f"  '{topic}' → {top.name} (score={top.score:.2f}, signals=[{sigs}])")
        else:
            print(f"  '{topic}' → no audience found")

    # ── 6. Execute capabilities ───────────────────────────────────────
    print("\n⚡ Step 6: Executing capabilities...")

    # Sentiment analysis
    result = await analyst_builder.invoke(
        "sentiment-analysis",
        {"text": "This is a good product with great features", "language": "en"},
    )
    print(f"  sentiment-analysis: ok={result.ok}, output={result.output}")

    # Fact checking
    result = await researcher_builder.invoke(
        "fact-check",
        {"claim": "The Earth orbits the Sun", "domain": "astronomy"},
    )
    print(f"  fact-check: ok={result.ok}, output={result.output}")

    # Summarization
    result = await writer_builder.invoke(
        "summarize",
        {"text": "The Manifold cognitive mesh enables AI agents to discover, negotiate, and compose capabilities across a distributed network.", "max_length": 80, "style": "concise"},
    )
    print(f"  summarize: ok={result.ok}, output={result.output}")

    # ── 7. Grade results and update trust ─────────────────────────────
    print("\n📊 Step 7: Grading results and updating trust...")

    # Coordinator grades each agent
    coordinator.grade("analyst", "sentiment", score=0.92)
    coordinator.grade("researcher", "fact-check", score=0.88)
    coordinator.grade("writer", "summarization", score=0.95)

    # Check trust ledger
    for agent_name in ["analyst", "researcher", "writer"]:
        scores = []
        for domain_map in coordinator._ledger._records.get(agent_name, {}).values():
            for rec in domain_map.grades if hasattr(domain_map, 'grades') else []:
                scores.append(rec.score)
        # Access the graded records
        domains = coordinator._ledger._records.get(agent_name, {})
        domain_scores = []
        for dom, rec in domains.items():
            if rec.grades:
                avg = sum(g.score for g in rec.grades) / len(rec.grades)
                domain_scores.append((dom, avg))
        if domain_scores:
            for dom, avg in domain_scores:
                print(f"  {agent_name} [{dom}]: trust={avg:.2f}")

    # ── 8. Re-route with trust signals ────────────────────────────────
    print("\n🔄 Step 8: Re-routing with trust signals...")

    report = coordinator.audience("nlp-analysis")
    for entry in report.entries:
        sigs = "+".join(s.value for s in entry.signals)
        print(f"  {entry.name}: score={entry.score:.2f} signals=[{sigs}] — {entry.reason}")

    # ── 9. Builder stats ──────────────────────────────────────────────
    print("\n📈 Step 9: Capability statistics...")

    for builder, name in [(analyst_builder, "analyst"), (researcher_builder, "researcher"), (writer_builder, "writer")]:
        stats = builder.stats()
        print(f"  {name}: {stats['active']} active caps, {stats['total_invocations']} invocations, avg {stats['avg_latency_ms']:.1f}ms")

    # ── 10. Full catalog export ───────────────────────────────────────
    print("\n📋 Step 10: Full capability catalog...")

    all_builders = [(analyst_builder, "analyst"), (researcher_builder, "researcher"), (writer_builder, "writer")]
    for builder, name in all_builders:
        catalog = builder.catalog()
        for cap_name, info in catalog.items():
            print(f"  {name}/{cap_name} v{info['version']} ({info['status']}) → {info['outputs']}")

    print("\n" + "=" * 60)
    print("✅ Capability lifecycle complete!")
    print("   Discovery → Routing → Execution → Grading → Trust → Re-routing")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
