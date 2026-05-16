"""Capability pack — pre-built, reusable capabilities for Manifold agents.

A library of common agent capabilities that can be loaded into any
``CapabilityBuilder``. Each pack function registers one or more capabilities
and returns the list of registered ``CapSpec`` objects.

Usage::

    from manifold.capability_builder import CapabilityBuilder
    from manifold.capability_pack import load_text_pack, load_math_pack

    builder = CapabilityBuilder(agent)
    load_text_pack(builder)
    load_math_pack(builder)

    result = await builder.invoke("text-summarize", {"text": "Long text..."})

Available packs:
- **text_pack**: summarization, keyword extraction, sentiment stub
- **math_pack**: basic arithmetic, statistics over lists
- **routing_pack**: audience-based message routing, topic broadcast
- **meta_pack**: self-inspection, capability catalog query
"""

from __future__ import annotations

import math
import re
import statistics
from typing import Any

from .capability_builder import CapSpec, CapabilityBuilder


# ─── Text Pack ──────────────────────────────────────────────────────────

async def _text_summarize(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract a summary by taking the first sentence + key phrases."""
    text = payload.get("text", "")
    max_words = payload.get("max_words", 50)

    if not text:
        return {"summary": "", "word_count": 0}

    # First sentence
    sentences = re.split(r'[.!?]+', text)
    first = sentences[0].strip() if sentences else text[:200]

    words = first.split()
    if len(words) > max_words:
        first = " ".join(words[:max_words]) + "..."

    return {"summary": first, "word_count": len(text.split())}


async def _text_keywords(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract keywords by frequency (stop-word filtered)."""
    text = payload.get("text", "").lower()
    top_n = payload.get("top_n", 10)

    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "it", "that", "this", "was", "are",
        "be", "has", "had", "not", "they", "we", "you", "he", "she", "its",
        "as", "have", "will", "do", "can", "would", "could", "should", "may",
    }

    words = re.findall(r'[a-z]{3,}', text)
    freq: dict[str, int] = {}
    for w in words:
        if w not in stopwords:
            freq[w] = freq.get(w, 0) + 1

    ranked = sorted(freq.items(), key=lambda x: -x[1])[:top_n]
    return {"keywords": [k for k, _ in ranked], "frequencies": dict(ranked)}


async def _text_sentiment(payload: dict[str, Any]) -> dict[str, Any]:
    """Simple rule-based sentiment scoring (-1 to +1)."""
    text = payload.get("text", "").lower()

    positive = {
        "good", "great", "excellent", "amazing", "wonderful", "love", "best",
        "happy", "awesome", "fantastic", "brilliant", "perfect", "beautiful",
        "outstanding", "superb", "nice", "enjoy", "glad", "impressive",
    }
    negative = {
        "bad", "terrible", "awful", "horrible", "hate", "worst", "poor",
        "angry", "ugly", "disappointing", "sad", "annoying", "broken",
        "fail", "failure", "useless", "stupid", "wrong", "error",
    }

    words = set(re.findall(r'[a-z]+', text))
    pos_count = len(words & positive)
    neg_count = len(words & negative)
    total = pos_count + neg_count

    if total == 0:
        score = 0.0
    else:
        score = (pos_count - neg_count) / total

    label = "positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral")

    return {
        "score": round(score, 3),
        "label": label,
        "positive_hits": list(words & positive),
        "negative_hits": list(words & negative),
    }


