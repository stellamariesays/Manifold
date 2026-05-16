"""Tests for the web research capability pack."""

import asyncio
import pytest

from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_research_pack, load_all_packs
from manifold.agent import Agent


@pytest.fixture
def research_builder():
    agent = Agent(name="test-researcher")
    builder = CapabilityBuilder(agent)
    load_research_pack(builder)
    return builder


# ─── research-plan ──────────────────────────────────────────────────────

class TestResearchPlan:
    @pytest.mark.asyncio
    async def test_basic_plan(self, research_builder):
        r = await research_builder.invoke("research-plan", {
            "question": "What are the effects of climate change on ocean biodiversity?",
        })
        assert r.ok
        assert len(r.output["subqueries"]) >= 1
        assert r.output["question"] == "What are the effects of climate change on ocean biodiversity?"
        assert r.output["plan_id"] is not None

    @pytest.mark.asyncio
    async def test_depth_control(self, research_builder):
        quick = await research_builder.invoke("research-plan", {
            "question": "quantum computing basics", "depth": "quick",
        })
        deep = await research_builder.invoke("research-plan", {
            "question": "quantum computing basics", "depth": "deep",
        })
        assert quick.output["depth"] == "quick"
        assert deep.output["depth"] == "deep"
        assert deep.output["estimated_sources"] >= quick.output["estimated_sources"]

    @pytest.mark.asyncio
    async def test_max_subqueries_limit(self, research_builder):
        r = await research_builder.invoke("research-plan", {
            "question": "artificial intelligence applications in healthcare",
            "max_subqueries": 3,
        })
        assert len(r.output["subqueries"]) <= 3

    @pytest.mark.asyncio
    async def test_empty_question(self, research_builder):
        r = await research_builder.invoke("research-plan", {"question": ""})
        assert r.ok  # handler ran
        assert r.output.get("ok") is False

    @pytest.mark.asyncio
    async def test_quoted_phrases_extracted(self, research_builder):
        r = await research_builder.invoke("research-plan", {
            "question": 'What is "quantum supremacy" and why does it matter?',
        })
        assert r.ok
        assert any("quantum supremacy" in sq for sq in r.output["subqueries"])


# ─── research-extract ───────────────────────────────────────────────────

class TestResearchExtract:
    @pytest.mark.asyncio
    async def test_extract_facts(self, research_builder):
        text = (
            "Researchers at MIT found that neural networks can achieve 95% accuracy. "
            "The study was published in Nature and showed significant improvement over previous methods. "
            "According to the lead author, this represents a breakthrough in deep learning."
        )
        r = await research_builder.invoke("research-extract", {
            "text": text, "source": "nature.com",
        })
        assert r.ok
        assert r.output["fact_count"] > 0
        assert r.output["source"] == "nature.com"
        assert r.output["word_count"] > 0

    @pytest.mark.asyncio
    async def test_extract_entities(self, research_builder):
        text = "Tim Berners-Lee founded the World Wide Web Consortium at MIT."
        r = await research_builder.invoke("research-extract", {"text": text, "source": "test"})
        assert r.ok
        assert "entities" in r.output

    @pytest.mark.asyncio
    async def test_empty_text(self, research_builder):
        r = await research_builder.invoke("research-extract", {"text": ""})
        assert r.output.get("ok") is False

    @pytest.mark.asyncio
    async def test_max_facts_limit(self, research_builder):
        text = ". ".join([f"Study {i} reported that method X achieved {i*10}% accuracy" for i in range(30)])
        r = await research_builder.invoke("research-extract", {"text": text, "max_facts": 5})
        assert r.output["fact_count"] <= 5


# ─── research-synthesize ────────────────────────────────────────────────

