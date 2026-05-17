"""Tests for the localization capability pack — chart, overlap, blindspots, atlas holes, diversity."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_localization_pack


def _make_mesh():
    """Create a small mesh with diverse agents."""
    alice = Agent("alice")
    alice.knows(["solar-prediction", "weather-forecast", "energy-trading"])
    bob = Agent("bob")
    bob.knows(["battery-optimization", "grid-balancing", "energy-trading"])
    carol = Agent("carol")
    carol.knows(["nlp-sentiment", "text-summarization"])

    # Share registry
    shared = alice._registry
    bob._registry = shared
    carol._registry = shared

    # Register all agents in shared registry
    from manifold.registry import _AgentRecord
    for a in [alice, bob, carol]:
        shared._records[a.name] = _AgentRecord(
            name=a.name,
            capabilities=list(a._capabilities),
            address="",
            focus=None,
        )

    return alice, bob, carol


def _run(coro):
    return asyncio.run(coro)


class TestLocalizeChart:
    def test_returns_chart_info(self):
        alice, _, _ = _make_mesh()
        builder = CapabilityBuilder(alice)
        load_localization_pack(builder, alice)

        result = _run(builder.invoke("localize-chart", {}))
        assert result.ok
        assert result.output["agent"] == "alice"
        assert "solar-prediction" in result.output["domain"]
        assert result.output["domain_size"] >= 3  # original caps + any registered by packs
        assert result.output["vocabulary_size"] > 0


class TestLocalizeOverlap:
    def test_overlap_with_peer(self):
        alice, bob, _ = _make_mesh()
        builder = CapabilityBuilder(alice)
        load_localization_pack(builder, alice)

        result = _run(builder.invoke("localize-overlap", {"peer": "bob"}))
        assert result.ok
        assert result.output["agent_a"] == "alice"
        assert result.output["agent_b"] == "bob"
        # Both share "energy-trading", so "energy" and "trading" should overlap
        assert result.output["overlap_size"] > 0
        assert result.output["coverage"] > 0

    def test_no_overlap_distant_agents(self):
        alice, _, carol = _make_mesh()
        builder = CapabilityBuilder(alice)
        load_localization_pack(builder, alice)

        result = _run(builder.invoke("localize-overlap", {"peer": "carol"}))
        assert result.ok

    def test_missing_peer_error(self):
        alice, _, _ = _make_mesh()
        builder = CapabilityBuilder(alice)
        load_localization_pack(builder, alice)

        result = _run(builder.invoke("localize-overlap", {}))
        assert not result.ok

    def test_unknown_peer(self):
        alice, _, _ = _make_mesh()
        builder = CapabilityBuilder(alice)
        load_localization_pack(builder, alice)

        result = _run(builder.invoke("localize-overlap", {"peer": "nonexistent"}))
        assert not result.ok


class TestLocalizeBlindspots:
    def test_returns_blindspots(self):
        alice, _, _ = _make_mesh()
        builder = CapabilityBuilder(alice)
        load_localization_pack(builder, alice)

        result = _run(builder.invoke("localize-blindspots", {}))
        assert result.ok
        assert result.output["agent"] == "alice"
        assert isinstance(result.output["blind_spots"], list)


class TestLocalizeAtlasHoles:
    def test_returns_atlas_info(self):
        alice, _, _ = _make_mesh()
        builder = CapabilityBuilder(alice)
        load_localization_pack(builder, alice)

        result = _run(builder.invoke("localize-atlas-holes", {}))
        assert result.ok
        assert "holes" in result.output
        assert "agent_count" in result.output


class TestLocalizeDiversity:
    def test_diversity_across_mesh(self):
        alice, _, _ = _make_mesh()
        builder = CapabilityBuilder(alice)
        load_localization_pack(builder, alice)

        result = _run(builder.invoke("localize-diversity", {}))
        assert result.ok
        assert result.output["agent_count"] == 3
        assert result.output["total_vocabulary_size"] > 0
        assert 0.0 <= result.output["diversity_index"] <= 1.0
        assert len(result.output["agents"]) == 3


class TestLocalizationInLoadAll:
    def test_load_all_includes_localization(self):
        alice, _, _ = _make_mesh()
        from manifold.capability_pack import load_all_packs
        builder = CapabilityBuilder(alice)
        specs = load_all_packs(builder, alice)
        names = [s.name for s in specs]
        assert "localize-chart" in names
        assert "localize-overlap" in names
        assert "localize-blindspots" in names
        assert "localize-atlas-holes" in names
        assert "localize-diversity" in names
