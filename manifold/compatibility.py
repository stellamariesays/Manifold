"""Capability compatibility — version resolution and interface matching.

Before agents can negotiate or compose capabilities, they need to know if
their versions are compatible and their interfaces align. This module provides:

- **Semantic version parsing** and comparison (major.minor.patch)
- **Interface compatibility** checks (input/output schema matching)
- **Compatibility policies** (strict, relaxed, best-effort)
- **Compatibility reports** with actionable migration hints

Usage::

    from manifold.compatibility import CompatibilityChecker, Version

    v1 = Version.parse("1.2.0")
    v2 = Version.parse("1.3.1")
    assert v1 < v2
    assert v1.is_compatible(v2)  # same major version

    checker = CompatibilityChecker()
    report = checker.check(local_spec, remote_spec)
    if report.compatible:
        print("Capabilities are compatible!")
    else:
        print(f"Incompatible: {report.reasons}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ─── Semantic Version ───────────────────────────────────────────────────

@dataclass(frozen=True)
class Version:
    """Semantic version (major.minor.patch)."""
    major: int
    minor: int
    patch: int
    pre: str = ""

    @classmethod
    def parse(cls, version_str: str) -> Version:
        """Parse a version string like '1.2.3' or '2.0.0-beta'."""
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-]([\w.]+))?$", version_str.strip())
        if not m:
            # Fallback: try to parse partial versions
            parts = version_str.strip().split(".")
            nums = []
            for p in parts:
                try:
                    nums.append(int(re.match(r"\d+", p).group()))
                except (AttributeError, ValueError):
                    nums.append(0)
            while len(nums) < 3:
                nums.append(0)
            return cls(nums[0], nums[1], nums[2])
        return cls(
            major=int(m.group(1)),
            minor=int(m.group(2)),
            patch=int(m.group(3)),
            pre=m.group(4) or "",
        )

    @property
    def is_prerelease(self) -> bool:
        return bool(self.pre)

    def is_compatible(self, other: Version) -> bool:
        """Check semver compatibility: same major version means compatible."""
        return self.major == other.major

    def __lt__(self, other: Version) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: Version) -> bool:
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)

    def __gt__(self, other: Version) -> bool:
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other: Version) -> bool:
        return (self.major, self.minor, self.patch) >= (other.major, other.minor, other.patch)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre:
            base += f"-{self.pre}"
        return base

    def __repr__(self) -> str:
        return f"Version('{self}')"


# ─── Compatibility Policy ───────────────────────────────────────────────

class CompatibilityPolicy(str, Enum):
    """How strict should compatibility checks be?"""
    STRICT = "strict"          # Exact version match required
    SEMVER = "semver"          # Same major version (default)
    RELAXED = "relaxed"        # Same or adjacent major version
    BEST_EFFORT = "best_effort"  # Accept anything, just warn


# ─── Compatibility Report ───────────────────────────────────────────────

@dataclass
class CompatibilityIssue:
    """A single compatibility problem."""
    field: str
    severity: str  # "error", "warning", "info"
    message: str

    def __repr__(self) -> str:
        return f"[{self.severity}] {self.field}: {self.message}"


@dataclass
class CompatibilityReport:
    """Result of checking compatibility between two capability specs."""
    local_name: str
    local_version: str
    remote_name: str
    remote_version: str
    compatible: bool = True
    policy: CompatibilityPolicy = CompatibilityPolicy.SEMVER
    issues: list[CompatibilityIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[CompatibilityIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[CompatibilityIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def summary(self) -> str:
        status = "✅ COMPATIBLE" if self.compatible else "❌ INCOMPATIBLE"
        lines = [
            f"{status}: {self.local_name} v{self.local_version} ↔ {self.remote_name} v{self.remote_version}",
            f"  Policy: {self.policy.value}",
        ]
        for issue in self.issues:
            lines.append(f"  {issue}")
        if not self.issues:
            lines.append("  No issues found")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<CompatibilityReport {self.local_name}@{self.local_version} ↔ "
            f"{self.remote_name}@{self.remote_version} "
            f"{'OK' if self.compatible else 'FAIL'}>"
        )


# ─── Capability Spec (lightweight, for cross-agent comparison) ──────────

@dataclass
class CapInterface:
    """Lightweight capability interface for compatibility checks."""
    name: str
    version: str = "1.0.0"
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    status: str = "active"

    @classmethod
    def from_spec(cls, spec: Any) -> CapInterface:
        """Create from a CapSpec (capability_builder) or dict."""
        if isinstance(spec, dict):
            return cls(
                name=spec.get("name", ""),
                version=spec.get("version", "1.0.0"),
                inputs=spec.get("inputs", []),
                outputs=spec.get("outputs", []),
                tags=spec.get("tags", []),
                description=spec.get("description", ""),
                status=spec.get("status", "active"),
            )
        # From CapSpec object
        return cls(
            name=getattr(spec, "name", ""),
            version=getattr(spec, "version", "1.0.0"),
            inputs=getattr(spec, "inputs", []),
            outputs=getattr(spec, "outputs", []),
            tags=getattr(spec, "tags", []),
            description=getattr(spec, "description", ""),
            status=getattr(spec, "status", "active"),
        )


# ─── Compatibility Checker ──────────────────────────────────────────────

class CompatibilityChecker:
    """
    Check compatibility between capability interfaces.

    Validates version compatibility and interface alignment between
    a local capability and a remote one (e.g., during negotiation
    or composition planning).

    Args:
        policy: How strict to be about version mismatches.
    """

    def __init__(self, policy: CompatibilityPolicy = CompatibilityPolicy.SEMVER) -> None:
        self.policy = policy

    def check(
        self,
        local: CapInterface | Any,
        remote: CapInterface | Any,
    ) -> CompatibilityReport:
        """
        Check compatibility between two capability interfaces.

        Args:
            local:  Your capability (CapInterface, CapSpec, or dict).
            remote: The remote capability to compare against.

        Returns:
            CompatibilityReport with issues and compatibility verdict.
        """
        local_iface = CapInterface.from_spec(local) if not isinstance(local, CapInterface) else local
        remote_iface = CapInterface.from_spec(remote) if not isinstance(remote, CapInterface) else remote

        local_ver = Version.parse(local_iface.version)
        remote_ver = Version.parse(remote_iface.version)

        report = CompatibilityReport(
            local_name=local_iface.name,
            local_version=local_iface.version,
            remote_name=remote_iface.name,
            remote_version=remote_iface.version,
            policy=self.policy,
        )

        # ── Name check ────────────────────────────────────────────────
        if local_iface.name != remote_iface.name:
            report.issues.append(CompatibilityIssue(
                field="name",
                severity="error",
                message=f"Name mismatch: {local_iface.name!r} vs {remote_iface.name!r}",
            ))
            report.compatible = False

        # ── Version check ─────────────────────────────────────────────
        self._check_version(local_ver, remote_ver, report)

        # ── Input compatibility ────────────────────────────────────────
        self._check_inputs(local_iface.inputs, remote_iface.inputs, report)

        # ── Output compatibility ───────────────────────────────────────
        self._check_outputs(local_iface.outputs, remote_iface.outputs, report)

        # ── Status check ──────────────────────────────────────────────
        if remote_iface.status == "deprecated":
            report.issues.append(CompatibilityIssue(
                field="status",
                severity="warning",
                message="Remote capability is deprecated — consider upgrading",
            ))
        elif remote_iface.status == "disabled":
            report.issues.append(CompatibilityIssue(
                field="status",
                severity="error",
                message="Remote capability is disabled and cannot be invoked",
            ))
            report.compatible = False

        return report

    def _check_version(
        self,
        local: Version,
        remote: Version,
        report: CompatibilityReport,
    ) -> None:
        """Apply version compatibility policy."""
        if local == remote:
            return  # Exact match, always fine

        if self.policy == CompatibilityPolicy.STRICT:
            report.issues.append(CompatibilityIssue(
                field="version",
                severity="error",
                message=f"Strict policy requires exact match: {local} != {remote}",
            ))
            report.compatible = False
            return

        if self.policy == CompatibilityPolicy.SEMVER:
            if local.major != remote.major:
                report.issues.append(CompatibilityIssue(
                    field="version",
                    severity="error",
                    message=f"Breaking change: major version differs ({local} vs {remote})",
                ))
                report.compatible = False
            elif local < remote:
                report.issues.append(CompatibilityIssue(
                    field="version",
                    severity="info",
                    message=f"Remote is newer within major version: {local} → {remote}",
                ))
            else:
                report.issues.append(CompatibilityIssue(
                    field="version",
                    severity="warning",
                    message=f"Local is newer than remote: {local} > {remote}. Remote may lack features.",
                ))
            return

        if self.policy == CompatibilityPolicy.RELAXED:
            if abs(local.major - remote.major) > 1:
                report.issues.append(CompatibilityIssue(
                    field="version",
                    severity="error",
                    message=f"Versions too far apart: {local} vs {remote}",
                ))
                report.compatible = False
            else:
                report.issues.append(CompatibilityIssue(
                    field="version",
                    severity="warning",
                    message=f"Adjacent major versions: {local} vs {remote}. Verify interface.",
                ))
            return

        # BEST_EFFORT: just warn
        report.issues.append(CompatibilityIssue(
            field="version",
            severity="warning",
            message=f"Version mismatch (best-effort): {local} vs {remote}",
        ))

    def _check_inputs(
        self,
        local: list[str],
        remote: list[str],
        report: CompatibilityReport,
    ) -> None:
        """Check if remote accepts at least the inputs local expects."""
        if not local and not remote:
            return

        # Remote must accept all inputs local would send
        missing_in_remote = set(local) - set(remote)
        extra_in_remote = set(remote) - set(local)

        if missing_in_remote:
            report.issues.append(CompatibilityIssue(
                field="inputs",
                severity="error",
                message=f"Remote is missing inputs: {', '.join(sorted(missing_in_remote))}",
            ))
            report.compatible = False

        if extra_in_remote:
            report.issues.append(CompatibilityIssue(
                field="inputs",
                severity="info",
                message=f"Remote has additional optional inputs: {', '.join(sorted(extra_in_remote))}",
            ))

    def _check_outputs(
        self,
        local: list[str],
        remote: list[str],
        report: CompatibilityReport,
    ) -> None:
        """Check if remote produces the outputs local expects."""
        if not local and not remote:
            return

        # Remote must produce all outputs local expects
        missing_in_remote = set(local) - set(remote)

        if missing_in_remote:
            report.issues.append(CompatibilityIssue(
                field="outputs",
                severity="warning",
                message=f"Remote is missing outputs you expect: {', '.join(sorted(missing_in_remote))}",
            ))
            # Not a hard error — consumer can handle missing outputs


def check_quick(
    local: CapInterface | Any,
    remote: CapInterface | Any,
    policy: str = "semver",
) -> bool:
    """Quick compatibility check — returns True/False."""
    p = CompatibilityPolicy(policy)
    checker = CompatibilityChecker(policy=p)
    return checker.check(local, remote).compatible
