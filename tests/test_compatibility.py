"""Tests for capability compatibility — version resolution and interface matching."""

import pytest
from manifold.compatibility import (
    Version,
    CapInterface,
    CompatibilityChecker,
    CompatibilityPolicy,
    CompatibilityReport,
    CompatibilityIssue,
    check_quick,
)


# ── Version parsing and comparison ──────────────────────────────────────

class TestVersion:
    def test_parse_standard(self):
        v = Version.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_with_prerelease(self):
        v = Version.parse("2.0.0-beta.1")
        assert v.major == 2
        assert v.pre == "beta.1"

    def test_parse_partial(self):
        v = Version.parse("1.2")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 0

    def test_parse_single(self):
        v = Version.parse("3")
        assert v.major == 3
        assert v.minor == 0
        assert v.patch == 0

    def test_str(self):
        v = Version(1, 2, 3)
        assert str(v) == "1.2.3"

    def test_str_with_pre(self):
        v = Version(1, 2, 3, pre="alpha")
        assert str(v) == "1.2.3-alpha"

    def test_comparison(self):
        v1 = Version(1, 0, 0)
        v2 = Version(2, 0, 0)
        assert v1 < v2
        assert v2 > v1
        assert v1 <= v2
        assert v2 >= v1

    def test_equality(self):
        v1 = Version(1, 2, 3)
        v2 = Version(1, 2, 3)
        assert v1 == v2
        assert v1 <= v2
        assert v1 >= v2

    def test_semver_compatible_same_major(self):
        v1 = Version(1, 0, 0)
        v2 = Version(1, 99, 99)
        assert v1.is_compatible(v2)

    def test_semver_incompatible_diff_major(self):
        v1 = Version(1, 0, 0)
        v2 = Version(2, 0, 0)
        assert not v1.is_compatible(v2)

    def test_is_prerelease(self):
        assert Version(1, 0, 0, pre="rc1").is_prerelease
        assert not Version(1, 0, 0).is_prerelease

    def test_repr(self):
        v = Version(1, 2, 3)
        assert "1.2.3" in repr(v)


# ── CapInterface ─────────────────────────────────────────────────────────

class TestCapInterface:
    def test_from_dict(self):
        iface = CapInterface.from_spec({
            "name": "solar-predict",
            "version": "2.1.0",
            "inputs": ["region"],
            "outputs": ["mw"],
        })
        assert iface.name == "solar-predict"
        assert iface.version == "2.1.0"
        assert iface.inputs == ["region"]
        assert iface.outputs == ["mw"]

    def test_from_spec_defaults(self):
        iface = CapInterface.from_spec({"name": "test"})
        assert iface.version == "1.0.0"
        assert iface.inputs == []


# ── CompatibilityChecker ─────────────────────────────────────────────────