def load_text_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register text processing capabilities."""
    specs = []
    specs.append(builder.register(
        name="text-summarize",
        handler=_text_summarize,
        version="1.0.0",
        description="Summarize text by extracting the first sentence and trimming to max_words",
        inputs=["text"],
        outputs=["summary", "word_count"],
        tags=["text", "nlp", "summarization"],
    ))
    specs.append(builder.register(
        name="text-keywords",
        handler=_text_keywords,
        version="1.0.0",
        description="Extract top-N keywords by frequency with stop-word filtering",
        inputs=["text", "top_n"],
        outputs=["keywords", "frequencies"],
        tags=["text", "nlp", "keywords"],
    ))
    specs.append(builder.register(
        name="text-sentiment",
        handler=_text_sentiment,
        version="1.0.0",
        description="Rule-based sentiment analysis returning score (-1 to +1) and label",
        inputs=["text"],
        outputs=["score", "label", "positive_hits", "negative_hits"],
        tags=["text", "nlp", "sentiment"],
    ))
    return specs


# ─── Math Pack ──────────────────────────────────────────────────────────

async def _math_arithmetic(payload: dict[str, Any]) -> dict[str, Any]:
    """Perform basic arithmetic on two numbers."""
    a = payload.get("a", 0)
    b = payload.get("b", 0)
    op = payload.get("op", "add")

    ops = {
        "add": lambda x, y: x + y,
        "sub": lambda x, y: x - y,
        "mul": lambda x, y: x * y,
        "div": lambda x, y: x / y if y != 0 else float("inf"),
        "mod": lambda x, y: x % y if y != 0 else float("nan"),
        "pow": lambda x, y: x ** y,
    }

    if op not in ops:
        return {"error": f"Unknown op: {op!r}. Use: {', '.join(ops)}", "ok": False}

    result = ops[op](a, b)
    return {"result": result, "op": op, "a": a, "b": b, "ok": True}


async def _math_statistics(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute descriptive statistics for a list of numbers."""
    values = payload.get("values", [])
    if not values:
        return {"error": "Empty values list", "ok": False}

    nums = [float(v) for v in values]
    n = len(nums)

    result: dict[str, Any] = {
        "count": n,
        "sum": round(sum(nums), 4),
        "mean": round(statistics.mean(nums), 4),
        "min": round(min(nums), 4),
        "max": round(max(nums), 4),
        "range": round(max(nums) - min(nums), 4),
        "ok": True,
    }

    if n >= 2:
        result["stdev"] = round(statistics.stdev(nums), 4)
        result["variance"] = round(statistics.variance(nums), 4)
        result["median"] = round(statistics.median(nums), 4)

    if n >= 4:
        try:
            result["skewness"] = round(statistics.skew(nums), 4) if hasattr(statistics, 'skew') else None
        except Exception:
            pass

    return result


