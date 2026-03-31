"""
Tests for the Glossolalia coordination pressure module.

Verifies suppression behaviour, non-mutation of the original atlas,
field typing, and expected Sophia delta directions for overlapping
and non-overlapping agent pairs.
"""

import pytest

from manifold.atlas import Atlas
from manifold.registry import CapabilityRegistry
from manifold.glossolalia import GlossolaliaProbe, GlossolaliaReading
from manifold.sophia import SophiaRegion


# ── Helpers ───────────────────────────────────────────────────────────────

def make_registry(*agents: tuple[str, list[str]]) -> CapabilityRegistry:
    """Build a CapabilityRegistry from (name, capabilities) pairs."""
    reg = CapabilityRegistry()
    for name, caps in agents:
        reg.register_self(name=name, capabilities=caps, address=f"mem://{name}")
    return reg


def make_atlas(*agents: tuple[str, list[str]]) -> Atlas:
    """Build an Atlas from (name, capabilities) pairs."""
    return Atlas.build(make_registry(*agents))


# Agent pairs for test scenarios

# High overlap: lots of shared vocabulary → high curvature potential
OVERLAPPING_AGENTS = [
    ("oracle",  ["risk-assessment", "uncertainty-quantification",
                  "feedback-loops", "tipping-points", "climate-risk"]),
    ("analyst", ["risk-modeling", "uncertainty-bounds",
                  "feedback-mechanisms", "tipping-dynamics", "climate-policy"]),
    ("bridge",  ["risk-scoring", "uncertainty-propagation",
                  "feedback-analysis", "climate-modeling", "policy-design"]),
]

# No overlap: vocabularies completely disjoint
NON_OVERLAPPING_AGENTS = [
    ("alpha", ["astrophysics", "stellar-dynamics", "quasar-emission"]),
    ("beta",  ["mycology", "fungal-networks", "spore-dispersal"]),
]


# ── Tests ─────────────────────────────────────────────────────────────────

