"""Tests for the reasoning capability pack."""

import pytest
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_reasoning_pack


# ── Fixtures ────────────────────────────────────────────────────────────

class _FakeAgent:
    """Minimal agent stub for CapabilityBuilder."""
    def __init__(self):
        self._capabilities = []
        self._name = "test-agent"

    def knows(self, caps):
        self._capabilities.extend(caps)


@pytest.fixture
def builder():
    agent = _FakeAgent()
    b = CapabilityBuilder(agent)
    load_reasoning_pack(b)
    return b


# ── Decompose ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_compound_problem(builder):
    """Compound problems split into sub-problems."""
    result = await builder.invoke("reasoning-decompose", {
        "problem": "build the API and deploy to staging and run integration tests",
    })
    assert result.ok
    assert result.output["is_compound"] is True
    assert result.output["total"] >= 2
    for step in result.output["steps"]:
        assert "description" in step
        assert "step" in step


@pytest.mark.asyncio
async def test_decompose_single_problem(builder):
    """Single problems get phased decomposition."""
    result = await builder.invoke("reasoning-decompose", {
        "problem": "What is the best approach for load balancing?",
    })
    assert result.ok
    assert result.output["is_compound"] is False
    assert result.output["total"] >= 2
    types = [s["type"] for s in result.output["steps"]]
    assert "understand" in types


@pytest.mark.asyncio
async def test_decompose_max_steps(builder):
    """max_steps limits decomposition."""
    result = await builder.invoke("reasoning-decompose", {
        "problem": "complex problem",
        "max_steps": 2,
    })
    assert result.output["total"] <= 2


@pytest.mark.asyncio
async def test_decompose_empty_problem(builder):
    """Empty problem returns error."""
    result = await builder.invoke("reasoning-decompose", {"problem": ""})
    assert not result.ok


# ── Synthesize ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthesize_agreement(builder):
    """Similar inputs show high coherence."""
    result = await builder.invoke("reasoning-synthesize", {
        "inputs": [
            "solar energy is growing rapidly",
            "solar power is expanding fast",
            "solar energy adoption is accelerating",
        ],
        "goal": "summarize solar trends",
    })
    assert result.ok
    assert result.output["coherence"] > 0.1
    assert result.output["input_count"] == 3


@pytest.mark.asyncio
async def test_synthesize_divergence(builder):
    """Dissimilar inputs show low coherence."""
    result = await builder.invoke("reasoning-synthesize", {
        "inputs": [
            "quantum computing breakthrough",
            "ancient roman architecture",
            "deep sea fishing techniques",
        ],
    })
    assert result.ok
    assert result.output["divergence_detected"] is True


@pytest.mark.asyncio
async def test_synthesize_empty_inputs(builder):
    """Empty inputs returns error."""
    result = await builder.invoke("reasoning-synthesize", {"inputs": []})
    assert not result.ok


# ── Decide ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decide_basic(builder):
    """Decision analysis returns ranked options."""
    result = await builder.invoke("reasoning-decide", {
        "options": ["simple direct approach", "complex rewrite"],
        "criteria": ["feasibility", "impact"],
    })
    assert result.ok
    assert result.output["recommended"] is not None
    assert len(result.output["ranked_options"]) == 2


@pytest.mark.asyncio
async def test_decide_with_weights(builder):
    """Custom weights influence ranking."""
    result = await builder.invoke("reasoning-decide", {
        "options": ["cheap low-impact solution", "expensive high-impact solution"],
        "criteria": ["cost", "impact"],
        "weights": {"cost": 0.2, "impact": 0.8},
    })
    assert result.ok
    assert result.output["ranked_options"][0]["option"] == "expensive high-impact solution"


@pytest.mark.asyncio
async def test_decide_too_few_options(builder):
    """Less than 2 options returns error."""
    result = await builder.invoke("reasoning-decide", {"options": ["only one"]})
    assert not result.ok


@pytest.mark.asyncio
async def test_decide_default_criteria(builder):
    """Decision works without explicit criteria."""
    result = await builder.invoke("reasoning-decide", {
        "options": ["option a", "option b", "option c"],
    })
    assert result.ok
    assert result.output["recommended"] is not None


# ── Chain of Thought ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chain_basic(builder):
    """Chain-of-thought produces reasoning hops."""
    result = await builder.invoke("reasoning-chain", {
        "premise": "All agents that know rust are fast therefore this agent is fast",
    })
    assert result.ok
    assert result.output["hops"] >= 1
    assert result.output["chain"][0]["confidence"] > 0.5
    first_implications = result.output["chain"][0]["implications"]
    assert len(first_implications) > 0


@pytest.mark.asyncio
async def test_chain_confidence_decay(builder):
    """Confidence decays with more hops."""
    result = await builder.invoke("reasoning-chain", {
        "premise": "complex multi-step reasoning about artificial intelligence and machine learning",
        "max_hops": 5,
    })
    assert result.ok
    if result.output["hops"] >= 2:
        assert result.output["chain"][-1]["confidence"] <= result.output["chain"][0]["confidence"]


@pytest.mark.asyncio
async def test_chain_universal_claims(builder):
    """Chain detects universal claims."""
    result = await builder.invoke("reasoning-chain", {
        "premise": "All systems always fail eventually",
    })
    assert result.ok
    all_implications = [imp for hop in result.output["chain"] for imp in hop["implications"]]
    assert any("universal" in imp.lower() or "counterexample" in imp.lower() for imp in all_implications)


@pytest.mark.asyncio
async def test_chain_empty_premise(builder):
    """Empty premise returns error."""
    result = await builder.invoke("reasoning-chain", {"premise": ""})
    assert not result.ok


@pytest.mark.asyncio
async def test_chain_max_hops_limit(builder):
    """max_hops caps the chain length."""
    result = await builder.invoke("reasoning-chain", {
        "premise": "reasoning about complex artificial intelligence systems and their applications",
        "max_hops": 2,
    })
    assert result.output["hops"] <= 2


# ── Pack registration ──────────────────────────────────────────────────

def test_pack_registers_four_capabilities(builder):
    """Reasoning pack registers exactly 4 capabilities."""
    caps = builder.list_capabilities()
    reasoning_caps = [c for c in caps if c.name.startswith("reasoning-")]
    assert len(reasoning_caps) == 4
    names = {c.name for c in reasoning_caps}
    assert names == {"reasoning-decompose", "reasoning-synthesize", "reasoning-decide", "reasoning-chain"}


def test_capabilities_have_handlers(builder):
    """All reasoning capabilities are invocable."""
    caps = builder.list_capabilities()
    reasoning_caps = [c for c in caps if c.name.startswith("reasoning-")]
    for cap in reasoning_caps:
        assert cap.is_invocable, f"{cap.name} should be invocable"


def test_capabilities_tagged(builder):
    """All reasoning capabilities have reasoning tag."""
    caps = builder.list_capabilities()
    reasoning_caps = [c for c in caps if c.name.startswith("reasoning-")]
    for cap in reasoning_caps:
        assert "reasoning" in cap.tags, f"{cap.name} should have 'reasoning' tag"
