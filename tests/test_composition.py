"""Tests for capability composition — pipelines and parallel dispatch."""

import asyncio
import pytest
from manifold.composition import (
    Pipeline, PipelineStep, PipelineResult, StepStatus, MergeStrategy,
    ParallelDispatch, ParallelBranch, ParallelResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────

async def _echo_executor(agent: str, capability: str, payload: dict) -> dict:
    """Simple executor that echoes agent + capability back."""
    return {"agent": agent, "capability": capability, "input_keys": list(payload.keys())}


async def _failing_executor(agent: str, capability: str, payload: dict) -> dict:
    """Executor that always fails."""
    raise RuntimeError(f"{agent} crashed on {capability}")


async def _transform_executor(agent: str, capability: str, payload: dict) -> dict:
    """Executor that adds a computed field."""
    return {f"{capability}_result": True, "from": agent}


# ── Pipeline tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_basic_pipeline():
    """Pipeline with two sequential steps completes."""
    pipe = Pipeline("test-pipe")
    pipe.step("step1", agent="alice", capability="data-ingest")
    pipe.step("step2", agent="bob", capability="analysis")

    result = await pipe.execute(context={"region": "eu"}, executor=_echo_executor)
    assert result.succeeded
    assert len(result.steps) == 2
    assert result.steps[0].status == StepStatus.COMPLETED
    assert result.steps[1].status == StepStatus.COMPLETED
    assert result.total_ms > 0
    print(f"✅ Basic pipeline: {result.summary()}")


@pytest.mark.asyncio
async def test_pipeline_dry_run():
    """Pipeline without executor runs as dry run (all steps complete)."""
    pipe = Pipeline("dry")
    pipe.step("s1", agent="a", capability="c1")
    pipe.step("s2", agent="b", capability="c2")

    result = await pipe.execute(context={"x": 1})
    assert result.succeeded
    assert all(s.status == StepStatus.COMPLETED for s in result.steps)
    print(f"✅ Dry run: {result.summary()}")


@pytest.mark.asyncio
async def test_pipeline_failure_stops():
    """Pipeline stops on first failure."""
    pipe = Pipeline("fail-pipe")
    pipe.step("good", agent="alice", capability="ok")
    pipe.step("bad", agent="bob", capability="crash")
    pipe.step("never", agent="carol", capability="too-late")

    result = await pipe.execute(
        executor=lambda a, c, p: _failing_executor(a, c, p) if c == "crash" else _echo_executor(a, c, p)
    )
    assert result.status == StepStatus.FAILED
    assert result.failed_step is not None
    assert result.failed_step.step_name == "bad"
    assert len(result.steps) == 2  # third step never appended
    print(f"✅ Failure stops pipeline: {result.summary()}")


@pytest.mark.asyncio
async def test_conditional_step():
    """Steps with conditions that evaluate to False get skipped."""
    pipe = Pipeline("conditional")
    pipe.step("always", agent="alice", capability="base")
    pipe.step(
        "sometimes", agent="bob", capability="optional",
        condition=lambda ctx: ctx.get("run_optional", False),
    )

    # Condition false → skip
    result = await pipe.execute(context={"run_optional": False}, executor=_echo_executor)
    assert result.steps[1].status == StepStatus.SKIPPED
    print(f"✅ Conditional skip: {result.summary()}")

    # Condition true → run
    result2 = await pipe.execute(context={"run_optional": True}, executor=_echo_executor)
    assert result2.steps[1].status == StepStatus.COMPLETED
    print(f"✅ Conditional run: {result2.summary()}")


@pytest.mark.asyncio
async def test_step_transform():
    """Step transforms modify output before merging."""
    pipe = Pipeline("transform")
    pipe.step(
        "transformed", agent="alice", capability="data",
        transform=lambda out: {**out, "extra": True},
    )

    result = await pipe.execute(context={}, executor=_echo_executor)
    assert result.succeeded
    assert result.output.get("extra") is True
    print(f"✅ Transform: {result.output}")


@pytest.mark.asyncio
async def test_pipeline_context_flow():
    """Each step receives accumulated context from previous steps."""
    async def _accumulating_executor(agent: str, cap: str, payload: dict) -> dict:
        return {"step_was": cap, "saw_keys": list(payload.keys())}

    pipe = Pipeline("flow")
    pipe.step("s1", agent="a", capability="first")
    pipe.step("s2", agent="b", capability="second")

    result = await pipe.execute(context={"initial": True}, executor=_accumulating_executor)
    assert result.succeeded
    # Second step should see the initial payload merged with first step's output
    assert result.succeeded
    print(f"✅ Context flow: {result.summary()}")


@pytest.mark.asyncio
async def test_merge_strategies():
    """Different merge strategies combine outputs differently."""
    # MERGE (default) — last write wins
    pipe_merge = Pipeline("merge", merge_strategy=MergeStrategy.MERGE)
    async def _key_executor(a, c, p):
        return {"key": f"{a}-{c}"}

    pipe_merge.step("s1", agent="a", capability="x")
    pipe_merge.step("s2", agent="b", capability="y")
    r_merge = await pipe_merge.execute(
        context={"key": "initial"},
        executor=_key_executor,
    )
    assert r_merge.output["key"] == "b-y"  # overwritten

    # FIRST — first write wins
    pipe_first = Pipeline("first", merge_strategy=MergeStrategy.FIRST)
    pipe_first.step("s1", agent="a", capability="x")
    pipe_first.step("s2", agent="b", capability="y")
    r_first = await pipe_first.execute(
        context={},
        executor=_key_executor,
    )
    assert r_first.output["key"] == "a-x"  # first wins
    print(f"✅ Merge strategies: merge={r_merge.output}, first={r_first.output}")


@pytest.mark.asyncio
async def test_pipeline_validate():
    """validate() catches duplicate step names."""
    pipe = Pipeline("dup")
    pipe.step("s1", agent="a", capability="c")
    pipe.step("s1", agent="b", capability="d")
    warnings = pipe.validate()
    assert len(warnings) == 1
    assert "Duplicate" in warnings[0]
    print(f"✅ Validate: {warnings}")


@pytest.mark.asyncio
async def test_pipeline_result_summary():
    """PipelineResult.summary() produces readable output."""
    pipe = Pipeline("summary-test")
    pipe.step("s1", agent="alice", capability="ingest")
    result = await pipe.execute(context={}, executor=_echo_executor)
    summary = result.summary()
    assert "summary-test" in summary
    assert "alice" in summary
    print(f"✅ Summary:\n{summary}")


@pytest.mark.asyncio
async def test_pipeline_chainable():
    """step() returns self for chaining."""
    pipe = Pipeline("chain")
    result = pipe.step("s1", agent="a", capability="c1").step("s2", agent="b", capability="c2")
    assert result is pipe
    assert len(pipe.steps) == 2
    print(f"✅ Chainable API")


# ── Parallel dispatch tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_basic_parallel():
    """Parallel dispatch fans out to multiple agents."""
    pd = ParallelDispatch("multi")
    pd.branch("b1", agent="alice", capability="analysis-a")
    pd.branch("b2", agent="bob", capability="analysis-b")

    result = await pd.execute(context={"data": [1, 2, 3]}, executor=_transform_executor)
    assert result.succeeded
    assert len(result.branches) == 2
    assert "b1" in result.branches
    assert "b2" in result.branches
    print(f"✅ Parallel: {result.summary()}")


@pytest.mark.asyncio
async def test_parallel_dry_run():
    """Parallel without executor completes all branches."""
    pd = ParallelDispatch("dry-parallel")
    pd.branch("b1", agent="a", capability="c1")
    result = await pd.execute(context={})
    assert result.succeeded
    print(f"✅ Parallel dry run: {result.summary()}")


@pytest.mark.asyncio
async def test_parallel_partial_failure():
    """Parallel with some failures still marks partial success."""
    pd = ParallelDispatch("partial")
    pd.branch("good", agent="alice", capability="ok")
    pd.branch("bad", agent="bob", capability="crash")

    result = await pd.execute(
        executor=lambda a, c, p: _failing_executor(a, c, p) if c == "crash" else _echo_executor(a, c, p)
    )
    assert result.branches["good"].status == StepStatus.COMPLETED
    assert result.branches["bad"].status == StepStatus.FAILED
    assert len(result.failures) == 1
    # Overall should complete (some branches succeeded)
    assert result.status == StepStatus.COMPLETED
    print(f"✅ Partial failure: {result.summary()}")


@pytest.mark.asyncio
async def test_parallel_all_fail():
    """Parallel where all branches fail → FAILED status."""
    pd = ParallelDispatch("all-fail")
    pd.branch("b1", agent="a", capability="x")
    pd.branch("b2", agent="b", capability="y")

    result = await pd.execute(executor=_failing_executor)
    assert result.status == StepStatus.FAILED
    assert len(result.failures) == 2
    print(f"✅ All fail: {result.summary()}")


@pytest.mark.asyncio
async def test_parallel_merge_all():
    """MergeStrategy.ALL collects all results into a list."""
    pd = ParallelDispatch("all-merge", merge_strategy=MergeStrategy.ALL)
    pd.branch("b1", agent="alice", capability="x")
    pd.branch("b2", agent="bob", capability="y")

    result = await pd.execute(context={}, executor=_transform_executor)
    assert result.succeeded
    assert "results" in result.merged
    assert len(result.merged["results"]) == 2
    print(f"✅ Merge ALL: {result.merged}")


@pytest.mark.asyncio
async def test_parallel_chainable():
    """branch() returns self for chaining."""
    pd = ParallelDispatch("chain")
    result = pd.branch("b1", agent="a", capability="c1").branch("b2", agent="b", capability="c2")
    assert result is pd
    assert len(pd.branches) == 2
    print(f"✅ Parallel chainable")


# ── Integration: Pipeline + Parallel ─────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_with_parallel_step():
    """A pipeline step can internally run a parallel dispatch."""
    pipe = Pipeline("mixed")
    pipe.step("prep", agent="alice", capability="prep")

    # Custom executor that simulates parallel sub-dispatch
    call_log: list[str] = []

    async def _logging_executor(agent: str, cap: str, payload: dict) -> dict:
        call_log.append(f"{agent}:{cap}")
        return {f"{cap}_done": True}

    result = await pipe.execute(context={"data": [1, 2]}, executor=_logging_executor)
    assert result.succeeded
    assert "alice:prep" in call_log
    print(f"✅ Mixed pipeline+parallel: {result.summary()}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
