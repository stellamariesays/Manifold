"""Tests for the capability exchange."""

import asyncio
import pytest
from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder, CapabilityStatus
from manifold.exchange import (
    CapabilityExchange,
    CatalogEntry,
    ExchangeStats,
    ExchangeStatus,
)


# ── Helpers ──────────────────────────────────────────────────────────────

async def _mesh_with_exchange():
    """Create a small mesh with agents, builders, and an exchange."""
    alice = Agent(name="alice", transport="memory://test")
    alice.knows(["solar-topology", "AR-classification"])
    await alice.join()

    bob = Agent(name="bob", transport="memory://test")
    bob.knows(["orbit-calculation", "stellar-dynamics"])
    await bob.join()

    carol = Agent(name="carol", transport="memory://test")
    carol.knows(["solar-prediction", "data-analysis"])
    await carol.join()

    # Announce to alice
    await alice._on_registry_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation", "stellar-dynamics"],
        "address": "memory://test",
        "focus": "orbit-calculation",
    })
    await alice._on_registry_announcement({
        "name": "carol",
        "capabilities": ["solar-prediction", "data-analysis"],
        "address": "memory://test",
        "focus": None,
    })

    # Set up alice's builder with structured capabilities
    builder = CapabilityBuilder(alice)

    @builder.define(
        name="solar-topology",
        version="2.1.0",
        description="Analyze solar mesh topology",
        inputs=["region"],
        outputs=["topology_map", "health_score"],
        tags=["solar", "topology", "analysis"],
    )
    async def solar_topology(payload: dict) -> dict:
        return {
            "topology_map": f"map-{payload.get('region', 'unknown')}",
            "health_score": 0.92,
        }

    @builder.define(
        name="AR-classification",
        version="1.0.0",
        description="Classify active regions",
        inputs=["image_data"],
        outputs=["classification", "confidence"],
        tags=["solar", "classification"],
    )
    async def ar_classify(payload: dict) -> dict:
        return {
            "classification": "beta-gamma",
            "confidence": 0.87,
        }

    # Create exchange
    exchange = CapabilityExchange(alice, builder=builder)

    return alice, bob, carol, builder, exchange


# ── Publishing ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_all():
    """publish_all registers local builder capabilities."""
    alice, _, _, builder, exchange = await _mesh_with_exchange()
    count = exchange.publish_all()
    assert count == 2

    # Should have alice's capabilities in the catalog
    local_caps = exchange.browse(agent_name="alice")
    names = [e.cap_name for e in local_caps]
    assert "solar-topology" in names
    assert "AR-classification" in names
    print(f"✅ Published {count} capabilities")


@pytest.mark.asyncio
async def test_publish_capability():
    """publish_capability adds a single capability."""
    alice, _, _, builder, exchange = await _mesh_with_exchange()
    spec = builder.list_capabilities()[0]
    exchange.publish_capability(spec)
    local = exchange.browse(agent_name="alice")
    assert len(local) == 1
    print(f"✅ Published single capability: {local[0].cap_name}")


@pytest.mark.asyncio
async def test_publish_no_builder():
    """Exchange without builder publishes nothing."""
    alice = Agent(name="solo", transport="memory://solo")
    await alice.join()
    exchange = CapabilityExchange(alice)
    count = exchange.publish_all()
    assert count == 0
    print("✅ No builder → 0 published")


# ─── Discovery ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_from_announcement():
    """Remote agent announcements populate the catalog."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation", "stellar-dynamics"],
    })

    bob_caps = exchange.browse(agent_name="bob")
    assert len(bob_caps) == 2
    names = [e.cap_name for e in bob_caps]
    assert "orbit-calculation" in names
    print(f"✅ Remote announcement: {names}")


@pytest.mark.asyncio
async def test_browse_all():
    """browse without filters returns all active capabilities."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation"],
    })

    all_caps = exchange.browse()
    assert len(all_caps) >= 3  # alice's 2 + bob's 1
    print(f"✅ Browse all: {len(all_caps)} capabilities")


@pytest.mark.asyncio
async def test_browse_by_tag():
    """browse with tag filter works."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()

    solar_caps = exchange.browse(tag="solar")
    assert len(solar_caps) == 2
    for entry in solar_caps:
        assert "solar" in entry.tags
    print(f"✅ Tag filter 'solar': {[e.cap_name for e in solar_caps]}")


@pytest.mark.asyncio
async def test_search():
    """search finds capabilities by keyword."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()

    results = exchange.search("classification")
    assert len(results) >= 1
    assert any(e.cap_name == "AR-classification" for e in results)
    print(f"✅ Search 'classification': {[e.cap_name for e in results]}")


