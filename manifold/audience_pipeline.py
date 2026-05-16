"""Audience routing pipeline — composable filters, transforms, and splitters.

Extends the base ``AudienceRouter`` with a pipeline architecture for
sophisticated routing decisions. Instead of a single route() call,
you chain *stages* that filter, score, transform, and split the
audience before dispatching.

Stages:

- **FilterStage** — drop agents that don't match a predicate
- **BoostStage** — multiply scores for agents matching a predicate
- **LimitStage** — cap the audience to the top-N entries
- **SplitStage** — partition the audience into groups (e.g. primary/fallback)
- **TransformStage** — arbitrary score transformation via a callable

Usage::

    from manifold.audience_pipeline import AudiencePipeline, FilterStage, BoostStage, LimitStage

    pipeline = AudiencePipeline(agent) \\
        .filter(lambda e: "solar" in " ".join(e.capabilities).lower()) \\
        .boost(lambda e: e.name == "braid", factor=2.0) \\
        .limit(3)

    report = pipeline.route("solar-flare-prediction")
    for entry in report.entries:
        print(f"{entry.name}: {entry.score:.2f}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .audience import AudienceEntry, AudienceReport, AudienceRouter, Signal


# Type aliases
Predicate = Callable[["AudienceEntry"], bool]
ScoreTransform = Callable[[float, "AudienceEntry"], float]


# ─── Stages ────────────────────────────────────────────────────────────────

@dataclass
class StageResult:
    """Metadata about a stage's execution."""
    stage_name: str
    input_count: int
    output_count: int
    extra: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"<StageResult {self.stage_name} {self.input_count}→{self.output_count}>"


class PipelineStage:
    """Base class for audience pipeline stages."""
    name: str = "stage"

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        raise NotImplementedError


class FilterStage(PipelineStage):
    """Drop entries that don't match a predicate."""

    name = "filter"

    def __init__(self, predicate: Predicate, reason: str = "") -> None:
        self._predicate = predicate
        self._reason = reason

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        return [e for e in entries if self._predicate(e)]


class BoostStage(PipelineStage):
    """Multiply scores for entries matching a predicate."""

    name = "boost"

    def __init__(self, predicate: Predicate, factor: float = 1.5, reason: str = "") -> None:
        self._predicate = predicate
        self._factor = factor
        self._reason = reason

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        result = []
        for e in entries:
            if self._predicate(e):
                boosted = AudienceEntry(
                    name=e.name,
                    score=min(e.score * self._factor, 1.0),
                    signals=e.signals,
                    capabilities=e.capabilities,
                    reason=f"{e.reason}; boosted ×{self._factor}" + (f" ({self._reason})" if self._reason else ""),
                )
                result.append(boosted)
            else:
                result.append(e)
        # Re-sort after boosting
        result.sort(key=lambda e: e.score, reverse=True)
        return result


class LimitStage(PipelineStage):
    """Cap the audience to the top-N entries."""

    name = "limit"

    def __init__(self, n: int) -> None:
        self._n = n

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        return entries[: self._n]


class DedupeStage(PipelineStage):
    """Remove duplicate agent entries, keeping the highest score."""

    name = "dedupe"

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        seen: dict[str, AudienceEntry] = {}
        for e in entries:
            if e.name not in seen or e.score > seen[e.name].score:
                seen[e.name] = e
        return sorted(seen.values(), key=lambda e: e.score, reverse=True)


class TransformStage(PipelineStage):
    """Apply an arbitrary score transformation."""

    name = "transform"

    def __init__(self, fn: ScoreTransform) -> None:
        self._fn = fn

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        result = []
        for e in entries:
            new_score = self._fn(e.score, e)
            result.append(AudienceEntry(
                name=e.name,
                score=max(0.0, min(1.0, new_score)),
                signals=e.signals,
                capabilities=e.capabilities,
                reason=e.reason,
            ))
        result.sort(key=lambda e: e.score, reverse=True)
        return result


class ThresholdStage(PipelineStage):
    """Drop entries below a score threshold."""

    name = "threshold"

    def __init__(self, min_score: float) -> None:
        self._min_score = min_score

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        return [e for e in entries if e.score >= self._min_score]


