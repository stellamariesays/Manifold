"""Tests for the data pipeline capability pack."""

import pytest
from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_data_pack


# ── Helpers ──────────────────────────────────────────────────────────────

def _builder():
    agent = Agent(name="data-agent", transport="memory://test")
    builder = CapabilityBuilder(agent)
    load_data_pack(builder)
    return builder


# ── Validate ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_pass():
    builder = _builder()
    result = await builder.invoke("data-validate", {
        "record": {"name": "alice", "age": 30},
        "rules": {
            "name": {"type": "str", "required": True},
            "age": {"type": "int", "required": True, "min": 0, "max": 150},
        },
    })
    assert result.output["valid"] is True
    assert result.output["errors"] == []


@pytest.mark.asyncio
async def test_validate_missing_required():
    builder = _builder()
    result = await builder.invoke("data-validate", {
        "record": {},
        "rules": {"name": {"required": True}},
    })
    assert result.output["valid"] is False
    assert any("required" in e for e in result.output["errors"])


@pytest.mark.asyncio
async def test_validate_type_mismatch():
    builder = _builder()
    result = await builder.invoke("data-validate", {
        "record": {"age": "thirty"},
        "rules": {"age": {"type": "int", "required": True}},
    })
    assert result.output["valid"] is False


@pytest.mark.asyncio
async def test_validate_range():
    builder = _builder()
    result = await builder.invoke("data-validate", {
        "record": {"score": 200},
        "rules": {"score": {"type": "int", "min": 0, "max": 100}},
    })
    assert result.output["valid"] is False


@pytest.mark.asyncio
async def test_validate_enum():
    builder = _builder()
    result = await builder.invoke("data-validate", {
        "record": {"status": "pending"},
        "rules": {"status": {"enum": ["active", "inactive"]}},
    })
    assert result.output["valid"] is False


# ── Transform ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transform_rename():
    builder = _builder()
    result = await builder.invoke("data-transform", {
        "records": [{"old_name": "alice"}],
        "operations": [{"type": "rename", "from": "old_name", "to": "name"}],
    })
    assert result.output["records"][0]["name"] == "alice"
    assert "old_name" not in result.output["records"][0]


@pytest.mark.asyncio
async def test_transform_filter():
    builder = _builder()
    result = await builder.invoke("data-transform", {
        "records": [{"v": 1}, {"v": 2}, {"v": 3}],
        "operations": [{"type": "filter", "field": "v", "op": "gt", "value": 1}],
    })
    assert result.output["count"] == 2


@pytest.mark.asyncio
async def test_transform_select():
    builder = _builder()
    result = await builder.invoke("data-transform", {
        "records": [{"a": 1, "b": 2, "c": 3}],
        "operations": [{"type": "select", "fields": ["a", "b"]}],
    })
    assert set(result.output["records"][0].keys()) == {"a", "b"}


@pytest.mark.asyncio
async def test_transform_sort():
    builder = _builder()
    result = await builder.invoke("data-transform", {
        "records": [{"v": 3}, {"v": 1}, {"v": 2}],
        "operations": [{"type": "sort", "field": "v"}],
    })
    assert [r["v"] for r in result.output["records"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_transform_single_record():
    builder = _builder()
    result = await builder.invoke("data-transform", {
        "records": {"x": 1},
        "operations": [{"type": "add_field", "name": "y", "value": 2}],
    })
    assert result.output["count"] == 1
    assert result.output["records"][0]["y"] == 2


# ── Aggregate ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregate_basic():
    builder = _builder()
    result = await builder.invoke("data-aggregate", {
        "records": [{"v": 10}, {"v": 20}, {"v": 30}],
        "field": "v",
    })
    assert result.output["ok"] is True
    assert result.output["count"] == 3
    assert result.output["sum"] == 60
    assert result.output["mean"] == 20.0
    assert result.output["min"] == 10
    assert result.output["max"] == 30


@pytest.mark.asyncio
async def test_aggregate_group_by():
    builder = _builder()
    result = await builder.invoke("data-aggregate", {
        "records": [
            {"team": "a", "score": 10},
            {"team": "a", "score": 20},
            {"team": "b", "score": 30},
        ],
        "field": "score",
        "group_by": "team",
    })
    assert result.output["ok"] is True
    assert "groups" in result.output
    assert result.output["groups"]["a"]["mean"] == 15.0
    assert result.output["groups"]["b"]["mean"] == 30.0


@pytest.mark.asyncio
async def test_aggregate_empty():
    builder = _builder()
    result = await builder.invoke("data-aggregate", {
        "records": [],
        "field": "v",
    })
    assert result.output["ok"] is False


# ── Merge ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_merge_inner():
    builder = _builder()
    result = await builder.invoke("data-merge", {
        "left": [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}],
        "right": [{"id": 1, "score": 95}, {"id": 3, "score": 80}],
        "key": "id",
    })
    assert result.output["count"] == 1
    assert result.output["records"][0]["name"] == "alice"
    assert result.output["records"][0]["score"] == 95


@pytest.mark.asyncio
async def test_merge_left():
    builder = _builder()
    result = await builder.invoke("data-merge", {
        "left": [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}],
        "right": [{"id": 1, "score": 95}],
        "key": "id",
        "how": "left",
    })
    assert result.output["count"] == 2


@pytest.mark.asyncio
async def test_merge_no_key():
    builder = _builder()
    result = await builder.invoke("data-merge", {
        "left": [{"a": 1}],
        "right": [{"b": 2}],
    })
    assert result.ok is False  # builder rejects missing required 'key' input
