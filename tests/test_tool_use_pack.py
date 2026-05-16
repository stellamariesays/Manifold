"""Tests for the tool-use capability pack."""

import pytest

from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_tool_use_pack, _tool_registry


@pytest.fixture
def builder():
    b = CapabilityBuilder(None)
    load_tool_use_pack(b)
    return b


@pytest.fixture(autouse=True)
def clear_registry():
    _tool_registry.clear()
    yield
    _tool_registry.clear()


# ─── describe ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_describe_and_list(builder):
    res = await builder.invoke("tool-describe", {
        "name": "web-search",
        "description": "Search the web for information",
        "inputs": ["query"],
        "outputs": ["results"],
        "tags": ["web", "search"],
    })
    assert res.ok
    assert res.output["tool"] == "web-search"

    res = await builder.invoke("tool-list", {})
    assert res.ok
    assert res.output["count"] == 1
    assert res.output["tools"][0]["name"] == "web-search"


@pytest.mark.asyncio
async def test_describe_no_name(builder):
    res = await builder.invoke("tool-describe", {"description": "oops"})
    assert not res.ok  # builder rejects missing required 'name' input
    assert "name" in (res.error or "")


# ─── list with tag filter ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tag_filter(builder):
    await builder.invoke("tool-describe", {
        "name": "a", "description": "a", "tags": ["alpha"],
    })
    await builder.invoke("tool-describe", {
        "name": "b", "description": "b", "tags": ["beta"],
    })
    res = await builder.invoke("tool-list", {"tag": "alpha"})
    assert res.ok
    assert res.output["count"] == 1
    assert res.output["tools"][0]["name"] == "a"


# ─── select ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_select_best_tool(builder):
    await builder.invoke("tool-describe", {
        "name": "web-search",
        "description": "Search the web for information",
        "tags": ["web", "search"],
    })
    await builder.invoke("tool-describe", {
        "name": "calculator",
        "description": "Perform arithmetic calculations",
        "tags": ["math", "compute"],
    })
    res = await builder.invoke("tool-select", {"task": "find information on the web"})
    assert res.ok
    assert res.output["tool"]["name"] == "web-search"


@pytest.mark.asyncio
async def test_select_no_match(builder):
    await builder.invoke("tool-describe", {
        "name": "calc", "description": "math stuff", "tags": ["math"],
    })
    res = await builder.invoke("tool-select", {"task": "xyzzy quantum platypus"})
    assert res.ok  # handler ran
    assert not res.output.get("ok", True)  # but no suitable tool found


@pytest.mark.asyncio
async def test_select_empty_registry(builder):
    res = await builder.invoke("tool-select", {"task": "something"})
    assert res.ok
    assert not res.output.get("ok", True)


# ─── chain ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chain_valid(builder):
    await builder.invoke("tool-describe", {
        "name": "fetch", "description": "fetch data",
        "inputs": ["url"], "outputs": ["raw_data"], "tags": ["io"],
    })
    await builder.invoke("tool-describe", {
        "name": "parse", "description": "parse raw data",
        "inputs": ["raw_data"], "outputs": ["structured"], "tags": ["transform"],
    })
    res = await builder.invoke("tool-chain", {"steps": ["fetch", "parse"]})
    assert res.ok
    assert res.output["valid"] is True
    assert len(res.output["chain"]) == 2


@pytest.mark.asyncio
async def test_chain_unknown_tool(builder):
    res = await builder.invoke("tool-chain", {"steps": ["nonexistent"]})
    assert res.ok
    assert not res.output.get("ok", True)


@pytest.mark.asyncio
async def test_chain_too_short(builder):
    res = await builder.invoke("tool-chain", {"steps": ["one"]})
    assert res.ok
    assert not res.output.get("ok", True)


@pytest.mark.asyncio
async def test_chain_compat_issue(builder):
    await builder.invoke("tool-describe", {
        "name": "a", "description": "a",
        "inputs": [], "outputs": ["x"], "tags": [],
    })
    await builder.invoke("tool-describe", {
        "name": "b", "description": "b",
        "inputs": ["y"], "outputs": [], "tags": [],
    })
    res = await builder.invoke("tool-chain", {"steps": ["a", "b"]})
    assert res.ok
    assert not res.output["valid"]
    assert len(res.output["compatibility_issues"]) == 1


# ─── validate ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_good(builder):
    await builder.invoke("tool-describe", {
        "name": "search", "description": "search",
        "inputs": ["query", "limit"], "outputs": ["results"], "tags": [],
    })
    res = await builder.invoke("tool-validate", {
        "name": "search", "inputs": {"query": "test", "limit": 10},
    })
    assert res.ok
    assert res.output["valid"] is True
    assert res.output["missing"] == []


@pytest.mark.asyncio
async def test_validate_missing_inputs(builder):
    await builder.invoke("tool-describe", {
        "name": "search", "description": "search",
        "inputs": ["query", "limit"], "outputs": ["results"], "tags": [],
    })
    res = await builder.invoke("tool-validate", {
        "name": "search", "inputs": {"query": "test"},
    })
    assert res.ok
    assert not res.output["valid"]
    assert "limit" in res.output["missing"]


@pytest.mark.asyncio
async def test_validate_unknown_tool(builder):
    res = await builder.invoke("tool-validate", {"name": "ghost", "inputs": {}})
    assert res.ok
    assert not res.output.get("ok", True)
