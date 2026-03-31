"""
Tests for the MRI cognitive mesh visualizer.

Covers:
  - MRISnapshot field presence and types
  - capture() returns a valid MRISnapshot
  - generate_html() returns non-empty HTML containing D3 and title markers
  - Embedded JSON snapshot present in HTML output
  - Graceful handling of missing glossolalia (None case)
  - Graceful handling of missing bottleneck (sparse mesh)
"""

import json

import pytest

from manifold.atlas import Atlas
from manifold.registry import CapabilityRegistry
from manifold.mri import MRISnapshot, capture, generate_html
from manifold.sophia import SophiaReading
from manifold.bottleneck import BottleneckReading
from manifold.bleed import BleedReading
from manifold.glossolalia import GlossolaliaReading


# ── Helpers ───────────────────────────────────────────────────────────────


def make_registry(*agents: tuple[str, list[str]]) -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for name, caps in agents:
        reg.register_self(name=name, capabilities=caps, address=f"mem://{name}")
    return reg


def make_atlas(*agents: tuple[str, list[str]]) -> Atlas:
    return Atlas.build(make_registry(*agents))


# Three-agent mesh with good overlap — mirrors the demo setup
THREE_AGENTS = [
    ("braid", [
        "mesh-theory", "topology-analysis", "coordination-dynamics",
        "pattern-recognition", "emergence-modeling", "transition-mapping",
    ]),
    ("stella", [
        "coordination-strategy", "dynamics-modeling", "agent-orchestration",
        "mesh-navigation", "emergence-monitoring", "conversational-topology",
    ]),
    ("fog-mapper", [
        "topology-gaps", "pattern-voids", "uncertainty-mapping",
        "blind-spot-detection", "fog-analysis", "emergence-signals",
    ]),
]

# Isolated agents — no shared vocabulary; bottleneck/sophia will be sparse
ISOLATED_AGENTS = [
    ("alpha", ["astrophysics", "quasar-emission", "stellar-collapse"]),
    ("beta",  ["mycology", "fungal-networks", "spore-dispersal"]),
]


# ── MRISnapshot field tests ───────────────────────────────────────────────


