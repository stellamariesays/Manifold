"""Tests for capability pipelines."""

import asyncio
import pytest
from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.pipeline import (
    Pipeline,
    PipelineBuilder,
    PipelineResult,
    PipelineStatus,
    StepResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_builder() -> tuple[Agent, CapabilityBuilder]:
    agent = Agent(name="test-pipeline-agent")
    builder = CapabilityBuilder(agent)

    @builder.define(
        name="extract",
        inputs=["raw_text"],
        outputs=["tokens", "count"],
    )
    async def extract(payload: dict) -> dict:
        text = payload.get("raw_text", "")
        tokens = text.split()
        return {"tokens": tokens, "count": len(tokens)}

    @builder.define(
        name="analyze",
        inputs=["tokens"],
        outputs=["sentiment", "score"],
    )
    async def analyze(payload: dict) -> dict:
        tokens = payload.get("tokens", [])
        score = len(tokens) * 0.1
        return {"sentiment": "positive" if score > 0.5 else "negative", "score": score}

    @builder.define(
        name="format-report",
        inputs=["sentiment", "score", "count"],
        outputs=["report"],
    )
    async def format_report(payload: dict) -> dict:
        return {
            "report": (
                f"Sentiment: {payload.get('sentiment')}, "
                f"Score: {payload.get('score', 0):.1f}, "
                f"Token count: {payload.get('count', 0)}"
            )
        }

    @builder.define(
        name="failing-cap",
        inputs=["data"],
        outputs=["result"],
    )
    async def failing_cap(payload: dict) -> dict:
        raise ValueError("intentional failure for testing")

    return agent, builder


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simple_two_step_pipeline():
    """Two steps: extract → analyze, with input mapping."""
    _, builder = _make_builder()

    pipeline = (
        PipelineBuilder(builder)
        .create("extract-analyze")
        .step("extract", name="tokenize")
        .step("analyze", name="sentiment", map_inputs={"tokens": "tokens"})
        .build()
    )

    result = await pipeline.run({"raw_text": "hello world foo"})

    assert result.succeeded
    assert len(result.steps) == 2
    assert result.steps[0].ok
    assert result.steps[1].ok
    assert result.output["sentiment"] == "negative"
    assert result.output["score"] == pytest.approx(0.3)
    assert result.elapsed_ms > 0


@pytest.mark.asyncio
async def test_three_step_pipeline_with_mapping():
    """Three steps: extract → analyze → format, with selective mapping."""
    _, builder = _make_builder()

    pipeline = (
        PipelineBuilder(builder)
        .create("full-report")
        .step("extract", name="tokenize")
        .step("analyze", name="sentiment", map_inputs={"tokens": "tokens"})
        .step(
            "format-report",
            name="report",
            map_inputs={"sentiment": "sentiment", "score": "score"},
            # count is already in the merged payload from step 1
        )
        .build()
    )

    result = await pipeline.run({"raw_text": "great wonderful amazing fantastic excellent brilliant"})

    assert result.succeeded
    assert "report" in result.output
    assert "Sentiment" in result.output["report"]


@pytest.mark.asyncio
async def test_pipeline_failure_stops_execution():
    """A failing step (non-optional) stops the pipeline."""
    _, builder = _make_builder()

    pipeline = (
        PipelineBuilder(builder)
        .create("will-fail")
        .step("failing-cap", name="boom")
        .step("extract", name="wont-reach")
        .build()
    )

    result = await pipeline.run({"data": "test"})

    assert result.status == PipelineStatus.FAILED
    assert result.error is not None
    assert "boom" in result.error
    assert len(result.steps) == 1  # second step never ran
    assert result.output == {}


@pytest.mark.asyncio
async def test_optional_step_failure_continues():
    """An optional step failure doesn't stop the pipeline."""
    _, builder = _make_builder()

    pipeline = (
        PipelineBuilder(builder)
        .create("optional-fail")
        .step("extract", name="tokenize")
        .step("failing-cap", name="optional-boom", optional=True)
        .step("analyze", name="sentiment", map_inputs={"tokens": "tokens"})
        .build()
    )

    result = await pipeline.run({"raw_text": "hello world"})

    assert result.status == PipelineStatus.PARTIAL
    assert result.steps[1].ok is False
    assert result.steps[2].ok is True  # continued past failure
    assert result.output["sentiment"] == "negative"  # 2 tokens × 0.1 = 0.2 < 0.5


@pytest.mark.asyncio
async def test_defaults_applied():
    """Defaults fill in missing input values."""
    _, builder = _make_builder()

    pipeline = (
        PipelineBuilder(builder)
        .create("with-defaults")
        .step("extract", name="tokenize", defaults={"raw_text": "default words here"})
        .build()
    )

    result = await pipeline.run({})  # no raw_text provided

    assert result.succeeded
    assert result.steps[0].output["count"] == 3


@pytest.mark.asyncio
async def test_pipeline_stats():
    """Stats track run count and timing."""
    _, builder = _make_builder()

    pipeline = (
        PipelineBuilder(builder)
        .create("stats-test")
        .step("extract", name="tokenize")
        .build()
    )

    assert pipeline.stats()["run_count"] == 0

    await pipeline.run({"raw_text": "hello"})
    await pipeline.run({"raw_text": "world"})

    stats = pipeline.stats()
    assert stats["run_count"] == 2
    assert stats["steps"] == 1
    assert stats["avg_elapsed_ms"] >= 0  # may be 0 for very fast handlers


@pytest.mark.asyncio
async def test_empty_pipeline_raises():
    """Building a pipeline with no steps raises ValueError."""
    _, builder = _make_builder()

    with pytest.raises(ValueError, match="at least one step"):
        PipelineBuilder(builder).create("empty").build()


@pytest.mark.asyncio
async def test_passthrough_without_mapping():
    """Without map_inputs, full previous output is passed to next step."""
    _, builder = _make_builder()

    pipeline = (
        PipelineBuilder(builder)
        .create("passthrough")
        .step("extract", name="step1")
        .step("analyze", name="step2")  # gets full output of extract
        .build()
    )

    result = await pipeline.run({"raw_text": "one two"})

    assert result.succeeded
    # analyze got tokens from extract's output
    assert result.output["sentiment"] is not None


def test_pipeline_repr():
    """PipelineResult and StepResult have useful reprs."""
    sr = StepResult(step_name="test", capability="cap", ok=True, elapsed_ms=42)
    assert "test" in repr(sr)

    pr = PipelineResult(
        pipeline_name="pipe",
        run_id="r1",
        status=PipelineStatus.COMPLETED,
        steps=[sr],
        output={"x": 1},
        elapsed_ms=100,
    )
    assert "1/1" in repr(pr)
    assert pr.succeeded
    assert pr.failed_step is None


@pytest.mark.asyncio
async def test_failed_step_property():
    """failed_step returns the first failed step."""
    _, builder = _make_builder()

    pipeline = (
        PipelineBuilder(builder)
        .create("fail-prop")
        .step("failing-cap", name="bad")
        .build()
    )

    result = await pipeline.run({"data": "x"})
    assert result.failed_step is not None
    assert result.failed_step.step_name == "bad"
