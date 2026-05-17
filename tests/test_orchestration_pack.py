"""Tests for the orchestration capability pack."""

import asyncio
import pytest

from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import (
    load_orchestration_pack,
    load_text_pack,
    load_math_pack,
)


@pytest.fixture
def builder():
    b = CapabilityBuilder(None)
    load_text_pack(b)
    load_math_pack(b)
    load_orchestration_pack(b)
    return b


def _run(coro):
    return asyncio.run(coro)


class TestOrchSequence:
    def test_empty_steps(self, builder):
        result = _run(builder.invoke("orch-sequence", {"steps": []}))
        assert result.output["ok"] is False

    def test_single_step(self, builder):
        result = _run(builder.invoke("orch-sequence", {
            "steps": [{"capability": "math-arithmetic", "input": {"a": 2, "b": 3, "op": "add"}}],
        }))
        assert result.ok is True
        assert result.output["steps_completed"] == 1

    def test_multi_step(self, builder):
        result = _run(builder.invoke("orch-sequence", {
            "steps": [
                {"capability": "math-arithmetic", "input": {"a": 10, "b": 5, "op": "add"}},
                {"capability": "text-keywords", "input": {"text": "hello world example", "top_n": 3}},
            ],
        }))
        assert result.ok is True
        assert result.output["steps_completed"] == 2

    def test_halts_on_error(self, builder):
        result = _run(builder.invoke("orch-sequence", {
            "steps": [
                {"capability": "math-arithmetic", "input": {"a": 1, "b": 2, "op": "add"}},
                {"capability": "nonexistent-cap", "input": {}},
                {"capability": "math-arithmetic", "input": {"a": 3, "b": 4, "op": "add"}},
            ],
        }))
        assert result.output["ok"] is False
        assert result.output["failed_step"] == 1


class TestOrchParallel:
    def test_empty_branches(self, builder):
        result = _run(builder.invoke("orch-parallel", {"branches": []}))
        assert result.output["ok"] is False

    def test_parallel_execution(self, builder):
        result = _run(builder.invoke("orch-parallel", {
            "branches": [
                {"capability": "math-arithmetic", "input": {"a": 1, "b": 2, "op": "add"}},
                {"capability": "math-statistics", "input": {"values": [10, 20, 30]}},
            ],
        }))
        assert result.ok is True
        assert result.output["branches_completed"] == 2


class TestOrchRetry:
    def test_succeeds_immediately(self, builder):
        result = _run(builder.invoke("orch-retry", {
            "capability": "math-arithmetic",
            "input": {"a": 5, "b": 3, "op": "add"},
            "max_retries": 3,
        }))
        assert result.ok is True
        assert result.output["attempts"] == 1

    def test_unknown_capability(self, builder):
        result = _run(builder.invoke("orch-retry", {
            "capability": "no-such-cap",
            "input": {},
            "max_retries": 2,
        }))
        assert result.output["ok"] is False


class TestOrchConditional:
    def test_eq_branch_then(self, builder):
        result = _run(builder.invoke("orch-conditional", {
            "condition": {"field": "x", "op": "eq", "value": 42},
            "context": {"x": 42},
            "then": {"capability": "math-arithmetic", "input": {"a": 1, "b": 1, "op": "add"}},
            "else": {"capability": "math-arithmetic", "input": {"a": 9, "b": 9, "op": "add"}},
        }))
        assert result.ok is True
        assert result.output["condition_met"] is True
        assert result.output["branch"] == "then"

    def test_eq_branch_else(self, builder):
        result = _run(builder.invoke("orch-conditional", {
            "condition": {"field": "x", "op": "eq", "value": 99},
            "context": {"x": 1},
            "then": {"capability": "math-arithmetic", "input": {"a": 1, "b": 1, "op": "add"}},
            "else": {"capability": "math-arithmetic", "input": {"a": 2, "b": 2, "op": "add"}},
        }))
        assert result.output["condition_met"] is False
        assert result.output["branch"] == "else"

    def test_exists_check(self, builder):
        result = _run(builder.invoke("orch-conditional", {
            "condition": {"field": "data", "op": "exists"},
            "context": {"data": "yes"},
        }))
        assert result.output["condition_met"] is True

    def test_no_branch_step(self, builder):
        result = _run(builder.invoke("orch-conditional", {
            "condition": {"field": "x", "op": "gt", "value": 5},
            "context": {"x": 3},
        }))
        assert result.ok is True
        assert result.output["branch"] == "else"

    def test_gt_lt_operators(self, builder):
        r1 = _run(builder.invoke("orch-conditional", {
            "condition": {"field": "v", "op": "gt", "value": 10},
            "context": {"v": 15},
        }))
        assert r1.output["condition_met"] is True

        r2 = _run(builder.invoke("orch-conditional", {
            "condition": {"field": "v", "op": "lt", "value": 10},
            "context": {"v": 5},
        }))
        assert r2.output["condition_met"] is True

    def test_contains_operator(self, builder):
        result = _run(builder.invoke("orch-conditional", {
            "condition": {"field": "msg", "op": "contains", "value": "hello"},
            "context": {"msg": "say hello world"},
        }))
        assert result.output["condition_met"] is True


class TestOrchPipeline:
    def test_empty_steps(self, builder):
        result = _run(builder.invoke("orch-pipeline", {"steps": []}))
        assert result.output["ok"] is False

    def test_pipeline_chaining(self, builder):
        result = _run(builder.invoke("orch-pipeline", {
            "steps": [
                {"capability": "math-arithmetic", "input": {"a": 100, "b": 200, "op": "add"}},
                {"capability": "text-keywords", "input": {"text": "pipeline test words", "top_n": 3}},
            ],
        }))
        assert result.ok is True
        assert result.output["steps_completed"] == 2
        assert "output" in result.output

    def test_pipeline_stops_on_unknown(self, builder):
        result = _run(builder.invoke("orch-pipeline", {
            "steps": [
                {"capability": "math-arithmetic", "input": {"a": 1, "b": 2, "op": "add"}},
                {"capability": "bogus", "input": {}},
            ],
        }))
        assert result.output["ok"] is False
        assert result.output["failed_step"] == 1
