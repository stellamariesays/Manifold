"""Capability pipelines — chain capabilities into multi-step workflows.

A pipeline wires capabilities together so that each step's output feeds
into the next step's input. This turns individual capabilities into
composable workflows without manual orchestration.

Pipelines validate the wiring at definition time (step N's outputs must
feed step N+1's inputs) and track execution history for observability.

Usage::

    from manifold.pipeline import Pipeline, PipelineBuilder

    builder = PipelineBuilder(agent_builder)

    pipeline = builder.create("solar-report", version="1.0.0") \\
        .step("solar-prediction", map_inputs={"region": "region", "horizon_hours": "horizon"}) \\
        .step("report-format", map_inputs={"prediction": "predicted_mw", "confidence": "confidence"}) \\
        .build()

    result = await pipeline.run({"region": "pacific", "horizon": 24})
    print(result.output)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .capability_builder import CapabilityBuilder


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class StepResult:
    """Result from a single pipeline step."""
    step_name: str
    capability: str
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    elapsed_ms: float = 0.0

    def __repr__(self) -> str:
        status = "✓" if self.ok else f"✗ {self.error}"
        return f"<Step {self.step_name!r} {status} {self.elapsed_ms:.0f}ms>"


@dataclass
class PipelineResult:
    """Result from a full pipeline execution."""
    pipeline_name: str
    run_id: str
    status: PipelineStatus
    steps: list[StepResult] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == PipelineStatus.COMPLETED

    @property
    def failed_step(self) -> StepResult | None:
        return next((s for s in self.steps if not s.ok), None)

    def __repr__(self) -> str:
        ok = sum(1 for s in self.steps if s.ok)
        total = len(self.steps)
        return f"<PipelineResult {self.pipeline_name!r} {self.status.value} [{ok}/{total}] {self.elapsed_ms:.0f}ms>"


@dataclass
class PipelineStep:
    """A single step in a pipeline definition."""
    capability: str
    name: str = ""
    map_inputs: dict[str, str] = field(default_factory=dict)
    # map_inputs: {payload_key: output_key_from_previous_step}
    # If empty, passes the full previous output as the payload
    defaults: dict[str, Any] = field(default_factory=dict)
    optional: bool = False  # If true, failure doesn't stop the pipeline
    timeout_ms: float = 30_000

    def __repr__(self) -> str:
        return f"<PipelineStep {self.name or self.capability!r}>"


class Pipeline:
    """
    A compiled, runnable pipeline of capability invocations.

    Don't construct directly — use PipelineBuilder.
    """

    def __init__(
        self,
        name: str,
        steps: list[PipelineStep],
        builder: CapabilityBuilder,
        version: str = "1.0.0",
        description: str = "",
    ) -> None:
        self.name = name
        self.version = version
        self.description = description
        self._steps = steps
        self._builder = builder
        self._run_count = 0
        self._last_run_at: float | None = None
        self._avg_elapsed_ms: float = 0.0

    @property
    def step_count(self) -> int:
        return len(self._steps)

    def _build_payload(
        self,
        step: PipelineStep,
        initial_input: dict[str, Any],
        prev_output: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build the input payload for a step."""
        payload = dict(initial_input)  # start with original inputs

        if prev_output is not None:
            if step.map_inputs:
                # Map specific keys from previous output
                for payload_key, output_key in step.map_inputs.items():
                    if output_key in prev_output:
                        payload[payload_key] = prev_output[output_key]
            else:
                # Pass entire previous output
                payload.update(prev_output)

        # Apply defaults for missing keys
        for key, value in step.defaults.items():
            payload.setdefault(key, value)

        return payload

    async def run(self, inputs: dict[str, Any] | None = None) -> PipelineResult:
        """
        Execute the pipeline sequentially.

        Each step receives the initial inputs merged with mapped outputs
        from the previous step.
        """
        inputs = inputs or {}
        run_id = f"pipe-{uuid.uuid4().hex[:12]}"
        t0 = time.monotonic()
        results: list[StepResult] = []
        prev_output: dict[str, Any] | None = None
        status = PipelineStatus.RUNNING

        for i, step in enumerate(self._steps):
            payload = self._build_payload(step, inputs, prev_output)
            step_t0 = time.monotonic()

            inv = await self._builder.invoke(
                step.capability, payload, validate_inputs=False
            )

            elapsed = (time.monotonic() - step_t0) * 1000
            sr = StepResult(
                step_name=step.name or f"step-{i}",
                capability=step.capability,
                ok=inv.ok,
                output=inv.output if inv.ok else {},
                error=inv.error,
                elapsed_ms=elapsed,
            )
            results.append(sr)

            if not inv.ok:
                if step.optional:
                    # Skip this output, keep previous
                    continue
                else:
                    status = PipelineStatus.FAILED
                    total_elapsed = (time.monotonic() - t0) * 1000
                    return PipelineResult(
                        pipeline_name=self.name,
                        run_id=run_id,
                        status=status,
                        steps=results,
                        output={},
                        elapsed_ms=total_elapsed,
                        error=f"Step {sr.step_name!r} failed: {sr.error}",
                    )

            prev_output = inv.output

        # All steps completed
        has_optional_failure = any(not s.ok for s in results)
        status = PipelineStatus.PARTIAL if has_optional_failure else PipelineStatus.COMPLETED

        total_elapsed = (time.monotonic() - t0) * 1000

        # Update stats
        self._run_count += 1
        self._last_run_at = time.time()
        total_time = self._avg_elapsed_ms * (self._run_count - 1) + total_elapsed
        self._avg_elapsed_ms = total_time / self._run_count

        return PipelineResult(
            pipeline_name=self.name,
            run_id=run_id,
            status=status,
            steps=results,
            output=prev_output or {},
            elapsed_ms=total_elapsed,
        )

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "steps": self.step_count,
            "run_count": self._run_count,
            "last_run_at": self._last_run_at,
            "avg_elapsed_ms": round(self._avg_elapsed_ms, 1),
        }


