"""Tests for the memory capability pack."""

import time

import pytest

from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_memory_pack, _memory_kv_store


@pytest.fixture
def builder():
    b = CapabilityBuilder(None)
    load_memory_pack(b)
    return b


@pytest.fixture(autouse=True)
def clear_store():
    _memory_kv_store.clear()
    yield
    _memory_kv_store.clear()


# ─── store / retrieve ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_store_and_retrieve(builder):
    res = await builder.invoke("memory-store", {"key": "foo", "value": "bar"})
    assert res.ok
    assert res.output["ok"] is True
    res = await builder.invoke("memory-retrieve", {"key": "foo"})
    assert res.ok
    assert res.output["value"] == "bar"


@pytest.mark.asyncio
async def test_store_no_key(builder):
    res = await builder.invoke("memory-store", {"value": "x"})
    assert not res.ok
    assert "key" in (res.error or "")


@pytest.mark.asyncio
async def test_store_with_tags(builder):
    await builder.invoke("memory-store", {"key": "k1", "value": 42, "tags": ["num", "answer"]})
    res = await builder.invoke("memory-retrieve", {"key": "k1"})
    assert res.output["tags"] == ["num", "answer"]


@pytest.mark.asyncio
async def test_retrieve_missing(builder):
    res = await builder.invoke("memory-retrieve", {"key": "nope"})
    assert res.ok  # handler succeeded
    assert res.output["ok"] is False
    assert res.output["error"] == "not_found"


# ─── TTL ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ttl_not_expired(builder):
    await builder.invoke("memory-store", {"key": "ttl1", "value": "v", "ttl": 60})
    res = await builder.invoke("memory-retrieve", {"key": "ttl1"})
    assert res.output["ok"] is True


@pytest.mark.asyncio
async def test_ttl_expired(builder):
    await builder.invoke("memory-store", {"key": "ttl2", "value": "v", "ttl": 0.01})
    time.sleep(0.02)
    res = await builder.invoke("memory-retrieve", {"key": "ttl2"})
    assert res.output["ok"] is False
    assert res.output["error"] == "expired"


# ─── search ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_by_tag(builder):
    await builder.invoke("memory-store", {"key": "a", "value": "1", "tags": ["x"]})
    await builder.invoke("memory-store", {"key": "b", "value": "2", "tags": ["y"]})
    await builder.invoke("memory-store", {"key": "c", "value": "3", "tags": ["x"]})
    res = await builder.invoke("memory-search", {"tag": "x"})
    assert res.output["count"] == 2


@pytest.mark.asyncio
async def test_search_by_prefix(builder):
    await builder.invoke("memory-store", {"key": "user:1", "value": "alice"})
    await builder.invoke("memory-store", {"key": "user:2", "value": "bob"})
    await builder.invoke("memory-store", {"key": "order:1", "value": "widget"})
    res = await builder.invoke("memory-search", {"prefix": "user:"})
    assert res.output["count"] == 2


@pytest.mark.asyncio
async def test_search_by_query(builder):
    await builder.invoke("memory-store", {"key": "k1", "value": "Hello World"})
    await builder.invoke("memory-store", {"key": "k2", "value": "hello moon"})
    res = await builder.invoke("memory-search", {"query": "world"})
    assert res.output["count"] == 1


@pytest.mark.asyncio
async def test_search_limit(builder):
    for i in range(10):
        await builder.invoke("memory-store", {"key": f"item{i}", "value": i, "tags": ["batch"]})
    res = await builder.invoke("memory-search", {"tag": "batch", "limit": 3})
    assert res.output["count"] == 3


# ─── summarize ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summarize_empty(builder):
    res = await builder.invoke("memory-summarize", {})
    assert res.output["total_entries"] == 0


@pytest.mark.asyncio
async def test_summarize_with_data(builder):
    await builder.invoke("memory-store", {"key": "a", "value": 1, "tags": ["x"]})
    await builder.invoke("memory-store", {"key": "b", "value": 2, "tags": ["x", "y"]})
    res = await builder.invoke("memory-summarize", {})
    assert res.output["total_entries"] == 2
    assert res.output["tag_distribution"]["x"] == 2
    assert res.output["tag_distribution"]["y"] == 1
    assert res.output["oldest_created_at"] is not None


# ─── forget ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forget_by_key(builder):
    await builder.invoke("memory-store", {"key": "gone", "value": "bye"})
    res = await builder.invoke("memory-forget", {"key": "gone"})
    assert res.output["removed"] == 1
    res = await builder.invoke("memory-retrieve", {"key": "gone"})
    assert res.output["ok"] is False


@pytest.mark.asyncio
async def test_forget_by_tag(builder):
    await builder.invoke("memory-store", {"key": "a", "value": 1, "tags": ["temp"]})
    await builder.invoke("memory-store", {"key": "b", "value": 2, "tags": ["keep"]})
    await builder.invoke("memory-store", {"key": "c", "value": 3, "tags": ["temp"]})
    res = await builder.invoke("memory-forget", {"tag": "temp"})
    assert res.output["removed"] == 2


@pytest.mark.asyncio
async def test_forget_missing_key(builder):
    res = await builder.invoke("memory-forget", {"key": "ghost"})
    assert res.output["removed"] == 0


@pytest.mark.asyncio
async def test_forget_no_args(builder):
    res = await builder.invoke("memory-forget", {})
    assert res.output["ok"] is False