class DiversityStage(PipelineStage):
    """Ensure diversity by capping how many entries can come from similar agents.

    Two agents are "similar" if they share more than ``max_overlap`` fraction
    of their capabilities.
    """

    name = "diversity"

    def __init__(self, max_overlap: float = 0.7, max_per_cluster: int = 2) -> None:
        self._max_overlap = max_overlap
        self._max_per_cluster = max_per_cluster

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        selected: list[AudienceEntry] = []
        clusters: list[set[str]] = []

        for e in entries:
            e_caps = set(c.lower() for c in e.capabilities)
            placed = False
            for cluster_caps in clusters:
                if e_caps and cluster_caps:
                    overlap = len(e_caps & cluster_caps) / max(len(e_caps | cluster_caps), 1)
                    if overlap > self._max_overlap:
                        # Count how many in selected belong to this cluster
                        count = sum(
                            1 for s in selected
                            if len(set(c.lower() for c in s.capabilities) & cluster_caps)
                            / max(len(set(c.lower() for c in s.capabilities) | cluster_caps), 1)
                            > self._max_overlap
                        )
                        if count >= self._max_per_cluster:
                            placed = True
                            break
            if not placed:
                selected.append(e)
                if e_caps:
                    clusters.append(e_caps)

        return selected


class RequireSignalStage(PipelineStage):
    """Only keep entries that have a specific signal present."""

    name = "require_signal"

    def __init__(self, signal: Signal) -> None:
        self._signal = signal

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        return [e for e in entries if self._signal in e.signals]


class SplitStage(PipelineStage):
    """Partition entries into named groups stored in context.

    Does not modify entries — stores the split in ``ctx["splits"]``.
    """

    name = "split"

    def __init__(self, key: str, partitions: dict[str, Predicate]) -> None:
        self._key = key
        self._partitions = partitions

    def apply(self, entries: list[AudienceEntry], ctx: dict[str, Any]) -> list[AudienceEntry]:
        splits: dict[str, list[AudienceEntry]] = {}
        remaining = list(entries)

        for part_name, predicate in self._partitions.items():
            group = [e for e in remaining if predicate(e)]
            splits[part_name] = group
            remaining = [e for e in remaining if not predicate(e)]

        if remaining:
            splits["_default"] = remaining

        ctx.setdefault("splits", {})[self._key] = splits
        return entries


# ─── Pipeline ──────────────────────────────────────────────────────────────

@dataclass
class PipelineReport:
    """Full pipeline routing result with stage metadata."""
    topic: str
    entries: list[AudienceEntry]
    total_candidates: int
    excluded: int
    stage_results: list[StageResult] = field(default_factory=list)
    splits: dict[str, dict[str, list[AudienceEntry]]] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)

    @property
    def primary(self) -> AudienceEntry | None:
        return self.entries[0] if self.entries else None

    def summary(self) -> str:
        lines = [f"Pipeline result for '{self.topic}': {len(self.entries)} agents"]
        for e in self.entries:
            sigs = "+".join(s.value for s in e.signals)
            lines.append(f"  {e.name}: {e.score:.2f} [{sigs}] — {e.reason}")
        if self.stage_results:
            lines.append(f"  Stages: {' → '.join(f'{s.stage_name}({s.input_count}→{s.output_count})' for s in self.stage_results)}")
        if self.splits:
            for key, partitions in self.splits.items():
                for pname, entries in partitions.items():
                    names = [e.name for e in entries]
                    lines.append(f"  Split '{key}/{pname}': {', '.join(names) or 'empty'}")
        if self.excluded:
            lines.append(f"  ({self.excluded} excluded)")
        return "\n".join(lines)