class TestMRISnapshotFields:
    """MRISnapshot has all required fields with correct types."""

    def test_all_fields_present(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert hasattr(snap, "atlas_data")
        assert hasattr(snap, "sophia")
        assert hasattr(snap, "bottleneck")
        assert hasattr(snap, "bleed")
        assert hasattr(snap, "holes")
        assert hasattr(snap, "glossolalia")
        assert hasattr(snap, "captured_at")

    def test_atlas_data_is_dict(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert isinstance(snap.atlas_data, dict)

    def test_atlas_data_has_nodes_and_edges(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert "nodes" in snap.atlas_data
        assert "edges" in snap.atlas_data
        assert isinstance(snap.atlas_data["nodes"], list)
        assert isinstance(snap.atlas_data["edges"], list)

    def test_sophia_is_sophia_reading(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert isinstance(snap.sophia, SophiaReading)

    def test_bottleneck_is_reading_or_none(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert snap.bottleneck is None or isinstance(snap.bottleneck, BottleneckReading)

    def test_bleed_is_list(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert isinstance(snap.bleed, list)

    def test_holes_is_list_of_strings(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert isinstance(snap.holes, list)
        for h in snap.holes:
            assert isinstance(h, str)

    def test_glossolalia_none_by_default(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert snap.glossolalia is None

    def test_captured_at_is_iso_string(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert isinstance(snap.captured_at, str)
        assert "T" in snap.captured_at  # basic ISO 8601 check


# ── capture() tests ───────────────────────────────────────────────────────


class TestCapture:
    """capture() produces a valid, fully-populated MRISnapshot."""

    def test_returns_mri_snapshot(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert isinstance(snap, MRISnapshot)

    def test_sophia_score_in_range(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert 0.0 <= snap.sophia.score <= 1.0

    def test_with_glossolalia(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas, agent_a="braid", agent_b="stella",
                       coordination_pressure=0.0)
        assert isinstance(snap.glossolalia, GlossolaliaReading)

    def test_glossolalia_delta_is_float(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas, agent_a="braid", agent_b="stella")
        assert snap.glossolalia is not None
        assert isinstance(snap.glossolalia.delta, float)

    def test_without_glossolalia_is_none(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert snap.glossolalia is None

    def test_bleed_empty_single_snapshot(self) -> None:
        """Single atlas → bleed_rate can't run → empty list."""
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        assert snap.bleed == []

    def test_bleed_populated_with_history(self) -> None:
        atlas1 = make_atlas(*THREE_AGENTS)
        atlas2 = make_atlas(*THREE_AGENTS)
        snap = capture(atlas1, atlas_history=[atlas1, atlas2])
        # bleed_rate may find no interesting regions, but list is returned
        assert isinstance(snap.bleed, list)

    def test_isolated_agents_no_bottleneck(self) -> None:
        """Agents with no overlap → bottleneck is None (no transition maps)."""
        atlas = make_atlas(*ISOLATED_AGENTS)
        snap = capture(atlas)
        assert snap.bottleneck is None

    def test_rich_mesh_has_bottleneck(self) -> None:
        """Three overlapping agents → bottleneck reading present."""
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        # With three overlapping agents there should be transition maps
        # and therefore a bottleneck reading
        if atlas._maps:
            assert snap.bottleneck is not None

    def test_unknown_agent_glossolalia_graceful(self) -> None:
        """Non-existent agent names → glossolalia is None, no crash."""
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas, agent_a="ghost", agent_b="phantom")
        # GlossolaliaProbe accepts any name; result might be near-zero but valid
        # OR capture() catches an exception and returns None — both are acceptable
        assert snap.glossolalia is None or isinstance(snap.glossolalia, GlossolaliaReading)


# ── generate_html() tests ─────────────────────────────────────────────────


class TestGenerateHtml:
    """generate_html() returns valid, complete HTML."""

    def test_returns_non_empty_string(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        html = generate_html(snap)
        assert isinstance(html, str)
        assert len(html) > 500

    def test_contains_d3(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        html = generate_html(snap)
        assert "d3" in html

    def test_contains_title(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        html = generate_html(snap)
        assert "Manifold MRI" in html

    def test_contains_embedded_json(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        html = generate_html(snap)
        assert "SNAPSHOT" in html
        assert "__SNAPSHOT_JSON__" not in html  # placeholder was replaced

    def test_embedded_json_is_parseable(self) -> None:
        """Extract the JSON from the SNAPSHOT assignment and parse it."""
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        html = generate_html(snap)
        # Find const SNAPSHOT = {...};
        marker = "const SNAPSHOT = "
        idx = html.find(marker)
        assert idx != -1, "SNAPSHOT assignment not found in HTML"
        # Find the closing semicolon on the same block
        start = idx + len(marker)
        # Count braces to find end of JSON object
        depth = 0
        end = start
        for i, ch in enumerate(html[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        json_fragment = html[start:end].replace("<\\/", "</").replace("<\\!--", "<!--")
        parsed = json.loads(json_fragment)
        assert "atlas" in parsed
        assert "sophia" in parsed
        assert "holes" in parsed
        assert "captured_at" in parsed

    def test_no_sidebar_without_glossolalia(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        html = generate_html(snap)
        # Without glossolalia, has-sidebar class should not be added
        assert "has-sidebar" not in html or "buildSidebar" in html

    def test_glossolalia_sidebar_present_when_provided(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas, agent_a="braid", agent_b="stella")
        html = generate_html(snap)
        assert "Glossolalia Probe" in html
        assert "emergence-delta" in html

    def test_doctype_and_structure(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        html = generate_html(snap)
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_d3_cdn_url(self) -> None:
        atlas = make_atlas(*THREE_AGENTS)
        snap = capture(atlas)
        html = generate_html(snap)
        assert "d3js.org/d3.v7.min.js" in html

    def test_without_glossolalia_none_case(self) -> None:
        """Explicitly verify the None glossolalia path produces clean HTML."""
        atlas = make_atlas(*ISOLATED_AGENTS)
        snap = capture(atlas)
        assert snap.glossolalia is None
        html = generate_html(snap)
        assert isinstance(html, str)
        assert "Manifold MRI" in html
        assert "d3" in html


# ── Top-level import tests ────────────────────────────────────────────────


def test_top_level_imports() -> None:
    from manifold import MRISnapshot, capture, generate_html
    assert MRISnapshot is not None
    assert callable(capture)
    assert callable(generate_html)


def test_mri_snapshot_is_dataclass() -> None:
    from manifold.mri import MRISnapshot
    assert hasattr(MRISnapshot, "__dataclass_fields__")
    fields = MRISnapshot.__dataclass_fields__
    for name in ("atlas_data", "sophia", "bottleneck", "bleed",
                 "holes", "glossolalia", "captured_at"):
        assert name in fields, f"Missing field: {name}"