async def _math_unit_convert(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert between common units."""
    value = payload.get("value", 0)
    from_unit = payload.get("from", "")
    to_unit = payload.get("to", "")

    conversions: dict[str, float] = {
        "km_mi": 0.621371, "mi_km": 1.60934,
        "kg_lb": 2.20462, "lb_kg": 0.453592,
        "c_f": None, "f_c": None,  # special-cased
        "m_ft": 3.28084, "ft_m": 0.3048,
    }

    key = f"{from_unit}_{to_unit}"
    if key == "c_f":
        result = value * 9 / 5 + 32
    elif key == "f_c":
        result = (value - 32) * 5 / 9
    elif key in conversions and conversions[key] is not None:
        result = value * conversions[key]
    else:
        return {"error": f"Unsupported conversion: {from_unit} -> {to_unit}", "ok": False}

    return {"result": round(result, 6), "from": f"{value} {from_unit}", "to": f"{round(result, 6)} {to_unit}", "ok": True}


def load_math_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register math and statistics capabilities."""
    specs = []
    specs.append(builder.register(
        name="math-arithmetic",
        handler=_math_arithmetic,
        version="1.0.0",
        description="Basic arithmetic operations: add, sub, mul, div, mod, pow",
        inputs=["a", "b", "op"],
        outputs=["result", "op", "ok"],
        tags=["math", "arithmetic"],
    ))
    specs.append(builder.register(
        name="math-statistics",
        handler=_math_statistics,
        version="1.0.0",
        description="Descriptive statistics: mean, median, stdev, range, etc.",
        inputs=["values"],
        outputs=["count", "mean", "median", "stdev", "ok"],
        tags=["math", "statistics"],
    ))
    specs.append(builder.register(
        name="math-unit-convert",
        handler=_math_unit_convert,
        version="1.0.0",
        description="Convert between common units (km/mi, kg/lb, C/F, m/ft)",
        inputs=["value", "from", "to"],
        outputs=["result", "from", "to", "ok"],
        tags=["math", "conversion", "units"],
    ))
    return specs


# ─── Meta Pack ──────────────────────────────────────────────────────────

async def _meta_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the capability catalog (populated at invoke time)."""
    # This will be patched with the builder reference at registration
    builder: CapabilityBuilder | None = payload.get("__builder__")
    if builder is None:
        return {"error": "No builder attached", "ok": False}
    return {"catalog": builder.catalog(), "stats": builder.stats(), "ok": True}


async def _meta_health(payload: dict[str, Any]) -> dict[str, Any]:
    """Return capability health — which are active, invocation counts."""
    builder: CapabilityBuilder | None = payload.get("__builder__")
    if builder is None:
        return {"error": "No builder attached", "ok": False}

    caps = builder.list_capabilities()
    return {
        "total": len(caps),
        "active": [c.name for c in caps if c.is_invocable],
        "disabled": [c.name for c in caps if c.status.value == "disabled"],
        "deprecated": [c.name for c in caps if c.status.value == "deprecated"],
        "most_invoked": sorted(
            [{"name": c.name, "count": c.invocation_count} for c in caps],
            key=lambda x: -x["count"],
        )[:5],
        "ok": True,
    }


def load_meta_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register self-inspection / meta capabilities."""
    import functools

    specs = []

    async def _catalog_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _meta_catalog({**payload, "__builder__": builder})

    async def _health_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _meta_health({**payload, "__builder__": builder})

    specs.append(builder.register(
        name="meta-catalog",
        handler=_catalog_wrapped,
        version="1.0.0",
        description="Query the full capability catalog and stats",
        inputs=[],
        outputs=["catalog", "stats", "ok"],
        tags=["meta", "introspection"],
    ))
    specs.append(builder.register(
        name="meta-health",
        handler=_health_wrapped,
        version="1.0.0",
        description="Capability health check — active, deprecated, invocation counts",
        inputs=[],
        outputs=["total", "active", "ok"],
        tags=["meta", "health", "introspection"],
    ))
    return specs


# ─── Routing Pack ───────────────────────────────────────────────────────

async def _route_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Route a message to the best audience for a topic."""
    # This gets patched with agent/router at registration
    agent = payload.get("__agent__")
    if agent is None:
        return {"error": "No agent attached", "ok": False}

    from .audience import AudienceRouter
    router = AudienceRouter(agent)
    topic = payload.get("topic", "")
    min_score = payload.get("min_score", 0.1)
    max_results = payload.get("max_results", 5)

    report = router.route(topic, min_score=min_score, max_results=max_results)
    return {"audience": report.names(), "report": report.summary(), "ok": True}


async def _broadcast_topic(payload: dict[str, Any]) -> dict[str, Any]:
    """Find all agents that should receive a topic broadcast."""
    agent = payload.get("__agent__")
    if agent is None:
        return {"error": "No agent attached", "ok": False}

    from .audience import AudienceRouter
    router = AudienceRouter(agent)
    topic = payload.get("topic", "")

    # Low threshold broadcast
    report = router.route(topic, min_score=0.05)
    return {
        "recipients": report.names(),
        "total": len(report.entries),
        "excluded": report.excluded,
        "ok": True,
    }


def load_routing_pack(builder: CapabilityBuilder, agent: Any) -> list[CapSpec]:
    """Register audience routing capabilities (requires agent reference)."""

    async def _route_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _route_message({**payload, "__agent__": agent})

    async def _broadcast_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _broadcast_topic({**payload, "__agent__": agent})

    specs = []
    specs.append(builder.register(
        name="route-message",
        handler=_route_wrapped,
        version="1.0.0",
        description="Route a message to the best-matching agents for a topic",
        inputs=["topic", "min_score", "max_results"],
        outputs=["audience", "report", "ok"],
        tags=["routing", "audience", "dispatch"],
    ))
    specs.append(builder.register(
        name="broadcast-topic",
        handler=_broadcast_wrapped,
        version="1.0.0",
        description="Find all agents that should receive a topic broadcast",
        inputs=["topic"],
        outputs=["recipients", "total", "ok"],
        tags=["routing", "audience", "broadcast"],
    ))
    return specs


# ─── Convenience ────────────────────────────────────────────────────────

def load_all_packs(builder: CapabilityBuilder, agent: Any | None = None) -> list[CapSpec]:
    """Load all available capability packs."""
    specs = []
    specs.extend(load_text_pack(builder))
    specs.extend(load_math_pack(builder))
    specs.extend(load_meta_pack(builder))
    if agent is not None:
        specs.extend(load_routing_pack(builder, agent))
    return specs