class TestResearchSynthesize:
    @pytest.mark.asyncio
    async def test_summary_format(self, research_builder):
        findings = [
            {
                "facts": [{"claim": "AI reduces diagnosis time by 40%", "confidence": 0.9, "source": "nature.com"}],
                "source": "nature.com",
                "entities": {"people": [], "organizations": [], "locations": []},
            },
            {
                "facts": [{"claim": "ML models show promise in early detection", "confidence": 0.8, "source": "arxiv.org"}],
                "source": "arxiv.org",
                "entities": {"people": [], "organizations": [], "locations": []},
            },
        ]
        r = await research_builder.invoke("research-synthesize", {
            "findings": findings, "question": "AI in medical diagnosis", "format": "summary",
        })
        assert r.ok
        assert r.output["source_count"] == 2
        assert "AI in medical diagnosis" in r.output["content"]
        assert r.output["format"] == "summary"

    @pytest.mark.asyncio
    async def test_bullet_format(self, research_builder):
        findings = [{
            "facts": [{"claim": "Test claim", "confidence": 0.8, "source": "test.com"}],
            "source": "test.com",
            "entities": {"people": [], "organizations": [], "locations": []},
        }]
        r = await research_builder.invoke("research-synthesize", {"findings": findings, "format": "bullet"})
        assert r.ok
        assert "•" in r.output["content"]

    @pytest.mark.asyncio
    async def test_briefing_format(self, research_builder):
        findings = [{
            "facts": [{"claim": "Quantum computers achieved 1000 qubits", "confidence": 0.95, "source": "ibm.com"}],
            "source": "ibm.com",
            "entities": {"people": [], "organizations": [], "locations": []},
        }]
        r = await research_builder.invoke("research-synthesize", {
            "findings": findings, "question": "Quantum computing progress", "format": "briefing",
        })
        assert r.ok
        assert "Briefing" in r.output["content"]

    @pytest.mark.asyncio
    async def test_empty_findings(self, research_builder):
        r = await research_builder.invoke("research-synthesize", {"findings": []})
        assert r.output.get("ok") is False

    @pytest.mark.asyncio
    async def test_deduplication(self, research_builder):
        findings = [
            {
                "facts": [{"claim": "Same fact repeated here", "confidence": 0.9, "source": "a.com"}],
                "source": "a.com",
                "entities": {"people": [], "organizations": [], "locations": []},
            },
            {
                "facts": [{"claim": "Same fact repeated here", "confidence": 0.8, "source": "b.com"}],
                "source": "b.com",
                "entities": {"people": [], "organizations": [], "locations": []},
            },
        ]
        r = await research_builder.invoke("research-synthesize", {"findings": findings})
        assert r.output["fact_count"] == 1


# ─── research-source-score ──────────────────────────────────────────────

class TestResearchSourceScore:
    @pytest.mark.asyncio
    async def test_rank_sources(self, research_builder):
        sources = [
            {"url": "https://nature.com/article1", "name": "Nature Article", "fact_count": 5, "avg_confidence": 0.9},
            {"url": "https://random-blog.com/post", "name": "Random Blog", "fact_count": 2, "avg_confidence": 0.5},
            {"url": "https://arxiv.org/paper", "name": "ArXiv Paper", "fact_count": 8, "avg_confidence": 0.85},
        ]
        r = await research_builder.invoke("research-source-score", {"sources": sources})
        assert r.ok
        assert r.output["total"] == 3
        ranked = r.output["ranked_sources"]
        assert ranked[0]["domain_reliability"] >= ranked[-1]["domain_reliability"]

    @pytest.mark.asyncio
    async def test_high_reliability_count(self, research_builder):
        sources = [
            {"url": "https://nature.com/a", "fact_count": 5, "avg_confidence": 0.9},
            {"url": "https://science.org/b", "fact_count": 3, "avg_confidence": 0.85},
            {"url": "https://medium.com/c", "fact_count": 4, "avg_confidence": 0.7},
        ]
        r = await research_builder.invoke("research-source-score", {"sources": sources})
        assert r.output["high_reliability"] == 2

    @pytest.mark.asyncio
    async def test_empty_sources(self, research_builder):
        r = await research_builder.invoke("research-source-score", {"sources": []})
        assert r.output.get("ok") is False

    @pytest.mark.asyncio
    async def test_source_without_url(self, research_builder):
        sources = [{"name": "Unknown Source", "fact_count": 1, "avg_confidence": 0.5}]
        r = await research_builder.invoke("research-source-score", {"sources": sources})
        assert r.ok
        assert r.output["total"] == 1


# ─── Integration: full pipeline ─────────────────────────────────────────

class TestResearchPipeline:
    @pytest.mark.asyncio
    async def test_plan_extract_synthesize(self, research_builder):
        plan = await research_builder.invoke("research-plan", {
            "question": "benefits of renewable energy", "depth": "quick",
        })
        assert plan.ok

        extract = await research_builder.invoke("research-extract", {
            "text": "Studies showed that solar energy costs dropped by 90% in the last decade. "
                    "According to the IEA, renewables will account for 80% of new power capacity by 2030.",
            "source": "iea.org",
        })
        assert extract.ok

        synthesize = await research_builder.invoke("research-synthesize", {
            "findings": [extract.output], "question": "benefits of renewable energy",
        })
        assert synthesize.ok
        assert synthesize.output["source_count"] >= 1

    @pytest.mark.asyncio
    async def test_loaded_in_all_packs(self):
        agent = Agent(name="pack-tester")
        builder = CapabilityBuilder(agent)
        specs = load_all_packs(builder)
        names = [s.name for s in specs]
        assert "research-plan" in names
        assert "research-extract" in names
        assert "research-synthesize" in names
        assert "research-source-score" in names