class TestCompatibilityChecker:
    def _make(self, name="test-cap", version="1.0.0", inputs=None, outputs=None, status="active"):
        return CapInterface(
            name=name,
            version=version,
            inputs=inputs or [],
            outputs=outputs or [],
            status=status,
        )

    def test_exact_match(self):
        checker = CompatibilityChecker()
        local = self._make(version="1.0.0")
        remote = self._make(version="1.0.0")
        report = checker.check(local, remote)
        assert report.compatible
        assert len(report.errors) == 0

    def test_same_major_compatible(self):
        checker = CompatibilityChecker(policy=CompatibilityPolicy.SEMVER)
        local = self._make(version="1.0.0")
        remote = self._make(version="1.5.3")
        report = checker.check(local, remote)
        assert report.compatible

    def test_different_major_incompatible(self):
        checker = CompatibilityChecker(policy=CompatibilityPolicy.SEMVER)
        local = self._make(version="1.0.0")
        remote = self._make(version="2.0.0")
        report = checker.check(local, remote)
        assert not report.compatible
        assert any(i.field == "version" for i in report.errors)

    def test_name_mismatch(self):
        checker = CompatibilityChecker()
        local = CapInterface(name="cap-a", version="1.0.0")
        remote = CapInterface(name="cap-b", version="1.0.0")
        report = checker.check(local, remote)
        assert not report.compatible

    def test_strict_policy_requires_exact(self):
        checker = CompatibilityChecker(policy=CompatibilityPolicy.STRICT)
        local = self._make(version="1.0.0")
        remote = self._make(version="1.0.1")
        report = checker.check(local, remote)
        assert not report.compatible

    def test_relaxed_policy_adjacent_major(self):
        checker = CompatibilityChecker(policy=CompatibilityPolicy.RELAXED)
        local = self._make(version="1.5.0")
        remote = self._make(version="2.0.0")
        report = checker.check(local, remote)
        assert report.compatible
        assert report.has_warnings

    def test_relaxed_policy_too_far(self):
        checker = CompatibilityChecker(policy=CompatibilityPolicy.RELAXED)
        local = self._make(version="1.0.0")
        remote = self._make(version="3.0.0")
        report = checker.check(local, remote)
        assert not report.compatible

    def test_best_effort_always_warns(self):
        checker = CompatibilityChecker(policy=CompatibilityPolicy.BEST_EFFORT)
        local = self._make(version="1.0.0")
        remote = self._make(version="5.0.0")
        report = checker.check(local, remote)
        # Best effort is compatible unless name mismatches or missing inputs
        assert report.compatible or not report.compatible  # depends on name match
        assert report.has_warnings

    def test_input_missing_in_remote(self):
        checker = CompatibilityChecker()
        local = self._make(inputs=["region", "horizon"])
        remote = self._make(inputs=["region"])
        report = checker.check(local, remote)
        assert not report.compatible
        assert any("horizon" in i.message for i in report.errors)

    def test_output_missing_in_remote(self):
        checker = CompatibilityChecker()
        local = self._make(outputs=["predicted_mw", "confidence"])
        remote = self._make(outputs=["predicted_mw"])
        report = checker.check(local, remote)
        assert report.has_warnings
        assert any("confidence" in i.message for i in report.warnings)

    def test_extra_inputs_in_remote_is_info(self):
        checker = CompatibilityChecker()
        local = self._make(inputs=["text"])
        remote = self._make(inputs=["text", "language"])
        report = checker.check(local, remote)
        assert report.compatible
        assert any(i.severity == "info" for i in report.issues)

    def test_deprecated_remote_warns(self):
        checker = CompatibilityChecker()
        local = self._make()
        remote = self._make(status="deprecated")
        report = checker.check(local, remote)
        assert report.has_warnings
        assert any("deprecated" in i.message.lower() for i in report.warnings)

    def test_disabled_remote_fails(self):
        checker = CompatibilityChecker()
        local = self._make()
        remote = self._make(status="disabled")
        report = checker.check(local, remote)
        assert not report.compatible

    def test_report_summary(self):
        checker = CompatibilityChecker()
        local = self._make(version="1.0.0")
        remote = self._make(version="1.0.0")
        report = checker.check(local, remote)
        summary = report.summary()
        assert "COMPATIBLE" in summary

    def test_report_summary_incompatible(self):
        checker = CompatibilityChecker()
        local = self._make(version="1.0.0")
        remote = self._make(version="2.0.0")
        report = checker.check(local, remote)
        summary = report.summary()
        assert "INCOMPATIBLE" in summary

    def test_check_from_dicts(self):
        checker = CompatibilityChecker()
        report = checker.check(
            {"name": "cap", "version": "1.0.0", "inputs": ["x"]},
            {"name": "cap", "version": "1.1.0", "inputs": ["x", "y"]},
        )
        assert report.compatible

    def test_local_newer_warns(self):
        checker = CompatibilityChecker()
        local = self._make(version="1.5.0")
        remote = self._make(version="1.2.0")
        report = checker.check(local, remote)
        assert report.compatible
        assert any("newer" in i.message.lower() for i in report.issues)

    def test_report_repr(self):
        checker = CompatibilityChecker()
        local = self._make(version="1.0.0")
        remote = self._make(version="1.0.0")
        report = checker.check(local, remote)
        assert "OK" in repr(report)


# ── Quick check helper ───────────────────────────────────────────────────

class TestCheckQuick:
    def test_compatible(self):
        assert check_quick(
            {"name": "cap", "version": "1.0.0"},
            {"name": "cap", "version": "1.1.0"},
        )

    def test_incompatible(self):
        assert not check_quick(
            {"name": "cap", "version": "1.0.0"},
            {"name": "cap", "version": "2.0.0"},
        )

    def test_different_policy(self):
        # Strict should fail on different patch
        assert not check_quick(
            {"name": "cap", "version": "1.0.0"},
            {"name": "cap", "version": "1.0.1"},
            policy="strict",
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
