"""Capability composition — chain agent capabilities into compound workflows.

Agents on the Manifold mesh don't just have individual capabilities — they can
compose them into multi-step workflows where each step's output feeds the next
step's input. The composition engine handles:

- **Pipelines**: sequential chains of (agent, capability) steps
- **Parallel fan-out**: dispatch the same payload to multiple agents simultaneously
- **Fan-in / merge**: collect parallel results and merge them
- **Conditional routing**: branch based on intermediate results

Usage::

    from manifold.composition import Pipeline, PipelineStep

    pipe = Pipeline("solar-analysis")
    pipe.step("data-ingest", agent="collector", capability="data-collection")
    pipe.step("predict", agent="solver", capability="solar-prediction")
    pipe.step("validate", agent="checker", capability="anomaly-detection")

    result = await pipe.execute(context={"region": "pacific"})
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MergeStrategy(str, Enum):
    """How to combine results from parallel branches."""
    CONCAT = "concat"       # list concatenation
    MERGE = "merge"         # dict merge (last write wins)
    FIRST = "first"         # take first non-error result
    ALL = "all"             # keep all results as a list


@dataclass
class PipelineStep:
    """One step in a capability pipeline."""
    name: str
    agent: str
    capability: str
    condition: Callable[[dict[str, Any]], bool] | None = None
    transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    timeout_ms: float = 30_000

    def should_run(self, context: dict[str, Any]) -> bool:
        """Check if this step should execute given current context."""
        if self.condition is None:
            return True
        return self.condition(context)


@dataclass
class StepResult:
    """Outcome of a single pipeline step."""
    step_name: str
    agent: str
    status: StepStatus = StepStatus.PENDING
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_ms: float = 0.0


@dataclass
class PipelineResult:
    """Outcome of a full pipeline execution."""
    pipeline_id: str
    name: str
    status: StepStatus = StepStatus.PENDING
    steps: list[StepResult] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    total_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.status == StepStatus.COMPLETED

    @property
    def failed_step(self) -> StepResult | None:
        """First failed step, if any."""
        return next((s for s in self.steps if s.status == StepStatus.FAILED), None)

    def summary(self) -> str:
        lines = [f"Pipeline '{self.name}' [{self.status.value}] {self.total_ms:.0f}ms"]
        for s in self.steps:
            mark = "✓" if s.status == StepStatus.COMPLETED else "✗" if s.status == StepStatus.FAILED else "–"
            lines.append(f"  {mark} {s.step_name} ({s.agent}) {s.elapsed_ms:.0f}ms")
        return "\n".join(lines)


class Pipeline:
    """
    A composable capability pipeline.

    Steps execute sequentially. Each step receives the accumulated context
    (initial payload + all previous step outputs merged in). Steps can have
    conditions (skip if false) and transforms (modify output before passing).
    """

    def __init__(self, name: str, merge_strategy: MergeStrategy = MergeStrategy.MERGE) -> None:
        self.name = name
        self._steps: list[PipelineStep] = []
        self._merge = merge_strategy
        self._step_map: dict[str, PipelineStep] = {}

    def step(
        self,
        name: str,
        agent: str,
        capability: str,
        condition: Callable[[dict[str, Any]], bool] | None = None,
        transform: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        timeout_ms: float = 30_000,
    ) -> "Pipeline":
        """Add a step. Chainable."""
        s = PipelineStep(
            name=name, agent=agent, capability=capability,
            condition=condition, transform=transform, timeout_ms=timeout_ms,
        )
        self._steps.append(s)
        self._step_map[name] = s
        return self

    @property
    def steps(self) -> list[PipelineStep]:
        return list(self._steps)

    def validate(self) -> list[str]:
        """Check pipeline for issues. Returns list of warnings (empty = OK)."""
        warnings: list[str] = []
        seen_names: set[str] = set()
        for s in self._steps:
            if s.name in seen_names:
                warnings.append(f"Duplicate step name: {s.name!r}")
            seen_names.add(s.name)
        return warnings

    async def execute(
        self,
        context: dict[str, Any] | None = None,
        executor: Callable[[str, str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]] | None = None,
    ) -> PipelineResult:
        """
        Execute the pipeline.

        Args:
            context: Initial payload / context dict.
            executor: Async callable (agent_name, capability, payload) -> result dict.
                      If None, steps run as no-ops (for testing/verification).

        Returns:
            PipelineResult with per-step and overall status.
        """
        result = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            name=self.name,
        )
        ctx: dict[str, Any] = dict(context or {})
        t0 = time.monotonic()

        for step in self._steps:
            step_result = StepResult(step_name=step.name, agent=step.agent)

            if not step.should_run(ctx):
                step_result.status = StepStatus.SKIPPED
                result.steps.append(step_result)
                continue

            step_result.status = StepStatus.RUNNING
            step_t0 = time.monotonic()

            if executor is not None:
                try:
                    output = await executor(step.agent, step.capability, dict(ctx))
                    if step.transform is not None:
                        output = step.transform(output)
                    step_result.output = output
                    step_result.status = StepStatus.COMPLETED
                    # Merge output into context for next step
                    ctx = self._merge_results(ctx, output)
                except Exception as exc:
                    step_result.status = StepStatus.FAILED
                    step_result.error = str(exc)
                    result.steps.append(step_result)
                    result.status = StepStatus.FAILED
                    break
            else:
                # No executor — dry run
                step_result.status = StepStatus.COMPLETED

            step_result.elapsed_ms = (time.monotonic() - step_t0) * 1000
            result.steps.append(step_result)

        if result.status != StepStatus.FAILED:
            result.status = StepStatus.COMPLETED

        result.total_ms = (time.monotonic() - t0) * 1000
        result.output = ctx
        return result

    def _merge_results(self, base: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        """Merge a step's output into the running context."""
        merged = dict(base)
        if self._merge == MergeStrategy.MERGE:
            merged.update(new)
        elif self._merge == MergeStrategy.CONCAT:
            for k, v in new.items():
                merged.setdefault(k, [])
                if isinstance(merged[k], list):
                    merged[k].extend(v if isinstance(v, list) else [v])
                else:
                    merged[k] = v
        elif self._merge == MergeStrategy.FIRST:
            for k, v in new.items():
                merged.setdefault(k, v)
        return merged