@pytest.mark.asyncio
async def test_search_ranked():
    """search results are ranked by fitness."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation"],
    })

    # Grade alice highly in solar
    exchange._agent.grade("alice", "solar-topology", score=0.95)
    exchange.publish_all()  # refresh trust scores

    results = exchange.search("solar")
    # Should return results (at least alice's solar-topology)
    assert len(results) >= 1
    print(f"✅ Search ranked: {[f'{e.agent_name}/{e.cap_name}' for e in results]}")


@pytest.mark.asyncio
async def test_find_best():
    """find_best returns the top agent for a capability."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation"],
    })

    best = exchange.find_best("orbit-calculation")
    assert best is not None
    assert best.agent_name == "bob"
    print(f"✅ Best for orbit-calculation: {best}")


@pytest.mark.asyncio
async def test_find_best_excludes_self():
    """find_best excludes self by default."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()

    # alice has "solar-topology" but find_best should exclude her
    best = exchange.find_best("solar-topology")
    assert best is None  # no remote agent has it
    print("✅ Self excluded from find_best")


@pytest.mark.asyncio
async def test_find_best_with_trust():
    """find_best respects min_trust threshold."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation"],
    })

    best = exchange.find_best("orbit-calculation", min_trust=0.99)
    assert best is None  # bob has no trust score that high
    print("✅ min_trust filter works")


@pytest.mark.asyncio
async def test_get_agents_for_capability():
    """get_agents_for_capability lists all providers."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation"],
    })

    providers = exchange.get_agents_for_capability("orbit-calculation")
    assert len(providers) == 1
    assert providers[0].agent_name == "bob"
    print(f"✅ Providers for orbit-calculation: {[p.agent_name for p in providers]}")


# ─── Routing & Dispatch ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_local_invoke():
    """route_and_dispatch invokes locally when builder has the cap."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()

    result = await exchange.route_and_dispatch(
        "solar-topology",
        payload={"region": "pacific"},
    )
    assert result.ok is True
    assert result.output["topology_map"] == "map-pacific"
    assert result.output["health_score"] == 0.92
    print(f"✅ Local invoke: {result}")


@pytest.mark.asyncio
async def test_route_capability_not_found():
    """route_and_dispatch returns error for unknown capabilities."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()

    result = await exchange.route_and_dispatch("quantum-teleportation")
    assert "error" in result
    print(f"✅ Not found: {result}")


# ─── Stats ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats():
    """Exchange stats reflect catalog state."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation", "stellar-dynamics"],
    })

    stats = exchange.stats()
    assert isinstance(stats, ExchangeStats)
    assert stats.total_capabilities >= 4  # alice 2 + bob 2
    assert stats.total_agents >= 2
    assert stats.local_capabilities == 2
    assert stats.remote_capabilities >= 2
    print(f"✅ Stats: {stats}")


@pytest.mark.asyncio
async def test_catalog_summary():
    """catalog_summary produces readable output."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.publish_all()

    summary = exchange.catalog_summary()
    assert "alice" in summary
    assert "solar-topology" in summary
    print(f"✅ Summary:\n{summary}")


@pytest.mark.asyncio
async def test_catalog_entry_matches():
    """CatalogEntry.matches works for various queries."""
    entry = CatalogEntry(
        agent_name="test",
        cap_name="solar-prediction",
        tags=["energy", "forecast"],
        description="Predict solar output",
        inputs=["region", "hours"],
    )
    assert entry.matches("solar")
    assert entry.matches("forecast")
    assert entry.matches("predict")
    assert entry.matches("region")
    assert not entry.matches("quantum")
    print("✅ CatalogEntry.matches works")


@pytest.mark.asyncio
async def test_catalog_entry_fitness():
    """CatalogEntry.fitness combines trust and latency."""
    high_trust = CatalogEntry(agent_name="a", cap_name="x", trust_score=0.9, avg_latency_ms=50)
    low_trust = CatalogEntry(agent_name="b", cap_name="x", trust_score=0.1, avg_latency_ms=500)
    assert high_trust.fitness() > low_trust.fitness()
    print(f"✅ Fitness: high={high_trust.fitness():.2f} > low={low_trust.fitness():.2f}")


@pytest.mark.asyncio
async def test_update_skips_self():
    """update_from_announcement ignores announcements about self."""
    alice, _, _, _, exchange = await _mesh_with_exchange()
    exchange.update_from_announcement({
        "name": "alice",
        "capabilities": ["something-new"],
    })
    # Self should not be in catalog from announcements
    alice_caps = exchange.browse(agent_name="alice")
    assert len(alice_caps) == 0
    print("✅ Self-announcement ignored")


@pytest.mark.asyncio
async def test_stale_capability_marking():
    """Capabilities not in new announcement get marked unknown."""
    _, _, _, _, exchange = await _mesh_with_exchange()
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation", "stellar-dynamics"],
    })
    # Re-announce with fewer caps
    exchange.update_from_announcement({
        "name": "bob",
        "capabilities": ["orbit-calculation"],
    })

    bob_caps = exchange.browse(agent_name="bob", status=None)
    stale = [e for e in bob_caps if e.cap_name == "stellar-dynamics"]
    assert len(stale) == 1
    assert stale[0].status == "unknown"
    print("✅ Stale capability marked unknown")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