class TestGlossolaliaReadingFields:
    """GlossolaliaReading has all required fields with correct types."""

    def test_all_fields_present(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        reading = probe.scan()

        assert hasattr(reading, "sophia_before")
        assert hasattr(reading, "sophia_after")
        assert hasattr(reading, "delta")
        assert hasattr(reading, "emergent_regions")
        assert hasattr(reading, "coordination_pressure")
        assert hasattr(reading, "interpretation")

    def test_field_types(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        reading = probe.scan()

        assert isinstance(reading.sophia_before, float)
        assert isinstance(reading.sophia_after, float)
        assert isinstance(reading.delta, float)
        assert isinstance(reading.emergent_regions, list)
        assert isinstance(reading.coordination_pressure, float)
        assert isinstance(reading.interpretation, str)

    def test_emergent_regions_are_sophia_region_instances(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        reading = probe.scan()

        for region in reading.emergent_regions:
            assert isinstance(region, SophiaRegion)

    def test_delta_equals_after_minus_before(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        reading = probe.scan()

        expected = round(reading.sophia_after - reading.sophia_before, 4)
        assert reading.delta == pytest.approx(expected, abs=1e-6)

    def test_coordination_pressure_recorded_correctly(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        for pressure in [0.0, 0.5, 1.0]:
            probe = GlossolaliaProbe(atlas, "oracle", "analyst",
                                      coordination_pressure=pressure)
            reading = probe.scan()
            assert reading.coordination_pressure == pytest.approx(pressure)

    def test_interpretation_is_nonempty_string(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        reading = probe.scan()
        assert len(reading.interpretation) > 5


class TestPressureEqualToOne:
    """pressure=1.0 means no suppression — Sophia delta should be ~0."""

    def test_pressure_one_gives_near_zero_delta(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=1.0)
        reading = probe.scan()
        # At pressure=1.0 the suppressed atlas is identical to the base atlas,
        # so the Sophia scores must be equal (delta == 0).
        assert reading.delta == pytest.approx(0.0, abs=1e-4)

    def test_pressure_one_interpretation_is_flat(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=1.0)
        reading = probe.scan()
        assert reading.interpretation == "flat — coordination pressure made no difference"

    def test_pressure_one_no_emergent_regions(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=1.0)
        reading = probe.scan()
        assert reading.emergent_regions == []


class TestOverlappingAgents:
    """Agents with high vocabulary overlap — suppression should shift Sophia."""

    def test_scan_returns_glossolalia_reading(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        reading = probe.scan()
        assert isinstance(reading, GlossolaliaReading)

    def test_sophia_before_and_after_in_range(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        reading = probe.scan()
        assert 0.0 <= reading.sophia_before <= 1.0
        assert 0.0 <= reading.sophia_after <= 1.0

    def test_interpretation_is_one_of_known_values(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        valid = {
            "tongues fired — emergence increased without coordination",
            "marginal uplift — seam active but weak",
            "flat — coordination pressure made no difference",
            "coordination was load-bearing — suppression collapsed the seam",
        }
        for pressure in [0.0, 0.5]:
            probe = GlossolaliaProbe(atlas, "oracle", "analyst",
                                      coordination_pressure=pressure)
            reading = probe.scan()
            assert reading.interpretation in valid


class TestNonOverlappingAgents:
    """Agents with no shared vocabulary — suppression has nothing to suppress."""

    def test_scan_runs_without_error(self) -> None:
        atlas = make_atlas(*NON_OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "alpha", "beta", coordination_pressure=0.0)
        reading = probe.scan()
        assert isinstance(reading, GlossolaliaReading)

    def test_delta_is_zero_when_no_overlap(self) -> None:
        """No transition maps between the pair → suppression has no effect."""
        atlas = make_atlas(*NON_OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "alpha", "beta", coordination_pressure=0.0)
        reading = probe.scan()
        # With zero overlap, there are no transition maps to suppress;
        # before and after are identical.
        assert reading.delta == pytest.approx(0.0, abs=1e-4)

    def test_no_emergent_regions_when_no_overlap(self) -> None:
        atlas = make_atlas(*NON_OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "alpha", "beta", coordination_pressure=0.0)
        reading = probe.scan()
        assert reading.emergent_regions == []


class TestAtlasNonMutation:
    """The original atlas must not be mutated after probe.scan()."""

    def test_transition_maps_unchanged_after_scan(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)

        # Snapshot original transition coverage values
        original_coverage = {
            key: tm.coverage for key, tm in atlas._maps.items()
        }
        original_overlap_sizes = {
            key: len(tm.overlap) for key, tm in atlas._maps.items()
        }

        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        probe.scan()

        # Verify no map was mutated
        for key, tm in atlas._maps.items():
            assert tm.coverage == pytest.approx(original_coverage[key], abs=1e-6), (
                f"Coverage changed for map {key}"
            )
            assert len(tm.overlap) == original_overlap_sizes[key], (
                f"Overlap size changed for map {key}"
            )

    def test_charts_unchanged_after_scan(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        original_chart_count = len(atlas._charts)
        original_names = set(atlas._charts.keys())

        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)
        probe.scan()

        assert len(atlas._charts) == original_chart_count
        assert set(atlas._charts.keys()) == original_names

    def test_multiple_scans_produce_consistent_results(self) -> None:
        """Scanning twice should give the same result (atlas not mutated)."""
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        probe = GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=0.0)

        reading_1 = probe.scan()
        reading_2 = probe.scan()

        assert reading_1.sophia_before == pytest.approx(reading_2.sophia_before, abs=1e-6)
        assert reading_1.sophia_after == pytest.approx(reading_2.sophia_after, abs=1e-6)
        assert reading_1.delta == pytest.approx(reading_2.delta, abs=1e-6)


class TestCoordinationPressureValidation:
    """Invalid pressure values should be rejected."""

    def test_pressure_below_zero_raises(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        with pytest.raises(ValueError, match="coordination_pressure"):
            GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=-0.1)

    def test_pressure_above_one_raises(self) -> None:
        atlas = make_atlas(*OVERLAPPING_AGENTS)
        with pytest.raises(ValueError, match="coordination_pressure"):
            GlossolaliaProbe(atlas, "oracle", "analyst", coordination_pressure=1.1)


# ── Top-level import smoke test ───────────────────────────────────────────

def test_top_level_imports() -> None:
    from manifold import GlossolaliaReading, GlossolaliaProbe
    assert GlossolaliaReading is not None
    assert GlossolaliaProbe is not None

def test_standalone_import() -> None:
    """Module must be importable standalone."""
    from manifold.glossolalia import GlossolaliaProbe, GlossolaliaReading
    assert callable(GlossolaliaProbe)
    assert GlossolaliaReading.__dataclass_fields__  # it's a dataclass