class AudiencePipeline(AudienceRouter):
    """
    Composable audience routing with pluggable stages.

    Extends ``AudienceRouter`` with a pipeline architecture. After the base
    routing computes scores, stages are applied in sequence to filter,
    boost, limit, and split the audience.

    Usage::

        pipeline = AudiencePipeline(agent) \\
            .boost(lambda e: Signal.TRUST in e.signals, factor=1.5) \\
            .filter(lambda e: e.score > 0.1) \\
            .limit(5)

        report = pipeline.route("solar-prediction")
    """

    def __init__(self, agent, weights: dict[str, float] | None = None) -> None:
        super().__init__(agent, weights)
        self._stages: list[PipelineStage] = []

    # ─── Fluent stage builders ──────────────────────────────────────

    def filter(self, predicate: Predicate, reason: str = "") -> AudiencePipeline:
        """Drop entries that don't match the predicate."""
        self._stages.append(FilterStage(predicate, reason))
        return self

    def boost(self, predicate: Predicate, factor: float = 1.5, reason: str = "") -> AudiencePipeline:
        """Multiply scores for matching entries."""
        self._stages.append(BoostStage(predicate, factor, reason))
        return self

    def limit(self, n: int) -> AudiencePipeline:
        """Cap to top-N entries."""
        self._stages.append(LimitStage(n))
        return self

    def dedupe(self) -> AudiencePipeline:
        """Remove duplicates, keeping highest score."""
        self._stages.append(DedupeStage())
        return self

    def threshold(self, min_score: float) -> AudiencePipeline:
        """Drop entries below a score threshold."""
        self._stages.append(ThresholdStage(min_score))
        return self

    def diversity(self, max_overlap: float = 0.7, max_per_cluster: int = 2) -> AudiencePipeline:
        """Ensure diverse agents by capping similar entries."""
        self._stages.append(DiversityStage(max_overlap, max_per_cluster))
        return self

    def require_signal(self, signal: Signal) -> AudiencePipeline:
        """Only keep entries with a specific signal."""
        self._stages.append(RequireSignalStage(signal))
        return self

    def transform(self, fn: ScoreTransform) -> AudiencePipeline:
        """Apply an arbitrary score transformation."""
        self._stages.append(TransformStage(fn))
        return self

    def split(self, key: str, partitions: dict[str, Predicate]) -> AudiencePipeline:
        """Partition entries into named groups (stored in report)."""
        self._stages.append(SplitStage(key, partitions))
        return self

    def add_stage(self, stage: PipelineStage) -> AudiencePipeline:
        """Add a custom stage."""
        self._stages.append(stage)
        return self

    # ─── Routing ────────────────────────────────────────────────────

    def route(
        self,
        topic: str,
        min_score: float = 0.0,
        exclude_self: bool = True,
        max_results: int | None = None,
    ) -> PipelineReport:
        """
        Route with the full pipeline applied.

        Runs base routing first, then applies all stages in order.
        Returns a PipelineReport with stage metadata.
        """
        # Run base routing
        base = super().route(topic, min_score=0.0, exclude_self=exclude_self)
        entries = list(base.entries)
        total = base.total_candidates

        # Pipeline context (mutable, shared across stages)
        ctx: dict[str, Any] = {"splits": {}, "topic": topic}

        # Apply stages
        stage_results: list[StageResult] = []
        for stage in self._stages:
            input_count = len(entries)
            entries = stage.apply(entries, ctx)
            stage_results.append(StageResult(
                stage_name=stage.name,
                input_count=input_count,
                output_count=len(entries),
            ))

        # Apply min_score filter
        if min_score > 0:
            before = len(entries)
            entries = [e for e in entries if e.score >= min_score]
            if len(entries) < before:
                stage_results.append(StageResult(
                    stage_name="min_score_filter",
                    input_count=before,
                    output_count=len(entries),
                ))

        # Apply max_results
        if max_results is not None:
            before = len(entries)
            entries = entries[:max_results]
            if len(entries) < before:
                stage_results.append(StageResult(
                    stage_name="max_results",
                    input_count=before,
                    output_count=len(entries),
                ))

        excluded = total - len(entries)

        return PipelineReport(
            topic=topic,
            entries=entries,
            total_candidates=total,
            excluded=excluded,
            stage_results=stage_results,
            splits=ctx.get("splits", {}),
            weights=dict(self._weights),
        )
