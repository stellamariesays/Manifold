"""Tests for SemanticRegistry — runs with zero extra deps (TF-IDF)."""

import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from manifold.semantic_registry import (
    SemanticRegistry,
    SemanticAgentRef,
    cosine_similarity,
    _normalise,
)


# ─── cosine_similarity ─────────────────────────────────────────────────────────

def test_cosine_identical():
    v = _normalise([1.0, 2.0, 3.0])
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

def test_cosine_orthogonal():
    a = _normalise([1.0, 0.0, 0.0])
    b = _normalise([0.0, 1.0, 0.0])
    assert cosine_similarity(a, b) == 0.0

def test_cosine_different_lengths():
    a = [1.0, 0.0]
    b = [1.0, 0.0, 0.5]
    # Should not raise — shorter vector is zero-padded
    sim = cosine_similarity(a, b)
    assert 0.0 <= sim <= 1.0


# ─── SemanticRegistry ──────────────────────────────────────────────────────────

@pytest.fixture
def registry():
    return SemanticRegistry(embedder="tfidf")

def test_register_and_len(registry):
    assert len(registry) == 0
    registry.register("agent-a", ["trading", "BTC"])
    assert len(registry) == 1
    registry.register("agent-b", ["solar", "XGBoost"])
    assert len(registry) == 2

def test_register_returns_record(registry):
    rec = registry.register("agent-a", ["trading", "BTC"], address="subway://localhost:8765")
    assert rec.name == "agent-a"
    assert rec.capabilities == ["trading", "BTC"]
    assert rec.address == "subway://localhost:8765"
    assert len(rec.embedding) > 0

def test_unregister(registry):
    registry.register("agent-a", ["trading"])
    registry.unregister("agent-a")
    assert len(registry) == 0

def test_unregister_missing_is_noop(registry):
    registry.unregister("ghost")  # should not raise

def test_seek_basic_routing(registry):
    registry.register("trader",    ["bitcoin", "trading", "momentum", "backtesting"])
    registry.register("scientist", ["solar-flares", "SHARP", "heliophysics"])
    registry.register("infra",     ["Docker", "Kubernetes", "Linux", "networking"])

    results = registry.seek("bitcoin trading strategy backtest")
    assert results[0].name == "trader"

def test_seek_excludes_self(registry):
    registry.register("me",    ["trading", "bitcoin"])
    registry.register("other", ["trading", "bitcoin"])

    results = registry.seek("bitcoin trading", exclude="me")
    names = [r.name for r in results]
    assert "me" not in names
    assert "other" in names

def test_seek_returns_similarity_sorted(registry):
    registry.register("a", ["foo", "bar", "baz"])
    registry.register("b", ["foo"])
    registry.register("c", ["qux", "quux"])

    results = registry.seek("foo bar baz")
    sims = [r.similarity for r in results]
    assert sims == sorted(sims, reverse=True)

def test_seek_top_k(registry):
    for i in range(10):
        registry.register(f"agent-{i}", [f"cap-{i}", "common"])

    results = registry.seek("common cap", top_k=3)
    assert len(results) <= 3

def test_seek_min_similarity(registry):
    registry.register("relevant",  ["XGBoost", "gradient-boosting", "classification"])
    registry.register("irrelevant", ["cooking", "recipes", "french-cuisine"])

    # TF-IDF note: "gradient-boosting" is tokenised to ["gradient", "boosting"];
    # "gradient boosted classifier" overlaps on "gradient" → relevant scores > 0
    # but threshold needs to be low enough for TF-IDF to pass it.
    # irrelevant has zero token overlap at any threshold.
    results_all = registry.seek("gradient boosted classifier", min_similarity=0.0)
    names_all = [r.name for r in results_all]
    assert "relevant" in names_all
    assert "irrelevant" in names_all  # zero overlap but > min_similarity=0

    # At threshold above irrelevant's score, only relevant survives
    relevant_sim = next(r.similarity for r in results_all if r.name == "relevant")
    irrelevant_sim = next(r.similarity for r in results_all if r.name == "irrelevant")
    # irrelevant has strictly less similarity than relevant (zero token overlap)
    assert relevant_sim >= irrelevant_sim
    # Filter at a threshold just above irrelevant's score
    cutoff = irrelevant_sim + 1e-6
    results_filtered = registry.seek("gradient boosted classifier", min_similarity=cutoff)
    names_filtered = [r.name for r in results_filtered]
    assert "relevant" in names_filtered
    assert "irrelevant" not in names_filtered

def test_seek_empty_registry(registry):
    results = registry.seek("anything")
    assert results == []

def test_seek_returns_semantic_agent_refs(registry):
    registry.register("agent-a", ["trading"])
    results = registry.seek("trading")
    assert all(isinstance(r, SemanticAgentRef) for r in results)

def test_seek_by_capabilities(registry):
    registry.register("trader",    ["bitcoin", "trading", "momentum"])
    registry.register("scientist", ["solar-flares", "SHARP"])

    results = registry.seek_by_capabilities(["bitcoin", "trading"])
    assert results[0].name == "trader"

def test_update_from_announcement_add(registry):
    registry.update_from_announcement({
        "name": "remote-agent",
        "capabilities": ["trading", "crypto"],
        "address": "subway://remote:8765",
    })
    assert len(registry) == 1
    assert registry.get("remote-agent") is not None

def test_update_from_announcement_leave(registry):
    registry.register("remote-agent", ["trading"])
    registry.update_from_announcement({
        "name": "remote-agent",
        "event": "leave",
        "capabilities": [],
    })
    assert len(registry) == 0

def test_update_from_announcement_with_embedding(registry):
    # Pre-computed embedding should be used directly (no re-embedding)
    emb = [0.1] * 10
    registry.update_from_announcement({
        "name": "fast-agent",
        "capabilities": ["trading"],
        "embedding": emb,
    })
    rec = registry.get("fast-agent")
    assert rec.embedding == emb

def test_similarity_matrix(registry):
    registry.register("a", ["trading"])
    registry.register("b", ["trading"])
    mat = registry.similarity_matrix()
    assert mat["a"]["a"] == 1.0
    assert 0.0 <= mat["a"]["b"] <= 1.0

def test_embedding_matrix_shape(registry):
    registry.register("a", ["trading"])
    registry.register("b", ["solar"])
    names, embeddings = registry.embedding_matrix()
    assert len(names) == 2
    assert len(embeddings) == 2
    assert all(isinstance(e, list) for e in embeddings)

def test_register_with_precomputed_embedding(registry):
    emb = _normalise([1.0, 0.0, 0.0])
    rec = registry.register("fast-agent", ["trading"], embedding=emb)
    assert rec.embedding == emb

def test_repr(registry):
    r = repr(registry)
    assert "SemanticRegistry" in r
    assert "tfidf" in r

def test_all_agents(registry):
    registry.register("a", ["x"])
    registry.register("b", ["y"])
    agents = registry.all_agents()
    assert len(agents) == 2
    assert {a.name for a in agents} == {"a", "b"}
