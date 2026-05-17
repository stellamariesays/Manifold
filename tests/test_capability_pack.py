"""Tests for capability_pack — pre-built capability packs."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import (
    load_text_pack,
    load_math_pack,
    load_meta_pack,
    load_routing_pack,
    load_fog_pack,
    load_learning_pack,
    load_all_packs,
)


@pytest.fixture
def agent():
    a = Agent("test-pack-agent")
    a.knows(["existing-cap"])
    return a


@pytest.fixture
def builder(agent):
    return CapabilityBuilder(agent)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Text Pack ──────────────────────────────────────────────────────────

class TestTextPack:
    def test_load_registers_all(self, builder):
        specs = load_text_pack(builder)
        assert len(specs) == 3
        names = [s.name for s in specs]
        assert "text-summarize" in names
        assert "text-keywords" in names
        assert "text-sentiment" in names

    def test_summarize(self, builder):
        load_text_pack(builder)
        result = _run(builder.invoke("text-summarize", {
            "text": "The quick brown fox jumps over the lazy dog. It was a sunny day. Everyone was happy.",
            "max_words": 10,
        }))
        assert result.ok
        assert "fox" in result.output["summary"]
        assert result.output["word_count"] > 0

    def test_summarize_empty(self, builder):
        load_text_pack(builder)
        result = _run(builder.invoke("text-summarize", {"text": ""}))
        assert result.ok
        assert result.output["summary"] == ""

    def test_keywords(self, builder):
        load_text_pack(builder)
        result = _run(builder.invoke("text-keywords", {
            "text": "python python python code code data data data data science",
            "top_n": 3,
        }))
        assert result.ok
        assert result.output["keywords"][0] == "data"
        assert len(result.output["keywords"]) == 3

    def test_sentiment_positive(self, builder):
        load_text_pack(builder)
        result = _run(builder.invoke("text-sentiment", {
            "text": "This is a great and amazing product, I love it!",
        }))
        assert result.ok
        assert result.output["label"] == "positive"
        assert result.output["score"] > 0

    def test_sentiment_negative(self, builder):
        load_text_pack(builder)
        result = _run(builder.invoke("text-sentiment", {
            "text": "This is terrible and awful, worst experience ever.",
        }))
        assert result.ok
        assert result.output["label"] == "negative"

    def test_sentiment_neutral(self, builder):
        load_text_pack(builder)
        result = _run(builder.invoke("text-sentiment", {
            "text": "The meeting is at 3pm in the conference room.",
        }))
        assert result.ok
        assert result.output["label"] == "neutral"

    def test_syncs_with_agent_capabilities(self, builder, agent):
        load_text_pack(builder)
        assert "text-summarize" in agent._capabilities


# ─── Math Pack ──────────────────────────────────────────────────────────

class TestMathPack:
    def test_load_registers_all(self, builder):
        specs = load_math_pack(builder)
        assert len(specs) == 3

    def test_arithmetic_add(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-arithmetic", {"a": 5, "b": 3, "op": "add"}))
        assert result.ok
        assert result.output["result"] == 8

    def test_arithmetic_div(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-arithmetic", {"a": 10, "b": 4, "op": "div"}))
        assert result.ok
        assert result.output["result"] == 2.5

    def test_arithmetic_div_zero(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-arithmetic", {"a": 5, "b": 0, "op": "div"}))
        assert result.ok
        assert result.output["result"] == float("inf")

    def test_arithmetic_unknown_op(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-arithmetic", {"a": 1, "b": 2, "op": "xor"}))
        assert not result.output["ok"]

    def test_statistics(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-statistics", {"values": [1, 2, 3, 4, 5]}))
        assert result.ok
        assert result.output["mean"] == 3.0
        assert result.output["count"] == 5
        assert "stdev" in result.output

    def test_statistics_empty(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-statistics", {"values": []}))
        assert not result.output["ok"]

    def test_unit_convert_km_mi(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-unit-convert", {"value": 10, "from": "km", "to": "mi"}))
        assert result.ok
        assert abs(result.output["result"] - 6.21371) < 0.01

    def test_unit_convert_c_f(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-unit-convert", {"value": 100, "from": "c", "to": "f"}))
        assert result.ok
        assert result.output["result"] == 212

    def test_unit_convert_unsupported(self, builder):
        load_math_pack(builder)
        result = _run(builder.invoke("math-unit-convert", {"value": 1, "from": "parsec", "to": "smoot"}))
        assert not result.output["ok"]


# ─── Meta Pack ──────────────────────────────────────────────────────────

class TestMetaPack:
    def test_catalog(self, builder):
        load_text_pack(builder)
        load_meta_pack(builder)
        result = _run(builder.invoke("meta-catalog", {}))
        assert result.ok
        assert "catalog" in result.output
        assert "stats" in result.output
        # Should see text-summarize in catalog
        assert "text-summarize" in result.output["catalog"]

    def test_health(self, builder):
        load_text_pack(builder)
        load_meta_pack(builder)
        result = _run(builder.invoke("meta-health", {}))
        assert result.ok
        assert result.output["total"] >= 3
        assert len(result.output["active"]) >= 3


# ─── Routing Pack ───────────────────────────────────────────────────────

class TestRoutingPack:
    def test_load_routing(self, builder, agent):
        specs = load_routing_pack(builder, agent)
        assert len(specs) == 2
        names = [s.name for s in specs]
        assert "route-message" in names
        assert "broadcast-topic" in names


# ─── Load All ───────────────────────────────────────────────────────────

class TestLoadAll:
    def test_load_all_with_agent(self, builder, agent):
        specs = load_all_packs(builder, agent)
        # 3 text + 3 math + 2 meta + 4 data + 3 monitor + 4 encoding + 3 planning + 2 routing + 5 fog + 4 reasoning + 5 network + 5 memory = 43
        assert len(specs) == 105  # +5 tool-use +5 collaboration +5 subscription +7 trust +4 research +6 audit +6 deliberation +5 orchestration +5 evaluation +5 adapter +4 learning pack

    def test_load_all_without_agent(self, builder):
        specs = load_all_packs(builder)
        # 3 text + 3 math + 2 meta + 4 data + 3 monitor + 4 encoding + 3 planning + 4 reasoning + 5 network + 5 memory = 36
        assert len(specs) == 93  # +5 tool-use +5 collaboration +5 subscription +7 trust +4 research +6 audit +6 deliberation +5 orchestration +5 evaluation +5 adapter +4 learning pack

    def test_search_finds_packs(self, builder, agent):
        load_all_packs(builder, agent)
        results = builder.search("sentiment")
        assert any("text-sentiment" in s.name for s in results)

    def test_stats_after_loading(self, builder, agent):
        load_all_packs(builder, agent)
        stats = builder.stats()
        assert stats["total_capabilities"] == 105
        assert stats["active"] == 105


# ─── Fog Awareness Pack ──────────────────────────────────────────────────

class TestFogPack:
    def test_load_registers_all(self, builder, agent):
        specs = load_fog_pack(builder, agent)
        assert len(specs) == 5
        names = [s.name for s in specs]
        assert "fog-blind-spots" in names
        assert "fog-map" in names
        assert "fog-seam-measure" in names
        assert "fog-atlas-holes" in names
        assert "fog-discover" in names

    def test_fog_map(self, builder, agent):
        load_fog_pack(builder, agent)
        cap = builder.get("fog-map")
        assert cap is not None
        result = _run(cap.handler({}))
        assert result["ok"] is True
        assert result["agent"] == "test-pack-agent"
        assert "gap_count" in result

    def test_fog_discover_requires_topic(self, builder, agent):
        load_fog_pack(builder, agent)
        cap = builder.get("fog-discover")
        assert cap is not None
        result = _run(cap.handler({}))
        assert result["ok"] is False
        assert "topic" in result["error"]

    def test_fog_discover_local(self, builder, agent):
        load_fog_pack(builder, agent)
        cap = builder.get("fog-discover")
        result = _run(cap.handler({"topic": "existing-cap"}))
        assert result["ok"] is True
        assert result["query"] == "existing-cap"

    def test_fog_seam_measure_requires_target(self, builder, agent):
        load_fog_pack(builder, agent)
        cap = builder.get("fog-seam-measure")
        result = _run(cap.handler({}))
        assert result["ok"] is False

    def test_fog_seam_measure(self, builder, agent):
        load_fog_pack(builder, agent)
        cap = builder.get("fog-seam-measure")
        result = _run(cap.handler({"target_agent": "nonexistent"}))
        assert result["ok"] is True
        assert "tension" in result

    def test_fog_pack_tags(self, builder, agent):
        specs = load_fog_pack(builder, agent)
        for spec in specs:
            assert "fog" in spec.tags

    # ─── Learning Pack ─────────────────────────────────────────────────────

    def test_learning_pack_loads(self, builder):
        specs = load_learning_pack(builder)
        assert len(specs) >= 4
        names = {s.name for s in specs}
        assert "learn-record" in names
        assert "learn-proficiency" in names
        assert "learn-suggest" in names
        assert "learn-reset" in names

    def test_learn_record(self, builder):
        load_learning_pack(builder)
        cap = builder.get("learn-record")
        assert cap is not None
        result = _run(cap.handler({"agent": "alice", "capability": "solar-prediction", "success": True, "grade": "A", "score": 0.95}))
        assert result["ok"] is True
        assert result["recorded"] is True
        assert result["success_rate"] == 1.0
        assert result["attempts"] == 1

    def test_learn_record_multiple(self, builder):
        load_learning_pack(builder)
        cap = builder.get("learn-record")
        _run(cap.handler({"agent": "bob", "capability": "math", "success": True, "grade": "B", "score": 0.8}))
        result = _run(cap.handler({"agent": "bob", "capability": "math", "success": False, "grade": "D", "score": 0.3}))
        assert result["ok"] is True
        assert result["success_rate"] == 0.5
        assert result["attempts"] == 2

    def test_learn_record_requires_capability(self, builder):
        load_learning_pack(builder)
        cap = builder.get("learn-record")
        with pytest.raises(ValueError, match="capability"):
            _run(cap.handler({"agent": "alice"}))

    def test_learn_proficiency(self, builder):
        load_learning_pack(builder)
        rec = builder.get("learn-record")
        prof = builder.get("learn-proficiency")
        _run(rec.handler({"agent": "carol", "capability": "nlp", "success": True, "score": 0.92}))
        _run(rec.handler({"agent": "carol", "capability": "nlp", "success": True, "score": 0.88}))
        result = _run(prof.handler({"agent": "carol"}))
        assert result["ok"] is True
        assert result["total_capabilities"] >= 1
        nlp = next(p for p in result["proficiencies"] if p["capability"] == "nlp")
        assert nlp["level"] == "expert"
        assert nlp["success_rate"] == 1.0

    def test_learn_proficiency_specific_cap(self, builder):
        load_learning_pack(builder)
        rec = builder.get("learn-record")
        prof = builder.get("learn-proficiency")
        _run(rec.handler({"agent": "dave", "capability": "crypto", "success": False, "score": 0.2}))
        result = _run(prof.handler({"agent": "dave", "capability": "crypto"}))
        assert result["ok"] is True
        assert len(result["proficiencies"]) == 1
        assert result["proficiencies"][0]["level"] == "developing"

    def test_learn_suggest(self, builder):
        load_learning_pack(builder)
        rec = builder.get("learn-record")
        sug = builder.get("learn-suggest")
        # Record poor outcomes
        for _ in range(3):
            _run(rec.handler({"agent": "eve", "capability": "weak-skill", "success": False, "score": 0.3}))
        result = _run(sug.handler({"agent": "eve", "threshold": 0.6}))
        assert result["ok"] is True
        assert result["count"] >= 1
        assert any(s["capability"] == "weak-skill" for s in result["suggestions"])

    def test_learn_suggest_no_weak_caps(self, builder):
        load_learning_pack(builder)
        rec = builder.get("learn-record")
        sug = builder.get("learn-suggest")
        _run(rec.handler({"agent": "frank", "capability": "strong-skill", "success": True, "score": 0.95}))
        result = _run(sug.handler({"agent": "frank", "threshold": 0.6}))
        assert result["ok"] is True
        assert result["count"] == 0

    def test_learn_reset_specific(self, builder):
        load_learning_pack(builder)
        rec = builder.get("learn-record")
        rst = builder.get("learn-reset")
        _run(rec.handler({"agent": "grace", "capability": "x", "success": True, "score": 1.0}))
        result = _run(rst.handler({"agent": "grace", "capability": "x"}))
        assert result["ok"] is True
        assert result["removed"] == 1

    def test_learn_reset_all(self, builder):
        load_learning_pack(builder)
        rec = builder.get("learn-record")
        rst = builder.get("learn-reset")
        _run(rec.handler({"agent": "heidi", "capability": "a", "success": True, "score": 1.0}))
        _run(rec.handler({"agent": "heidi", "capability": "b", "success": True, "score": 1.0}))
        result = _run(rst.handler({"agent": "heidi"}))
        assert result["ok"] is True
        assert result["removed"] == 2

    def test_learn_improvement_streak(self, builder):
        load_learning_pack(builder)
        rec = builder.get("learn-record")
        for grade in ["C", "B", "A"]:
            _run(rec.handler({"agent": "ivan", "capability": "rising-star", "success": True, "grade": grade, "score": 0.7}))
        prof = builder.get("learn-proficiency")
        result = _run(prof.handler({"agent": "ivan", "capability": "rising-star"}))
        assert result["proficiencies"][0]["improvement_streak"] == 2

    def test_learning_pack_tags(self, builder):
        specs = load_learning_pack(builder)
        for spec in specs:
            assert "learning" in spec.tags