@dataclass
class ParallelBranch:
    """One branch of a parallel fan-out."""
    name: str
    agent: str
    capability: str


@dataclass
class ParallelResult:
    """Result of a parallel fan-out + fan-in."""
    parallel_id: str
    branches: dict[str, StepResult] = field(default_factory=dict)
    merged: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    total_ms: float = 0.0

    @property
    def succeeded(self) -> bool:
        return all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for s in self.branches.values()
        )

    @property
    def failures(self) -> list[StepResult]:
        return [s for s in self.branches.values() if s.status == StepStatus.FAILED]

    def summary(self) -> str:
        lines = [f"Parallel [{self.status.value}] {self.total_ms:.0f}ms"]
        for name, s in self.branches.items():
            mark = "✓" if s.status == StepStatus.COMPLETED else "✗" if s.status == StepStatus.FAILED else "–"
            lines.append(f"  {mark} {name} ({s.agent}) {s.elapsed_ms:.0f}ms")
        return "\n".join(lines)


class ParallelDispatch:
    """
    Fan-out to multiple agents in parallel, then merge results.

    Useful when you want multiple perspectives on the same data — e.g.,
    run three different analysis capabilities on the same dataset and
    merge the outputs.
    """

    def __init__(self, name: str, merge_strategy: MergeStrategy = MergeStrategy.MERGE) -> None:
        self.name = name
        self._branches: list[ParallelBranch] = []
        self._merge = merge_strategy

    def branch(self, name: str, agent: str, capability: str) -> "ParallelDispatch":
        """Add a parallel branch. Chainable."""
        self._branches.append(ParallelBranch(name=name, agent=agent, capability=capability))
        return self

    @property
    def branches(self) -> list[ParallelBranch]:
        return list(self._branches)

    async def execute(
        self,
        context: dict[str, Any] | None = None,
        executor: Callable[[str, str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]] | None = None,
    ) -> ParallelResult:
        """Execute all branches in parallel, merge results."""
        import asyncio

        result = ParallelResult(parallel_id=str(uuid.uuid4()))
        ctx: dict[str, Any] = dict(context or {})
        t0 = time.monotonic()

        async def _run_branch(b: ParallelBranch) -> StepResult:
            sr = StepResult(step_name=b.name, agent=b.agent, status=StepStatus.RUNNING)
            bt0 = time.monotonic()
            if executor is not None:
                try:
                    output = await executor(b.agent, b.capability, dict(ctx))
                    sr.output = output
                    sr.status = StepStatus.COMPLETED
                except Exception as exc:
                    sr.status = StepStatus.FAILED
                    sr.error = str(exc)
            else:
                sr.status = StepStatus.COMPLETED
            sr.elapsed_ms = (time.monotonic() - bt0) * 1000
            return sr

        tasks = {b.name: asyncio.create_task(_run_branch(b)) for b in self._branches}
        for name, task in tasks.items():
            result.branches[name] = await task

        # Merge outputs
        merged: dict[str, Any] = {}
        for sr in result.branches.values():
            if sr.status == StepStatus.COMPLETED:
                if self._merge == MergeStrategy.MERGE:
                    merged.update(sr.output)
                elif self._merge == MergeStrategy.CONCAT:
                    for k, v in sr.output.items():
                        merged.setdefault(k, [])
                        if isinstance(merged[k], list):
                            merged[k].extend(v if isinstance(v, list) else [v])
                elif self._merge == MergeStrategy.ALL:
                    merged.setdefault("results", [])
                    merged["results"].append(sr.output)
                elif self._merge == MergeStrategy.FIRST:
                    for k, v in sr.output.items():
                        merged.setdefault(k, v)

        result.merged = merged
        result.total_ms = (time.monotonic() - t0) * 1000

        if result.succeeded:
            result.status = StepStatus.COMPLETED
        elif result.failures:
            result.status = StepStatus.FAILED if len(result.failures) == len(self._branches) else StepStatus.COMPLETED

        return result
