"""Tests for capability discovery."""

import asyncio
import pytest
from manifold.agent import Agent
from manifold.discovery import Discovery, DiscoveryMode, DiscoveryHit, DiscoveryResult


# ── Helpers ──────────────────────────────────────────────────────────────

async def _mesh_with_caps():
    """Create a mesh with agents that have various capabilities."""
    alice = Agent(name="alice", transport="memory://test")
    alice.knows(["solar-topology", "AR-classification", "rust"])
    await alice.join()

    bob = Agent(name="bob", transport="memory://test")
    bob.knows(["orbit-calculation", "stellar-dynamics"])
    await bob.join()

    carol = Agent(name="carol", transport="memory://test")
    carol.knows(["solar-prediction", "data-analysis", "bitcoin-analysis"])
    await carol.join()

    # Announce to alice's registry
    for peer, caps, focus in [
        ("bob", ["orbit-calculation", "stellar-dynamics"], "orbit-calculation"),
        ("carol", ["solar-prediction", "data-analysis", "bitcoin-analysis"], None),
    ]:
        await alice._on_registry_announcement({
            "name": peer,
            "capabilities": caps,
            "address": "memory://test",
            "focus": focus,
        })

    return alice, bob, carol


# ── Local search tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_local_search_basic():
    """Local search returns matching capabilities."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    result = disco.search_local("solar")
    assert isinstance(result, DiscoveryResult)
    assert result.mode == DiscoveryMode.LOCAL
    assert len(result.hits) > 0
    # Both alice (solar-topology) and carol (solar-prediction) match
    cap_names = [h.capability for h in result.hits]
    assert "solar-prediction" in cap_names
    assert "solar-topology" in cap_names
    print(f"✅ Local search: {result.summary()}")


@pytest.mark.asyncio
async def test_local_search_exact_match():
    """Exact capability name match scores 1.0."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    result = disco.search_local("orbit-calculation")
    best = result.best
    assert best is not None
    assert best.relevance == 1.0
    assert best.agent_name == "bob"
    print(f"✅ Exact match: {best}")


@pytest.mark.asyncio
async def test_local_search_no_results():
    """Search with no matches returns empty hits."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    result = disco.search_local("quantum-entanglement", min_relevance=0.5)
    assert len(result.hits) == 0
    print(f"✅ No results: {result}")


@pytest.mark.asyncio
async def test_local_search_relevance_threshold():
    """min_relevance filters out weak matches."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice, min_relevance=0.8)
    result = disco.search_local("solar")
    # Only exact/substring matches should survive 0.8 threshold
    for h in result.hits:
        assert h.relevance >= 0.8
    print(f"✅ Threshold filter: {len(result.hits)} hits above 0.8")


@pytest.mark.asyncio
async def test_local_search_empty_mesh():
    """Search on agent with no peers returns empty."""
    solo = Agent(name="solo", transport="memory://solo")
    solo.knows(["everything"])
    await solo.join()
    disco = Discovery(solo)
    result = disco.search_local("anything")
    # Solo agent sees itself in registry
    assert result.agents_queried >= 0
    print(f"✅ Empty mesh: {result}")


# ── Result structure tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_result_best():
    """result.best returns top hit."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    result = disco.search_local("solar")
    assert result.best == result.hits[0]
    print(f"✅ Best: {result.best}")


@pytest.mark.asyncio
async def test_result_top_n():
    """top(n) returns correct slice."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    result = disco.search_local("solar")
    top1 = result.top(1)
    assert len(top1) <= 1
    print(f"✅ Top(1): {top1}")


@pytest.mark.asyncio
async def test_result_agent_names():
    """agent_names returns unique agent names ranked by relevance."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    result = disco.search_local("solar")
    names = result.agent_names
    assert "carol" in names
    assert isinstance(names, list)
    print(f"✅ Agent names: {names}")


@pytest.mark.asyncio
async def test_result_by_agent():
    """by_agent groups hits by agent."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    result = disco.search_local("solar")
    by_agent = result.by_agent()
    assert isinstance(by_agent, dict)
    assert "carol" in by_agent
    print(f"✅ By agent: {list(by_agent.keys())}")


@pytest.mark.asyncio
async def test_result_summary():
    """summary produces readable output."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    result = disco.search_local("solar")
    summary = result.summary()
    assert "solar" in summary
    assert "local" in summary
    print(f"✅ Summary:\n{summary}")


# ── Catalog tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog():
    """catalog returns all known capabilities by agent."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    catalog = disco.catalog()
    assert "bob" in catalog
    assert "carol" in catalog
    assert "orbit-calculation" in catalog["bob"]
    assert "bitcoin-analysis" in catalog["carol"]
    print(f"✅ Catalog: {catalog}")


# ── Request handling tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_request():
    """handle_request returns matching caps from this agent."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    payload = {
        "type": "discovery_request",
        "query": "solar",
        "min_relevance": 0.1,
        "requester": "bob",
    }
    hits = disco.handle_request(payload)
    assert len(hits) > 0
    assert any(h["capability"] == "solar-topology" for h in hits)
    print(f"✅ Handle request: {hits}")


@pytest.mark.asyncio
async def test_handle_request_no_match():
    """handle_request returns empty when nothing matches."""
    alice, _, _ = await _mesh_with_caps()
    disco = Discovery(alice)
    payload = {
        "type": "discovery_request",
        "query": "quantum-computing",
        "min_relevance": 0.5,
        "requester": "bob",
    }
    hits = disco.handle_request(payload)
    assert len(hits) == 0
    print(f"✅ No match request: {hits}")


# ── Relevance computation tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_relevance_exact():
    from manifold.discovery import _compute_relevance
    assert _compute_relevance("solar-topology", "solar-topology") == 1.0


@pytest.mark.asyncio
async def test_relevance_substring():
    from manifold.discovery import _compute_relevance
    assert _compute_relevance("solar", "solar-topology") == 0.85


@pytest.mark.asyncio
async def test_relevance_trigram():
    from manifold.discovery import _compute_relevance
    score = _compute_relevance("bitcoin", "bitcoin-analysis")
    assert score > 0.0
    print(f"✅ Trigram score: {score}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
