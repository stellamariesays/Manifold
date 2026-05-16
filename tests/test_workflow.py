"""Tests for the workflow engine — DAG orchestration with retries, conditions, compensation."""

import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manifold.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowStatus,
    StepExecutionStatus,
    StepRetryPolicy,
    WorkflowResult,
)


# ─── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def simple_wf():
    """Linear 3-step workflow."""
    wf = Workflow("simple")

    @wf.step("a")
    async def a(ctx):
        return {"value": ctx.get("x", 1) * 2}

    @wf.step("b", depends_on=["a"])
    async def b(ctx):
        return {"value": ctx["a"]["value"] + 10}

    @wf.step("c", depends_on=["b"])
    async def c(ctx):
        return {"value": ctx["b"]["value"] * 3}

    return wf


@pytest.fixture
def dag_wf():
    """Diamond DAG: entry -> [left, right] -> merge."""
    wf = Workflow("diamond")

    @wf.step("entry")
    async def entry(ctx):
        return {"data": [1, 2, 3]}

    @wf.step("left", depends_on=["entry"])
    async def left(ctx):
        return {"sum": sum(ctx["entry"]["data"])}

    @wf.step("right", depends_on=["entry"])
    async def right(ctx):
        return {"count": len(ctx["entry"]["data"])}

    @wf.step("merge", depends_on=["left", "right"])
    async def merge(ctx):
        return {"mean": ctx["left"]["sum"] / ctx["right"]["count"]}

    return wf


# ─── Basic Execution ────────────────────────────────────────────────────

class TestBasicWorkflow:
    def test_empty_workflow(self):
        wf = Workflow("empty")
        # Empty workflow should still validate with a warning
        issues = wf.validate()
        assert len(issues) > 0

    @pytest.mark.asyncio
    async def test_single_step(self):
        wf = Workflow("single")

        @wf.step("go")
        async def go(ctx):
            return {"ok": True}

        result = await wf.run()
        assert result.ok
        assert result.steps["go"].status == StepExecutionStatus.COMPLETED
        assert result.steps["go"].output == {"ok": True}

    @pytest.mark.asyncio
    async def test_linear_chain(self, simple_wf):
        result = await simple_wf.run({"x": 5})
        assert result.ok
        assert result.steps["a"].output["value"] == 10
        assert result.steps["b"].output["value"] == 20
        assert result.steps["c"].output["value"] == 60

    @pytest.mark.asyncio
    async def test_diamond_dag(self, dag_wf):
        result = await dag_wf.run()
        assert result.ok
        assert result.steps["entry"].status == StepExecutionStatus.COMPLETED
        assert result.steps["left"].output["sum"] == 6
        assert result.steps["right"].output["count"] == 3
        assert result.steps["merge"].output["mean"] == 2.0

    @pytest.mark.asyncio
    async def test_context_flows_through(self):
        wf = Workflow("ctx-flow")

        @wf.step("first")
        async def first(ctx):
            return {"name": "test"}

        @wf.step("second", depends_on=["first"])
        async def second(ctx):
            # Should have access to both payload and step outputs
            return {
                "got_name": ctx["first"]["name"],
                "got_payload": ctx.get("initial", None),
            }

        result = await wf.run({"initial": "hello"})
        assert result.ok
        assert result.steps["second"].output["got_name"] == "test"
        assert result.steps["second"].output["got_payload"] == "hello"


# ─── Failure & Retry ───────────────────────────────────────────────────

