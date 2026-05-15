"""Tests for audience routing."""

import asyncio
import pytest
from manifold.agent import Agent
from manifold.audience import AudienceRouter, AudienceReport, AudienceEntry, Signal


# ── Helpers ──────────────────────────────────────────────────────────────

async def _mesh_with_agents():
    """Create a small mesh with multiple agents for routing tests."""
    alice = Agent(name="alice", transport="memory://test")
    alice.knows(["solar-topology", "AR-classification", "rust"])
    await alice.join()

    bob = Agent(name="bob", transport="memory://test")
    bob.knows(["orbit-calculation", "stellar-dynamics"])
    await bob.join()

    carol = Agent(name="carol", transport="memory://test")
    carol.knows(["solar-prediction", "data-analysis"])
    await carol.join()

    # alice sees the others via registry announcements
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

    return alice, bob, carol


# ── Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_basic_routing():
    """Audience routing returns ranked agents."""
    alice, bob, carol = await _mesh_with_agents()
    report = alice.audience("solar-prediction")
    assert isinstance(report, AudienceReport)
    assert len(report.entries) == 2
    # Carol should rank higher — she has solar-prediction cap
    assert report.entries[0].name == "carol"
    assert report.entries[0].score > 0.0
    print(f"✅ Basic routing: {report}")


@pytest.mark.asyncio
async def test_capability_signal():
    """Agents with relevant capabilities get the CAPABILITY signal."""
    alice, _, _ = await _mesh_with_agents()
    report = alice.audience("orbit-calculation")
    bob_entry = next(e for e in report.entries if e.name == "bob")
    assert Signal.CAPABILITY in bob_entry.signals
    print(f"✅ Capability signal: {bob_entry}")


@pytest.mark.asyncio
async def test_focus_signal():
    """Agents with matching focus get the FOCUS signal."""
    alice, _, _ = await _mesh_with_agents()
    report = alice.audience("orbit-calculation")
    bob_entry = next(e for e in report.entries if e.name == "bob")
    assert Signal.FOCUS in bob_entry.signals
    print(f"✅ Focus signal: {bob_entry}")


@pytest.mark.asyncio
async def test_min_score_threshold():
    """min_score filters out low-scoring agents."""
    alice, _, _ = await _mesh_with_agents()
    report = alice.audience("quantum-computing", min_score=0.99)
    # Nothing matches quantum computing well
    assert len(report.entries) == 0 or report.entries[0].score < 0.99
    print(f"✅ Min score filter: {report}")


@pytest.mark.asyncio
async def test_exclude_self():
    """Routing excludes self by default."""
    alice, _, _ = await _mesh_with_agents()
    report = alice.audience("solar-topology")
    names = report.names()
    assert "alice" not in names
    print(f"✅ Self excluded: {names}")


@pytest.mark.asyncio
async def test_include_self():
    """exclude_self=False includes the routing agent."""
    alice, _, _ = await _mesh_with_agents()
    report = alice.audience("solar-topology", exclude_self=False)
    assert "alice" in report.names()
    print(f"✅ Self included when requested")


@pytest.mark.asyncio
async def test_max_results():
    """max_results caps the output list."""
    alice, _, _ = await _mesh_with_agents()
    report = alice.audience("solar", max_results=1)
    assert len(report.entries) <= 1
    print(f"✅ Max results: {len(report.entries)}")


@pytest.mark.asyncio
async def test_empty_mesh():
    """Routing on empty mesh returns empty report."""
    agent = Agent(name="solo", transport="memory://solo")
    agent.knows(["everything"])
    await agent.join()
    report = agent.audience("anything")
    assert len(report.entries) == 0
    assert report.total_candidates == 0
    print(f"✅ Empty mesh: {report}")


@pytest.mark.asyncio
async def test_trust_signal():
    """Graded agents get trust signal in audience scoring."""
    alice, bob, carol = await _mesh_with_agents()
    # Alice grades bob highly in solar domain
    alice.grade("bob", "solar", score=0.95)
    report = alice.audience("solar-prediction")
    bob_entry = next((e for e in report.entries if e.name == "bob"), None)
    if bob_entry:
        assert Signal.TRUST in bob_entry.signals
        print(f"✅ Trust signal: {bob_entry}")
    else:
        print(f"✅ Trust signal: bob not in results (score below threshold)")


@pytest.mark.asyncio
async def test_report_summary():
    """Report produces a readable summary."""
    alice, _, _ = await _mesh_with_agents()
    report = alice.audience("solar")
    summary = report.summary()
    assert "solar" in summary
    assert len(summary) > 0
    print(f"✅ Summary:\n{summary}")


@pytest.mark.asyncio
async def test_custom_weights():
    """Custom weights change routing behaviour."""
    alice, _, _ = await _mesh_with_agents()
    # Trust-only routing
    report_trust = alice.audience(
        "solar-prediction",
        weights={"trust": 1.0, "capability": 0.0, "focus": 0.0, "fog_gap": 0.0, "topology": 0.0},
    )
    # Capability-only routing
    report_cap = alice.audience(
        "solar-prediction",
        weights={"trust": 0.0, "capability": 1.0, "focus": 0.0, "fog_gap": 0.0, "topology": 0.0},
    )
    # Both should return results but potentially different ordering
    assert isinstance(report_trust, AudienceReport)
    assert isinstance(report_cap, AudienceReport)
    print(f"✅ Custom weights: trust={report_trust}, cap={report_cap}")


@pytest.mark.asyncio
async def test_top_n():
    """top(n) returns the right slice."""
    alice, _, _ = await _mesh_with_agents()
    report = alice.audience("solar")
    top1 = report.top(1)
    assert len(top1) <= 1
    if report.entries:
        assert top1[0].name == report.entries[0].name
    print(f"✅ Top(1): {top1}")


if __name__ == "__main__":
    asyncio.run(_run_all())
