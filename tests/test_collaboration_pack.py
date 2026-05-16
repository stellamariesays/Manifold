"""Tests for collaboration capability pack — multi-agent coordination primitives."""

import pytest
from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_collaboration_pack


# ── Helpers ──────────────────────────────────────────────────────────────

async def _builder_with_collab(name: str = "coordinator") -> CapabilityBuilder:
    agent = Agent(name=name, transport="memory://test")
    agent.knows(["collaboration"])
    await agent.join()
    builder = CapabilityBuilder(agent)
    load_collaboration_pack(builder, agent)
    return builder


# ─── Delegation ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delegate_returns_plan():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-delegate", {
        "target_capability": "solar-prediction",
        "inputs": {"region": "pacific"},
        "min_score": 0.2,
        "max_candidates": 3,
    })
    assert result.ok
    assert result.output["status"] == "planned"
    assert result.output["target_capability"] == "solar-prediction"
    assert result.output["candidates_requested"] == 3


# ─── Voting ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vote_majority_consensus():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-vote", {
        "proposal": "deploy-to-prod",
        "votes": [
            {"voter": "alice", "choice": "yes", "weight": 1.0},
            {"voter": "bob", "choice": "yes", "weight": 1.0},
            {"voter": "carol", "choice": "no", "weight": 1.0},
        ],
        "method": "majority",
    })
    assert result.ok
    assert result.output["winner"] == "yes"
    assert result.output["consensus"] is True
    assert result.output["vote_counts"]["yes"] == 2.0


@pytest.mark.asyncio
async def test_vote_no_consensus_when_tied():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-vote", {
        "proposal": "deploy",
        "votes": [
            {"voter": "a", "choice": "yes"},
            {"voter": "b", "choice": "no"},
        ],
        "method": "majority",
    })
    assert result.ok
    assert result.output["consensus"] is False


@pytest.mark.asyncio
async def test_vote_unanimous():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-vote", {
        "proposal": "critical",
        "votes": [
            {"voter": "a", "choice": "go"},
            {"voter": "b", "choice": "go"},
        ],
        "method": "unanimous",
    })
    assert result.ok
    assert result.output["consensus"] is True


@pytest.mark.asyncio
async def test_vote_unanimous_fails_on_split():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-vote", {
        "proposal": "critical",
        "votes": [
            {"voter": "a", "choice": "go"},
            {"voter": "b", "choice": "stop"},
        ],
        "method": "unanimous",
    })
    assert result.ok
    assert result.output["consensus"] is False


@pytest.mark.asyncio
async def test_vote_weighted():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-vote", {
        "proposal": "weighted",
        "votes": [
            {"voter": "a", "choice": "yes", "weight": 3.0},
            {"voter": "b", "choice": "no", "weight": 1.0},
            {"voter": "c", "choice": "no", "weight": 1.0},
        ],
        "method": "weighted",
    })
    assert result.ok
    assert result.output["winner"] == "yes"
    assert result.output["vote_counts"]["yes"] == 3.0
    assert result.output["consensus"] is False  # 3/5 = 0.6, not > 0.6


@pytest.mark.asyncio
async def test_vote_empty():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-vote", {
        "proposal": "empty",
        "votes": [],
        "method": "majority",
    })
    assert result.ok
    assert result.output["winner"] is None
    assert result.output["consensus"] is False
    assert result.output["total_votes"] == 0


# ─── Aggregation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregate_best():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-aggregate", {
        "results": [
            {"value": "low", "score": 0.3},
            {"value": "mid", "score": 0.6},
            {"value": "high", "score": 0.9},
        ],
        "strategy": "best",
    })
    assert result.ok
    assert result.output["count"] == 1
    assert result.output["aggregated"][0]["value"] == "high"


@pytest.mark.asyncio
async def test_aggregate_merge():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-aggregate", {
        "results": [
            {"value": "a", "score": 0.5},
            {"value": "b", "score": 0.9},
        ],
        "strategy": "merge",
    })
    assert result.ok
    assert result.output["count"] == 2
    # Sorted by score desc
    assert result.output["aggregated"][0]["value"] == "b"


@pytest.mark.asyncio
async def test_aggregate_dedupe():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-aggregate", {
        "results": [
            {"id": "1", "score": 0.5},
            {"id": "1", "score": 0.9},
            {"id": "2", "score": 0.7},
        ],
        "strategy": "dedupe",
        "key_field": "id",
    })
    assert result.ok
    assert result.output["count"] == 2
    deduped_ids = [r["id"] for r in result.output["aggregated"]]
    assert "1" in deduped_ids
    assert "2" in deduped_ids


@pytest.mark.asyncio
async def test_aggregate_empty():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-aggregate", {
        "results": [],
        "strategy": "merge",
    })
    assert result.ok
    assert result.output["count"] == 0


# ─── Fan-out ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fanout_dispatch():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-fanout", {
        "topic": "solar-check",
        "targets": ["alice", "bob", "carol"],
        "timeout_ms": 3000,
    })
    assert result.ok
    assert result.output["total"] == 3
    assert result.output["pending"] == 3
    assert len(result.output["dispatched"]) == 3
    names = [d["target"] for d in result.output["dispatched"]]
    assert "alice" in names


@pytest.mark.asyncio
async def test_fanout_empty_targets():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-fanout", {
        "topic": "nothing",
        "targets": [],
    })
    assert result.ok
    assert result.output["total"] == 0


# ─── Scatter-Gather ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scatter_gather_chunks():
    builder = await _builder_with_collab()
    items = list(range(25))
    result = await builder.invoke("collab-scatter-gather", {
        "items": items,
        "chunk_size": 10,
        "merge_strategy": "concat",
    })
    assert result.ok
    assert result.output["total_items"] == 25
    assert result.output["total_chunks"] == 3
    # First two chunks have 10, last has 5
    assert result.output["chunks"][0]["size"] == 10
    assert result.output["chunks"][2]["size"] == 5


@pytest.mark.asyncio
async def test_scatter_gather_empty():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-scatter-gather", {
        "items": [],
        "chunk_size": 5,
        "merge_strategy": "concat",
    })
    assert result.ok
    assert result.output["total_items"] == 0
    assert result.output["total_chunks"] == 0


@pytest.mark.asyncio
async def test_scatter_gather_single_chunk():
    builder = await _builder_with_collab()
    result = await builder.invoke("collab-scatter-gather", {
        "items": [1, 2, 3],
        "chunk_size": 10,
        "merge_strategy": "concat",
    })
    assert result.ok
    assert result.output["total_chunks"] == 1
    assert result.output["chunks"][0]["size"] == 3


# ─── Pack Registration ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_collab_caps_registered():
    builder = await _builder_with_collab()
    caps = builder.list_capabilities()
    cap_names = [c.name for c in caps]
    assert "collab-delegate" in cap_names
    assert "collab-vote" in cap_names
    assert "collab-aggregate" in cap_names
    assert "collab-fanout" in cap_names
    assert "collab-scatter-gather" in cap_names


@pytest.mark.asyncio
async def test_collab_caps_have_tags():
    builder = await _builder_with_collab()
    for cap in builder.list_capabilities():
        if cap.name.startswith("collab-"):
            assert "collaboration" in cap.tags, f"{cap.name} missing collaboration tag"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