class TestFailureAndRetry:
    @pytest.mark.asyncio
    async def test_step_failure_stops_workflow(self):
        wf = Workflow("fail-stop")
        call_count = {"n": 0}

        @wf.step("a")
        async def a(ctx):
            return {"ok": True}

        @wf.step("b", depends_on=["a"])
        async def b(ctx):
            raise ValueError("boom")

        @wf.step("c", depends_on=["b"])
        async def c(ctx):
            return {"ok": True}

        result = await wf.run()
        assert result.status == WorkflowStatus.FAILED
        assert result.steps["b"].status == StepExecutionStatus.FAILED
        assert result.steps["c"].status == StepExecutionStatus.SKIPPED
        assert result.failed_step == "b"

    @pytest.mark.asyncio
    async def test_retry_succeeds(self):
        wf = Workflow("retry-ok")
        attempts = {"n": 0}

        @wf.step("flaky", retries=3)
        async def flaky(ctx):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("not yet")
            return {"finally": True}

        result = await wf.run()
        assert result.ok
        assert result.steps["flaky"].attempts == 3
        assert result.steps["flaky"].output["finally"] is True

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        wf = Workflow("retry-fail")

        @wf.step("always-fail", retries=2)
        async def always_fail(ctx):
            raise RuntimeError("nope")

        result = await wf.run()
        assert result.status == WorkflowStatus.FAILED
        assert result.steps["always-fail"].attempts == 3  # 1 initial + 2 retries
        assert "nope" in result.steps["always-fail"].error

    @pytest.mark.asyncio
    async def test_continue_on_failure(self):
        wf = Workflow("continue-on-fail")

        @wf.step("a")
        async def a(ctx):
            raise ValueError("fail")

        @wf.step("b", depends_on=["a"])
        async def b(ctx):
            return {"ok": True}

        result = await wf.run(stop_on_failure=False)
        assert result.status == WorkflowStatus.FAILED
        # b should be skipped because its dependency a failed
        assert result.steps["b"].status == StepExecutionStatus.SKIPPED


# ─── Conditions ─────────────────────────────────────────────────────────

class TestConditions:
    @pytest.mark.asyncio
    async def test_conditional_step_runs(self):
        wf = Workflow("conditional")

        @wf.step("check")
        async def check(ctx):
            return {"flag": True}

        @wf.step("branch-yes", depends_on=["check"],
                 condition=lambda ctx: ctx.get("check", {}).get("flag") is True)
        async def branch_yes(ctx):
            return {"ran": "yes"}

        @wf.step("branch-no", depends_on=["check"],
                 condition=lambda ctx: ctx.get("check", {}).get("flag") is False)
        async def branch_no(ctx):
            return {"ran": "no"}

        result = await wf.run()
        assert result.ok
        assert result.steps["branch-yes"].status == StepExecutionStatus.COMPLETED
        assert result.steps["branch-no"].status == StepExecutionStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_conditional_step_skipped(self):
        wf = Workflow("cond-skip")

        @wf.step("a")
        async def a(ctx):
            return {"run_b": False}

        @wf.step("b", depends_on=["a"],
                 condition=lambda ctx: ctx["a"].get("run_b", False))
        async def b(ctx):
            return {"should_not_run": True}

        result = await wf.run()
        assert result.ok
        assert result.steps["b"].status == StepExecutionStatus.SKIPPED


# ─── Compensation ───────────────────────────────────────────────────────

class TestCompensation:
    @pytest.mark.asyncio
    async def test_compensation_runs_on_failure(self):
        compensated = []

        wf = Workflow("compensate")

        @wf.step("a")
        async def a(ctx):
            return {"id": 42}

        @wf.step("b", depends_on=["a"])
        async def b(ctx):
            raise RuntimeError("fail after a")

        # Add compensation manually
        async def undo_a(output):
            compensated.append(output["id"])

        wf._steps["a"].compensate = undo_a

        result = await wf.run()
        assert result.status == WorkflowStatus.FAILED

        await wf.compensate(result)
        assert 42 in compensated
        assert result.steps["a"].status == StepExecutionStatus.COMPENSATED

    @pytest.mark.asyncio
    async def test_compensation_reverse_order(self):
        order = []

        wf = Workflow("undo-order")

        @wf.step("first")
        async def first(ctx):
            return {"n": 1}

        @wf.step("second", depends_on=["first"])
        async def second(ctx):
            return {"n": 2}

        @wf.step("third", depends_on=["second"])
        async def third(ctx):
            raise RuntimeError("fail")

        async def undo_first(out):
            order.append(f"undo-{out['n']}")

        async def undo_second(out):
            order.append(f"undo-{out['n']}")

        wf._steps["first"].compensate = undo_first
        wf._steps["second"].compensate = undo_second

        result = await wf.run()
        await wf.compensate(result)
        # Should undo in reverse: second, then first
        assert order == ["undo-2", "undo-1"]


# ─── Validation ─────────────────────────────────────────────────────────