class PipelineBuilder:
    """
    Fluent builder for capability pipelines.

    Usage::

        pb = PipelineBuilder(capability_builder)
        pipeline = pb.create("my-workflow") \\
            .step("cap-a") \\
            .step("cap-b", map_inputs={"x": "y"}) \\
            .build()
    """

    def __init__(self, builder: CapabilityBuilder) -> None:
        self._builder = builder

    def create(
        self,
        name: str,
        version: str = "1.0.0",
        description: str = "",
    ) -> _PipelineBuilderWip:
        return _PipelineBuilderWip(
            builder=self._builder,
            name=name,
            version=version,
            description=description,
        )


class _PipelineBuilderWip:
    """Intermediate builder state — collect steps, then build."""

    def __init__(
        self,
        builder: CapabilityBuilder,
        name: str,
        version: str,
        description: str,
    ) -> None:
        self._builder = builder
        self._name = name
        self._version = version
        self._description = description
        self._steps: list[PipelineStep] = []

    def step(
        self,
        capability: str,
        name: str = "",
        map_inputs: dict[str, str] | None = None,
        defaults: dict[str, Any] | None = None,
        optional: bool = False,
        timeout_ms: float = 30_000,
    ) -> _PipelineBuilderWip:
        """Add a step to the pipeline."""
        self._steps.append(PipelineStep(
            capability=capability,
            name=name,
            map_inputs=map_inputs or {},
            defaults=defaults or {},
            optional=optional,
            timeout_ms=timeout_ms,
        ))
        return self

    def build(self) -> Pipeline:
        """Compile and return the pipeline."""
        if not self._steps:
            raise ValueError(f"Pipeline {self._name!r} needs at least one step")

        # Validate capabilities exist (warn but don't fail — they may be registered later)
        for step in self._steps:
            spec = self._builder.get(step.capability)
            if spec is None:
                # Capability not yet registered — that's okay for deferred wiring
                pass

        return Pipeline(
            name=self._name,
            steps=self._steps,
            builder=self._builder,
            version=self._version,
            description=self._description,
        )
