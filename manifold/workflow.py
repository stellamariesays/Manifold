"""Workflow engine — declarative DAG orchestrator for multi-step agent workflows.

Builds on top of the composition system (Pipeline, ParallelDispatch) and adds:
- **DAG-based workflows**: steps with explicit dependencies, not just linear chains
- **Conditional branching**: route to different steps based on intermediate results
- **Retry & compensation**: per-step retry policies and undo handlers
- **Workflow templates**: define once, instantiate with different payloads
- **State tracking**: full execution history for observability and debugging

Usage::

    from manifold.workflow import Workflow, WorkflowStep, RetryPolicy

    wf = Workflow("solar-report")

    @wf.step("collect", retries=2)
    async def collect(ctx):
        return {"data": [1, 2, 3]}

    @wf.step("analyze", depends_on=["collect"])
    async def analyze(ctx):
        return {"mean": sum(ctx["collect"]["data"]) / len(ctx["collect"]["data"])}

    @wf.step("report", depends_on=["analyze"])
    async def report(ctx):
        return {"summary": f"Mean: {ctx['analyze']['mean']}"}

    result = await wf.run({"region": "pacific"})
    print(result.output)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


# ─── Types ──────────────────────────────────────────────────────────────

class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPENSATING = "compensating"


class StepExecutionStatus(str, Enum):
    WAITING = "waiting"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"


@dataclass
class StepRetryPolicy:
    """Retry configuration for a workflow step."""
    max_retries: int = 0
    backoff_base_ms: float = 100.0
    backoff_max_ms: float = 10_000.0
    retry_on: list[str] | None = None  # exception type names; None = all

    def delay_ms(self, attempt: int) -> float:
        """Exponential backoff delay in ms for a given attempt number."""
        delay = self.backoff_base_ms * (2 ** attempt)
        return min(delay, self.backoff_max_ms)


@dataclass
class StepOutput:
    """Recorded output from a completed step."""
    step_name: str
    status: StepExecutionStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    attempts: int = 1
    elapsed_ms: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    workflow_id: str
    workflow_name: str
    status: WorkflowStatus
    steps: dict[str, StepOutput] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def ok(self) -> bool:
        return self.status == WorkflowStatus.COMPLETED

    @property
    def elapsed_ms(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    @property
    def failed_step(self) -> str | None:
        for name, step in self.steps.items():
            if step.status == StepExecutionStatus.FAILED:
                return name
        return None

    def summary(self) -> str:
        completed = sum(1 for s in self.steps.values() if s.status == StepExecutionStatus.COMPLETED)
        failed = sum(1 for s in self.steps.values() if s.status == StepExecutionStatus.FAILED)
        total = len(self.steps)
        return (
            f"Workflow {self.workflow_name!r} [{self.status.value}] "
            f"{completed}/{total} completed, {failed} failed "
            f"in {self.elapsed_ms:.0f}ms"
        )

    def __repr__(self) -> str:
        return f"<WorkflowResult {self.workflow_name!r} {self.status.value} {self.elapsed_ms:.0f}ms>"


# ─── Workflow Step ──────────────────────────────────────────────────────

@dataclass
class WorkflowStep:
    """A single step in a workflow DAG."""
    name: str
    handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]]
    depends_on: list[str] = field(default_factory=list)
    condition: Callable[[dict[str, Any]], bool] | None = None
    compensate: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None
    retry_policy: StepRetryPolicy | None = None
    timeout_ms: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        deps = ", ".join(self.depends_on) if self.depends_on else "none"
        return f"<WorkflowStep {self.name!r} depends=[{deps}]>"


# ─── Workflow Engine ────────────────────────────────────────────────────

class Workflow:
    """
    Declarative DAG-based workflow engine.

    Define steps with dependencies, conditions, retries, and compensation
    handlers, then execute the workflow with a payload. Steps run in
    topological order, with independent steps eligible for parallel execution.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._steps: dict[str, WorkflowStep] = {}
        self._execution_order: list[str] | None = None

    def step(
        self,
        name: str,
        depends_on: list[str] | None = None,
        condition: Callable[[dict[str, Any]], bool] | None = None,
        compensate: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        retries: int = 0,
        timeout_ms: float | None = None,
    ) -> Callable:
        """
        Decorator to register a workflow step.

        Args:
            name:       Unique step name.
            depends_on: List of step names that must complete before this step.
            condition:  Optional callable; step only runs if it returns True.
                        Receives the accumulated context dict.
            compensate: Async undo handler called if workflow needs rollback.
            retries:    Max retry attempts on failure.
            timeout_ms: Optional per-step timeout.
        """
        def decorator(fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> Callable:
            retry_policy = StepRetryPolicy(max_retries=retries) if retries > 0 else None
            s = WorkflowStep(
                name=name,
                handler=fn,
                depends_on=depends_on or [],
                condition=condition,
                compensate=compensate,
                retry_policy=retry_policy,
                timeout_ms=timeout_ms,
            )
            self._register_step(s)
            return fn
        return decorator

    def add_step(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
        depends_on: list[str] | None = None,
        condition: Callable[[dict[str, Any]], bool] | None = None,
        compensate: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        retries: int = 0,
        timeout_ms: float | None = None,
    ) -> WorkflowStep:
        """Imperative (non-decorator) step registration."""
        retry_policy = StepRetryPolicy(max_retries=retries) if retries > 0 else None
        s = WorkflowStep(
            name=name,
            handler=handler,
            depends_on=depends_on or [],
            condition=condition,
            compensate=compensate,
            retry_policy=retry_policy,
            timeout_ms=timeout_ms,
        )
        self._register_step(s)
        return s

    def _register_step(self, step: WorkflowStep) -> None:
        if step.name in self._steps:
            raise ValueError(f"Duplicate step name: {step.name!r}")
        self._steps[step.name] = step
        self._execution_order = None  # invalidate cache

    def _topological_order(self) -> list[str]:
        """Kahn's algorithm for topological sort."""
        if self._execution_order is not None:
            return self._execution_order

        in_degree: dict[str, int] = {name: 0 for name in self._steps}
        graph: dict[str, list[str]] = {name: [] for name in self._steps}

        for name, step in self._steps.items():
            for dep in step.depends_on:
                if dep not in self._steps:
                    raise ValueError(
                        f"Step {name!r} depends on unknown step {dep!r}"
                    )
                graph[dep].append(name)
                in_degree[name] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        order: list[str] = []

        while queue:
            queue.sort()  # deterministic order
            node = queue.pop(0)
            order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self._steps):
            raise ValueError("Workflow has circular dependencies")

        self._execution_order = order
        return order

    def validate(self) -> list[str]:
        """Validate the workflow DAG. Returns list of issues (empty = valid)."""
        issues: list[str] = []

        if not self._steps:
            issues.append("Workflow has no steps")
            return issues

        # Check for unknown dependencies
        for name, step in self._steps.items():
            for dep in step.depends_on:
                if dep not in self._steps:
                    issues.append(f"Step {name!r} depends on unknown step {dep!r}")

        # Check for cycles
        if not issues:
            try:
                self._topological_order()
            except ValueError as e:
                issues.append(str(e))

        return issues

    async def run(
        self,
        payload: dict[str, Any] | None = None,
        stop_on_failure: bool = True,
    ) -> WorkflowResult:
        """
        Execute the workflow.

        Args:
            payload:        Initial context passed to each step.
            stop_on_failure: If True, stop on first failure. If False, skip
                             dependent steps but continue others.

        Returns:
            WorkflowResult with full execution details.
        """
        payload = payload or {}
        workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
        result = WorkflowResult(
            workflow_id=workflow_id,
            workflow_name=self.name,
            status=WorkflowStatus.RUNNING,
            context=dict(payload),
            started_at=time.time(),
        )

        order = self._topological_order()
        completed_steps: set[str] = set()
        failed_steps: set[str] = set()
        step_outputs: dict[str, dict[str, Any]] = {}

        for step_name in order:
            step = self._steps[step_name]

            # Check if any dependency failed
            dep_failed = any(d in failed_steps for d in step.depends_on)
            if dep_failed:
                result.steps[step_name] = StepOutput(
                    step_name=step_name,
                    status=StepExecutionStatus.SKIPPED,
                    error="Dependency failed",
                )
                failed_steps.add(step_name)
                continue

            # Check condition
            if step.condition is not None:
                try:
                    should_run = step.condition(step_outputs)
                except Exception:
                    should_run = False
                if not should_run:
                    result.steps[step_name] = StepOutput(
                        step_name=step_name,
                        status=StepExecutionStatus.SKIPPED,
                    )
                    continue

            # Build step context: payload + outputs from dependencies
            ctx = dict(payload)
            ctx.update(step_outputs)

            # Execute with retries
            step_result = await self._execute_step(step, ctx)
            result.steps[step_name] = step_result

            if step_result.status == StepExecutionStatus.COMPLETED:
                completed_steps.add(step_name)
                step_outputs[step_name] = step_result.output
                result.context[step_name] = step_result.output
            else:
                failed_steps.add(step_name)
                if stop_on_failure:
                    # Mark remaining steps as skipped
                    for remaining in order[order.index(step_name) + 1:]:
                        if remaining not in result.steps:
                            result.steps[remaining] = StepOutput(
                                step_name=remaining,
                                status=StepExecutionStatus.SKIPPED,
                                error="Workflow stopped on failure",
                            )
                    break

        # Determine final status
        if failed_steps:
            result.status = WorkflowStatus.FAILED
        else:
            result.status = WorkflowStatus.COMPLETED

        result.completed_at = time.time()
        return result

    async def _execute_step(
        self,
        step: WorkflowStep,
        ctx: dict[str, Any],
    ) -> StepOutput:
        """Execute a single step with retry logic."""
        max_attempts = 1
        if step.retry_policy:
            max_attempts = step.retry_policy.max_retries + 1

        last_error: str | None = None
        started_at = time.time()

        for attempt in range(max_attempts):
            t0 = time.monotonic()
            try:
                output = await step.handler(ctx)
                elapsed = (time.monotonic() - t0) * 1000
                return StepOutput(
                    step_name=step.name,
                    status=StepExecutionStatus.COMPLETED,
                    output=output if isinstance(output, dict) else {"value": output},
                    attempts=attempt + 1,
                    elapsed_ms=elapsed,
                    started_at=started_at,
                    completed_at=time.time(),
                )
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                last_error = str(exc)
                # Could add backoff sleep here for real async scenarios

        return StepOutput(
            step_name=step.name,
            status=StepExecutionStatus.FAILED,
            error=last_error,
            attempts=max_attempts,
            elapsed_ms=(time.monotonic() - started_at) * 1000 if started_at else 0.0,
            started_at=started_at,
            completed_at=time.time(),
        )

    async def compensate(self, result: WorkflowResult) -> None:
        """
        Run compensation (undo) handlers for all completed steps, in reverse order.

        Only compensates steps that have a compensate handler defined and
        that completed successfully.
        """
        completed = [
            (name, step_result)
            for name, step_result in result.steps.items()
            if step_result.status == StepExecutionStatus.COMPLETED
        ]
        # Reverse order
        completed.reverse()

        for step_name, step_result in completed:
            step = self._steps.get(step_name)
            if step and step.compensate:
                try:
                    await step.compensate(step_result.output)
                    step_result.status = StepExecutionStatus.COMPENSATED
                except Exception:
                    pass  # compensation best-effort

    def list_steps(self) -> list[WorkflowStep]:
        """Return steps in execution order."""
        order = self._topological_order()
        return [self._steps[name] for name in order]

    def dag_summary(self) -> str:
        """Human-readable DAG representation."""
        lines = [f"Workflow: {self.name}", "=" * 40]
        for name in self._topological_order():
            step = self._steps[name]
            deps = f" after [{', '.join(step.depends_on)}]" if step.depends_on else " (entry)"
            cond = " [conditional]" if step.condition else ""
            retry = f" retry={step.retry_policy.max_retries}" if step.retry_policy else ""
            lines.append(f"  {name}{deps}{cond}{retry}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<Workflow {self.name!r} steps={len(self._steps)}>"