class TestValidation:
    def test_valid_workflow(self, simple_wf):
        issues = simple_wf.validate()
        assert issues == []

    def test_unknown_dependency(self):
        wf = Workflow("bad-dep")

        @wf.step("a", depends_on=["nonexistent"])
        async def a(ctx):
            return {}

        issues = wf.validate()
        assert len(issues) > 0
        assert any("nonexistent" in i for i in issues)

    def test_duplicate_step_name(self):
        wf = Workflow("dup")

        @wf.step("a")
        async def a1(ctx):
            return {}

        with pytest.raises(ValueError, match="Duplicate"):
            @wf.step("a")
            async def a2(ctx):
                return {}


# ─── Observability ──────────────────────────────────────────────────────

class TestObservability:
    @pytest.mark.asyncio
    async def test_timing(self, simple_wf):
        result = await simple_wf.run({"x": 1})
        assert result.elapsed_ms > 0
        assert result.started_at is not None
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_summary(self, simple_wf):
        result = await simple_wf.run({"x": 1})
        s = result.summary()
        assert "simple" in s
        assert "completed" in s

    @pytest.mark.asyncio
    async def test_dag_summary(self, simple_wf):
        s = simple_wf.dag_summary()
        assert "simple" in s
        assert "a" in s
        assert "b" in s
        assert "c" in s

    @pytest.mark.asyncio
    async def test_list_steps_in_order(self, dag_wf):
        steps = dag_wf.list_steps()
        names = [s.name for s in steps]
        assert names.index("entry") < names.index("left")
        assert names.index("entry") < names.index("right")
        assert names.index("left") < names.index("merge")
        assert names.index("right") < names.index("merge")

    @pytest.mark.asyncio
    async def test_repr(self, simple_wf):
        assert "simple" in repr(simple_wf)
        assert "steps=3" in repr(simple_wf)


# ─── Imperative API ─────────────────────────────────────────────────────

class TestImperativeAPI:
    @pytest.mark.asyncio
    async def test_add_step_imperative(self):
        wf = Workflow("imperative")

        async def handler(ctx):
            return {"result": ctx.get("x", 0) + 1}

        wf.add_step("inc", handler)
        result = await wf.run({"x": 9})
        assert result.ok
        assert result.steps["inc"].output["result"] == 10

    @pytest.mark.asyncio
    async def test_add_step_with_deps(self):
        wf = Workflow("deps")
        call_order = []

        async def step_a(ctx):
            call_order.append("a")
            return {"val": "A"}

        async def step_b(ctx):
            call_order.append("b")
            return {"val": "B"}

        wf.add_step("a", step_a)
        wf.add_step("b", step_b, depends_on=["a"])

        result = await wf.run()
        assert result.ok
        assert call_order == ["a", "b"]


# ─── Edge Cases ─────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_handler_returns_non_dict(self):
        wf = Workflow("non-dict")

        @wf.step("a")
        async def a(ctx):
            return 42  # not a dict

        result = await wf.run()
        assert result.ok
        assert result.steps["a"].output == {"value": 42}

    @pytest.mark.asyncio
    async def test_large_dag(self):
        """Stress test with a 20-step linear chain."""
        wf = Workflow("large")

        prev = None
        for i in range(20):
            deps = [prev] if prev else []
            name = f"step-{i}"

            async def handler(ctx, _i=i):
                return {"i": _i}

            wf.add_step(name, handler, depends_on=deps)
            prev = name

        result = await wf.run()
        assert result.ok
        assert len(result.steps) == 20

    @pytest.mark.asyncio
    async def test_fan_out_fan_in(self):
        """Entry fans out to 5 parallel steps, then merges."""
        wf = Workflow("fan")
        results = {}

        @wf.step("source")
        async def source(ctx):
            return {"values": [10, 20, 30, 40, 50]}

        for i in range(5):

            @wf.step(f"worker-{i}", depends_on=["source"])
            async def worker(ctx, _i=i):
                val = ctx["source"]["values"][_i]
                return {"doubled": val * 2}

        @wf.step("collect", depends_on=[f"worker-{i}" for i in range(5)])
        async def collect(ctx):
            total = sum(ctx[f"worker-{i}"]["doubled"] for i in range(5))
            return {"total": total}

        result = await wf.run()
        assert result.ok
        assert result.steps["collect"].output["total"] == 300
