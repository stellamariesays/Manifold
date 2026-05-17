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
- **data_pack**: validation, transform, aggregation, merge
- **monitor_pack**: threshold alerts, heartbeat checks, anomaly detection
- **encoding_pack**: base64, JSON, CSV, URL encoding/decoding
- **fog_pack**: blind spots, fog map, seam measure, atlas holes, fog discovery
- **network_pack**: message compose, relay chains, broadcast, request-response, acknowledgements
- **memory_pack**: key-value store, retrieval, search, summarization, TTL expiry, tag-based forget
- **subscription_pack**: pub/sub notifications — subscribe, publish, poll, status
- **research_pack**: web research — plan queries, extract facts, synthesize findings, score sources
- **adapter_pack**: format conversion, schema mapping, protocol bridging, normalization, validation
- **security_pack**: token auth, permission checks, rate limiting, input sanitization, access audit
- **strategy_pack**: cost-benefit analysis, priority scoring, resource allocation, conflict resolution, decision logging, tradeoff matrix
"""

from __future__ import annotations

import math
import re
import statistics
import time
import uuid
from typing import Any

from .capability_builder import CapSpec, CapabilityBuilder
from .audience import _trigram_similarity
from .subscription import SubscriptionBus


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


# ─── Data Pipeline Pack ────────────────────────────────────────────────

async def _data_validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a data record against required fields and type rules."""
    record = payload.get("record", {})
    rules = payload.get("rules", {})
    # rules: {"field": {"type": "int", "required": true, "min": 0, "max": 100}}
    errors: list[str] = []
    warnings: list[str] = []

    for field_name, rule in rules.items():
        value = record.get(field_name)
        if rule.get("required") and value is None:
            errors.append(f"{field_name}: required but missing")
            continue
        if value is None:
            continue
        expected_type = rule.get("type")
        type_map = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "dict": dict}
        if expected_type and expected_type in type_map:
            if not isinstance(value, type_map[expected_type]):
                errors.append(f"{field_name}: expected {expected_type}, got {type(value).__name__}")
                continue
        if "min" in rule and isinstance(value, (int, float)) and value < rule["min"]:
            errors.append(f"{field_name}: {value} below minimum {rule['min']}")
        if "max" in rule and isinstance(value, (int, float)) and value > rule["max"]:
            errors.append(f"{field_name}: {value} above maximum {rule['max']}")
        if "pattern" in rule and isinstance(value, str):
            if not re.match(rule["pattern"], value):
                errors.append(f"{field_name}: does not match pattern {rule['pattern']}")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{field_name}: {value!r} not in {rule['enum']}")

    # Check for unexpected fields
    allowed = set(rules.keys())
    if rule.get("strict"):
        for key in record:
            if key not in allowed:
                warnings.append(f"{key}: unexpected field")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checked_fields": len(rules),
    }


async def _data_transform(payload: dict[str, Any]) -> dict[str, Any]:
    """Transform records with map/rename/filter operations."""
    records = payload.get("records", [])
    ops = payload.get("operations", [])

    if isinstance(records, dict):
        records = [records]

    result = list(records)

    for op in ops:
        op_type = op.get("type")
        if op_type == "rename":
            old, new = op["from"], op["to"]
            for rec in result:
                if old in rec:
                    rec[new] = rec.pop(old)
        elif op_type == "select":
            fields = op.get("fields", [])
            result = [{k: rec.get(k) for k in fields if k in rec} for rec in result]
        elif op_type == "filter":
            field = op.get("field")
            value = op.get("value")
            op_val = op.get("op", "eq")
            if op_val == "eq":
                result = [r for r in result if r.get(field) == value]
            elif op_val == "neq":
                result = [r for r in result if r.get(field) != value]
            elif op_val == "gt":
                result = [r for r in result if r.get(field, value) > value]
            elif op_val == "lt":
                result = [r for r in result if r.get(field, value) < value]
            elif op_val == "gte":
                result = [r for r in result if r.get(field, value) >= value]
            elif op_val == "lte":
                result = [r for r in result if r.get(field, value) <= value]
        elif op_type == "add_field":
            name = op.get("name")
            val = op.get("value")
            for rec in result:
                rec[name] = val
        elif op_type == "sort":
            field = op.get("field")
            reverse = op.get("reverse", False)
            result.sort(key=lambda r: r.get(field, ""), reverse=reverse)

    return {"records": result, "count": len(result)}


async def _data_aggregate(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregate numeric data: sum, mean, min, max, count, group-by."""
    records = payload.get("records", [])
    field = payload.get("field")
    group_by = payload.get("group_by")

    if not records or not field:
        return {"error": "records and field required", "ok": False}

    values = [rec.get(field) for rec in records if isinstance(rec.get(field), (int, float))]

    if not values:
        return {"error": f"no numeric values for field '{field}'", "ok": False}

    base = {
        "count": len(values),
        "sum": sum(values),
        "mean": statistics.mean(values),
        "min": min(values),
        "max": max(values),
    }
    if len(values) > 1:
        base["stdev"] = statistics.stdev(values)
        base["median"] = statistics.median(values)

    # Group-by support
    groups: dict[str, list[float]] = {}
    if group_by:
        for rec in records:
            key = str(rec.get(group_by, "__none__"))
            val = rec.get(field)
            if isinstance(val, (int, float)):
                groups.setdefault(key, []).append(val)
        base["groups"] = {}
        for gk, gvals in groups.items():
            base["groups"][gk] = {
                "count": len(gvals),
                "sum": sum(gvals),
                "mean": statistics.mean(gvals),
            }

    base["ok"] = True
    return base


async def _data_merge(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge two datasets on a key field (inner/left join)."""
    left = payload.get("left", [])
    right = payload.get("right", [])
    key = payload.get("key")
    how = payload.get("how", "inner")  # inner or left

    if not key:
        return {"error": "key field required", "ok": False}

    right_index: dict[str, dict] = {}
    for rec in right:
        k = rec.get(key)
        if k is not None:
            right_index[str(k)] = rec

    merged = []
    for rec in left:
        k = str(rec.get(key, ""))
        right_rec = right_index.get(k)
        if right_rec:
            combined = {**rec, **{f"{rk}": rv for rk, rv in right_rec.items() if rk != key}}
            merged.append(combined)
        elif how == "left":
            merged.append(dict(rec))

    return {"records": merged, "count": len(merged), "ok": True}


def load_data_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register data pipeline capabilities: validate, transform, aggregate, merge."""
    specs = []
    specs.append(builder.register(
        name="data-validate",
        handler=_data_validate,
        version="1.0.0",
        description="Validate records against field rules (type, range, enum, pattern)",
        inputs=["record", "rules"],
        outputs=["valid", "errors", "warnings"],
        tags=["data", "validation", "pipeline"],
    ))
    specs.append(builder.register(
        name="data-transform",
        handler=_data_transform,
        version="1.0.0",
        description="Transform records: rename, select, filter, sort, add fields",
        inputs=["records", "operations"],
        outputs=["records", "count"],
        tags=["data", "transform", "pipeline"],
    ))
    specs.append(builder.register(
        name="data-aggregate",
        handler=_data_aggregate,
        version="1.0.0",
        description="Aggregate numeric fields: sum, mean, min, max, group-by stats",
        inputs=["records", "field"],
        outputs=["count", "sum", "mean", "min", "max", "groups"],
        tags=["data", "aggregation", "statistics", "pipeline"],
    ))
    specs.append(builder.register(
        name="data-merge",
        handler=_data_merge,
        version="1.0.0",
        description="Merge two datasets on a key field (inner/left join)",
        inputs=["left", "right", "key"],
        outputs=["records", "count"],
        tags=["data", "merge", "join", "pipeline"],
    ))
    return specs


# ─── Monitor Pack ───────────────────────────────────────────────────────

async def _monitor_threshold(payload: dict[str, Any]) -> dict[str, Any]:
    """Check values against thresholds and return alert status."""
    metrics = payload.get("metrics", {})
    rules = payload.get("rules", {})
    # rules: {"metric_name": {"min": float, "max": float, "warn_min": float, "warn_max": float}}

    alerts: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    ok = True

    for name, rule in rules.items():
        value = metrics.get(name)
        if value is None:
            continue
        lo = rule.get("min", float("-inf"))
        hi = rule.get("max", float("inf"))
        warn_lo = rule.get("warn_min", lo)
        warn_hi = rule.get("warn_max", hi)

        if value < lo or value > hi:
            alerts.append({"metric": name, "value": value, "rule": rule, "severity": "critical"})
            ok = False
        elif value < warn_lo or value > warn_hi:
            warnings.append({"metric": name, "value": value, "rule": rule, "severity": "warning"})

    return {"ok": ok, "alerts": alerts, "warnings": warnings, "checked": len(rules)}


async def _monitor_heartbeat(payload: dict[str, Any]) -> dict[str, Any]:
    """Track periodic heartbeats and detect stale agents."""
    agents = payload.get("agents", {})
    now = payload.get("now") or time.time()
    stale_threshold = payload.get("stale_seconds", 300)
    dead_threshold = payload.get("dead_seconds", 900)

    stale: list[dict[str, Any]] = []
    dead: list[dict[str, Any]] = []
    healthy: list[str] = []

    for name, info in agents.items():
        last_seen = info.get("last_seen", 0)
        age = now - last_seen
        entry = {"name": name, "age_seconds": round(age, 1), "last_seen": last_seen}
        if age > dead_threshold:
            dead.append(entry)
        elif age > stale_threshold:
            stale.append(entry)
        else:
            healthy.append(name)

    return {
        "healthy": healthy,
        "stale": stale,
        "dead": dead,
        "healthy_count": len(healthy),
        "stale_count": len(stale),
        "dead_count": len(dead),
        "ok": len(dead) == 0,
    }


async def _monitor_anomaly(payload: dict[str, Any]) -> dict[str, Any]:
    """Detect anomalies in a time series using z-score."""
    values = payload.get("values", [])
    window = payload.get("window", 20)
    z_threshold = payload.get("z_threshold", 2.0)

    if len(values) < 3:
        return {"anomalies": [], "anomaly_count": 0, "mean": None, "std": None, "ok": True}

    # Use last `window` values as baseline, or all if fewer
    baseline = values[-window:] if len(values) > window else values
    mean_val = statistics.mean(baseline)
    std_val = statistics.stdev(baseline) if len(baseline) > 1 else 0.0

    anomalies: list[dict[str, Any]] = []
    if std_val > 0:
        for i, v in enumerate(values):
            z = abs(v - mean_val) / std_val
            if z > z_threshold:
                anomalies.append({"index": i, "value": v, "z_score": round(z, 2)})

    return {
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "mean": round(mean_val, 4),
        "std": round(std_val, 4) if std_val else 0.0,
        "ok": len(anomalies) == 0,
    }


# ─── Encoding Pack ──────────────────────────────────────────────────────

async def _encode_base64(payload: dict[str, Any]) -> dict[str, Any]:
    """Encode or decode base64."""
    import base64 as b64mod

    data = payload.get("data", "")
    direction = payload.get("direction", "encode")

    if direction == "decode":
        try:
            decoded = b64mod.b64decode(data).decode("utf-8", errors="replace")
            return {"result": decoded, "direction": "decode", "ok": True}
        except Exception as e:
            return {"result": "", "direction": "decode", "ok": False, "error": str(e)}
    else:
        encoded = b64mod.b64encode(data.encode("utf-8")).decode("ascii")
        return {"result": encoded, "direction": "encode", "ok": True}


async def _encode_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse or serialize JSON."""
    import json as json_mod

    direction = payload.get("direction", "parse")

    if direction == "parse":
        text = payload.get("text", "")
        try:
            parsed = json_mod.loads(text)
            return {"result": parsed, "direction": "parse", "ok": True}
        except json_mod.JSONDecodeError as e:
            return {"result": None, "direction": "parse", "ok": False, "error": str(e)}
    else:
        obj = payload.get("object", {})
        indent = payload.get("indent", 2)
        try:
            text = json_mod.dumps(obj, indent=indent, sort_keys=True, default=str)
            return {"result": text, "direction": "serialize", "ok": True}
        except (TypeError, ValueError) as e:
            return {"result": "", "direction": "serialize", "ok": False, "error": str(e)}


async def _encode_csv(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse records from CSV text or serialize records to CSV."""
    import csv as csv_mod
    import io

    direction = payload.get("direction", "parse")

    if direction == "parse":
        text = payload.get("text", "")
        reader = csv_mod.DictReader(io.StringIO(text))
        records = [dict(row) for row in reader]
        return {"records": records, "count": len(records), "direction": "parse", "ok": True}
    else:
        records = payload.get("records", [])
        if not records:
            return {"text": "", "direction": "serialize", "ok": True}
        output = io.StringIO()
        writer = csv_mod.DictWriter(output, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
        return {"text": output.getvalue(), "direction": "serialize", "ok": True}


async def _encode_url(payload: dict[str, Any]) -> dict[str, Any]:
    """Encode or decode URL components."""
    import urllib.parse as urlparse

    text = payload.get("text", "")
    direction = payload.get("direction", "encode")
    component = payload.get("component", "query")

    if direction == "decode":
        if component == "path":
            result = urlparse.unquote(text)
        else:
            result = urlparse.unquote_plus(text)
    else:
        if component == "path":
            result = urlparse.quote(text, safe="/")
        else:
            result = urlparse.quote_plus(text)

    return {"result": result, "direction": direction, "component": component, "ok": True}


def load_monitor_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register monitoring and alerting capabilities."""
    specs = []
    specs.append(builder.register(
        name="monitor-threshold",
        handler=_monitor_threshold,
        version="1.0.0",
        description="Check metrics against threshold rules, return alerts and warnings",
        inputs=["metrics", "rules"],
        outputs=["ok", "alerts", "warnings"],
        tags=["monitoring", "alerting", "threshold"],
    ))
    specs.append(builder.register(
        name="monitor-heartbeat",
        handler=_monitor_heartbeat,
        version="1.0.0",
        description="Track agent heartbeats, detect stale and dead agents",
        inputs=["agents", "now"],
        outputs=["healthy", "stale", "dead", "ok"],
        tags=["monitoring", "heartbeat", "health"],
    ))
    specs.append(builder.register(
        name="monitor-anomaly",
        handler=_monitor_anomaly,
        version="1.0.0",
        description="Detect anomalies in numeric time series using z-score analysis",
        inputs=["values"],
        outputs=["anomalies", "anomaly_count", "mean", "std", "ok"],
        tags=["monitoring", "anomaly", "statistics"],
    ))
    return specs


def load_encoding_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register encoding and serialization capabilities."""
    specs = []
    specs.append(builder.register(
        name="encode-base64",
        handler=_encode_base64,
        version="1.0.0",
        description="Encode or decode base64 strings",
        inputs=["data"],
        outputs=["result", "ok"],
        tags=["encoding", "base64"],
    ))
    specs.append(builder.register(
        name="encode-json",
        handler=_encode_json,
        version="1.0.0",
        description="Parse JSON text to object or serialize object to JSON",
        inputs=[],
        outputs=["result", "ok"],
        tags=["encoding", "json"],
    ))
    specs.append(builder.register(
        name="encode-csv",
        handler=_encode_csv,
        version="1.0.0",
        description="Parse CSV text to records or serialize records to CSV",
        inputs=[],
        outputs=["records", "text", "ok"],
        tags=["encoding", "csv"],
    ))
    specs.append(builder.register(
        name="encode-url",
        handler=_encode_url,
        version="1.0.0",
        description="Encode or decode URL components (query or path)",
        inputs=["text"],
        outputs=["result", "ok"],
        tags=["encoding", "url"],
    ))
    return specs


# ─── Scheduling Pack ────────────────────────────────────────────────────

async def _schedule_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Schedule a one-shot or recurring task."""
    topic = payload.get("topic", "")
    if not topic:
        return {"ok": False, "error": "topic is required"}
    delay = payload.get("delay_seconds", 0)
    interval = payload.get("interval_seconds", 0)
    priority = payload.get("priority", 0.5)
    job_payload = payload.get("payload", {})
    scheduler = payload.get("_scheduler")
    if scheduler is None:
        return {"ok": False, "error": "no scheduler available"}
    if interval > 0:
        job = scheduler.every(topic, interval_seconds=interval, payload=job_payload)
        job.priority = priority
    else:
        job = scheduler.once(topic, delay_seconds=delay, payload=job_payload)
        job.priority = priority
    return {"ok": True, "job_id": job.job_id, "topic": topic, "kind": job.kind.value}


async def _schedule_cancel(payload: dict[str, Any]) -> dict[str, Any]:
    """Cancel a scheduled job by ID."""
    job_id = payload.get("job_id", "")
    scheduler = payload.get("_scheduler")
    if scheduler is None:
        return {"ok": False, "error": "no scheduler available"}
    for job in scheduler.pending():
        if job.job_id == job_id:
            job.status = "cancelled"
            return {"ok": True, "job_id": job_id}
    return {"ok": False, "error": f"job {job_id!r} not found"}


async def _schedule_list(payload: dict[str, Any]) -> dict[str, Any]:
    """List pending/running scheduled jobs."""
    scheduler = payload.get("_scheduler")
    if scheduler is None:
        return {"ok": False, "error": "no scheduler available"}
    jobs = []
    for job in scheduler.pending():
        jobs.append({
            "job_id": job.job_id,
            "topic": job.topic,
            "kind": job.kind.value,
            "status": job.status.value if hasattr(job.status, 'value') else str(job.status),
            "priority": job.priority,
            "run_count": job.run_count,
            "next_run_at": job.next_run_at,
        })
    return {"ok": True, "jobs": jobs, "count": len(jobs)}


def load_schedule_pack(builder: CapabilityBuilder, scheduler: Any) -> list[CapSpec]:
    """Load scheduling capabilities backed by an AgentScheduler."""
    # Wrap handlers to inject scheduler reference
    async def _sched_task(p: dict[str, Any]) -> dict[str, Any]:
        p["_scheduler"] = scheduler
        return await _schedule_task(p)

    async def _sched_cancel(p: dict[str, Any]) -> dict[str, Any]:
        p["_scheduler"] = scheduler
        return await _schedule_cancel(p)

    async def _sched_list(p: dict[str, Any]) -> dict[str, Any]:
        p["_scheduler"] = scheduler
        return await _schedule_list(p)

    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="schedule-task",
        handler=_sched_task,
        version="1.0.0",
        description="Schedule a one-shot or recurring task",
        inputs=["topic"],
        outputs=["ok", "job_id"],
        tags=["scheduling", "tasks"],
    ))
    specs.append(builder.register(
        name="schedule-cancel",
        handler=_sched_cancel,
        version="1.0.0",
        description="Cancel a scheduled job by ID",
        inputs=["job_id"],
        outputs=["ok"],
        tags=["scheduling", "tasks"],
    ))
    specs.append(builder.register(
        name="schedule-list",
        handler=_sched_list,
        version="1.0.0",
        description="List pending and running scheduled jobs",
        inputs=[],
        outputs=["ok", "jobs", "count"],
        tags=["scheduling", "tasks"],
    ))
    return specs


# ─── Planning Pack ───────────────────────────────────────────────────────

async def _plan_toposort(payload: dict[str, Any]) -> dict[str, Any]:
    """Topological sort of tasks with dependency ordering."""
    tasks = payload.get("tasks", [])
    if not tasks:
        return {"ok": False, "error": "no tasks provided"}
    # Build adjacency: task_name -> set of dependency names
    graph: dict[str, set[str]] = {}
    task_map: dict[str, dict[str, Any]] = {}
    for task in tasks:
        name = task.get("name", "")
        if not name:
            return {"ok": False, "error": "each task needs a 'name'"}
        deps = set(task.get("depends_on", []))
        graph[name] = deps
        task_map[name] = task
    # Kahn's algorithm
    in_degree = {n: 0 for n in graph}
    for n, deps in graph.items():
        for d in deps:
            if d in in_degree:
                in_degree[d]  # ensure exists
    # recalc in-degree properly
    in_degree = {n: 0 for n in graph}
    for n, deps in graph.items():
        for d in deps:
            if d in in_degree:
                pass  # d doesn't depend on n; n depends on d
    # Correct: in_degree[x] = number of tasks x depends on that haven't been processed
    queue: list[str] = [n for n, deps in graph.items() if not deps]
    order: list[str] = []
    resolved: set[str] = set()
    while queue:
        # Sort for deterministic output (priority-based: lower priority value = higher priority)
        queue.sort(key=lambda n: task_map[n].get("priority", 0.5))
        node = queue.pop(0)
        order.append(node)
        resolved.add(node)
        for n, deps in graph.items():
            if n not in resolved and n not in queue:
                if deps <= resolved:
                    queue.append(n)
    # Check for cycles
    if len(order) != len(graph):
        missing = set(graph.keys()) - set(order)
        return {"ok": False, "error": f"circular dependency involving: {missing}"}
    return {
        "ok": True,
        "order": order,
        "total": len(order),
        "details": [
            {
                "name": name,
                "depends_on": list(graph.get(name, set())),
                "priority": task_map[name].get("priority", 0.5),
            }
            for name in order
        ],
    }


async def _plan_priority_queue(payload: dict[str, Any]) -> dict[str, Any]:
    """Sort tasks by priority (lower = more urgent) with optional grouping."""
    tasks = payload.get("tasks", [])
    group_by = payload.get("group_by")
    if not tasks:
        return {"ok": False, "error": "no tasks provided"}
    for t in tasks:
        if "name" not in t:
            return {"ok": False, "error": "each task needs a 'name'"}
        t.setdefault("priority", 0.5)
    sorted_tasks = sorted(tasks, key=lambda t: t["priority"])
    result: dict[str, Any] = {"ok": True, "order": [t["name"] for t in sorted_tasks], "total": len(sorted_tasks)}
    if group_by:
        groups: dict[str, list[str]] = {}
        for t in sorted_tasks:
            key = str(t.get(group_by, "ungrouped"))
            groups.setdefault(key, []).append(t["name"])
        result["groups"] = groups
    return result


async def _plan_estimate(payload: dict[str, Any]) -> dict[str, Any]:
    """Estimate total time for a task plan based on individual estimates."""
    tasks = payload.get("tasks", [])
    parallelism = payload.get("parallelism", 1)
    if not tasks:
        return {"ok": False, "error": "no tasks provided"}
    total_serial = sum(t.get("estimate_seconds", 0) for t in tasks)
    # Simple model: divide by parallelism, add 10% coordination overhead
    estimated = (total_serial / max(parallelism, 1)) * 1.1
    critical_path = max((t.get("estimate_seconds", 0) for t in tasks), default=0)
    return {
        "ok": True,
        "total_serial_seconds": total_serial,
        "estimated_seconds": round(estimated, 1),
        "parallelism": parallelism,
        "critical_path_seconds": critical_path,
        "task_count": len(tasks),
    }


def load_planning_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load planning and task-orchestration capabilities."""
    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="plan-toposort",
        handler=_plan_toposort,
        version="1.0.0",
        description="Topological sort of tasks with dependency ordering",
        inputs=["tasks"],
        outputs=["ok", "order"],
        tags=["planning", "scheduling", "dependencies"],
    ))
    specs.append(builder.register(
        name="plan-priority-queue",
        handler=_plan_priority_queue,
        version="1.0.0",
        description="Sort tasks by priority with optional grouping",
        inputs=["tasks"],
        outputs=["ok", "order"],
        tags=["planning", "scheduling", "priority"],
    ))
    specs.append(builder.register(
        name="plan-estimate",
        handler=_plan_estimate,
        version="1.0.0",
        description="Estimate execution time for a task plan",
        inputs=["tasks"],
        outputs=["ok", "estimated_seconds"],
        tags=["planning", "estimation"],
    ))
    return specs


# ─── Fog Awareness Pack ─────────────────────────────────────────────────

async def _fog_blind_spots(payload: dict[str, Any]) -> dict[str, Any]:
    """Detect blind spots — topics with no complementary peer on mesh."""
    agent = payload.get("__agent__")
    if agent is None:
        return {"error": "No agent attached", "ok": False}

    spots = agent.blind_spot()
    results = []
    for s in spots:
        results.append({
            "topic": s.topic,
            "kind": s.kind,
            "depth": s.depth,
            "recurrence": s.recurrence,
        })
    return {"blind_spots": results, "count": len(results), "ok": True}


async def _fog_map_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Snapshot of the agent's epistemic fog map."""
    agent = payload.get("__agent__")
    if agent is None:
        return {"error": "No agent attached", "ok": False}

    fog = agent.fog()
    gaps = []
    for g in fog.gaps.values():
        gaps.append({
            "key": g.key,
            "kind": g.kind.value,
            "domain": g.domain,
            "confidence": g.confidence,
        })
    return {
        "agent": fog.agent_id,
        "gap_count": len(gaps),
        "gaps": gaps,
        "ok": True,
    }


async def _fog_seam_measure(payload: dict[str, Any]) -> dict[str, Any]:
    """Measure fog seam tension between this agent and another agent's fog map."""
    agent = payload.get("__agent__")
    if agent is None:
        return {"error": "No agent attached", "ok": False}

    target_name = payload.get("target_agent", "")
    if not target_name:
        return {"error": "target_agent is required", "ok": False}

    my_fog = agent.fog()

    # Build target fog from registry if possible
    from .fog import FogMap, GapKind
    target_fog = FogMap(agent_id=target_name)
    rec = agent._registry._records.get(target_name)
    if rec:
        for cap in rec.capabilities:
            target_fog.add(key=cap, kind=GapKind.KNOWN_UNKNOWN, domain="capability")

    seam = agent.fog_seam(target_fog)
    return {
        "agents": f"{my_fog.agent_id}↔{target_name}",
        "tension": round(seam.tension, 3),
        "a_only": list(seam.only_in_a),
        "b_only": list(seam.only_in_b),
        "shared": list(seam.shared),
        "high_potential": seam.tension > 0.5,
        "ok": True,
    }


async def _fog_atlas_holes(payload: dict[str, Any]) -> dict[str, Any]:
    """Find atlas holes — regions of the mesh no agent covers."""
    agent = payload.get("__agent__")
    if agent is None:
        return {"error": "No agent attached", "ok": False}

    atlas = agent.atlas()
    holes = atlas.holes()
    return {
        "holes": holes,
        "count": len(holes),
        "total_charts": len(atlas.charts),
        "ok": True,
    }


async def _fog_discovery(payload: dict[str, Any]) -> dict[str, Any]:
    """Discover agents that can fill fog gaps for a given topic."""
    agent = payload.get("__agent__")
    if agent is None:
        return {"error": "No agent attached", "ok": False}

    from .discovery import Discovery
    disco = Discovery(agent)
    topic = payload.get("topic", "")
    if not topic:
        return {"error": "topic is required", "ok": False}

    result = disco.search_local(topic)
    return {
        "query": topic,
        "hits": [
            {
                "agent": h.agent_name,
                "capability": h.capability,
                "relevance": round(h.relevance, 3),
            }
            for h in result.top(10)
        ],
        "total": len(result.hits),
        "ok": True,
    }


def load_fog_pack(builder: CapabilityBuilder, agent: Any) -> list[CapSpec]:
    """Register fog awareness capabilities (requires agent reference).

    Caps:lind_spots, fog_map, seam_measure, atlas_holes, fog_discover.
    Each cap integrates with the fog subsystem for epistemic awareness.
    """

    async def _blind_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _fog_blind_spots({**payload, "__agent__": agent})

    async def _map_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _fog_map_snapshot({**payload, "__agent__": agent})

    async def _seam_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _fog_seam_measure({**payload, "__agent__": agent})

    async def _atlas_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _fog_atlas_holes({**payload, "__agent__": agent})

    async def _disco_wrapped(payload: dict[str, Any]) -> dict[str, Any]:
        return await _fog_discovery({**payload, "__agent__": agent})

    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="fog-blind-spots",
        handler=_blind_wrapped,
        version="1.0.0",
        description="Detect blind spots — topics with no complementary peer on mesh",
        inputs=[],
        outputs=["blind_spots", "count", "ok"],
        tags=["fog", "awareness", "blind-spots"],
    ))
    specs.append(builder.register(
        name="fog-map",
        handler=_map_wrapped,
        version="1.0.0",
        description="Snapshot of agent's epistemic fog map — gaps and unknowns",
        inputs=[],
        outputs=["agent", "gap_count", "gaps", "ok"],
        tags=["fog", "awareness", "map"],
    ))
    specs.append(builder.register(
        name="fog-seam-measure",
        handler=_seam_wrapped,
        version="1.0.0",
        description="Measure fog seam tension between this agent and another",
        inputs=["target_agent"],
        outputs=["agents", "tension", "a_only", "b_only", "shared", "ok"],
        tags=["fog", "awareness", "seam"],
    ))
    specs.append(builder.register(
        name="fog-atlas-holes",
        handler=_atlas_wrapped,
        version="1.0.0",
        description="Find atlas holes — mesh regions no agent covers",
        inputs=[],
        outputs=["holes", "count", "total_charts", "ok"],
        tags=["fog", "awareness", "atlas", "holes"],
    ))
    specs.append(builder.register(
        name="fog-discover",
        handler=_disco_wrapped,
        version="1.0.0",
        description="Discover agents that can fill fog gaps for a given topic",
        inputs=["topic"],
        outputs=["query", "hits", "total", "ok"],
        tags=["fog", "awareness", "discovery"],
    ))
    return specs


# ─── Reasoning Pack ──────────────────────────────────────────────────────

async def _reasoning_decompose(payload: dict[str, Any]) -> dict[str, Any]:
    """Break a complex problem into ordered sub-problems."""
    problem = payload.get("problem", "")
    if not problem:
        raise ValueError("problem is required")
    max_steps = min(payload.get("max_steps", 6), 20)
    
    # Heuristic decomposition: split on common delimiters and structures
    steps: list[dict[str, Any]] = []
    
    # Detect compound questions
    connectors = [" and ", " but ", " then ", " also ", " as well as ", " while "]
    parts = [problem]
    for conn in connectors:
        new_parts: list[str] = []
        for part in parts:
            new_parts.extend(part.split(conn))
        parts = new_parts
    
    # If compound, each part is a sub-problem
    if len(parts) > 1:
        for i, part in enumerate(parts):
            part = part.strip().rstrip(".?,!")
            if part:
                steps.append({
                    "step": i + 1,
                    "description": part,
                    "type": "sub_problem",
                    "depends_on": [i] if i > 0 else [],
                })
    else:
        # Single problem — decompose by analysis phases
        phases = [
            ("understand", "Identify key concepts and constraints"),
            ("gather", "Collect relevant information and data"),
            ("analyze", "Apply reasoning to the gathered information"),
            ("conclude", "Synthesize findings into an answer"),
        ]
        for i, (phase_name, desc) in enumerate(phases[:max_steps]):
            steps.append({
                "step": i + 1,
                "description": f"{desc} for: {problem}",
                "type": phase_name,
                "depends_on": [i] if i > 0 else [],
            })
    
    steps = steps[:max_steps]
    return {
        "problem": problem,
        "steps": steps,
        "total": len(steps),
        "is_compound": len(parts) > 1,
        "ok": True,
    }


async def _reasoning_synthesize(payload: dict[str, Any]) -> dict[str, Any]:
    """Synthesize multiple inputs into a unified conclusion."""
    inputs = payload.get("inputs", [])
    if not inputs:
        raise ValueError("inputs list is required")
    
    goal = payload.get("goal", "synthesize")
    
    # Structural analysis
    str_items = [str(i) for i in inputs]
    total_items = len(str_items)
    avg_len = sum(len(s) for s in str_items) / max(total_items, 1)
    
    # Find common themes via trigram overlap
    all_trigrams: list[set[str]] = []
    for item in str_items:
        t = f"  {item.lower()}  "
        trigrams = {t[j:j+3] for j in range(len(t) - 2)}
        all_trigrams.append(trigrams)
    
    # Pairwise similarity
    similarities: list[float] = []
    for i in range(len(all_trigrams)):
        for j in range(i + 1, len(all_trigrams)):
            a, b = all_trigrams[i], all_trigrams[j]
            if a and b:
                sim = len(a & b) / len(a | b)
                similarities.append(sim)
    
    coherence = statistics.mean(similarities) if similarities else 0.0
    
    # Identify consensus vs divergence
    consensus: list[str] = []
    divergence: list[str] = []
    if all_trigrams and len(all_trigrams) > 1:
        common = all_trigrams[0]
        for t in all_trigrams[1:]:
            common = common & t
        # Extract fragments that appear in all inputs
        for trig in list(common)[:10]:
            for item in str_items:
                if trig in item.lower():
                    # Find the word containing this trigram
                    words = item.split()
                    for w in words:
                        if trig.strip() in w.lower():
                            if w not in consensus:
                                consensus.append(w)
                            break
                    break
    
    return {
        "goal": goal,
        "input_count": total_items,
        "coherence": round(coherence, 3),
        "consensus_terms": consensus[:10],
        "divergence_detected": coherence < 0.3,
        "summary": (
            f"{total_items} inputs analyzed, "
            f"coherence={coherence:.2f}. "
            f"{'High agreement' if coherence > 0.6 else 'Mixed signals' if coherence > 0.3 else 'Low agreement'}"
        ),
        "ok": True,
    }


async def _reasoning_decide(payload: dict[str, Any]) -> dict[str, Any]:
    """Multi-criteria decision analysis across options."""
    options = payload.get("options", [])
    if len(options) < 2:
        raise ValueError("At least 2 options required")
    
    criteria = payload.get("criteria", [])
    if not criteria:
        # Default criteria
        criteria = ["feasibility", "impact", "cost"]
    
    weights = payload.get("weights", {})
    
    # Score each option against each criterion
    results: list[dict[str, Any]] = []
    for opt in options:
        opt_str = str(opt)
        scores: dict[str, float] = {}
        reasons: list[str] = []
        
        for criterion in criteria:
            w = weights.get(criterion, 1.0)
            # Heuristic scoring based on option properties
            score = 0.5  # neutral baseline
            opt_lower = opt_str.lower()
            
            if criterion == "feasibility":
                if any(w in opt_lower for w in ["simple", "easy", "direct", "existing"]):
                    score = 0.8
                elif any(w in opt_lower for w in ["complex", "hard", "rewrite"]):
                    score = 0.3
            elif criterion == "impact":
                if any(w in opt_lower for w in ["high", "critical", "essential", "key"]):
                    score = 0.85
                elif any(w in opt_lower for w in ["low", "minor", "nice-to-have"]):
                    score = 0.2
            elif criterion == "cost":
                if any(w in opt_lower for w in ["cheap", "free", "minimal", "low"]):
                    score = 0.8
                elif any(w in opt_lower for w in ["expensive", "high", "significant"]):
                    score = 0.25
            else:
                # Generic: use string length as proxy for specificity
                score = min(len(opt_str) / 100.0, 1.0) * 0.5 + 0.25
            
            scores[criterion] = round(score * w, 3)
            if score > 0.6:
                reasons.append(f"{criterion}: strong ({score:.1f})")
        
        weighted_total = sum(scores.values()) / sum(
            weights.get(c, 1.0) for c in criteria
        )
        results.append({
            "option": opt_str,
            "scores": scores,
            "weighted_total": round(weighted_total, 3),
            "strengths": reasons,
        })
    
    # Rank by weighted total
    results.sort(key=lambda r: r["weighted_total"], reverse=True)
    
    return {
        "criteria": criteria,
        "weights": weights or {c: 1.0 for c in criteria},
        "ranked_options": results,
        "recommended": results[0]["option"] if results else None,
        "ok": True,
    }


async def _reasoning_chain(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a chain-of-thought reasoning trace."""
    premise = payload.get("premise", "")
    if not premise:
        raise ValueError("premise is required")
    
    max_hops = min(payload.get("max_hops", 5), 15)
    
    # Build reasoning chain
    chain: list[dict[str, Any]] = []
    current = premise
    
    for hop in range(max_hops):
        # Analyze current state
        words = current.split()
        key_terms = [w for w in words if len(w) > 4][:5]
        
        # Deductive step: extract implications
        implications: list[str] = []
        if " because " in current.lower():
            implications.append("causal link detected — verify both sides")
        if " therefore " in current.lower() or " so " in current.lower():
            implications.append("conclusion step — check for logical leaps")
        if any(w in current.lower() for w in ["all", "every", "always", "never"]):
            implications.append("universal claim — look for counterexamples")
        if " implies " in current.lower() or " leads to " in current.lower():
            implications.append("implication chain — trace dependency")
        
        if not implications:
            # Generate next reasoning step
            if hop == 0:
                implications.append(f"premise accepted: identify key claims")
            else:
                implications.append("no further logical structure detected")
        
        confidence = max(0.0, 1.0 - hop * 0.15)
        chain.append({
            "hop": hop + 1,
            "state": current[:200],
            "key_terms": key_terms,
            "implications": implications,
            "confidence": round(confidence, 2),
        })
        
        # Advance: shorten to key terms for next hop
        if key_terms:
            current = " ".join(key_terms)
        else:
            break
        
        # Stop if confidence drops too low
        if confidence < 0.3:
            break
    
    final_confidence = chain[-1]["confidence"] if chain else 0.0
    
    return {
        "premise": premise[:200],
        "chain": chain,
        "hops": len(chain),
        "final_confidence": final_confidence,
        "reasoning_depth": "deep" if len(chain) >= 4 else "moderate" if len(chain) >= 2 else "shallow",
        "ok": True,
    }


def load_reasoning_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register reasoning and analysis capabilities.

    Caps: decompose, synthesize, decide, chain.
    Enables structured reasoning: problem decomposition, multi-source
    synthesis, multi-criteria decision making, and chain-of-thought tracing.
    """
    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="reasoning-decompose",
        handler=_reasoning_decompose,
        version="1.0.0",
        description="Break a complex problem into ordered sub-problems",
        inputs=["problem"],
        outputs=["steps", "total", "is_compound", "ok"],
        tags=["reasoning", "planning", "decomposition"],
    ))
    specs.append(builder.register(
        name="reasoning-synthesize",
        handler=_reasoning_synthesize,
        version="1.0.0",
        description="Synthesize multiple inputs into a unified conclusion with coherence scoring",
        inputs=["inputs"],
        outputs=["coherence", "consensus_terms", "summary", "ok"],
        tags=["reasoning", "synthesis", "analysis"],
    ))
    specs.append(builder.register(
        name="reasoning-decide",
        handler=_reasoning_decide,
        version="1.0.0",
        description="Multi-criteria decision analysis across options",
        inputs=["options"],
        outputs=["ranked_options", "recommended", "ok"],
        tags=["reasoning", "decision", "analysis"],
    ))
    specs.append(builder.register(
        name="reasoning-chain",
        handler=_reasoning_chain,
        version="1.0.0",
        description="Execute a chain-of-thought reasoning trace from a premise",
        inputs=["premise"],
        outputs=["chain", "hops", "final_confidence", "ok"],
        tags=["reasoning", "chain-of-thought", "analysis"],
    ))
    return specs


# ─── Network Communication Pack ─────────────────────────────────────────

async def _net_compose(payload: dict[str, Any]) -> dict[str, Any]:
    """Compose a structured inter-agent message with envelope metadata."""
    to = payload.get("to", [])
    subject = payload.get("subject", "")
    body = payload.get("body", {})
    priority = payload.get("priority", 0.5)  # 0=low, 1=critical
    ttl_seconds = payload.get("ttl_seconds", 300)
    msg_type = payload.get("type", "inform")  # inform | request | command | alert
    reply_to = payload.get("reply_to")
    correlation_id = payload.get("correlation_id") or f"msg-{uuid.uuid4().hex[:12]}"
    trace_id = payload.get("trace_id") or f"trace-{uuid.uuid4().hex[:8]}"

    if isinstance(to, str):
        to = [to]

    now = time.time()
    envelope = {
        "message_id": f"msg-{uuid.uuid4().hex[:12]}",
        "correlation_id": correlation_id,
        "trace_id": trace_id,
        "from": payload.get("from", "unknown"),
        "to": to,
        "subject": subject,
        "type": msg_type,
        "priority": round(min(max(priority, 0.0), 1.0), 2),
        "ttl_seconds": ttl_seconds,
        "expires_at": round(now + ttl_seconds, 1),
        "created_at": round(now, 1),
        "reply_to": reply_to,
        "body": body,
        "hops": 0,
    }

    return {"envelope": envelope, "ok": True}


async def _net_relay(payload: dict[str, Any]) -> dict[str, Any]:
    """Relay a message through a chain of agents, tracking the route."""
    chain = payload.get("chain", [])  # ordered list of agent names
    envelope = payload.get("envelope", {})
    current_hop = payload.get("current_hop", 0)

    if not chain:
        return {"error": "chain is empty", "ok": False}

    if not envelope:
        envelope = (await _net_compose(payload)).get("envelope", {})

    hops = envelope.get("hops", 0) + 1
    envelope["hops"] = hops
    visited = envelope.get("visited", [])
    current_agent = chain[current_hop] if current_hop < len(chain) else None

    if current_agent:
        visited.append({"agent": current_agent, "at": round(time.time(), 1), "hop": hops})

    envelope["visited"] = visited

    next_hop = current_hop + 1
    remaining = chain[next_hop:] if next_hop < len(chain) else []
    is_final = next_hop >= len(chain)

    return {
        "envelope": envelope,
        "current_agent": current_agent,
        "next_hop": next_hop if not is_final else None,
        "remaining": remaining,
        "is_final": is_final,
        "total_hops": hops,
        "ok": True,
    }


async def _net_broadcast(payload: dict[str, Any]) -> dict[str, Any]:
    """Fan-out a message to multiple recipients with acknowledgement tracking."""
    recipients = payload.get("recipients", [])
    subject = payload.get("subject", "")
    body = payload.get("body", {})
    require_ack = payload.get("require_ack", True)
    ack_timeout = payload.get("ack_timeout_seconds", 30)

    if isinstance(recipients, str):
        recipients = [recipients]

    if not recipients:
        return {"error": "no recipients", "ok": False}

    envelope = (await _net_compose({
        "to": recipients,
        "subject": subject,
        "body": body,
        "type": "inform",
        "from": payload.get("from", "unknown"),
    })).get("envelope", {})

    acks: dict[str, str] = {}
    if require_ack:
        now = time.time()
        for r in recipients:
            acks[r] = "pending"

    return {
        "envelope": envelope,
        "recipients": recipients,
        "recipient_count": len(recipients),
        "acks": acks,
        "ack_timeout_seconds": ack_timeout,
        "delivered_at": round(time.time(), 1),
        "ok": True,
    }


async def _net_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a request-response contract with timeout and retry policy."""
    target = payload.get("target", "")
    capability = payload.get("capability", "")
    request_body = payload.get("body", {})
    timeout_seconds = payload.get("timeout_seconds", 60)
    max_retries = payload.get("max_retries", 2)
    priority = payload.get("priority", 0.5)

    if not target or not capability:
        return {"error": "target and capability required", "ok": False}

    request_id = f"req-{uuid.uuid4().hex[:12]}"
    now = time.time()

    contract = {
        "request_id": request_id,
        "target": target,
        "capability": capability,
        "body": request_body,
        "timeout_seconds": timeout_seconds,
        "max_retries": max_retries,
        "priority": round(min(max(priority, 0.0), 1.0), 2),
        "created_at": round(now, 1),
        "expires_at": round(now + timeout_seconds, 1),
        "attempts": 0,
        "status": "pending",  # pending | sent | completed | failed | timeout
    }

    return {
        "contract": contract,
        "request_id": request_id,
        "ok": True,
    }


async def _net_ack(payload: dict[str, Any]) -> dict[str, Any]:
    """Acknowledge receipt of a message, optionally with a response."""
    message_id = payload.get("message_id", "")
    status = payload.get("status", "received")  # received | processing | completed | rejected
    response = payload.get("response", {})
    latency_ms = payload.get("latency_ms", 0.0)

    if not message_id:
        return {"error": "message_id required", "ok": False}

    ack = {
        "message_id": message_id,
        "status": status,
        "response": response,
        "latency_ms": latency_ms,
        "acked_at": round(time.time(), 1),
    }

    return {"ack": ack, "ok": True}


def load_network_pack(builder: CapabilityBuilder, agent: Any | None = None) -> list[CapSpec]:
    """Register network communication capabilities.

    Caps: compose, relay, broadcast, request, ack.
    Enables structured inter-agent messaging with envelope metadata,
    relay chains, fan-out with acknowledgement tracking, and
    request-response contracts with timeout/retry policies.
    """
    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="net-compose",
        handler=_net_compose,
        version="1.0.0",
        description="Compose a structured inter-agent message with envelope, priority, and TTL",
        inputs=["to", "subject", "body"],
        outputs=["envelope", "ok"],
        tags=["network", "messaging", "compose"],
    ))
    specs.append(builder.register(
        name="net-relay",
        handler=_net_relay,
        version="1.0.0",
        description="Relay a message through an ordered chain of agents with hop tracking",
        inputs=["chain"],
        outputs=["envelope", "current_agent", "is_final", "ok"],
        tags=["network", "messaging", "relay"],
    ))
    specs.append(builder.register(
        name="net-broadcast",
        handler=_net_broadcast,
        version="1.0.0",
        description="Fan-out a message to multiple recipients with acknowledgement tracking",
        inputs=["recipients", "subject", "body"],
        outputs=["envelope", "recipients", "acks", "ok"],
        tags=["network", "messaging", "broadcast"],
    ))
    specs.append(builder.register(
        name="net-request",
        handler=_net_request,
        version="1.0.0",
        description="Create a request-response contract with timeout and retry policy",
        inputs=["target", "capability"],
        outputs=["contract", "request_id", "ok"],
        tags=["network", "messaging", "request-response"],
    ))
    specs.append(builder.register(
        name="net-ack",
        handler=_net_ack,
        version="1.0.0",
        description="Acknowledge receipt of a message with optional response payload",
        inputs=["message_id"],
        outputs=["ack", "ok"],
        tags=["network", "messaging", "acknowledgement"],
    ))
    return specs


# ─── Memory Pack ────────────────────────────────────────────────────────

# In-process memory store shared across all memory-pack instances.
_memory_kv_store: dict[str, dict[str, Any]] = {}


async def _memory_store(payload: dict[str, Any]) -> dict[str, Any]:
    """Store a key-value entry with optional tags and TTL."""
    key = payload.get("key", "")
    value = payload.get("value")
    tags = payload.get("tags", [])
    ttl = payload.get("ttl", 0)  # seconds; 0 = no expiry

    if not key:
        return {"ok": False, "error": "key is required"}

    entry: dict[str, Any] = {
        "key": key,
        "value": value,
        "tags": list(tags),
        "created_at": time.time(),
        "updated_at": time.time(),
        "ttl": ttl,
        "expires_at": time.time() + ttl if ttl > 0 else None,
    }

    _memory_kv_store[key] = entry
    return {"ok": True, "key": key, "created_at": entry["created_at"]}


async def _memory_retrieve(payload: dict[str, Any]) -> dict[str, Any]:
    """Retrieve a stored entry by key, respecting TTL expiry."""
    key = payload.get("key", "")
    if not key:
        return {"ok": False, "error": "key is required"}

    entry = _memory_kv_store.get(key)
    if entry is None:
        return {"ok": False, "error": "not_found", "key": key}

    # Check expiry
    expires_at = entry.get("expires_at")
    if expires_at is not None and time.time() > expires_at:
        del _memory_kv_store[key]
        return {"ok": False, "error": "expired", "key": key}

    return {
        "ok": True,
        "key": key,
        "value": entry["value"],
        "tags": entry["tags"],
        "created_at": entry["created_at"],
        "updated_at": entry["updated_at"],
    }


async def _memory_search(payload: dict[str, Any]) -> dict[str, Any]:
    """Search entries by tag, prefix, or text match."""
    tag = payload.get("tag")
    prefix = payload.get("prefix")
    query = payload.get("query", "")
    limit = min(payload.get("limit", 20), 100)

    now = time.time()
    results: list[dict[str, Any]] = []

    for entry in _memory_kv_store.values():
        # Skip expired
        exp = entry.get("expires_at")
        if exp is not None and now > exp:
            continue

        match = False
        if tag and tag in entry["tags"]:
            match = True
        if prefix and entry["key"].startswith(prefix):
            match = True
        if query and query.lower() in str(entry["value"]).lower():
            match = True
        if not tag and not prefix and not query:
            match = True  # list all

        if match:
            results.append({
                "key": entry["key"],
                "value": entry["value"],
                "tags": entry["tags"],
                "created_at": entry["created_at"],
            })
            if len(results) >= limit:
                break

    return {"ok": True, "results": results, "count": len(results)}


async def _memory_summarize(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize stored entries — count, tag distribution, oldest/newest."""
    now = time.time()
    tag_counts: dict[str, int] = {}
    total = 0
    oldest = None
    newest = None

    for entry in _memory_kv_store.values():
        exp = entry.get("expires_at")
        if exp is not None and now > exp:
            continue
        total += 1
        for t in entry["tags"]:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        created = entry["created_at"]
        if oldest is None or created < oldest:
            oldest = created
        if newest is None or created > newest:
            newest = created

    return {
        "ok": True,
        "total_entries": total,
        "tag_distribution": tag_counts,
        "oldest_created_at": oldest,
        "newest_created_at": newest,
    }


async def _memory_forget(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove entries by key or tag. Returns count of removed entries."""
    key = payload.get("key")
    tag = payload.get("tag")

    if key:
        if key in _memory_kv_store:
            del _memory_kv_store[key]
            return {"ok": True, "removed": 1}
        return {"ok": True, "removed": 0}

    if tag:
        to_remove = [k for k, v in _memory_kv_store.items() if tag in v.get("tags", [])]
        for k in to_remove:
            del _memory_kv_store[k]
        return {"ok": True, "removed": len(to_remove)}

    return {"ok": False, "error": "key or tag required"}


def load_memory_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register memory and knowledge management capabilities.

    Caps: store, retrieve, search, summarize, forget.
    Provides an in-process key-value store with tags, TTL expiry,
    prefix/tag/text search, and entry statistics.
    """
    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="memory-store",
        handler=_memory_store,
        version="1.0.0",
        description="Store a key-value entry with optional tags and TTL expiry",
        inputs=["key", "value"],
        outputs=["ok", "key", "created_at"],
        tags=["memory", "storage", "kv"],
    ))
    specs.append(builder.register(
        name="memory-retrieve",
        handler=_memory_retrieve,
        version="1.0.0",
        description="Retrieve a stored entry by key, respecting TTL expiry",
        inputs=["key"],
        outputs=["ok", "key", "value", "tags"],
        tags=["memory", "retrieval"],
    ))
    specs.append(builder.register(
        name="memory-search",
        handler=_memory_search,
        version="1.0.0",
        description="Search entries by tag, key prefix, or text content match",
        inputs=[],
        outputs=["ok", "results", "count"],
        tags=["memory", "search"],
    ))
    specs.append(builder.register(
        name="memory-summarize",
        handler=_memory_summarize,
        version="1.0.0",
        description="Summarize stored entries — count, tag distribution, time range",
        inputs=[],
        outputs=["ok", "total_entries", "tag_distribution"],
        tags=["memory", "statistics"],
    ))
    specs.append(builder.register(
        name="memory-forget",
        handler=_memory_forget,
        version="1.0.0",
        description="Remove entries by key or tag, returns count removed",
        inputs=[],
        outputs=["ok", "removed"],
        tags=["memory", "deletion"],
    ))
    return specs


# ─── Tool-Use Pack ──────────────────────────────────────────────────────

# Lightweight tool registry for describing, selecting, and composing tools.
# Independent of the main CapabilityBuilder so agents can reason about
# *external* tools they don't own but can invoke.

_tool_registry: dict[str, dict[str, Any]] = {}


async def _tool_describe(payload: dict[str, Any]) -> dict[str, Any]:
    """Register a tool description in the tool registry."""
    name = payload.get("name")
    if not name:
        return {"ok": False, "error": "name required"}
    _tool_registry[name] = {
        "name": name,
        "description": payload.get("description", ""),
        "inputs": payload.get("inputs", []),
        "outputs": payload.get("outputs", []),
        "tags": payload.get("tags", []),
        "examples": payload.get("examples", []),
    }
    return {"ok": True, "tool": name}


async def _tool_list(payload: dict[str, Any]) -> dict[str, Any]:
    """List all registered tools, optionally filtered by tag."""
    tag_filter = payload.get("tag")
    tools = []
    for t in _tool_registry.values():
        if tag_filter and tag_filter not in t["tags"]:
            continue
        tools.append(t)
    return {"ok": True, "tools": tools, "count": len(tools)}


async def _tool_select(payload: dict[str, Any]) -> dict[str, Any]:
    """Select the best tool for a task description using trigram similarity."""
    task = payload.get("task", "")
    if not task:
        return {"ok": False, "error": "task required"}
    if not _tool_registry:
        return {"ok": False, "error": "no tools registered"}

    best_name = ""
    best_score = 0.0
    for name, t in _tool_registry.items():
        corpus = f"{t['name']} {t['description']} {' '.join(t['tags'])}"
        score = _trigram_similarity(task, corpus)
        if score > best_score:
            best_score = score
            best_name = name

    if best_score < 0.10:
        return {"ok": False, "error": "no suitable tool", "best_score": best_score}

    return {"ok": True, "tool": _tool_registry[best_name], "score": round(best_score, 3)}


async def _tool_chain(payload: dict[str, Any]) -> dict[str, Any]:
    """Plan a chain of tools to accomplish a multi-step task.

    Given a task and available tools, returns an ordered execution plan
    by matching output tags of one tool to input tags of the next.
    """
    steps = payload.get("steps", [])
    if not steps or len(steps) < 2:
        return {"ok": False, "error": "need at least 2 steps"}

    # Validate each step references a known tool
    chain = []
    for i, step_name in enumerate(steps):
        if step_name not in _tool_registry:
            return {"ok": False, "error": f"unknown tool at step {i}: {step_name}"}
        chain.append({"step": i, "tool": step_name, "info": _tool_registry[step_name]})

    # Check output→input compatibility between consecutive steps
    compat_issues = []
    for i in range(len(chain) - 1):
        out_tags = set(chain[i]["info"].get("outputs", []))
        in_tags = set(chain[i + 1]["info"].get("inputs", []))
        if in_tags and not (out_tags & in_tags):
            compat_issues.append({
                "from_step": i,
                "to_step": i + 1,
                "missing_inputs": list(in_tags - out_tags),
            })

    return {
        "ok": True,
        "chain": chain,
        "compatibility_issues": compat_issues,
        "valid": len(compat_issues) == 0,
    }


async def _tool_validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate inputs against a tool's schema."""
    name = payload.get("name")
    inputs = payload.get("inputs", {})
    if not name:
        return {"ok": False, "error": "name required"}
    if name not in _tool_registry:
        return {"ok": False, "error": f"unknown tool: {name}"}

    tool = _tool_registry[name]
    expected = set(tool.get("inputs", []))
    provided = set(inputs.keys()) if isinstance(inputs, dict) else set()
    missing = list(expected - provided)
    extra = list(provided - expected)

    return {
        "ok": True,
        "valid": len(missing) == 0,
        "missing": missing,
        "extra": extra,
        "tool": name,
    }


def load_tool_use_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register tool-use capabilities: describe, list, select, chain, validate."""
    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="tool-describe",
        handler=_tool_describe,
        version="1.0.0",
        description="Register a tool with name, description, inputs, outputs, tags",
        inputs=["name"],
        outputs=["ok", "tool"],
        tags=["tool-use", "registry"],
    ))

    specs.append(builder.register(
        name="tool-list",
        handler=_tool_list,
        version="1.0.0",
        description="List all registered tools, optionally filtered by tag",
        inputs=[],
        outputs=["ok", "tools", "count"],
        tags=["tool-use", "discovery"],
    ))

    specs.append(builder.register(
        name="tool-select",
        handler=_tool_select,
        version="1.0.0",
        description="Select the best tool for a task using fuzzy matching",
        inputs=["task"],
        outputs=["ok", "tool", "score"],
        tags=["tool-use", "selection"],
    ))

    specs.append(builder.register(
        name="tool-chain",
        handler=_tool_chain,
        version="1.0.0",
        description="Plan and validate a chain of tools for multi-step tasks",
        inputs=["steps"],
        outputs=["ok", "chain", "valid", "compatibility_issues"],
        tags=["tool-use", "composition"],
    ))

    specs.append(builder.register(
        name="tool-validate",
        handler=_tool_validate,
        version="1.0.0",
        description="Validate inputs against a tool's declared schema",
        inputs=["name", "inputs"],
        outputs=["ok", "valid", "missing", "extra"],
        tags=["tool-use", "validation"],
    ))

    return specs


# ─── Collaboration Pack ─────────────────────────────────────────────────

async def _collab_delegate(payload: dict[str, Any]) -> dict[str, Any]:
    """Delegate a sub-task to another agent via audience routing.

    Inputs: target_capability, inputs, min_score, max_candidates
    Outputs: delegated_to, status, candidates
    """
    target_cap = payload.get("target_capability", "")
    task_inputs = payload.get("inputs", {})
    min_score = payload.get("min_score", 0.1)
    max_candidates = payload.get("max_candidates", 3)

    # Return delegation plan — actual routing happens at agent level
    return {
        "delegated_to": None,
        "status": "planned",
        "target_capability": target_cap,
        "candidates_requested": max_candidates,
        "min_score": min_score,
        "inputs": task_inputs,
    }


async def _collab_vote(payload: dict[str, Any]) -> dict[str, Any]:
    """Consensus voting — aggregate votes from multiple agents.

    Inputs: proposal, votes (list of {voter, choice, weight}), method (majority/unanimous/weighted)
    Outputs: winner, consensus, vote_counts
    """
    proposal = payload.get("proposal", "")
    votes = payload.get("votes", [])
    method = payload.get("method", "majority")

    if not votes:
        return {"winner": None, "consensus": False, "vote_counts": {}, "total_votes": 0}

    # Tally votes
    counts: dict[str, float] = {}
    for v in votes:
        choice = v.get("choice", "abstain")
        weight = v.get("weight", 1.0)
        counts[choice] = counts.get(choice, 0.0) + weight

    total = sum(counts.values())
    winner = max(counts, key=counts.get) if counts else None  # type: ignore[arg-type]

    # Determine consensus
    if method == "unanimous":
        consensus = len(counts) == 1 and total > 0
    elif method == "weighted":
        consensus = counts.get(winner, 0) / max(total, 1) > 0.6
    else:  # majority
        consensus = counts.get(winner, 0) / max(total, 1) > 0.5

    return {
        "proposal": proposal,
        "winner": winner,
        "consensus": consensus,
        "vote_counts": counts,
        "total_votes": len(votes),
        "method": method,
    }


async def _collab_aggregate(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregate results from multiple agents — merge, dedupe, rank.

    Inputs: results (list of dicts), strategy (merge/best/all), key_field
    Outputs: aggregated, count, strategy_used
    """
    results = payload.get("results", [])
    strategy = payload.get("strategy", "merge")
    key_field = payload.get("key_field", "")

    if not results:
        return {"aggregated": [], "count": 0, "strategy_used": strategy}

    if strategy == "best":
        # Pick result with highest score/confidence
        best = max(results, key=lambda r: r.get("score", r.get("confidence", 0.0)))
        return {"aggregated": [best], "count": 1, "strategy_used": strategy}

    if strategy == "dedupe" and key_field:
        seen: dict[str, dict] = {}
        for r in results:
            key = str(r.get(key_field, id(r)))
            if key not in seen or r.get("score", 0) > seen[key].get("score", 0):
                seen[key] = r
        return {"aggregated": list(seen.values()), "count": len(seen), "strategy_used": strategy}

    # merge: combine all, sorted by score
    sorted_results = sorted(
        results,
        key=lambda r: r.get("score", r.get("confidence", 0.0)),
        reverse=True,
    )
    return {"aggregated": sorted_results, "count": len(sorted_results), "strategy_used": strategy}


async def _collab_fanout(payload: dict[str, Any]) -> dict[str, Any]:
    """Fan-out a task to multiple agents and collect responses.

    Inputs: topic, payload_template, targets (list of agent names), timeout_ms
    Outputs: dispatched, pending, timed_out
    """
    topic = payload.get("topic", "")
    targets = payload.get("targets", [])
    timeout_ms = payload.get("timeout_ms", 5000)

    dispatched = []
    for t in targets:
        dispatched.append({
            "target": t,
            "topic": topic,
            "status": "dispatched",
            "timeout_ms": timeout_ms,
        })

    return {
        "dispatched": dispatched,
        "total": len(dispatched),
        "pending": len(dispatched),
        "timed_out": 0,
        "topic": topic,
    }


async def _collab_scatter_gather(payload: dict[str, Any]) -> dict[str, Any]:
    """Scatter-gather pattern — split work, distribute, merge results.

    Inputs: items (list), chunk_size, merge_strategy
    Outputs: chunks, total_items, merge_strategy
    """
    items = payload.get("items", [])
    chunk_size = payload.get("chunk_size", 10)
    merge_strategy = payload.get("merge_strategy", "concat")

    if not items:
        return {"chunks": [], "total_items": 0, "total_chunks": 0, "merge_strategy": merge_strategy}

    chunks = []
    for i in range(0, len(items), chunk_size):
        chunk = items[i:i + chunk_size]
        chunks.append({
            "index": len(chunks),
            "items": chunk,
            "size": len(chunk),
        })

    return {
        "chunks": chunks,
        "total_items": len(items),
        "total_chunks": len(chunks),
        "merge_strategy": merge_strategy,
    }


def load_collaboration_pack(builder: CapabilityBuilder, agent: Any | None = None) -> list[CapSpec]:
    """Load collaboration and multi-agent coordination capabilities.

    Provides primitives for multi-agent workflows:
    - **collab-delegate**: Delegate sub-tasks to the best agent
    - **collab-vote**: Consensus voting (majority/unanimous/weighted)
    - **collab-aggregate**: Merge results from multiple agents
    - **collab-fanout**: Broadcast task to multiple targets
    - **collab-scatter-gather**: Split work, distribute, merge
    """
    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="collab-delegate",
        handler=_collab_delegate,
        version="1.0.0",
        description="Delegate a sub-task to the best-matched agent via audience routing",
        inputs=["target_capability", "inputs"],
        outputs=["delegated_to", "status", "candidates"],
        tags=["collaboration", "delegation", "routing"],
    ))

    specs.append(builder.register(
        name="collab-vote",
        handler=_collab_vote,
        version="1.0.0",
        description="Consensus voting — aggregate agent votes with configurable method",
        inputs=["proposal", "votes", "method"],
        outputs=["winner", "consensus", "vote_counts"],
        tags=["collaboration", "voting", "consensus"],
    ))

    specs.append(builder.register(
        name="collab-aggregate",
        handler=_collab_aggregate,
        version="1.0.0",
        description="Aggregate results from multiple agents — merge, dedupe, or pick best",
        inputs=["results", "strategy"],
        outputs=["aggregated", "count", "strategy_used"],
        tags=["collaboration", "aggregation", "merge"],
    ))

    specs.append(builder.register(
        name="collab-fanout",
        handler=_collab_fanout,
        version="1.0.0",
        description="Fan-out a task to multiple agents and collect responses",
        inputs=["topic", "targets"],
        outputs=["dispatched", "total", "pending"],
        tags=["collaboration", "fanout", "broadcast"],
    ))

    specs.append(builder.register(
        name="collab-scatter-gather",
        handler=_collab_scatter_gather,
        version="1.0.0",
        description="Scatter-gather pattern — split work into chunks, distribute, merge results",
        inputs=["items", "chunk_size", "merge_strategy"],
        outputs=["chunks", "total_items", "total_chunks"],
        tags=["collaboration", "scatter-gather", "distributed"],
    ))

    return specs


# ─── Subscription Pack ────────────────────────────────────────────────────

async def _sub_subscribe(payload: dict[str, Any]) -> dict[str, Any]:
    """Subscribe an agent to a topic on the bus."""
    bus: SubscriptionBus | None = payload.get("__bus__")
    if bus is None:
        return {"error": "No subscription bus attached", "ok": False}

    agent_name = payload.get("agent_name", "")
    topic = payload.get("topic", "")
    min_score = payload.get("min_score")
    filter_tags = payload.get("filter_tags", [])
    max_buffer = payload.get("max_buffer", 100)

    if not agent_name or not topic:
        return {"error": "agent_name and topic required", "ok": False}

    sub = bus.subscribe(
        agent_name=agent_name,
        topic=topic,
        min_score=min_score,
        filter_tags=filter_tags,
        max_buffer=max_buffer,
    )
    return {
        "ok": True,
        "subscription_id": sub.sub_id,
        "agent": agent_name,
        "topic": topic,
    }


async def _sub_unsubscribe(payload: dict[str, Any]) -> dict[str, Any]:
    bus: SubscriptionBus | None = payload.get("__bus__")
    if bus is None:
        return {"error": "No subscription bus attached", "ok": False}

    sub_id = payload.get("subscription_id", "")
    if bus.unsubscribe(sub_id):
        return {"ok": True, "subscription_id": sub_id, "status": "cancelled"}
    return {"ok": False, "error": f"Subscription {sub_id!r} not found"}


async def _sub_publish(payload: dict[str, Any]) -> dict[str, Any]:
    bus: SubscriptionBus | None = payload.get("__bus__")
    if bus is None:
        return {"error": "No subscription bus attached", "ok": False}

    message = payload.get("message", "")
    topic = payload.get("topic", "")
    metadata = payload.get("metadata", {})
    exclude_agent = payload.get("exclude_agent")

    if not message or not topic:
        return {"error": "message and topic required", "ok": False}

    result = bus.publish(
        message=message,
        topic=topic,
        metadata=metadata,
        exclude_agent=exclude_agent,
    )
    return {
        "ok": True,
        "matched": result.matched_subscriptions,
        "notifications": result.notifications_created,
        "dropped": result.notifications_dropped,
    }


async def _sub_poll(payload: dict[str, Any]) -> dict[str, Any]:
    bus: SubscriptionBus | None = payload.get("__bus__")
    if bus is None:
        return {"error": "No subscription bus attached", "ok": False}

    agent_name = payload.get("agent_name", "")
    limit = payload.get("limit")

    if not agent_name:
        return {"error": "agent_name required", "ok": False}

    notifs = bus.poll(agent_name, limit=limit)
    return {
        "ok": True,
        "notifications": [
            {
                "id": n.notif_id,
                "topic": n.topic,
                "message": n.message,
                "score": round(n.score, 3),
                "metadata": n.metadata,
            }
            for n in notifs
        ],
        "count": len(notifs),
    }


async def _sub_status(payload: dict[str, Any]) -> dict[str, Any]:
    bus: SubscriptionBus | None = payload.get("__bus__")
    if bus is None:
        return {"error": "No subscription bus attached", "ok": False}

    stats = bus.stats()
    return {
        "ok": True,
        "total_subscriptions": stats.total_subscriptions,
        "active_subscriptions": stats.active_subscriptions,
        "pending_notifications": stats.pending_notifications,
        "delivered_notifications": stats.delivered_notifications,
        "dropped_notifications": stats.dropped_notifications,
        "topics": stats.topics,
    }


def load_subscription_pack(
    builder: CapabilityBuilder, bus: SubscriptionBus | None = None
) -> list[CapSpec]:
    """Load subscription and notification capabilities.

    Provides pub/sub primitives for topic-based agent notification:
    - **sub-subscribe**: Subscribe an agent to a topic with optional filters
    - **sub-unsubscribe**: Cancel a subscription
    - **sub-publish**: Publish a message to matching subscribers
    - **sub-poll**: Retrieve pending notifications for an agent
    - **sub-status**: Get subscription bus statistics

    Args:
        builder: The capability builder to register with.
        bus:     A SubscriptionBus instance. Created if not provided.
    """
    if bus is None:
        bus = SubscriptionBus()

    def _wrap(handler):
        async def _wrapped(payload: dict[str, Any]) -> dict[str, Any]:
            return await handler({**payload, "__bus__": bus})
        return _wrapped

    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="sub-subscribe",
        handler=_wrap(_sub_subscribe),
        version="1.0.0",
        description="Subscribe an agent to a topic with optional tag filters",
        inputs=["agent_name", "topic", "min_score", "filter_tags"],
        outputs=["subscription_id", "agent", "topic", "ok"],
        tags=["subscription", "notification", "pubsub"],
    ))

    specs.append(builder.register(
        name="sub-unsubscribe",
        handler=_wrap(_sub_unsubscribe),
        version="1.0.0",
        description="Cancel a subscription by ID",
        inputs=["subscription_id"],
        outputs=["status", "ok"],
        tags=["subscription", "notification"],
    ))

    specs.append(builder.register(
        name="sub-publish",
        handler=_wrap(_sub_publish),
        version="1.0.0",
        description="Publish a message to all matching topic subscribers",
        inputs=["message", "topic", "metadata", "exclude_agent"],
        outputs=["matched", "notifications", "dropped", "ok"],
        tags=["subscription", "notification", "publish"],
    ))

    specs.append(builder.register(
        name="sub-poll",
        handler=_wrap(_sub_poll),
        version="1.0.0",
        description="Poll pending notifications for an agent",
        inputs=["agent_name", "limit"],
        outputs=["notifications", "count", "ok"],
        tags=["subscription", "notification", "poll"],
    ))

    specs.append(builder.register(
        name="sub-status",
        handler=_wrap(_sub_status),
        version="1.0.0",
        description="Get subscription bus statistics",
        inputs=[],
        outputs=["total_subscriptions", "active_subscriptions", "pending", "ok"],
        tags=["subscription", "notification", "status"],
    ))

    return specs


# ─── Trust & Verification Pack ──────────────────────────────────────────


def _trust_grade(payload: dict[str, Any]) -> dict[str, Any]:
    """File a grade for an agent after task completion."""
    from .grading import Grade, GradeReport
    ledger = payload.get("__ledger__")
    executor = payload.get("executor", "")
    caller = payload.get("caller", "unknown")
    task_id = payload.get("task_id", "")
    grade_str = payload.get("grade", "C")
    feedback = payload.get("feedback", "")
    exec_ms = payload.get("execution_time_ms")

    try:
        grade = Grade(grade_str)
    except ValueError:
        return {"ok": False, "error": f"Invalid grade: {grade_str}. Use A/B/C/D/F."}

    report = GradeReport(
        task_id=task_id,
        executor=executor,
        caller=caller,
        grade=grade,
        feedback=feedback,
        execution_time_ms=exec_ms,
    )
    score = ledger.record_grade(report)
    return {
        "ok": True,
        "executor": executor,
        "grade": grade_str,
        "new_score": round(score, 4),
        "grade_id": report.id,
    }


def _trust_score(payload: dict[str, Any]) -> dict[str, Any]:
    """Query trust score for a specific agent."""
    ledger = payload.get("__ledger__")
    agent = payload.get("agent", "")
    score = ledger.get_agent_trust(agent)
    reliable = ledger.scorer.is_reliable(agent)
    count = ledger.scorer._grade_counts.get(agent, 0)
    return {
        "ok": True,
        "agent": agent,
        "trust_score": score,
        "reliable": reliable,
        "grade_count": count,
    }


def _trust_leaderboard(payload: dict[str, Any]) -> dict[str, Any]:
    """Get the top trusted agents."""
    ledger = payload.get("__ledger__")
    limit = payload.get("limit", 10)
    top = ledger.get_top_agents(n=limit)
    return {
        "ok": True,
        "leaderboard": [{"agent": a, "score": round(s, 4)} for a, s in top],
        "count": len(top),
    }


def _trust_history(payload: dict[str, Any]) -> dict[str, Any]:
    """Get grade history for a specific agent."""
    ledger = payload.get("__ledger__")
    agent = payload.get("agent", "")
    limit = payload.get("limit", 20)
    history = ledger.get_grade_history(agent)
    recent = history[-limit:]
    return {
        "ok": True,
        "agent": agent,
        "grades": [g.to_dict() for g in recent],
        "total": len(history),
    }


def _trust_recent(payload: dict[str, Any]) -> dict[str, Any]:
    """Get recent grades across all agents."""
    ledger = payload.get("__ledger__")
    limit = payload.get("limit", 10)
    recent = ledger.get_recent_grades(n=limit)
    return {
        "ok": True,
        "grades": [g.to_dict() for g in recent],
        "count": len(recent),
    }


def _trust_verify(payload: dict[str, Any]) -> dict[str, Any]:
    """Verify if an agent meets a minimum trust threshold."""
    ledger = payload.get("__ledger__")
    agent = payload.get("agent", "")
    min_score = payload.get("min_score", 2.0)
    score = ledger.get_agent_trust(agent)
    raw = ledger.scorer.get_raw_score(agent)
    reliable = ledger.scorer.is_reliable(agent)
    meets = (score is not None) and (score >= min_score)
    return {
        "ok": True,
        "agent": agent,
        "trust_score": score,
        "raw_score": round(raw, 4) if raw is not None else None,
        "reliable": reliable,
        "meets_threshold": meets,
        "threshold": min_score,
    }


def _trust_compare(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare trust scores between two agents."""
    ledger = payload.get("__ledger__")
    agent_a = payload.get("agent_a", "")
    agent_b = payload.get("agent_b", "")
    score_a = ledger.get_agent_trust(agent_a)
    score_b = ledger.get_agent_trust(agent_b)
    if score_a is not None and score_b is not None:
        winner = agent_a if score_a >= score_b else agent_b
    elif score_a is not None:
        winner = agent_a
    elif score_b is not None:
        winner = agent_b
    else:
        winner = None
    return {
        "ok": True,
        "agent_a": agent_a,
        "score_a": score_a,
        "agent_b": agent_b,
        "score_b": score_b,
        "recommended": winner,
    }


def load_trust_pack(
    builder: CapabilityBuilder,
    ledger: Any | None = None,
) -> list[CapSpec]:
    """Load trust and verification capabilities.

    Provides trust primitives for grade filing, score queries, leaderboards,
    verification, and comparison — all backed by the TrustLedger:
    - **trust-grade**: File a grade (A–F) for an agent after task completion
    - **trust-score**: Query an agent's current EMA trust score
    - **trust-leaderboard**: Get top-N agents ranked by trust
    - **trust-history**: Get grade history for a specific agent
    - **trust-recent**: Get recent grades across all agents
    - **trust-verify**: Check if an agent meets a minimum trust threshold
    - **trust-compare**: Compare trust scores between two agents

    Args:
        builder: The capability builder to register with.
        ledger:  A TrustLedger instance. Created in-memory if not provided.
    """
    if ledger is None:
        from .grading import TrustLedger as GradingLedger
        ledger = GradingLedger(path="trust_pack_ledger.json")

    def _wrap(handler):
        async def _wrapped(payload: dict[str, Any]) -> dict[str, Any]:
            return handler({**payload, "__ledger__": ledger})
        return _wrapped

    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="trust-grade",
        handler=_wrap(_trust_grade),
        version="1.0.0",
        description="File a grade (A–F) for an agent after task completion",
        inputs=["executor", "grade"],
        outputs=["ok", "executor", "grade", "new_score", "grade_id"],
        tags=["trust", "grading", "verification"],
    ))

    specs.append(builder.register(
        name="trust-score",
        handler=_wrap(_trust_score),
        version="1.0.0",
        description="Query an agent's current EMA trust score",
        inputs=["agent"],
        outputs=["ok", "agent", "trust_score", "reliable", "grade_count"],
        tags=["trust", "score", "query"],
    ))

    specs.append(builder.register(
        name="trust-leaderboard",
        handler=_wrap(_trust_leaderboard),
        version="1.0.0",
        description="Get top-N agents ranked by trust score",
        inputs=[],
        outputs=["ok", "leaderboard", "count"],
        tags=["trust", "leaderboard", "ranking"],
    ))

    specs.append(builder.register(
        name="trust-history",
        handler=_wrap(_trust_history),
        version="1.0.0",
        description="Get grade history for a specific agent",
        inputs=["agent"],
        outputs=["ok", "agent", "grades", "total"],
        tags=["trust", "history", "audit"],
    ))

    specs.append(builder.register(
        name="trust-recent",
        handler=_wrap(_trust_recent),
        version="1.0.0",
        description="Get recent grades across all agents",
        inputs=[],
        outputs=["ok", "grades", "count"],
        tags=["trust", "recent", "audit"],
    ))

    specs.append(builder.register(
        name="trust-verify",
        handler=_wrap(_trust_verify),
        version="1.0.0",
        description="Check if an agent meets a minimum trust threshold",
        inputs=["agent"],
        outputs=["ok", "agent", "trust_score", "raw_score", "reliable", "meets_threshold", "threshold"],
        tags=["trust", "verification", "threshold"],
    ))

    specs.append(builder.register(
        name="trust-compare",
        handler=_wrap(_trust_compare),
        version="1.0.0",
        description="Compare trust scores between two agents and recommend one",
        inputs=["agent_a", "agent_b"],
        outputs=["ok", "agent_a", "score_a", "agent_b", "score_b", "recommended"],
        tags=["trust", "comparison", "recommendation"],
    ))

    return specs


# ─── Web Research Pack ─────────────────────────────────────────────────

async def _research_plan(payload: dict[str, Any]) -> dict[str, Any]:
    """Decompose a research question into searchable sub-queries."""
    question = payload.get("question", "")
    max_subqueries = payload.get("max_subqueries", 5)
    depth = payload.get("depth", "standard")  # quick / standard / deep

    if not question:
        return {"error": "question is required", "ok": False}

    # Simple heuristic decomposition based on keywords and structure
    words = question.split()
    subqueries: list[str] = []

    # The question itself is always a sub-query
    subqueries.append(question)

    # Extract quoted phrases as dedicated sub-queries
    import re as _re
    quotes = _re.findall(r'"([^"]+)"', question)
    subqueries.extend(quotes)

    # Generate aspect-based sub-queries
    aspects = ["what is", "how does", "why", "benefits", "risks", "examples", "comparison"]
    topic_words = [w for w in words if len(w) > 3 and w.lower() not in {
        "what", "how", "why", "does", "the", "are", "can", "with", "from",
        "that", "this", "about", "there", "their", "been", "have", "will",
    }]
    core_topic = " ".join(topic_words[:4])

    for aspect in aspects:
        if aspect not in question.lower() and len(subqueries) < max_subqueries:
            subqueries.append(f"{aspect} {core_topic}")

    # For deep research, add alternative phrasings
    if depth == "deep" and len(subqueries) < max_subqueries:
        subqueries.append(f"{core_topic} overview")
        subqueries.append(f"{core_topic} recent developments")

    subqueries = subqueries[:max_subqueries]

    # Estimate scope
    scope = "quick" if depth == "quick" else ("deep" if depth == "deep" else "standard")
    estimated_sources = {"quick": 3, "standard": 8, "deep": 15}.get(scope, 8)

    return {
        "ok": True,
        "question": question,
        "subqueries": subqueries,
        "depth": scope,
        "estimated_sources": estimated_sources,
        "plan_id": uuid.uuid4().hex[:12],
    }


async def _research_extract(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract key facts, entities, and claims from text content."""
    text = payload.get("text", "")
    source = payload.get("source", "unknown")
    max_facts = payload.get("max_facts", 20)

    if not text:
        return {"error": "text is required", "ok": False}

    import re as _re

    # Extract sentences that look like factual claims
    sentences = _re.split(r'(?<=[.!?])\s+', text)
    facts: list[dict[str, Any]] = []

    # Indicators of factual claims
    claim_patterns = [
        r'\d+(?:\.\d+)?%?',  # numbers/percentages
        r'\b(?:found|showed|reported|published|announced|revealed|estimated)\b',
        r'\b(?:according to|based on|compared to|resulted in)\b',
    ]

    for sent in sentences:
        if len(facts) >= max_facts:
            break
        if len(sent) < 15:
            continue
        score = sum(1 for p in claim_patterns if _re.search(p, sent, _re.IGNORECASE))
        if score > 0:
            facts.append({
                "claim": sent.strip(),
                "confidence": min(score / 3.0, 1.0),
                "source": source,
            })

    # Extract named entities (simple heuristic)
    entities: dict[str, list[str]] = {"people": [], "organizations": [], "locations": []}
    capitalized = _re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    for name in capitalized:
        if len(name) > 2 and name not in {"The", "This", "That", "These", "Those"}:
            if any(kw in name.lower() for kw in ["inc", "corp", "ltd", "university", "institute", "foundation"]):
                entities["organizations"].append(name)
            elif any(kw in name.lower() for kw in ["city", "country", "state", "region", "river", "mountain"]):
                entities["locations"].append(name)
            else:
                entities["people"].append(name)

    # Deduplicate
    for key in entities:
        entities[key] = list(dict.fromkeys(entities[key]))[:10]

    return {
        "ok": True,
        "facts": facts,
        "fact_count": len(facts),
        "entities": entities,
        "source": source,
        "word_count": len(text.split()),
    }


async def _research_synthesize(payload: dict[str, Any]) -> dict[str, Any]:
    """Synthesize findings from multiple sources into a coherent summary."""
    findings = payload.get("findings", [])
    question = payload.get("question", "")
    format_type = payload.get("format", "summary")  # summary / briefing / bullet

    if not findings:
        return {"error": "findings list is required", "ok": False}

    # Collect all facts
    all_facts: list[dict[str, Any]] = []
    sources: set[str] = set()
    for finding in findings:
        facts = finding.get("facts", [])
        all_facts.extend(facts)
        src = finding.get("source", "")
        if src:
            sources.add(src)

    # Sort by confidence
    all_facts.sort(key=lambda f: f.get("confidence", 0), reverse=True)

    # Deduplicate similar claims (simple)
    seen_claims: set[str] = set()
    unique_facts: list[dict[str, Any]] = []
    for fact in all_facts:
        claim_lower = fact["claim"].lower()[:60]
        if claim_lower not in seen_claims:
            seen_claims.add(claim_lower)
            unique_facts.append(fact)

    top_facts = unique_facts[:15]

    # Format output
    if format_type == "bullet":
        bullets = [f"• {f['claim']} ({f['source']})" for f in top_facts]
        content = "\n".join(bullets)
    elif format_type == "briefing":
        lines = [f"# Research Briefing: {question}", ""]
        lines.append(f"Sources consulted: {len(sources)}")
        lines.append(f"Key findings: {len(top_facts)}")
        lines.append("")
        for i, f in enumerate(top_facts, 1):
            lines.append(f"{i}. {f['claim']}")
        content = "\n".join(lines)
    else:
        # Default summary
        if question:
            content = f"Research summary for: {question}\n\n"
        else:
            content = "Research summary:\n\n"
        for f in top_facts:
            content += f"{f['claim']}\n"
        content += f"\nBased on {len(sources)} source(s)."

    # Collect all entities
    all_entities: dict[str, list[str]] = {"people": [], "organizations": [], "locations": []}
    for finding in findings:
        for key in all_entities:
            all_entities[key].extend(finding.get("entities", {}).get(key, []))
    for key in all_entities:
        all_entities[key] = list(dict.fromkeys(all_entities[key]))[:10]

    return {
        "ok": True,
        "content": content,
        "format": format_type,
        "source_count": len(sources),
        "sources": list(sources),
        "fact_count": len(unique_facts),
        "top_facts": len(top_facts),
        "entities": all_entities,
    }


async def _research_source_score(payload: dict[str, Any]) -> dict[str, Any]:
    """Score and rank sources by reliability indicators."""
    sources = payload.get("sources", [])

    if not sources:
        return {"error": "sources list is required", "ok": False}

    # Reliability indicators
    high_reliability_domains = {
        "wikipedia.org", "nature.com", "science.org", "arxiv.org",
        "ieee.org", "acm.org", "github.com", "docs.python.org",
        "mozilla.org", "w3.org", "ietf.org", "nist.gov",
        "reuters.com", "apnews.com", "bbc.com", "nytimes.com",
    }
    medium_reliability = {
        "medium.com", "dev.to", "stackoverflow.com", "stackexchange.com",
        "reddit.com", "hackernews", "news.ycombinator.com",
    }

    scored: list[dict[str, Any]] = []
    for source in sources:
        url = source.get("url", "")
        name = source.get("name", url)
        fact_count = source.get("fact_count", 0)
        avg_confidence = source.get("avg_confidence", 0.5)

        # Base score from domain
        domain_score = 0.5
        domain = ""
        if url:
            import re as _re
            domain_match = _re.search(r'://([^/]+)', url)
            domain = domain_match.group(1).replace("www.", "") if domain_match else ""
            for hrd in high_reliability_domains:
                if domain.endswith(hrd):
                    domain_score = 0.9
                    break
            else:
                for mrd in medium_reliability:
                    if domain.endswith(mrd):
                        domain_score = 0.7
                        break

        # Combined score
        recency = min(source.get("recency_score", 1.0), 1.0)
        final_score = (domain_score * 0.4 + avg_confidence * 0.35 + recency * 0.15 + min(fact_count / 10, 1.0) * 0.1)

        scored.append({
            "name": name,
            "url": url,
            "domain": domain,
            "score": round(final_score, 3),
            "domain_reliability": round(domain_score, 2),
            "fact_count": fact_count,
            "avg_confidence": round(avg_confidence, 3),
        })

    scored.sort(key=lambda s: s["score"], reverse=True)

    return {
        "ok": True,
        "ranked_sources": scored,
        "total": len(scored),
        "high_reliability": len([s for s in scored if s["domain_reliability"] >= 0.9]),
        "medium_reliability": len([s for s in scored if 0.6 <= s["domain_reliability"] < 0.9]),
    }


def load_research_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register web research capabilities: planning, extraction, synthesis, source scoring."""
    specs = []
    specs.append(builder.register(
        name="research-plan",
        handler=_research_plan,
        version="1.0.0",
        description="Decompose a research question into searchable sub-queries with depth control",
        inputs=["question"],
        outputs=["subqueries", "depth", "estimated_sources", "plan_id"],
        tags=["research", "planning", "web"],
    ))
    specs.append(builder.register(
        name="research-extract",
        handler=_research_extract,
        version="1.0.0",
        description="Extract key facts, entities, and claims from text content",
        inputs=["text"],
        outputs=["facts", "entities", "word_count"],
        tags=["research", "extraction", "nlp"],
    ))
    specs.append(builder.register(
        name="research-synthesize",
        handler=_research_synthesize,
        version="1.0.0",
        description="Synthesize findings from multiple sources into summary, briefing, or bullet format",
        inputs=["findings"],
        outputs=["content", "source_count", "fact_count", "entities"],
        tags=["research", "synthesis", "summarization"],
    ))
    specs.append(builder.register(
        name="research-source-score",
        handler=_research_source_score,
        version="1.0.0",
        description="Score and rank sources by reliability, confidence, and recency indicators",
        inputs=["sources"],
        outputs=["ranked_sources", "total", "high_reliability"],
        tags=["research", "scoring", "reliability"],
    ))
    return specs


# ─── Audit & Compliance Pack ────────────────────────────────────────────


class _AuditLog:
    """In-memory structured audit log backed by the agent's store."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._spans: dict[str, dict[str, Any]] = {}

    def record(
        self,
        action: str,
        actor: str = "system",
        target: str = "",
        outcome: str = "success",
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "audit_id": uuid.uuid4().hex[:12],
            "action": action,
            "actor": actor,
            "target": target,
            "outcome": outcome,
            "metadata": metadata or {},
            "tags": tags or [],
            "timestamp": time.time(),
        }
        self._entries.append(entry)
        return entry

    def start_span(
        self,
        operation: str,
        actor: str = "system",
        parent_span_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        span_id = uuid.uuid4().hex[:10]
        span: dict[str, Any] = {
            "span_id": span_id,
            "operation": operation,
            "actor": actor,
            "parent_span_id": parent_span_id,
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "duration_ms": None,
            "children": [],
            "events": [],
            "metadata": metadata or {},
        }
        self._spans[span_id] = span
        if parent_span_id and parent_span_id in self._spans:
            self._spans[parent_span_id]["children"].append(span_id)
        return span

    def finish_span(self, span_id: str, status: str = "ok", result: dict[str, Any] | None = None) -> dict[str, Any] | None:
        span = self._spans.get(span_id)
        if span is None:
            return None
        now = time.time()
        span["status"] = status
        span["finished_at"] = now
        span["duration_ms"] = round((now - span["started_at"]) * 1000, 2)
        if result:
            span["result"] = result
        return span

    def add_event(self, span_id: str, event: str, metadata: dict[str, Any] | None = None) -> bool:
        span = self._spans.get(span_id)
        if span is None:
            return False
        span["events"].append({
            "event": event,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })
        return True

    def query(
        self,
        actor: str | None = None,
        action: str | None = None,
        outcome: str | None = None,
        tag: str | None = None,
        since: float | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        results = self._entries
        if actor:
            results = [e for e in results if e["actor"] == actor]
        if action:
            results = [e for e in results if action in e["action"]]
        if outcome:
            results = [e for e in results if e["outcome"] == outcome]
        if tag:
            results = [e for e in results if tag in e.get("tags", [])]
        if since:
            results = [e for e in results if e["timestamp"] >= since]
        return results[-limit:]

    def get_span(self, span_id: str) -> dict[str, Any] | None:
        return self._spans.get(span_id)

    def active_spans(self) -> list[dict[str, Any]]:
        return [s for s in self._spans.values() if s["status"] == "running"]

    def stats(self) -> dict[str, Any]:
        outcomes = {}
        for e in self._entries:
            o = e["outcome"]
            outcomes[o] = outcomes.get(o, 0) + 1
        return {
            "total_events": len(self._entries),
            "total_spans": len(self._spans),
            "active_spans": len(self.active_spans()),
            "outcomes": outcomes,
        }


async def _audit_record(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a structured audit event."""
    log: _AuditLog | None = payload.get("__audit_log__")
    if log is None:
        return {"error": "No audit log attached", "ok": False}
    entry = log.record(
        action=payload.get("action", ""),
        actor=payload.get("actor", "system"),
        target=payload.get("target", ""),
        outcome=payload.get("outcome", "success"),
        metadata=payload.get("metadata"),
        tags=payload.get("tags"),
    )
    return {"ok": True, "audit_id": entry["audit_id"], "timestamp": entry["timestamp"]}


async def _audit_query(payload: dict[str, Any]) -> dict[str, Any]:
    """Query audit log entries with filters."""
    log: _AuditLog | None = payload.get("__audit_log__")
    if log is None:
        return {"error": "No audit log attached", "ok": False}
    entries = log.query(
        actor=payload.get("actor"),
        action=payload.get("action"),
        outcome=payload.get("outcome"),
        tag=payload.get("tag"),
        since=payload.get("since"),
        limit=payload.get("limit", 50),
    )
    return {"ok": True, "entries": entries, "count": len(entries)}


async def _audit_span_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Start a trace span for an operation."""
    log: _AuditLog | None = payload.get("__audit_log__")
    if log is None:
        return {"error": "No audit log attached", "ok": False}
    span = log.start_span(
        operation=payload.get("operation", ""),
        actor=payload.get("actor", "system"),
        parent_span_id=payload.get("parent_span_id"),
        metadata=payload.get("metadata"),
    )
    return {"ok": True, "span_id": span["span_id"], "operation": span["operation"]}


async def _audit_span_finish(payload: dict[str, Any]) -> dict[str, Any]:
    """Finish a trace span and record duration."""
    log: _AuditLog | None = payload.get("__audit_log__")
    if log is None:
        return {"error": "No audit log attached", "ok": False}
    span_id = payload.get("span_id", "")
    status = payload.get("status", "ok")
    result = payload.get("result")
    span = log.finish_span(span_id, status=status, result=result)
    if span is None:
        return {"ok": False, "error": f"Span {span_id!r} not found"}
    return {
        "ok": True,
        "span_id": span_id,
        "status": span["status"],
        "duration_ms": span["duration_ms"],
    }


async def _audit_span_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a named event to a running span."""
    log: _AuditLog | None = payload.get("__audit_log__")
    if log is None:
        return {"error": "No audit log attached", "ok": False}
    span_id = payload.get("span_id", "")
    event = payload.get("event", "")
    added = log.add_event(span_id, event, metadata=payload.get("metadata"))
    if not added:
        return {"ok": False, "error": f"Span {span_id!r} not found"}
    return {"ok": True, "span_id": span_id, "event": event}


async def _audit_stats(payload: dict[str, Any]) -> dict[str, Any]:
    """Get audit log statistics."""
    log: _AuditLog | None = payload.get("__audit_log__")
    if log is None:
        return {"error": "No audit log attached", "ok": False}
    return {"ok": True, **log.stats()}


def load_audit_pack(
    builder: CapabilityBuilder,
    audit_log: _AuditLog | None = None,
) -> list[CapSpec]:
    """Load audit, tracing, and compliance capabilities.

    Provides structured event logging and distributed-trace spans:
    - **audit-record**: Record a structured audit event with actor, action, target, outcome
    - **audit-query**: Query audit log entries with filters (actor, action, outcome, tag, since)
    - **audit-span-start**: Start a trace span (optional parent for nesting)
    - **audit-span-finish**: Finish a span, recording duration and status
    - **audit-span-event**: Add a named event to a running span
    - **audit-stats**: Get audit log statistics (event counts, active spans, outcomes)

    Args:
        builder:   The capability builder to register with.
        audit_log: An _AuditLog instance. Created in-memory if not provided.
    """
    if audit_log is None:
        audit_log = _AuditLog()

    def _wrap(handler):
        async def _wrapped(payload: dict[str, Any]) -> dict[str, Any]:
            return await handler({**payload, "__audit_log__": audit_log})
        return _wrapped

    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="audit-record",
        handler=_wrap(_audit_record),
        version="1.0.0",
        description="Record a structured audit event with actor, action, target, and outcome",
        inputs=["action"],
        outputs=["ok", "audit_id", "timestamp"],
        tags=["audit", "logging", "compliance"],
    ))
    specs.append(builder.register(
        name="audit-query",
        handler=_wrap(_audit_query),
        version="1.0.0",
        description="Query audit log entries with filters for actor, action, outcome, tag, or time range",
        inputs=[],
        outputs=["ok", "entries", "count"],
        tags=["audit", "query", "compliance"],
    ))
    specs.append(builder.register(
        name="audit-span-start",
        handler=_wrap(_audit_span_start),
        version="1.0.0",
        description="Start a trace span for an operation, optionally nested under a parent span",
        inputs=["operation"],
        outputs=["ok", "span_id", "operation"],
        tags=["audit", "tracing", "spans"],
    ))
    specs.append(builder.register(
        name="audit-span-finish",
        handler=_wrap(_audit_span_finish),
        version="1.0.0",
        description="Finish a trace span, recording duration and final status",
        inputs=["span_id"],
        outputs=["ok", "span_id", "duration_ms"],
        tags=["audit", "tracing", "spans"],
    ))
    specs.append(builder.register(
        name="audit-span-event",
        handler=_wrap(_audit_span_event),
        version="1.0.0",
        description="Add a named event annotation to a running trace span",
        inputs=["span_id", "event"],
        outputs=["ok", "span_id", "event"],
        tags=["audit", "tracing", "events"],
    ))
    specs.append(builder.register(
        name="audit-stats",
        handler=_wrap(_audit_stats),
        version="1.0.0",
        description="Get audit log statistics — event counts, active spans, outcome breakdown",
        inputs=[],
        outputs=["ok", "total_events", "total_spans", "active_spans", "outcomes"],
        tags=["audit", "stats", "monitoring"],
    ))

    return specs


# ─── Deliberation Pack ───────────────────────────────────────────────────

async def _deliberation_propose(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a structured proposal for agent deliberation."""
    topic = payload.get("topic", "")
    proposal_text = payload.get("proposal", "")
    proposer = payload.get("proposer", "unknown")
    options = payload.get("options", [])
    deadline_s = payload.get("deadline_s", 3600)

    if not topic:
        raise ValueError("topic is required")

    proposal_id = str(uuid.uuid4())[:8]
    now = time.time()

    proposal = {
        "id": proposal_id,
        "topic": topic,
        "proposal": proposal_text,
        "proposer": proposer,
        "options": options or ["support", "oppose", "abstain"],
        "created_at": now,
        "deadline": now + deadline_s,
        "status": "open",
        "votes": {},
        "arguments": [],
    }

    return {
        "ok": True,
        "proposal_id": proposal_id,
        "proposal": proposal,
        "status": "open",
    }


async def _deliberation_argue(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit a structured argument (for/against) on a proposal."""
    proposal_id = payload.get("proposal_id", "")
    position = payload.get("position", "neutral")  # support | oppose | neutral
    argument = payload.get("argument", "")
    agent_name = payload.get("agent", "unknown")
    evidence = payload.get("evidence", [])
    confidence = payload.get("confidence", 0.5)

    if not proposal_id or not argument:
        raise ValueError("proposal_id and argument are required")

    arg_entry = {
        "id": str(uuid.uuid4())[:8],
        "agent": agent_name,
        "position": position,
        "argument": argument,
        "evidence": evidence,
        "confidence": max(0.0, min(1.0, confidence)),
        "timestamp": time.time(),
    }

    # Score argument quality heuristically
    length_score = min(len(argument.split()) / 50.0, 1.0) * 0.3
    evidence_score = min(len(evidence) / 3.0, 1.0) * 0.3
    confidence_score = abs(confidence - 0.5) * 2 * 0.2  # extreme positions score higher
    has_structure = 0.2 if any(kw in argument.lower() for kw in ["because", "therefore", "however", "evidence", "data"]) else 0.0
    quality = min(length_score + evidence_score + confidence_score + has_structure, 1.0)

    arg_entry["quality_score"] = round(quality, 3)

    return {
        "ok": True,
        "argument_id": arg_entry["id"],
        "position": position,
        "quality_score": round(quality, 3),
        "argument": arg_entry,
    }


async def _deliberation_vote(payload: dict[str, Any]) -> dict[str, Any]:
    """Cast a vote on a proposal with optional weighting."""
    proposal_id = payload.get("proposal_id", "")
    agent_name = payload.get("agent", "unknown")
    vote = payload.get("vote", "abstain")
    weight = payload.get("weight", 1.0)
    rationale = payload.get("rationale", "")

    if not proposal_id:
        raise ValueError("proposal_id is required")

    valid_votes = ["support", "oppose", "abstain"]
    if vote not in valid_votes:
        raise ValueError(f"vote must be one of {valid_votes}")

    vote_entry = {
        "agent": agent_name,
        "vote": vote,
        "weight": max(0.0, weight),
        "rationale": rationale,
        "timestamp": time.time(),
    }

    # Tally (simulated — real impl would update proposal state)
    tally = {
        "support": weight if vote == "support" else 0.0,
        "oppose": weight if vote == "oppose" else 0.0,
        "abstain": weight if vote == "abstain" else 0.0,
    }

    return {
        "ok": True,
        "vote": vote_entry,
        "tally": tally,
    }


async def _deliberation_consensus(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate consensus level from a set of positions."""
    positions = payload.get("positions", [])
    threshold = payload.get("threshold", 0.6)

    if not positions:
        raise ValueError("positions list is required")

    total = len(positions)
    position_counts: dict[str, int] = {}
    for p in positions:
        pos = p.get("position", "neutral")
        position_counts[pos] = position_counts.get(pos, 0) + 1

    if not position_counts:
        return {"ok": True, "consensus": False, "agreement": 0.0, "dominant": None}

    dominant = max(position_counts, key=position_counts.get)  # type: ignore[arg-type]
    agreement = position_counts[dominant] / total
    has_consensus = agreement >= threshold

    # Compute entropy (lower = more agreement)
    entropy = 0.0
    for count in position_counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p) if p > 0 else 0.0
    max_entropy = math.log2(max(len(position_counts), 1))
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0

    return {
        "ok": True,
        "consensus": has_consensus,
        "agreement": round(agreement, 3),
        "dominant": dominant,
        "threshold": threshold,
        "position_counts": position_counts,
        "entropy": round(normalized_entropy, 3),
        "total": total,
    }


async def _deliberation_quorum(payload: dict[str, Any]) -> dict[str, Any]:
    """Check if a quorum of agents have participated."""
    participants = payload.get("participants", [])
    total_eligible = payload.get("total_eligible", 10)
    quorum_fraction = payload.get("quorum_fraction", 0.5)

    count = len(set(participants))
    quorum_size = math.ceil(total_eligible * quorum_fraction)
    met = count >= quorum_size
    participation_rate = count / max(total_eligible, 1)

    return {
        "ok": True,
        "quorum_met": met,
        "participants": count,
        "quorum_size": quorum_size,
        "total_eligible": total_eligible,
        "participation_rate": round(participation_rate, 3),
        "deficit": max(0, quorum_size - count),
    }


async def _deliberation_synthesize(payload: dict[str, Any]) -> dict[str, Any]:
    """Synthesize arguments into a collective position."""
    arguments = payload.get("arguments", [])

    if not arguments:
        raise ValueError("arguments list is required")

    # Group by position
    by_position: dict[str, list[dict]] = {}
    for arg in arguments:
        pos = arg.get("position", "neutral")
        by_position.setdefault(pos, []).append(arg)

    # Weight by quality scores
    weighted_positions: dict[str, float] = {}
    for pos, args in by_position.items():
        total_quality = sum(a.get("quality_score", 0.5) for a in args)
        avg_confidence = sum(a.get("confidence", 0.5) for a in args) / max(len(args), 1)
        weighted_positions[pos] = total_quality * avg_confidence

    total_weight = sum(weighted_positions.values()) or 1.0
    normalized = {k: round(v / total_weight, 3) for k, v in weighted_positions.items()}

    # Collect strongest arguments per position
    strongest: dict[str, list[str]] = {}
    for pos, args in by_position.items():
        top = sorted(args, key=lambda a: a.get("quality_score", 0), reverse=True)[:3]
        strongest[pos] = [a.get("argument", "")[:120] for a in top]

    # Collective position = highest weighted
    collective = max(normalized, key=normalized.get) if normalized else "neutral"  # type: ignore[arg-type]

    return {
        "ok": True,
        "collective_position": collective,
        "weighted_positions": normalized,
        "strongest_arguments": strongest,
        "argument_counts": {k: len(v) for k, v in by_position.items()},
        "total_arguments": len(arguments),
    }


def load_deliberation_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register multi-agent deliberation capabilities.

    Caps: propose, argue, vote, consensus, quorum, synthesize.
    Enables structured multi-agent deliberation: proposals, arguments,
    weighted voting, consensus detection, quorum checks, and synthesis
    of collective positions from diverse agent arguments.
    """
    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="deliberation-propose",
        handler=_deliberation_propose,
        version="1.0.0",
        description="Create a structured proposal for agent deliberation",
        inputs=["topic"],
        outputs=["ok", "proposal_id", "status"],
        tags=["deliberation", "governance", "proposal"],
    ))

    specs.append(builder.register(
        name="deliberation-argue",
        handler=_deliberation_argue,
        version="1.0.0",
        description="Submit a structured argument for/against a proposal with quality scoring",
        inputs=["proposal_id", "argument"],
        outputs=["ok", "argument_id", "position", "quality_score"],
        tags=["deliberation", "argument", "debate"],
    ))

    specs.append(builder.register(
        name="deliberation-vote",
        handler=_deliberation_vote,
        version="1.0.0",
        description="Cast a weighted vote on a proposal",
        inputs=["proposal_id", "vote"],
        outputs=["ok", "vote", "tally"],
        tags=["deliberation", "voting", "governance"],
    ))

    specs.append(builder.register(
        name="deliberation-consensus",
        handler=_deliberation_consensus,
        version="1.0.0",
        description="Evaluate consensus level from agent positions with entropy scoring",
        inputs=["positions"],
        outputs=["ok", "consensus", "agreement", "dominant", "entropy"],
        tags=["deliberation", "consensus", "agreement"],
    ))

    specs.append(builder.register(
        name="deliberation-quorum",
        handler=_deliberation_quorum,
        version="1.0.0",
        description="Check if quorum of agents have participated",
        inputs=["participants"],
        outputs=["ok", "quorum_met", "participants", "participation_rate"],
        tags=["deliberation", "quorum", "governance"],
    ))

    specs.append(builder.register(
        name="deliberation-synthesize",
        handler=_deliberation_synthesize,
        version="1.0.0",
        description="Synthesize diverse agent arguments into a collective weighted position",
        inputs=["arguments"],
        outputs=["ok", "collective_position", "weighted_positions", "strongest_arguments"],
        tags=["deliberation", "synthesis", "collective"],
    ))

    return specs


# ─── Orchestration Pack ─────────────────────────────────────────────────

async def _orch_sequence(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a sequence of capability calls, piping outputs forward."""
    builder = payload.get("__orch_builder__")
    steps = payload.get("steps", [])
    if not steps:
        return {"ok": False, "error": "No steps provided"}
    if builder is None:
        return {"ok": False, "error": "No builder attached"}

    results = []
    context: dict[str, Any] = dict(payload.get("initial_context", {}))

    for i, step in enumerate(steps):
        cap_name = step.get("capability", "")
        step_input = {**context, **step.get("input", {})}
        try:
            inv = await builder.invoke(cap_name, step_input)
            result = inv.output if inv.ok else {"ok": False, "error": inv.error}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}

        results.append({"step": i, "capability": cap_name, "result": result})
        if result.get("ok", False) or "error" not in result:
            context.update(result)
        else:
            if step.get("halt_on_error", True):
                return {"ok": False, "failed_step": i, "results": results}

    return {"ok": True, "results": results, "steps_completed": len(results)}


async def _orch_parallel(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute multiple capability calls concurrently and merge results."""
    import asyncio

    builder = payload.get("__orch_builder__")
    branches = payload.get("branches", [])
    if not branches:
        return {"ok": False, "error": "No branches provided"}
    if builder is None:
        return {"ok": False, "error": "No builder attached"}

    async def run_branch(idx: int, branch: dict) -> dict:
        cap_name = branch.get("capability", "")
        branch_input = dict(branch.get("input", {}))
        try:
            inv = await builder.invoke(cap_name, branch_input)
            result = inv.output if inv.ok else {"ok": False, "error": inv.error}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        return {"branch": idx, "capability": cap_name, "result": result}

    tasks = [run_branch(i, b) for i, b in enumerate(branches)]
    branch_results = await asyncio.gather(*tasks)

    errors = [r for r in branch_results if "error" in r.get("result", {})]
    merged = {}
    for br in branch_results:
        merged.update(br.get("result", {}))

    return {
        "ok": len(errors) == 0,
        "results": branch_results,
        "branches_completed": len(branch_results),
        "errors": len(errors),
        "merged": merged,
    }


async def _orch_retry(payload: dict[str, Any]) -> dict[str, Any]:
    """Retry a capability call with exponential backoff."""
    import asyncio

    builder = payload.get("__orch_builder__")
    cap_name = payload.get("capability", "")
    cap_input = dict(payload.get("input", {}))
    max_retries = payload.get("max_retries", 3)
    base_delay = payload.get("base_delay", 0.1)

    if builder is None:
        return {"ok": False, "error": "No builder attached"}

    last_result = {}
    for attempt in range(max_retries + 1):
        try:
            inv = await builder.invoke(cap_name, cap_input)
            if inv.ok:
                return {"ok": True, "result": inv.output, "attempts": attempt + 1}
            last_result = {"ok": False, "error": inv.error}
        except Exception as exc:
            last_result = {"ok": False, "error": str(exc)}

        if attempt < max_retries:
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)

    return {"ok": False, "result": last_result, "attempts": max_retries + 1}


async def _orch_conditional(payload: dict[str, Any]) -> dict[str, Any]:
    """Branch execution based on a condition evaluation."""
    builder = payload.get("__orch_builder__")
    condition = payload.get("condition", {})
    field = condition.get("field", "")
    op = condition.get("op", "eq")
    value = condition.get("value")
    context = dict(payload.get("context", {}))

    actual = context.get(field)
    passed = False
    if op == "eq":
        passed = actual == value
    elif op == "neq":
        passed = actual != value
    elif op == "gt":
        passed = actual is not None and actual > value
    elif op == "lt":
        passed = actual is not None and actual < value
    elif op == "gte":
        passed = actual is not None and actual >= value
    elif op == "lte":
        passed = actual is not None and actual <= value
    elif op == "contains":
        passed = value in actual if actual else False
    elif op == "exists":
        passed = actual is not None

    branch = "then" if passed else "else"
    step = payload.get(branch, {})
    if not step:
        return {"ok": True, "condition_met": passed, "branch": branch, "result": None}
    if builder is None:
        return {"ok": True, "condition_met": passed, "branch": branch, "result": None}

    cap_name = step.get("capability", "")
    step_input = {**context, **step.get("input", {})}
    try:
        inv = await builder.invoke(cap_name, step_input)
        result = inv.output if inv.ok else {"ok": False, "error": inv.error}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    return {"ok": True, "condition_met": passed, "branch": branch, "result": result}


async def _orch_pipeline(payload: dict[str, Any]) -> dict[str, Any]:
    """Chain capabilities where each step's output feeds the next step's input."""
    builder = payload.get("__orch_builder__")
    steps = payload.get("steps", [])
    if not steps:
        return {"ok": False, "error": "No steps provided"}
    if builder is None:
        return {"ok": False, "error": "No builder attached"}

    current = dict(payload.get("initial_input", {}))
    results = []

    for i, step in enumerate(steps):
        cap_name = step.get("capability", "")
        step_input = {**current, **step.get("input", {})}

        try:
            inv = await builder.invoke(cap_name, step_input)
            if not inv.ok:
                return {"ok": False, "failed_step": i, "error": inv.error, "results": results}
            current = inv.output
        except Exception as exc:
            return {"ok": False, "failed_step": i, "error": str(exc), "results": results}

        results.append({"step": i, "capability": cap_name})

    return {"ok": True, "results": results, "output": current, "steps_completed": len(results)}



def load_orchestration_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load orchestration capabilities — sequence, parallel, retry, conditional, pipeline."""
    specs: list[CapSpec] = []

    # Wrap handlers to inject builder reference
    def _wrap(fn):
        async def _w(payload):
            payload["__orch_builder__"] = builder
            return await fn(payload)
        return _w

    specs.append(builder.register(
        name="orch-sequence",
        handler=_wrap(_orch_sequence),
        version="1.0.0",
        description="Execute capability calls in sequence, accumulating context",
        inputs=["steps"],
        outputs=["ok", "results", "steps_completed"],
        tags=["orchestration", "sequence", "workflow"],
    ))
    specs.append(builder.register(
        name="orch-parallel",
        handler=_wrap(_orch_parallel),
        version="1.0.0",
        description="Execute multiple capability calls concurrently",
        inputs=["branches"],
        outputs=["ok", "results", "branches_completed", "merged"],
        tags=["orchestration", "parallel", "fan-out"],
    ))
    specs.append(builder.register(
        name="orch-retry",
        handler=_wrap(_orch_retry),
        version="1.0.0",
        description="Retry a capability call with exponential backoff",
        inputs=["capability", "input", "max_retries"],
        outputs=["ok", "result", "attempts"],
        tags=["orchestration", "retry", "resilience"],
    ))
    specs.append(builder.register(
        name="orch-conditional",
        handler=_wrap(_orch_conditional),
        version="1.0.0",
        description="Branch execution based on a condition evaluation",
        inputs=["condition"],
        outputs=["ok", "condition_met", "branch", "result"],
        tags=["orchestration", "conditional", "branching"],
    ))
    specs.append(builder.register(
        name="orch-pipeline",
        handler=_wrap(_orch_pipeline),
        version="1.0.0",
        description="Chain capabilities with strict output-to-input piping",
        inputs=["steps"],
        outputs=["ok", "results", "output", "steps_completed"],
        tags=["orchestration", "pipeline", "chain"],
    ))

    return specs


# ─── Localization Pack ──────────────────────────────────────────────────

class LocalizationError(Exception):
    """Base for localization pack errors."""


async def _localize_chart(payload: dict[str, Any]) -> dict[str, Any]:
    """Describe an agent's local chart — domain, vocabulary, coverage."""
    agent = payload.get("__agent__")
    if agent is None:
        raise LocalizationError("No agent attached")

    from .chart import Chart
    chart = Chart.from_agent(
        name=agent.name,
        capabilities=list(agent._capabilities) if hasattr(agent, '_capabilities') else [],
        focus=getattr(agent._topology, '_focus', None),
    )

    return {
        "agent": agent.name,
        "domain": sorted(chart.domain),
        "vocabulary": sorted(chart.vocabulary),
        "domain_size": len(chart.domain),
        "vocabulary_size": len(chart.vocabulary),
        "focus": chart.focus,
        "ok": True,
    }


async def _localize_overlap(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute vocabulary overlap between this agent and another."""
    agent = payload.get("__agent__")
    if agent is None:
        raise LocalizationError("No agent attached")
    peer_name = payload.get("peer")
    if not peer_name:
        raise LocalizationError("'peer' field required")

    from .chart import Chart

    my_chart = Chart.from_agent(
        name=agent.name,
        capabilities=list(agent._capabilities) if hasattr(agent, '_capabilities') else [],
        focus=getattr(agent, '_topology', None) and getattr(agent._topology, '_focus', None),
    )
    peers = [r for r in agent._registry.all_agents() if r.name == peer_name]
    if not peers:
        raise LocalizationError(f"Agent {peer_name!r} not found")

    ref = peers[0]
    peer_chart = Chart(agent_name=ref.name, domain=set(ref.capabilities), vocabulary=set())
    for cap in ref.capabilities:
        peer_chart.vocabulary.update(cap.lower().replace("-", " ").replace("_", " ").split())

    overlap = my_chart.vocabulary & peer_chart.vocabulary
    coverage = len(overlap) / len(my_chart.vocabulary) if my_chart.vocabulary else 0.0

    return {
        "agent_a": agent.name,
        "agent_b": peer_name,
        "overlap": sorted(overlap),
        "overlap_size": len(overlap),
        "coverage": round(coverage, 4),
        "ok": True,
    }


async def _localize_blindspots(payload: dict[str, Any]) -> dict[str, Any]:
    """Find this agent's blind spots — unmatched focus, isolated capabilities, dark topics."""
    agent = payload.get("__agent__")
    if agent is None:
        raise LocalizationError("No agent attached")

    try:
        spots = agent.blind_spot()
    except Exception:
        spots = []

    return {
        "agent": agent.name,
        "blind_spots": [
            {
                "kind": s.kind,
                "topic": s.topic,
                "severity": round(s.depth, 3),
                "description": getattr(s, 'evidence', [])[:2] or s.topic,
            }
            for s in spots
        ],
        "count": len(spots),
        "ok": True,
    }


async def _localize_atlas_holes(payload: dict[str, Any]) -> dict[str, Any]:
    """Find topics that no agent on the mesh covers — atlas holes."""
    agent = payload.get("__agent__")
    if agent is None:
        raise LocalizationError("No agent attached")

    from .atlas import Atlas
    atlas = Atlas.build(agent._registry)

    holes = atlas.holes() if hasattr(atlas, 'holes') else []

    return {
        "holes": holes if isinstance(holes, list) else [],
        "count": len(holes) if isinstance(holes, (list, tuple)) else 0,
        "agent_count": len(atlas._charts),
        "ok": True,
    }


async def _localize_knowledge_diversity(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute knowledge diversity across the mesh — how varied are agent domains."""
    agent = payload.get("__agent__")
    if agent is None:
        raise LocalizationError("No agent attached")

    from .chart import Chart

    all_agents = agent._registry.all_agents()
    if not all_agents:
        return {"diversity": 0.0, "agent_count": 0, "ok": True}

    all_vocab: set[str] = set()
    per_agent: list[dict[str, Any]] = []

    for ref in all_agents:
        vocab = set()
        for cap in ref.capabilities:
            vocab.update(cap.lower().replace("-", " ").replace("_", " ").split())
        all_vocab.update(vocab)
        per_agent.append({"name": ref.name, "vocab_size": len(vocab), "unique": len(vocab - all_vocab)})

    # Unique knowledge per agent
    agent_vocabs: list[set[str]] = []
    for ref in all_agents:
        vocab = set()
        for cap in ref.capabilities:
            vocab.update(cap.lower().replace("-", " ").replace("_", " ").split())
        agent_vocabs.append(vocab)

    total_unique = 0
    for i, vocab in enumerate(agent_vocabs):
        others = set()
        for j, v in enumerate(agent_vocabs):
            if i != j:
                others.update(v)
        total_unique += len(vocab - others)

    diversity = total_unique / len(all_vocab) if all_vocab else 0.0

    return {
        "total_vocabulary_size": len(all_vocab),
        "agent_count": len(all_agents),
        "diversity_index": round(diversity, 4),
        "agents": per_agent,
        "ok": True,
    }


def load_localization_pack(builder: CapabilityBuilder, agent: Any) -> list[CapSpec]:
    """Register cognitive localization capabilities — chart, overlap, blind spots, atlas, diversity."""

    def _wrap(fn):
        async def _w(payload):
            return await fn({**payload, "__agent__": agent})
        return _w

    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="localize-chart",
        handler=_wrap(_localize_chart),
        version="1.0.0",
        description="Describe an agent's local chart — domain, vocabulary, coverage",
        inputs=[],
        outputs=["agent", "domain", "vocabulary", "ok"],
        tags=["localization", "chart", "topology", "introspection"],
    ))
    specs.append(builder.register(
        name="localize-overlap",
        handler=_wrap(_localize_overlap),
        version="1.0.0",
        description="Compute vocabulary overlap between this agent and a named peer",
        inputs=["peer"],
        outputs=["overlap", "coverage", "ok"],
        tags=["localization", "overlap", "topology"],
    ))
    specs.append(builder.register(
        name="localize-blindspots",
        handler=_wrap(_localize_blindspots),
        version="1.0.0",
        description="Find blind spots — unmatched focus, isolated capabilities, dark topics",
        inputs=[],
        outputs=["blind_spots", "count", "ok"],
        tags=["localization", "blind-spots", "fog", "introspection"],
    ))
    specs.append(builder.register(
        name="localize-atlas-holes",
        handler=_wrap(_localize_atlas_holes),
        version="1.0.0",
        description="Find topics that no agent covers — atlas holes in the knowledge mesh",
        inputs=[],
        outputs=["holes", "agent_count", "ok"],
        tags=["localization", "atlas", "topology", "fog"],
    ))
    specs.append(builder.register(
        name="localize-diversity",
        handler=_wrap(_localize_knowledge_diversity),
        version="1.0.0",
        description="Compute knowledge diversity across the mesh — unique vs shared vocabulary",
        inputs=[],
        outputs=["diversity_index", "total_vocabulary_size", "ok"],
        tags=["localization", "diversity", "topology", "introspection"],
    ))
    return specs


# ─── Evaluation Pack ────────────────────────────────────────────────────

# Tracks quality scores per capability/agent over time, computes benchmarks,
# and supports inter-agent comparison.

_eval_history: dict[str, list[dict[str, Any]]] = {}


def _record_eval(cap_name: str, agent_name: str, score: float, metadata: dict[str, Any] | None = None) -> None:
    key = f"{agent_name}:{cap_name}"
    entry = {"score": score, "ts": time.time(), "metadata": metadata or {}}
    _eval_history.setdefault(key, []).append(entry)


async def _eval_score_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Score an output against criteria. Supports numeric, boolean, and rubric-based scoring."""
    output = payload.get("output", "")
    criteria = payload.get("criteria", [])
    mode = payload.get("mode", "numeric")  # numeric | rubric | pass_fail
    agent_name = payload.get("agent_name", "unknown")
    cap_name = payload.get("capability", "unspecified")

    if mode == "pass_fail":
        passed = payload.get("expected_pass", False)
        score = 1.0 if passed else 0.0
        _record_eval(cap_name, agent_name, score, {"mode": "pass_fail"})
        return {"score": score, "passed": passed, "ok": True}

    if mode == "rubric":
        rubric = payload.get("rubric", [])  # list of {"name": str, "weight": float, "score": float}
        if not rubric:
            return {"score": 0.0, "ok": False, "error": "No rubric provided"}
        total_weight = sum(r.get("weight", 1.0) for r in rubric)
        weighted = sum(r.get("score", 0.0) * r.get("weight", 1.0) for r in rubric)
        score = weighted / total_weight if total_weight > 0 else 0.0
        _record_eval(cap_name, agent_name, score, {"mode": "rubric", "rubric": rubric})
        return {"score": round(score, 4), "rubric": rubric, "ok": True}

    # Default: numeric
    score = payload.get("score", 0.0)
    score = max(0.0, min(1.0, float(score)))
    _record_eval(cap_name, agent_name, score, {"mode": "numeric", "criteria": criteria})
    return {"score": score, "ok": True}


async def _eval_get_history(payload: dict[str, Any]) -> dict[str, Any]:
    """Retrieve evaluation history for an agent/capability pair."""
    agent_name = payload.get("agent_name", "")
    cap_name = payload.get("capability", "")
    limit = payload.get("limit", 50)

    if agent_name and cap_name:
        key = f"{agent_name}:{cap_name}"
        entries = _eval_history.get(key, [])[-limit:]
    elif agent_name:
        entries = []
        for k, v in _eval_history.items():
            if k.startswith(f"{agent_name}:"):
                entries.extend(v[-limit:])
    else:
        entries = []
        for v in _eval_history.values():
            entries.extend(v[-limit:])

    entries.sort(key=lambda e: e["ts"], reverse=True)
    return {"entries": entries[:limit], "count": len(entries), "ok": True}


async def _eval_benchmark(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute benchmark statistics across evaluations for a capability."""
    cap_name = payload.get("capability", "")
    agent_name = payload.get("agent_name", "")

    relevant: list[dict[str, Any]] = []
    for k, entries in _eval_history.items():
        parts = k.split(":", 1)
        a_name, c_name = parts[0], parts[1] if len(parts) > 1 else ""
        if cap_name and c_name != cap_name:
            continue
        if agent_name and a_name != agent_name:
            continue
        relevant.extend(entries)

    if not relevant:
        return {"ok": True, "count": 0, "mean": 0.0, "min": 0.0, "max": 0.0, "std": 0.0, "trend": "no_data"}

    scores = [e["score"] for e in relevant]
    mean_score = statistics.mean(scores)
    min_score = min(scores)
    max_score = max(scores)
    std_score = statistics.stdev(scores) if len(scores) > 1 else 0.0

    # Trend: compare last 3 vs first 3
    trend = "stable"
    if len(scores) >= 4:
        recent = statistics.mean(scores[-3:])
        early = statistics.mean(scores[:3])
        if recent > early + 0.05:
            trend = "improving"
        elif recent < early - 0.05:
            trend = "declining"

    return {
        "ok": True,
        "count": len(scores),
        "mean": round(mean_score, 4),
        "min": round(min_score, 4),
        "max": round(max_score, 4),
        "std": round(std_score, 4),
        "trend": trend,
    }


async def _eval_compare(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare evaluation performance between two agents."""
    agent_a = payload.get("agent_a", "")
    agent_b = payload.get("agent_b", "")
    cap_name = payload.get("capability", "")

    if not agent_a or not agent_b:
        return {"ok": False, "error": "Both agent_a and agent_b required"}

    def _stats_for(agent: str) -> dict[str, Any]:
        scores: list[float] = []
        for k, entries in _eval_history.items():
            parts = k.split(":", 1)
            if parts[0] != agent:
                continue
            if cap_name and (len(parts) < 2 or parts[1] != cap_name):
                continue
            scores.extend(e["score"] for e in entries)
        if not scores:
            return {"count": 0, "mean": 0.0}
        return {"count": len(scores), "mean": round(statistics.mean(scores), 4)}

    stats_a = _stats_for(agent_a)
    stats_b = _stats_for(agent_b)

    if stats_a["count"] == 0 or stats_b["count"] == 0:
        return {"ok": True, "agent_a": stats_a, "agent_b": stats_b, "winner": "insufficient_data"}

    winner = agent_a if stats_a["mean"] > stats_b["mean"] else agent_b
    delta = abs(stats_a["mean"] - stats_b["mean"])

    return {
        "ok": True,
        "agent_a": stats_a,
        "agent_b": stats_b,
        "winner": winner,
        "delta": round(delta, 4),
    }


async def _eval_leaderboard(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a leaderboard of agents ranked by evaluation score."""
    cap_name = payload.get("capability", "")
    top_n = payload.get("top_n", 10)

    agent_scores: dict[str, list[float]] = {}
    for k, entries in _eval_history.items():
        parts = k.split(":", 1)
        if cap_name and (len(parts) < 2 or parts[1] != cap_name):
            continue
        agent = parts[0]
        agent_scores.setdefault(agent, []).extend(e["score"] for e in entries)

    board = []
    for agent, scores in agent_scores.items():
        board.append({
            "agent": agent,
            "mean_score": round(statistics.mean(scores), 4),
            "eval_count": len(scores),
            "latest_score": round(scores[-1], 4) if scores else 0.0,
        })

    board.sort(key=lambda x: x["mean_score"], reverse=True)
    return {"leaderboard": board[:top_n], "total_agents": len(board), "ok": True}


def load_evaluation_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Register evaluation and benchmarking capabilities.

    Provides structured quality scoring, benchmark tracking, inter-agent
    comparison, and leaderboard generation.
    """
    specs = []

    specs.append(builder.register(
        name="eval-score",
        handler=_eval_score_output,
        version="1.0.0",
        description="Score an output against criteria (numeric, rubric, or pass/fail)",
        inputs=["output", "mode", "score", "criteria", "rubric"],
        outputs=["score", "ok"],
        tags=["evaluation", "quality", "scoring"],
    ))

    specs.append(builder.register(
        name="eval-history",
        handler=_eval_get_history,
        version="1.0.0",
        description="Retrieve evaluation history for an agent or capability",
        inputs=["agent_name", "capability", "limit"],
        outputs=["entries", "count", "ok"],
        tags=["evaluation", "history", "tracking"],
    ))

    specs.append(builder.register(
        name="eval-benchmark",
        handler=_eval_benchmark,
        version="1.0.0",
        description="Compute benchmark statistics (mean, std, trend) for evaluations",
        inputs=["capability", "agent_name"],
        outputs=["count", "mean", "min", "max", "std", "trend", "ok"],
        tags=["evaluation", "benchmark", "statistics"],
    ))

    specs.append(builder.register(
        name="eval-compare",
        handler=_eval_compare,
        version="1.0.0",
        description="Compare evaluation performance between two agents",
        inputs=["agent_a", "agent_b", "capability"],
        outputs=["agent_a", "agent_b", "winner", "delta", "ok"],
        tags=["evaluation", "comparison", "benchmark"],
    ))

    specs.append(builder.register(
        name="eval-leaderboard",
        handler=_eval_leaderboard,
        version="1.0.0",
        description="Generate a ranked leaderboard of agents by evaluation score",
        inputs=["capability", "top_n"],
        outputs=["leaderboard", "total_agents", "ok"],
        tags=["evaluation", "leaderboard", "ranking"],
    ))

    return specs


# ─── Adapter Pack ────────────────────────────────────────────────────────

async def _adapter_format(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert data between formats (json, csv, yaml, toml, xml-stub, plain)."""
    data = payload.get("data", "")
    from_fmt = payload.get("from_format", "json").lower()
    to_fmt = payload.get("to_format", "json").lower()

    if not data or not str(data).strip():
        raise ValueError("No data provided")

    # Parse from source format
    parsed: Any = None
    try:
        if from_fmt == "json":
            import json
            parsed = json.loads(data)
        elif from_fmt == "csv":
            import csv
            import io
            reader = csv.DictReader(io.StringIO(data))
            parsed = list(reader)
        elif from_fmt == "yaml":
            try:
                import yaml
                parsed = yaml.safe_load(data)
            except ImportError:
                raise ValueError("PyYAML not installed")
        elif from_fmt == "toml":
            try:
                import tomllib
                parsed = tomllib.loads(data)
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore
                    parsed = tomllib.loads(data)
                except ImportError:
                    raise ValueError("TOML support not available")
        elif from_fmt in ("text", "plain"):
            parsed = data
        else:
            raise ValueError(f"Unknown source format: {from_fmt}")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Parse error: {e}")

    # Serialize to target format
    output = ""
    try:
        if to_fmt == "json":
            import json
            indent = payload.get("indent", 2)
            output = json.dumps(parsed, indent=indent, ensure_ascii=False)
        elif to_fmt == "csv":
            import csv
            import io
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                buf = io.StringIO()
                writer = csv.DictWriter(buf, fieldnames=parsed[0].keys())
                writer.writeheader()
                writer.writerows(parsed)
                output = buf.getvalue()
            else:
                raise ValueError("CSV export requires list of dicts")
        elif to_fmt == "yaml":
            try:
                import yaml
                output = yaml.dump(parsed, default_flow_style=False, allow_unicode=True)
            except ImportError:
                raise ValueError("PyYAML not installed")
        elif to_fmt == "toml":
            try:
                import tomli_w
                output = tomli_w.dumps(parsed)
            except ImportError:
                raise ValueError("tomli-w not installed")
        elif to_fmt in ("text", "plain"):
            output = str(parsed)
        else:
            raise ValueError(f"Unknown target format: {to_fmt}")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Serialize error: {e}")

    return {"ok": True, "output": output, "from": from_fmt, "to": to_fmt}


async def _adapter_schema_map(payload: dict[str, Any]) -> dict[str, Any]:
    """Map fields between two schemas using a mapping definition.

    Input: source data, source schema fields, target schema fields, and optional
    explicit mapping. Produces the mapped output.
    """
    source = payload.get("data", {})
    source_fields = payload.get("source_fields", [])
    target_fields = payload.get("target_fields", [])
    mapping = payload.get("mapping", {})  # source_field -> target_field

    if not source:
        raise ValueError("No source data")

    # Auto-generate mapping if not provided: match by name similarity
    if not mapping:
        for sf in source_fields:
            best_match = ""
            best_score = 0.0
            for tf in target_fields:
                score = _trigram_similarity(sf, tf)
                if score > best_score:
                    best_score = score
                    best_match = tf
            if best_match and best_score > 0.3:
                mapping[sf] = best_match

    # Apply mapping
    mapped: dict[str, Any] = {}
    unmapped: list[str] = []

    source_dict = source if isinstance(source, dict) else {source_fields[i]: v for i, v in enumerate(source) if i < len(source_fields)}

    for sf, tf in mapping.items():
        if sf in source_dict:
            mapped[tf] = source_dict[sf]
        else:
            unmapped.append(sf)

    # Carry over unmapped fields
    for key, val in source_dict.items():
        if key not in mapping:
            mapped[key] = val

    return {
        "ok": True,
        "mapped": mapped,
        "mapping_used": mapping,
        "unmapped_fields": unmapped,
    }


async def _adapter_bridge(payload: dict[str, Any]) -> dict[str, Any]:
    """Bridge between two agent protocol versions.

    Wraps/unwraps messages for compatibility between agents speaking
    different protocol versions.
    """
    message = payload.get("message", {})
    from_version = payload.get("from_version", "1.0")
    to_version = payload.get("to_version", "1.0")

    if from_version == to_version:
        return {"ok": True, "message": message, "bridged": False}

    bridged = dict(message)

    # v1.0 -> v2.0: wrap payload in nested structure
    if from_version.startswith("1.") and to_version.startswith("2."):
        bridged = {
            "envelope": {
                "version": to_version,
                "timestamp": time.time(),
            },
            "payload": message,
            "metadata": message.pop("metadata", {}) if isinstance(message, dict) else {},
        }
    # v2.0 -> v1.0: flatten envelope
    elif from_version.startswith("2.") and to_version.startswith("1."):
        if "payload" in bridged:
            inner = bridged["payload"]
            if isinstance(inner, dict):
                meta = bridged.get("metadata", {})
                inner.update(meta)
                bridged = inner
        elif "envelope" in bridged:
            bridged.pop("envelope", None)

    return {"ok": True, "message": bridged, "bridged": True}


async def _adapter_normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize data to a canonical form — strip whitespace, unify casing,
    flatten nested dicts, standardize date/number formats."""
    data = payload.get("data")
    rules = payload.get("rules", {})

    if data is None:
        raise ValueError("No data provided")

    def _normalize(value: Any, rule_overrides: dict[str, Any] | None = None) -> Any:
        r = rule_overrides or rules
        if isinstance(value, dict):
            return {k: _normalize(v, r) for k, v in value.items()}
        elif isinstance(value, list):
            return [_normalize(v, r) for v in value]
        elif isinstance(value, str):
            result = value
            if r.get("strip", True):
                result = result.strip()
            if r.get("lowercase"):
                result = result.lower()
            if r.get("uppercase"):
                result = result.upper()
            return result
        return value

    normalized = _normalize(data)
    return {"ok": True, "normalized": normalized}


async def _adapter_validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate data against a schema definition.

    Checks required fields, type constraints, and enum values.
    """
    data = payload.get("data", {})
    schema = payload.get("schema", {})

    if not schema:
        return {"ok": True, "valid": True, "errors": []}

    errors: list[str] = []
    required = schema.get("required", [])
    fields = schema.get("fields", {})

    # Check required fields
    for field_name in required:
        if isinstance(data, dict) and field_name not in data:
            errors.append(f"Missing required field: {field_name}")

    # Check field types and enums
    for field_name, constraints in fields.items():
        if isinstance(data, dict) and field_name in data:
            val = data[field_name]
            expected_type = constraints.get("type")
            if expected_type:
                type_map = {
                    "string": str, "int": int, "float": (int, float),
                    "bool": bool, "list": list, "dict": dict,
                }
                expected = type_map.get(expected_type)
                if expected and not isinstance(val, expected):
                    errors.append(f"Field {field_name}: expected {expected_type}, got {type(val).__name__}")
            allowed = constraints.get("enum")
            if allowed and val not in allowed:
                errors.append(f"Field {field_name}: value {val!r} not in {allowed}")

    return {
        "ok": True,
        "valid": len(errors) == 0,
        "errors": errors,
    }


# ─── Learning Pack ──────────────────────────────────────────────────────

# Module-level learning store: maps (agent_name, capability) -> stats
_learning_store: dict[tuple[str, str], dict[str, Any]] = {}


def _learn_get_stats(agent: str, cap: str) -> dict[str, Any]:
    """Get or create learning stats for an agent-capability pair."""
    key = (agent, cap)
    if key not in _learning_store:
        _learning_store[key] = {
            "attempts": 0,
            "successes": 0,
            "failures": 0,
            "total_score": 0.0,
            "recent_grades": [],  # last 20 grades
            "improvements": 0,  # consecutive improving results
        }
    return _learning_store[key]


async def _learn_record(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a task outcome for learning."""
    agent = payload.get("agent", "unknown")
    capability = payload.get("capability", "")
    success = payload.get("success", False)
    grade = payload.get("grade", "")  # A-F
    score = payload.get("score", 0.0)  # 0-1 numeric

    if not capability:
        raise ValueError("capability is required")

    stats = _learn_get_stats(agent, capability)
    stats["attempts"] += 1

    if success:
        stats["successes"] += 1
    else:
        stats["failures"] += 1

    if score > 0:
        stats["total_score"] += score

    if grade:
        stats["recent_grades"].append(grade)
        stats["recent_grades"] = stats["recent_grades"][-20:]
        # Track improvement streak
        grades_list = stats["recent_grades"]
        if len(grades_list) >= 2:
            grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
            if grade_order.get(grades_list[-1], 0) > grade_order.get(grades_list[-2], 0):
                stats["improvements"] += 1
            else:
                stats["improvements"] = 0

    success_rate = stats["successes"] / stats["attempts"] if stats["attempts"] else 0.0
    avg_score = stats["total_score"] / stats["attempts"] if stats["attempts"] else 0.0

    return {
        "ok": True,
        "agent": agent,
        "capability": capability,
        "recorded": True,
        "success_rate": round(success_rate, 3),
        "avg_score": round(avg_score, 3),
        "attempts": stats["attempts"],
        "improvement_streak": stats["improvements"],
    }


async def _learn_proficiency(payload: dict[str, Any]) -> dict[str, Any]:
    """Get proficiency report for an agent's capabilities."""
    agent = payload.get("agent", "unknown")
    capability = payload.get("capability", None)  # specific or all

    results: list[dict[str, Any]] = []
    target_caps = [capability] if capability else sorted(
        k[1] for k in _learning_store if k[0] == agent
    )

    for cap in target_caps:
        stats = _learn_get_stats(agent, cap)
        if stats["attempts"] == 0 and capability is None:
            continue

        success_rate = stats["successes"] / stats["attempts"] if stats["attempts"] else 0.0
        avg_score = stats["total_score"] / stats["attempts"] if stats["attempts"] else 0.0

        # Compute proficiency level
        if avg_score >= 0.9 and success_rate >= 0.9:
            level = "expert"
        elif avg_score >= 0.75 and success_rate >= 0.8:
            level = "proficient"
        elif avg_score >= 0.5 and success_rate >= 0.6:
            level = "competent"
        elif stats["attempts"] > 0:
            level = "developing"
        else:
            level = "untested"

        results.append({
            "capability": cap,
            "level": level,
            "success_rate": round(success_rate, 3),
            "avg_score": round(avg_score, 3),
            "attempts": stats["attempts"],
            "improvement_streak": stats["improvements"],
            "recent_grades": stats["recent_grades"][-5:],
        })

    return {
        "ok": True,
        "agent": agent,
        "proficiencies": results,
        "total_capabilities": len(results),
    }


async def _learn_suggest(payload: dict[str, Any]) -> dict[str, Any]:
    """Suggest capabilities that need improvement."""
    agent = payload.get("agent", "unknown")
    threshold = payload.get("threshold", 0.6)

    suggestions: list[dict[str, Any]] = []
    for (a, cap), stats in _learning_store.items():
        if a != agent or stats["attempts"] < 2:
            continue
        avg_score = stats["total_score"] / stats["attempts"]
        success_rate = stats["successes"] / stats["attempts"]
        if avg_score < threshold or success_rate < threshold:
            suggestions.append({
                "capability": cap,
                "avg_score": round(avg_score, 3),
                "success_rate": round(success_rate, 3),
                "reason": "low_score" if avg_score < threshold else "low_success",
                "attempts": stats["attempts"],
            })

    suggestions.sort(key=lambda s: s["avg_score"])
    return {
        "ok": True,
        "agent": agent,
        "suggestions": suggestions[:10],
        "count": len(suggestions),
    }


async def _learn_reset(payload: dict[str, Any]) -> dict[str, Any]:
    """Reset learning data for an agent or specific capability."""
    agent = payload.get("agent", "unknown")
    capability = payload.get("capability", None)

    if capability:
        key = (agent, capability)
        if key in _learning_store:
            del _learning_store[key]
            removed = 1
        else:
            removed = 0
    else:
        keys = [k for k in _learning_store if k[0] == agent]
        removed = len(keys)
        for k in keys:
            del _learning_store[k]

    return {
        "ok": True,
        "agent": agent,
        "capability": capability,
        "removed": removed,
    }


def load_learning_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load the learning/feedback capability pack.

    Provides agents with the ability to record task outcomes,
    track proficiency across capabilities, get improvement
    suggestions, and reset learning data.

    Caps: learn-record, learn-proficiency, learn-suggest, learn-reset.
    """
    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="learn-record",
        handler=_learn_record,
        version="1.0.0",
        description="Record a task outcome (success/failure, grade, score)",
        inputs=["agent", "capability", "success", "grade", "score"],
        outputs=["ok", "agent", "capability", "recorded", "success_rate", "avg_score"],
        tags=["learning", "feedback", "outcome", "grading"],
    ))

    specs.append(builder.register(
        name="learn-proficiency",
        handler=_learn_proficiency,
        version="1.0.0",
        description="Get proficiency report for agent capabilities",
        inputs=["agent", "capability"],
        outputs=["ok", "agent", "proficiencies", "total_capabilities"],
        tags=["learning", "proficiency", "skill", "assessment"],
    ))

    specs.append(builder.register(
        name="learn-suggest",
        handler=_learn_suggest,
        version="1.0.0",
        description="Suggest capabilities that need improvement",
        inputs=["agent", "threshold"],
        outputs=["ok", "agent", "suggestions", "count"],
        tags=["learning", "suggestion", "improvement", "feedback"],
    ))

    specs.append(builder.register(
        name="learn-reset",
        handler=_learn_reset,
        version="1.0.0",
        description="Reset learning data for an agent or capability",
        inputs=["agent", "capability"],
        outputs=["ok", "agent", "capability", "removed"],
        tags=["learning", "reset", "clear", "fresh-start"],
    ))

    return specs


def load_adapter_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load the adapter/translation capability pack.

    Provides format conversion, schema mapping, protocol bridging,
    data normalization, and schema validation — essential for
    inter-agent communication across heterogeneous meshes.
    """
    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="adapter-format",
        handler=_adapter_format,
        version="1.0.0",
        description="Convert data between formats (json, csv, yaml, toml, text)",
        inputs=["data", "from_format", "to_format"],
        outputs=["ok", "output", "from", "to"],
        tags=["adapter", "format", "conversion", "serialization"],
    ))

    specs.append(builder.register(
        name="adapter-schema-map",
        handler=_adapter_schema_map,
        version="1.0.0",
        description="Map fields between schemas using explicit or auto-detected mapping",
        inputs=["data", "source_fields", "target_fields"],
        outputs=["ok", "mapped", "mapping_used", "unmapped_fields"],
        tags=["adapter", "schema", "mapping", "translation"],
    ))

    specs.append(builder.register(
        name="adapter-bridge",
        handler=_adapter_bridge,
        version="1.0.0",
        description="Bridge messages between protocol versions (v1.x ↔ v2.x)",
        inputs=["message", "from_version", "to_version"],
        outputs=["ok", "message", "bridged"],
        tags=["adapter", "protocol", "bridge", "compatibility"],
    ))

    specs.append(builder.register(
        name="adapter-normalize",
        handler=_adapter_normalize,
        version="1.0.0",
        description="Normalize data to canonical form (strip, case, flatten)",
        inputs=["data"],
        outputs=["ok", "normalized"],
        tags=["adapter", "normalize", "clean", "canonical"],
    ))

    specs.append(builder.register(
        name="adapter-validate",
        handler=_adapter_validate,
        version="1.0.0",
        description="Validate data against a schema (required fields, types, enums)",
        inputs=["data", "schema"],
        outputs=["ok", "valid", "errors"],
        tags=["adapter", "validate", "schema", "check"],
    ))

    return specs


# ─── Security Pack ──────────────────────────────────────────────────────

# In-memory stores for security pack (per-process)
_security_tokens: dict[str, dict[str, Any]] = {}
_security_rate_limits: dict[str, list[float]] = {}
_security_audit_log: list[dict[str, Any]] = []


async def _security_auth_token(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate or issue a simple auth token.

    Modes:
      issue  — generate a new token for an agent/role pair.
      verify — check an existing token is valid and not expired.
    """
    mode = payload.get("mode", "verify")
    agent_name = payload.get("agent", "")
    role = payload.get("role", "agent")
    token = payload.get("token", "")
    ttl_seconds = payload.get("ttl", 3600)

    if mode == "issue":
        if not agent_name:
            return {"ok": False, "error": "agent name required"}
        new_token = f"mf_{uuid.uuid4().hex[:24]}"
        _security_tokens[new_token] = {
            "agent": agent_name,
            "role": role,
            "issued_at": time.time(),
            "expires_at": time.time() + ttl_seconds,
        }
        return {
            "ok": True,
            "token": new_token,
            "agent": agent_name,
            "role": role,
            "expires_in": ttl_seconds,
        }

    # verify mode
    if not token:
        return {"ok": False, "error": "token required for verification"}
    record = _security_tokens.get(token)
    if not record:
        return {"ok": False, "error": "token not found", "valid": False}
    if time.time() > record["expires_at"]:
        del _security_tokens[token]
        return {"ok": False, "error": "token expired", "valid": False}
    return {
        "ok": True,
        "valid": True,
        "agent": record["agent"],
        "role": record["role"],
    }


async def _security_permission_check(payload: dict[str, Any]) -> dict[str, Any]:
    """Check if an agent has a specific permission.

    Uses a simple role-based model with predefined role permissions.
    """
    ROLE_PERMISSIONS: dict[str, set[str]] = {
        "admin": {"read", "write", "delete", "manage", "invoke", "delegate"},
        "operator": {"read", "write", "invoke", "delegate"},
        "agent": {"read", "invoke"},
        "observer": {"read"},
    }

    role = payload.get("role", "agent")
    permission = payload.get("permission", "")
    agent_name = payload.get("agent", "unknown")

    if not permission:
        return {"ok": False, "error": "permission required"}

    perms = ROLE_PERMISSIONS.get(role, set())
    allowed = permission in perms

    _security_audit_log.append({
        "ts": time.time(),
        "action": "permission_check",
        "agent": agent_name,
        "role": role,
        "permission": permission,
        "allowed": allowed,
    })

    return {
        "ok": True,
        "allowed": allowed,
        "role": role,
        "permission": permission,
        "agent": agent_name,
    }


async def _security_rate_limit(payload: dict[str, Any]) -> dict[str, Any]:
    """Check or enforce a sliding-window rate limit for a key.

    Call with action='check' to test, action='consume' to count the request.
    """
    action = payload.get("action", "check")
    key = payload.get("key", "default")
    max_requests = payload.get("max_requests", 100)
    window_seconds = payload.get("window_seconds", 60)

    now = time.time()
    window_start = now - window_seconds

    # Clean old entries
    if key not in _security_rate_limits:
        _security_rate_limits[key] = []
    _security_rate_limits[key] = [
        t for t in _security_rate_limits[key] if t > window_start
    ]

    current_count = len(_security_rate_limits[key])
    allowed = current_count < max_requests

    if action == "consume" and allowed:
        _security_rate_limits[key].append(now)
        current_count += 1
        allowed = current_count <= max_requests

    return {
        "ok": True,
        "allowed": allowed,
        "key": key,
        "current": current_count,
        "limit": max_requests,
        "window_seconds": window_seconds,
    }


async def _security_sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize input data — strip dangerous patterns.

    Removes HTML tags, normalizes whitespace, blocks injection patterns.
    """
    data = payload.get("data", "")
    mode = payload.get("mode", "text")  # text | strict

    if not isinstance(data, str):
        return {"ok": False, "error": "data must be a string"}

    original_length = len(data)
    cleaned = data

    # Strip HTML tags
    cleaned = re.sub(r'<[^>]+>', '', cleaned)

    # Normalize whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    threats = []

    if mode == "strict":
        # Block common injection patterns
        injection_patterns = [
            (r'(?:;|\|)\s*(?:rm|del|drop|shutdown|exec|eval|system)\b', 'command_injection'),
            (r'(?:UNION|SELECT|INSERT|DROP|DELETE)\s', 'sql_injection'),
            (r'<script', 'xss'),
            (r'\.\.[/\\]', 'path_traversal'),
        ]
        for pattern, threat_name in injection_patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                threats.append(threat_name)
                cleaned = re.sub(pattern, '[BLOCKED]', cleaned, flags=re.IGNORECASE)

    return {
        "ok": True,
        "cleaned": cleaned,
        "original_length": original_length,
        "cleaned_length": len(cleaned),
        "threats": threats,
        "safe": len(threats) == 0,
    }


async def _security_audit(payload: dict[str, Any]) -> dict[str, Any]:
    """Query or append to the security audit log."""
    action = payload.get("action", "query")
    agent_filter = payload.get("agent", None)
    limit = payload.get("limit", 50)

    if action == "append":
        entry = {
            "ts": time.time(),
            "action": payload.get("event", "custom"),
            "agent": payload.get("agent", "unknown"),
            "details": payload.get("details", {}),
        }
        _security_audit_log.append(entry)
        return {"ok": True, "recorded": True}

    # query mode
    entries = _security_audit_log
    if agent_filter:
        entries = [e for e in entries if e.get("agent") == agent_filter]
    entries = entries[-limit:]

    return {
        "ok": True,
        "entries": entries,
        "total": len(_security_audit_log),
        "returned": len(entries),
    }


def load_security_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load the security capability pack.

    Provides authentication, authorization, rate limiting, input
    sanitization, and audit logging — essential for secure mesh
    communication between agents.

    Caps: sec-auth, sec-permission, sec-rate-limit, sec-sanitize, sec-audit.
    """
    specs: list[CapSpec] = []

    specs.append(builder.register(
        name="sec-auth",
        handler=_security_auth_token,
        version="1.0.0",
        description="Issue or verify auth tokens for agent identity",
        inputs=["mode"],
        outputs=["ok", "token", "valid", "agent", "role", "expires_in"],
        tags=["security", "auth", "token", "identity"],
    ))

    specs.append(builder.register(
        name="sec-permission",
        handler=_security_permission_check,
        version="1.0.0",
        description="Check if a role has a specific permission",
        inputs=["role", "permission"],
        outputs=["ok", "allowed", "role", "permission"],
        tags=["security", "permission", "rbac", "authorization"],
    ))

    specs.append(builder.register(
        name="sec-rate-limit",
        handler=_security_rate_limit,
        version="1.0.0",
        description="Sliding-window rate limiter for keys/agents",
        inputs=["action", "key"],
        outputs=["ok", "allowed", "current", "limit"],
        tags=["security", "rate-limit", "throttle", "quota"],
    ))

    specs.append(builder.register(
        name="sec-sanitize",
        handler=_security_sanitize,
        version="1.0.0",
        description="Sanitize input data, strip dangerous patterns",
        inputs=["data", "mode"],
        outputs=["ok", "cleaned", "threats", "safe"],
        tags=["security", "sanitize", "validation", "injection"],
    ))

    specs.append(builder.register(
        name="sec-audit",
        handler=_security_audit,
        version="1.0.0",
        description="Query or append to the security audit log",
        inputs=["action"],
        outputs=["ok", "entries", "total", "returned"],
        tags=["security", "audit", "log", "compliance"],
    ))

    return specs


# ─── Audience Analytics Pack ─────────────────────────────────────────────

_routing_log: list[dict[str, Any]] = []
_signal_weights: dict[str, float] = {
    "capability": 0.30,
    "focus": 0.25,
    "trust": 0.20,
    "fog_gap": 0.15,
    "topology": 0.10,
}


async def _audience_record(payload: dict[str, Any]) -> dict[str, Any]:
    """Record a routing decision and its outcome for later analysis.

    Inputs:
        topic      – the routed topic
        agent      – the agent that was routed to
        score      – the routing score
        signals    – list of signal names that contributed
        outcome    – "success" | "partial" | "fail" | "timeout"
        metadata   – optional dict of extra context
    """
    entry = {
        "id": str(uuid.uuid4()),
        "topic": payload.get("topic", ""),
        "agent": payload.get("agent", ""),
        "score": float(payload.get("score", 0.0)),
        "signals": payload.get("signals", []),
        "outcome": payload.get("outcome", "unknown"),
        "metadata": payload.get("metadata", {}),
        "ts": time.time(),
    }
    _routing_log.append(entry)
    # Keep bounded
    if len(_routing_log) > 1000:
        del _routing_log[:100]
    return {"ok": True, "recorded_id": entry["id"], "total": len(_routing_log)}


async def _audience_analyze(payload: dict[str, Any]) -> dict[str, Any]:
    """Analyze routing history to find patterns and effectiveness.

    Inputs:
        topic     – optional filter by topic substring
        agent     – optional filter by agent name
        outcome   – optional filter by outcome
        since     – optional minimum timestamp
    """
    topic_filter = payload.get("topic", "").lower()
    agent_filter = payload.get("agent", "").lower()
    outcome_filter = payload.get("outcome", "").lower()
    since = payload.get("since", 0.0)

    filtered = [
        e for e in _routing_log
        if (not topic_filter or topic_filter in e["topic"].lower())
        and (not agent_filter or agent_filter in e["agent"].lower())
        and (not outcome_filter or outcome_filter == e["outcome"].lower())
        and e["ts"] >= since
    ]

    if not filtered:
        return {"ok": True, "count": 0, "summary": "No matching records"}

    # Outcome distribution
    outcomes: dict[str, int] = {}
    for e in filtered:
        o = e["outcome"]
        outcomes[o] = outcomes.get(o, 0) + 1
    total = len(filtered)
    success_rate = (outcomes.get("success", 0) + 0.5 * outcomes.get("partial", 0)) / total

    # Signal effectiveness — which signals correlate with success?
    signal_stats: dict[str, dict[str, float]] = {}
    for e in filtered:
        for sig in e.get("signals", []):
            if sig not in signal_stats:
                signal_stats[sig] = {"count": 0.0, "success": 0.0}
            signal_stats[sig]["count"] += 1
            if e["outcome"] in ("success", "partial"):
                signal_stats[sig]["success"] += 1

    signal_effectiveness = {
        sig: round(stats["success"] / stats["count"], 3) if stats["count"] else 0.0
        for sig, stats in signal_stats.items()
    }

    # Average score by outcome
    score_by_outcome: dict[str, list[float]] = {}
    for e in filtered:
        score_by_outcome.setdefault(e["outcome"], []).append(e["score"])
    avg_scores = {
        o: round(sum(s) / len(s), 3) for o, s in score_by_outcome.items()
    }

    return {
        "ok": True,
        "count": total,
        "outcomes": outcomes,
        "success_rate": round(success_rate, 3),
        "signal_effectiveness": signal_effectiveness,
        "avg_score_by_outcome": avg_scores,
    }


async def _audience_weights(payload: dict[str, Any]) -> dict[str, Any]:
    """Get or update signal weights for routing.

    Inputs:
        action   – "get" | "set" | "auto_tune"
        weights  – dict of signal→weight (for "set")
    """
    action = payload.get("action", "get")

    if action == "get":
        return {"ok": True, "weights": dict(_signal_weights)}

    if action == "set":
        new_weights = payload.get("weights", {})
        for k, v in new_weights.items():
            if k in _signal_weights:
                _signal_weights[k] = float(v)
        # Normalize
        total_w = sum(_signal_weights.values()) or 1.0
        for k in _signal_weights:
            _signal_weights[k] = round(_signal_weights[k] / total_w, 4)
        return {"ok": True, "weights": dict(_signal_weights)}

    if action == "auto_tune":
        # Use routing log to adjust weights toward effective signals
        if not _routing_log:
            return {"ok": True, "weights": dict(_signal_weights), "tuned": False, "reason": "no data"}

        signal_perf: dict[str, list[bool]] = {}
        for e in _routing_log[-200:]:
            success = e["outcome"] in ("success", "partial")
            for sig in e.get("signals", []):
                signal_perf.setdefault(sig, []).append(success)

        # Compute success rate per signal
        new_w = dict(_signal_weights)
        for sig, results in signal_perf.items():
            if sig in new_w and len(results) >= 5:
                rate = sum(results) / len(results)
                # Boost effective signals, penalize ineffective
                adjustment = (rate - 0.5) * 0.1  # ±0.05 max shift
                new_w[sig] = max(0.01, new_w[sig] + adjustment)

        # Normalize
        total_w = sum(new_w.values()) or 1.0
        for k in new_w:
            new_w[k] = round(new_w[k] / total_w, 4)
        _signal_weights.update(new_w)
        return {"ok": True, "weights": dict(_signal_weights), "tuned": True}

    return {"ok": False, "error": f"Unknown action: {action}"}


async def _audience_suggest(payload: dict[str, Any]) -> dict[str, Any]:
    """Suggest routing improvements based on historical data.

    Inputs:
        topic  – optional topic to get specific suggestions for
    """
    topic = payload.get("topic", "").lower()
    relevant = [
        e for e in _routing_log
        if not topic or topic in e["topic"].lower()
    ]

    if not relevant:
        return {"ok": True, "suggestions": ["Insufficient routing history — keep routing messages to build data"]}

    suggestions = []

    # Find consistently failing agents
    agent_outcomes: dict[str, dict[str, int]] = {}
    for e in relevant:
        agent_outcomes.setdefault(e["agent"], {})
        agent_outcomes[e["agent"]][e["outcome"]] = agent_outcomes[e["agent"]].get(e["outcome"], 0) + 1

    for agent, outcomes in agent_outcomes.items():
        fails = outcomes.get("fail", 0) + outcomes.get("timeout", 0)
        total = sum(outcomes.values())
        if total >= 3 and fails / total > 0.6:
            suggestions.append(
                f"Agent '{agent}' fails {fails}/{total} times — consider excluding or lowering trust"
            )

    # Find underused but effective agents
    for agent, outcomes in agent_outcomes.items():
        successes = outcomes.get("success", 0)
        total = sum(outcomes.values())
        if 1 <= total <= 3 and successes == total:
            suggestions.append(
                f"Agent '{agent}' is 100% successful over {total} routes — consider routing more traffic"
            )

    # Signal advice
    sig_perf: dict[str, list[bool]] = {}
    for e in relevant:
        success = e["outcome"] in ("success", "partial")
        for sig in e.get("signals", []):
            sig_perf.setdefault(sig, []).append(success)
    for sig, results in sig_perf.items():
        if len(results) >= 5:
            rate = sum(results) / len(results)
            if rate < 0.3:
                suggestions.append(f"Signal '{sig}' has low effectiveness ({rate:.0%}) — consider reducing weight")
            elif rate > 0.8:
                suggestions.append(f"Signal '{sig}' is highly effective ({rate:.0%}) — consider increasing weight")

    if not suggestions:
        suggestions.append("Routing performance looks healthy — no major improvements needed")

    return {"ok": True, "suggestions": suggestions, "based_on": len(relevant)}


def load_audience_analytics_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load audience routing analytics capabilities.

    Capabilities:
    - audience-record:  Record a routing decision + outcome
    - audience-analyze: Analyze routing history (filter, stats, signal effectiveness)
    - audience-weights: Get/set/auto-tune signal weights for routing
    - audience-suggest: Get actionable suggestions for routing improvement
    """
    specs = []

    specs.append(builder.register(
        name="audience-record",
        handler=_audience_record,
        version="1.0.0",
        description="Record a routing decision and outcome for analytics",
        inputs=["topic", "agent", "score", "signals", "outcome"],
        outputs=["ok", "recorded_id", "total"],
        tags=["audience", "routing", "analytics", "feedback"],
    ))

    specs.append(builder.register(
        name="audience-analyze",
        handler=_audience_analyze,
        version="1.0.0",
        description="Analyze routing history — outcomes, signal effectiveness, score patterns",
        inputs=["topic", "agent", "outcome", "since"],
        outputs=["ok", "count", "outcomes", "success_rate", "signal_effectiveness"],
        tags=["audience", "routing", "analytics", "statistics"],
    ))

    specs.append(builder.register(
        name="audience-weights",
        handler=_audience_weights,
        version="1.0.0",
        description="Get, set, or auto-tune signal weights for audience routing",
        inputs=["action", "weights"],
        outputs=["ok", "weights", "tuned"],
        tags=["audience", "routing", "weights", "tuning", "optimization"],
    ))

    specs.append(builder.register(
        name="audience-suggest",
        handler=_audience_suggest,
        version="1.0.0",
        description="Suggest routing improvements based on historical performance",
        inputs=["topic"],
        outputs=["ok", "suggestions", "based_on"],
        tags=["audience", "routing", "analytics", "suggestions", "optimization"],
    ))

    return specs


# ─── Convenience ────────────────────────────────────────────────────────

# ─── Resilience Pack ─────────────────────────────────────────────────────

class _CircuitBreaker:
    """Thread-safe circuit breaker state machine.

    States: closed → open → half_open → closed|open
    Tracks failure count, last failure time, and recovery attempts.
    """

    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: float = 30.0) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = "closed"  # closed | open | half_open
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float = 0.0
        self.last_state_change: float = time.time()

    def record_success(self) -> None:
        self.success_count += 1
        if self.state == "half_open":
            self.state = "closed"
            self.failure_count = 0
            self.last_state_change = time.time()

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.last_state_change = time.time()

    def allow(self) -> bool:
        """Check if a request should be allowed through."""
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_state_change >= self.reset_timeout:
                self.state = "half_open"
                self.last_state_change = time.time()
                return True  # allow one probe
            return False
        # half_open: allow one request to test
        return True

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout,
            "last_failure_time": self.last_failure_time,
            "seconds_since_change": round(time.time() - self.last_state_change, 1),
        }


class _RateLimiter:
    """Token bucket rate limiter.

    Tracks per-key request rates with configurable burst and refill.
    """

    def __init__(self, default_rate: float = 10.0, default_burst: int = 20) -> None:
        self.default_rate = default_rate
        self.default_burst = default_burst
        self._buckets: dict[str, dict[str, Any]] = {}

    def configure(self, key: str, rate: float, burst: int | None = None) -> None:
        self._buckets[key] = {
            "rate": rate,
            "burst": burst or int(rate * 2),
            "tokens": float(burst or int(rate * 2)),
            "last_refill": time.time(),
        }

    def allow(self, key: str) -> bool:
        if key not in self._buckets:
            self.configure(key, self.default_rate, self.default_burst)
        bucket = self._buckets[key]
        now = time.time()
        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(
            bucket["burst"],
            bucket["tokens"] + elapsed * bucket["rate"],
        )
        bucket["last_refill"] = now
        if bucket["tokens"] >= 1.0:
            bucket["tokens"] -= 1.0
            return True
        return False

    def status(self, key: str) -> dict[str, Any]:
        if key not in self._buckets:
            return {"key": key, "configured": False}
        b = self._buckets[key]
        return {
            "key": key,
            "configured": True,
            "rate": b["rate"],
            "burst": b["burst"],
            "tokens_remaining": round(b["tokens"], 1),
        }

    def all_status(self) -> list[dict[str, Any]]:
        return [self.status(k) for k in self._buckets]


# Shared state for resilience pack
_circuit_breakers: dict[str, _CircuitBreaker] = {}
_rate_limiter = _RateLimiter()
_bulkheads: dict[str, dict[str, Any]] = {}


async def _resilience_circuit_check(payload: dict[str, Any]) -> dict[str, Any]:
    """Check or update circuit breaker state."""
    name = payload.get("name", "default")
    action = payload.get("action", "check")  # check | success | failure | reset

    if name not in _circuit_breakers:
        threshold = payload.get("failure_threshold", 5)
        timeout = payload.get("reset_timeout", 30.0)
        _circuit_breakers[name] = _CircuitBreaker(name, threshold, timeout)

    cb = _circuit_breakers[name]

    if action == "success":
        cb.record_success()
    elif action == "failure":
        cb.record_failure()
    elif action == "reset":
        cb.state = "closed"
        cb.failure_count = 0
        cb.last_state_change = time.time()

    return {**cb.status(), "allow": cb.allow(), "ok": True}


async def _resilience_rate_limit(payload: dict[str, Any]) -> dict[str, Any]:
    """Check or configure rate limiting."""
    action = payload.get("action", "check")  # check | configure | status
    key = payload.get("key", "default")

    if action == "configure":
        rate = payload.get("rate", 10.0)
        burst = payload.get("burst")
        _rate_limiter.configure(key, rate, burst)
        return {"ok": True, "key": key, "rate": rate, "burst": burst or int(rate * 2)}

    if action == "status":
        return {"ok": True, "buckets": _rate_limiter.all_status()}

    # check: consume a token
    allowed = _rate_limiter.allow(key)
    return {"ok": True, "key": key, "allowed": allowed}


async def _resilience_retry(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute retry delay with exponential backoff and jitter."""
    attempt = payload.get("attempt", 1)
    base_delay = payload.get("base_delay", 1.0)
    max_delay = payload.get("max_delay", 60.0)
    jitter = payload.get("jitter", True)
    strategy = payload.get("strategy", "exponential")  # exponential | linear | constant

    if strategy == "linear":
        delay = base_delay * attempt
    elif strategy == "constant":
        delay = base_delay
    else:  # exponential
        delay = base_delay * (2 ** (attempt - 1))

    delay = min(delay, max_delay)

    if jitter:
        import random
        delay = delay * (0.5 + random.random() * 0.5)

    return {
        "ok": True,
        "attempt": attempt,
        "delay_seconds": round(delay, 3),
        "strategy": strategy,
        "max_delay": max_delay,
    }


async def _resilience_bulkhead(payload: dict[str, Any]) -> dict[str, Any]:
    """Bulkhead isolation — limit concurrency per pool."""
    action = payload.get("action", "check")  # check | acquire | release | configure | status
    pool = payload.get("pool", "default")

    if action == "configure":
        max_concurrent = payload.get("max_concurrent", 10)
        _bulkheads[pool] = {
            "max_concurrent": max_concurrent,
            "current": 0,
            "total_acquired": 0,
            "total_rejected": 0,
        }
        return {"ok": True, "pool": pool, "max_concurrent": max_concurrent}

    if pool not in _bulkheads:
        _bulkheads[pool] = {"max_concurrent": 10, "current": 0, "total_acquired": 0, "total_rejected": 0}

    bh = _bulkheads[pool]

    if action == "acquire":
        if bh["current"] < bh["max_concurrent"]:
            bh["current"] += 1
            bh["total_acquired"] += 1
            return {"ok": True, "pool": pool, "acquired": True, "current": bh["current"]}
        else:
            bh["total_rejected"] += 1
            return {"ok": True, "pool": pool, "acquired": False, "current": bh["current"], "reason": "at_capacity"}

    if action == "release":
        bh["current"] = max(0, bh["current"] - 1)
        return {"ok": True, "pool": pool, "current": bh["current"]}

    if action == "status":
        return {"ok": True, "pools": {k: dict(v) for k, v in _bulkheads.items()}}

    # check
    return {"ok": True, "pool": pool, "current": bh["current"], "max": bh["max_concurrent"], "available": bh["max_concurrent"] - bh["current"]}


async def _resilience_health(payload: dict[str, Any]) -> dict[str, Any]:
    """Overall resilience health — all circuit breakers, rate limiters, bulkheads."""
    circuits = {name: cb.status() for name, cb in _circuit_breakers.items()}
    open_circuits = [n for n, s in circuits.items() if s["state"] == "open"]
    half_open = [n for n, s in circuits.items() if s["state"] == "half_open"]

    bulkhead_status = {}
    at_capacity = []
    for pool, bh in _bulkheads.items():
        bulkhead_status[pool] = bh
        if bh["current"] >= bh["max_concurrent"]:
            at_capacity.append(pool)

    healthy = len(open_circuits) == 0 and len(at_capacity) == 0

    return {
        "ok": True,
        "healthy": healthy,
        "circuit_breakers": circuits,
        "open_circuits": open_circuits,
        "half_open_circuits": half_open,
        "rate_limiters": _rate_limiter.all_status(),
        "bulkheads": bulkhead_status,
        "at_capacity_bulkheads": at_capacity,
    }


def load_resilience_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load resilience capabilities — circuit breaker, rate limiter, retry backoff, bulkhead.

    Capabilities:
    - resilience-circuit:    Circuit breaker check/update (closed → open → half_open)
    - resilience-rate-limit: Token bucket rate limiting per key
    - resilience-retry:      Compute retry delay with exponential backoff + jitter
    - resilience-bulkhead:   Bulkhead isolation — limit concurrency per pool
    - resilience-health:     Overall resilience subsystem health summary
    """
    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="resilience-circuit",
        handler=_resilience_circuit_check,
        version="1.0.0",
        description="Circuit breaker — track failures, auto-open, probe on half-open",
        inputs=["name", "action"],
        outputs=["ok", "state", "allow"],
        tags=["resilience", "circuit-breaker", "fault-tolerance"],
    ))
    specs.append(builder.register(
        name="resilience-rate-limit",
        handler=_resilience_rate_limit,
        version="1.0.0",
        description="Token bucket rate limiting — configure, check, consume tokens",
        inputs=["key", "action"],
        outputs=["ok", "allowed"],
        tags=["resilience", "rate-limit", "throttling"],
    ))
    specs.append(builder.register(
        name="resilience-retry",
        handler=_resilience_retry,
        version="1.0.0",
        description="Compute retry delay with exponential/linear/constant backoff and jitter",
        inputs=["attempt", "strategy"],
        outputs=["ok", "delay_seconds"],
        tags=["resilience", "retry", "backoff"],
    ))
    specs.append(builder.register(
        name="resilience-bulkhead",
        handler=_resilience_bulkhead,
        version="1.0.0",
        description="Bulkhead isolation — limit concurrent executions per pool",
        inputs=["pool", "action"],
        outputs=["ok", "acquired", "current"],
        tags=["resilience", "bulkhead", "concurrency"],
    ))
    specs.append(builder.register(
        name="resilience-health",
        handler=_resilience_health,
        version="1.0.0",
        description="Overall resilience health — circuits, rate limiters, bulkheads summary",
        inputs=[],
        outputs=["ok", "healthy"],
        tags=["resilience", "health", "observability"],
    ))
    return specs


# ─── Fog Alert Pack ─────────────────────────────────────────────────────

# In-memory alert rule store: name → rule dict
_fog_alert_rules: dict[str, dict[str, Any]] = {}
# In-memory alert history: list of fired alerts
_fog_alert_history: list[dict[str, Any]] = []
_FOG_ALERT_HISTORY_MAX = 200


async def _alert_rule_create(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a fog alert rule.

    Payload keys:
        name:        unique rule name
        event_type:  fog event type to watch (seam.shift, dark.pressure, fog.volume)
        condition:   comparison — {"field": "data.delta", "op": "gt", "value": 0.5}
        topic:       optional topic for audience routing when alert fires
        severity:    info | warning | critical (default: warning)
        cooldown:    min seconds between fires for same rule (default: 60)
    """
    name = payload.get("name", "")
    if not name:
        return {"error": "Rule name is required", "ok": False}
    if name in _fog_alert_rules:
        return {"error": f"Rule '{name}' already exists", "ok": False}

    event_type = payload.get("event_type", "")
    if event_type not in ("seam.shift", "dark.pressure", "fog.volume", "mesh.mutation"):
        return {"error": f"Unsupported event_type: {event_type}", "ok": False}

    condition = payload.get("condition", {})
    if not condition.get("field") or not condition.get("op") or "value" not in condition:
        return {"error": "condition requires field, op, value", "ok": False}

    valid_ops = {"gt", "gte", "lt", "lte", "eq", "ne"}
    if condition["op"] not in valid_ops:
        return {"error": f"Invalid op '{condition['op']}'. Use: {', '.join(sorted(valid_ops))}", "ok": False}

    rule: dict[str, Any] = {
        "name": name,
        "event_type": event_type,
        "condition": condition,
        "topic": payload.get("topic"),
        "severity": payload.get("severity", "warning"),
        "cooldown": payload.get("cooldown", 60),
        "enabled": True,
        "fire_count": 0,
        "last_fired": None,
        "created_at": __import__("time").time(),
    }
    _fog_alert_rules[name] = rule
    return {"ok": True, "rule": {k: v for k, v in rule.items()}, "total_rules": len(_fog_alert_rules)}


async def _alert_rule_delete(payload: dict[str, Any]) -> dict[str, Any]:
    """Delete an alert rule by name."""
    name = payload.get("name", "")
    if name not in _fog_alert_rules:
        return {"error": f"Rule '{name}' not found", "ok": False}
    del _fog_alert_rules[name]
    return {"ok": True, "deleted": name, "total_rules": len(_fog_alert_rules)}


async def _alert_rule_toggle(payload: dict[str, Any]) -> dict[str, Any]:
    """Enable or disable an alert rule."""
    name = payload.get("name", "")
    if name not in _fog_alert_rules:
        return {"error": f"Rule '{name}' not found", "ok": False}
    rule = _fog_alert_rules[name]
    rule["enabled"] = not rule["enabled"]
    return {"ok": True, "name": name, "enabled": rule["enabled"]}


async def _alert_rule_list(payload: dict[str, Any]) -> dict[str, Any]:
    """List all alert rules."""
    rules = [
        {k: v for k, v in r.items()}
        for r in _fog_alert_rules.values()
    ]
    return {"ok": True, "rules": rules, "total": len(rules)}


def _eval_condition(condition: dict[str, Any], event_data: dict[str, Any]) -> bool:
    """Evaluate a condition against event data using dotted field paths."""
    import operator as _op
    ops = {"gt": _op.gt, "gte": _op.ge, "lt": _op.lt, "lte": _op.le, "eq": _op.eq, "ne": _op.ne}

    field_path = condition["field"]
    op_fn = ops.get(condition["op"])
    threshold = condition["value"]

    if op_fn is None:
        return False

    # Navigate dotted path into event_data
    value = event_data
    for part in field_path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return False
        if value is None:
            return False

    try:
        return op_fn(value, threshold)
    except (TypeError, ValueError):
        return False


async def _alert_evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a fog event against all active rules.

    Payload:
        event: dict with 'type', 'timestamp', 'data' (matching FogEvent format)

    Returns list of matching rules and whether they fired (cooldown respected).
    """
    import time as _time

    event = payload.get("event", {})
    event_type = event.get("type", "")
    event_data = event.get("data", {})

    matches: list[dict[str, Any]] = []
    now = _time.time()

    for rule in _fog_alert_rules.values():
        if not rule["enabled"]:
            continue
        if rule["event_type"] != event_type:
            continue
        if not _eval_condition(rule["condition"], event_data):
            continue

        # Cooldown check
        last = rule.get("last_fired") or 0
        cooldown_left = max(0, rule["cooldown"] - (now - last))
        can_fire = cooldown_left == 0

        if can_fire:
            rule["fire_count"] += 1
            rule["last_fired"] = now

            alert_record = {
                "rule": rule["name"],
                "event_type": event_type,
                "severity": rule["severity"],
                "topic": rule.get("topic"),
                "condition": rule["condition"],
                "event_data": event_data,
                "fired_at": now,
            }
            _fog_alert_history.append(alert_record)
            if len(_fog_alert_history) > _FOG_ALERT_HISTORY_MAX:
                _fog_alert_history.pop(0)

        matches.append({
            "rule": rule["name"],
            "severity": rule["severity"],
            "topic": rule.get("topic"),
            "fired": can_fire,
            "cooldown_remaining": round(cooldown_left, 1),
        })

    return {"ok": True, "matches": matches, "total_rules_checked": len(_fog_alert_rules)}


async def _alert_history(payload: dict[str, Any]) -> dict[str, Any]:
    """Return recent alert fire history."""
    limit = min(int(payload.get("limit", 50)), 200)
    severity = payload.get("severity")
    entries = _fog_alert_history
    if severity:
        entries = [e for e in entries if e.get("severity") == severity]
    return {"ok": True, "history": entries[-limit:], "total": len(entries)}


def load_fog_alert_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load fog alerting and escalation capabilities.

    Capabilities:
    - fog-alert-create:  Create an alert rule for fog events
    - fog-alert-delete:  Delete an alert rule
    - fog-alert-toggle:  Enable/disable a rule
    - fog-alert-list:    List all rules
    - fog-alert-eval:    Evaluate a fog event against active rules
    - fog-alert-history: Recent alert fire history
    """
    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="fog-alert-create",
        handler=_alert_rule_create,
        version="1.0.0",
        description="Create a fog alert rule with condition, severity, and optional topic for audience routing",
        inputs=["name", "event_type", "condition"],
        outputs=["ok", "rule"],
        tags=["fog", "alert", "escalation", "monitoring"],
    ))
    specs.append(builder.register(
        name="fog-alert-delete",
        handler=_alert_rule_delete,
        version="1.0.0",
        description="Delete an alert rule by name",
        inputs=["name"],
        outputs=["ok", "deleted"],
        tags=["fog", "alert"],
    ))
    specs.append(builder.register(
        name="fog-alert-toggle",
        handler=_alert_rule_toggle,
        version="1.0.0",
        description="Toggle an alert rule on or off",
        inputs=["name"],
        outputs=["ok", "enabled"],
        tags=["fog", "alert"],
    ))
    specs.append(builder.register(
        name="fog-alert-list",
        handler=_alert_rule_list,
        version="1.0.0",
        description="List all configured alert rules",
        inputs=[],
        outputs=["ok", "rules"],
        tags=["fog", "alert"],
    ))
    specs.append(builder.register(
        name="fog-alert-eval",
        handler=_alert_evaluate,
        version="1.0.0",
        description="Evaluate a fog event against all active alert rules (with cooldown)",
        inputs=["event"],
        outputs=["ok", "matches"],
        tags=["fog", "alert", "evaluation"],
    ))
    specs.append(builder.register(
        name="fog-alert-history",
        handler=_alert_history,
        version="1.0.0",
        description="Query recent alert fire history with optional severity filter",
        inputs=[],
        outputs=["ok", "history"],
        tags=["fog", "alert", "history"],
    ))
    return specs


# ─── Notification Pack ──────────────────────────────────────────────────

# In-memory notification state
_notification_channels: dict[str, dict[str, Any]] = {}
_notification_subs: dict[str, dict[str, Any]] = {}  # sub_id → subscription
_notification_queue: list[dict[str, Any]] = []
_notification_templates: dict[str, str] = {}
_notification_rate_limits: dict[str, dict[str, Any]] = {}  # channel_id → {tokens, max, refill_rate, last_refill}
_NOTIFICATION_QUEUE_MAX = 500


async def _notif_channel_register(payload: dict[str, Any]) -> dict[str, Any]:
    """Register a notification channel.

    Payload:
        channel_id: unique id (e.g. 'slack-ops', 'email-admin')
        type:       webhook | email | in_app | telegram
        config:     type-specific config (url, email, chat_id, etc.)
        enabled:    default True
    """
    import time as _time
    channel_id = payload.get("channel_id", "")
    if not channel_id:
        return {"error": "channel_id is required", "ok": False}
    if channel_id in _notification_channels:
        return {"error": f"Channel '{channel_id}' already exists", "ok": False}
    valid_types = {"webhook", "email", "in_app", "telegram"}
    ch_type = payload.get("type", "")
    if ch_type not in valid_types:
        return {"error": f"Invalid type '{ch_type}'. Use: {', '.join(sorted(valid_types))}", "ok": False}
    channel: dict[str, Any] = {
        "channel_id": channel_id,
        "type": ch_type,
        "config": payload.get("config", {}),
        "enabled": payload.get("enabled", True),
        "created_at": _time.time(),
        "sent_count": 0,
    }
    _notification_channels[channel_id] = channel
    return {"ok": True, "channel": channel}


async def _notif_channel_list(payload: dict[str, Any]) -> dict[str, Any]:
    """List all registered notification channels."""
    channels = list(_notification_channels.values())
    return {"ok": True, "channels": channels, "total": len(channels)}


async def _notif_channel_remove(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove a notification channel."""
    channel_id = payload.get("channel_id", "")
    if channel_id not in _notification_channels:
        return {"error": f"Channel '{channel_id}' not found", "ok": False}
    del _notification_channels[channel_id]
    # Remove subs targeting this channel
    to_remove = [sid for sid, s in _notification_subs.items() if s["channel_id"] == channel_id]
    for sid in to_remove:
        del _notification_subs[sid]
    return {"ok": True, "removed": channel_id, "subs_removed": len(to_remove)}


async def _notif_subscribe(payload: dict[str, Any]) -> dict[str, Any]:
    """Subscribe a channel to a topic/pattern.

    Payload:
        channel_id:  target channel
        topic:       topic or '*' for all
        min_severity: info | warning | critical (default: info)
        sub_id:      optional custom id (auto-generated if omitted)
    """
    import uuid as _uuid
    channel_id = payload.get("channel_id", "")
    if channel_id not in _notification_channels:
        return {"error": f"Channel '{channel_id}' not found", "ok": False}
    topic = payload.get("topic", "*")
    min_severity = payload.get("min_severity", "info")
    sub_id = payload.get("sub_id") or f"sub-{_uuid.uuid4().hex[:8]}"
    if sub_id in _notification_subs:
        return {"error": f"Subscription '{sub_id}' already exists", "ok": False}
    sub: dict[str, Any] = {
        "sub_id": sub_id,
        "channel_id": channel_id,
        "topic": topic,
        "min_severity": min_severity,
        "created_at": __import__('time').time(),
    }
    _notification_subs[sub_id] = sub
    return {"ok": True, "subscription": sub}


async def _notif_unsubscribe(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove a subscription."""
    sub_id = payload.get("sub_id", "")
    if sub_id not in _notification_subs:
        return {"error": f"Subscription '{sub_id}' not found", "ok": False}
    del _notification_subs[sub_id]
    return {"ok": True, "removed": sub_id}


async def _notif_send(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a notification to matching subscribers.

    Payload:
        topic:     notification topic
        severity:  info | warning | critical
        title:     notification title
        body:      notification body (or template_vars for template expansion)
        template:  optional template name to use
        metadata:  optional extra dict
    """
    import time as _time
    topic = payload.get("topic", "")
    severity = payload.get("severity", "info")
    severity_order = {"info": 0, "warning": 1, "critical": 2}
    sev_level = severity_order.get(severity, 0)

    # Resolve body via template
    body = payload.get("body", "")
    template_name = payload.get("template")
    if template_name and template_name in _notification_templates:
        tmpl = _notification_templates[template_name]
        tvars = payload.get("template_vars", {})
        try:
            body = tmpl.format(**tvars)
        except (KeyError, IndexError):
            body = tmpl  # fallback

    title = payload.get("title", "")

    # Find matching subscriptions
    matched_channels: list[str] = []
    for sub in _notification_subs.values():
        if sub["topic"] != "*" and sub["topic"] != topic:
            continue
        sub_sev = severity_order.get(sub["min_severity"], 0)
        if sev_level < sub_sev:
            continue
        matched_channels.append(sub["channel_id"])

    # Dedupe
    matched_channels = list(dict.fromkeys(matched_channels))

    # Rate limit check per channel
    now = _time.time()
    delivered: list[dict[str, Any]] = []
    for ch_id in matched_channels:
        ch = _notification_channels.get(ch_id)
        if not ch or not ch["enabled"]:
            continue

        # Token bucket rate limit: 60 per minute per channel
        rl = _notification_rate_limits.setdefault(ch_id, {"tokens": 60, "max": 60, "refill_rate": 1.0, "last_refill": now})
        elapsed = now - rl["last_refill"]
        rl["tokens"] = min(rl["max"], rl["tokens"] + elapsed * rl["refill_rate"])
        rl["last_refill"] = now
        if rl["tokens"] < 1:
            delivered.append({"channel_id": ch_id, "status": "rate_limited"})
            continue
        rl["tokens"] -= 1

        notification: dict[str, Any] = {
            "id": f"notif-{__import__('uuid').uuid4().hex[:8]}",
            "channel_id": ch_id,
            "channel_type": ch["type"],
            "topic": topic,
            "severity": severity,
            "title": title,
            "body": body,
            "metadata": payload.get("metadata", {}),
            "sent_at": now,
        }
        _notification_queue.append(notification)
        if len(_notification_queue) > _NOTIFICATION_QUEUE_MAX:
            _notification_queue.pop(0)
        ch["sent_count"] += 1
        delivered.append({"channel_id": ch_id, "status": "sent", "notification_id": notification["id"]})

    return {
        "ok": True,
        "delivered": delivered,
        "total_channels": len(matched_channels),
        "topic": topic,
        "severity": severity,
    }


async def _notif_history(payload: dict[str, Any]) -> dict[str, Any]:
    """Query notification history.

    Payload:
        channel_id: optional filter
        topic:      optional filter
        severity:   optional filter
        limit:      max entries (default 50)
    """
    limit = min(int(payload.get("limit", 50)), 200)
    entries = _notification_queue
    channel_id = payload.get("channel_id")
    if channel_id:
        entries = [e for e in entries if e["channel_id"] == channel_id]
    topic = payload.get("topic")
    if topic:
        entries = [e for e in entries if e["topic"] == topic]
    severity = payload.get("severity")
    if severity:
        entries = [e for e in entries if e["severity"] == severity]
    return {"ok": True, "notifications": entries[-limit:], "total": len(entries)}


async def _notif_template_set(payload: dict[str, Any]) -> dict[str, Any]:
    """Register or update a notification template (Python str.format style).

    Payload:
        name:     template name
        template: template string with {var} placeholders
    """
    name = payload.get("name", "")
    template = payload.get("template", "")
    if not name or not template:
        return {"error": "name and template are required", "ok": False}
    _notification_templates[name] = template
    return {"ok": True, "name": name, "template": template}


async def _notif_template_list(payload: dict[str, Any]) -> dict[str, Any]:
    """List all registered templates."""
    return {"ok": True, "templates": dict(_notification_templates), "total": len(_notification_templates)}


def load_notification_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load multi-channel notification capabilities.

    Capabilities:
    - notif-channel-register: Register a notification channel (webhook/email/in_app/telegram)
    - notif-channel-list:     List all channels
    - notif-channel-remove:  Remove a channel
    - notif-subscribe:       Subscribe a channel to a topic with min severity
    - notif-unsubscribe:     Remove a subscription
    - notif-send:            Send a notification to matching subscribers (rate-limited)
    - notif-history:         Query notification history with filters
    - notif-template-set:    Register a notification template
    - notif-template-list:   List all templates
    """
    specs: list[CapSpec] = []
    specs.append(builder.register(
        name="notif-channel-register",
        handler=_notif_channel_register,
        version="1.0.0",
        description="Register a notification channel (webhook/email/in_app/telegram)",
        inputs=["channel_id", "type", "config"],
        outputs=["ok", "channel"],
        tags=["notification", "channel", "setup"],
    ))
    specs.append(builder.register(
        name="notif-channel-list",
        handler=_notif_channel_list,
        version="1.0.0",
        description="List all registered notification channels",
        inputs=[],
        outputs=["ok", "channels"],
        tags=["notification", "channel"],
    ))
    specs.append(builder.register(
        name="notif-channel-remove",
        handler=_notif_channel_remove,
        version="1.0.0",
        description="Remove a notification channel and its subscriptions",
        inputs=["channel_id"],
        outputs=["ok", "removed"],
        tags=["notification", "channel"],
    ))
    specs.append(builder.register(
        name="notif-subscribe",
        handler=_notif_subscribe,
        version="1.0.0",
        description="Subscribe a channel to a topic with minimum severity filter",
        inputs=["channel_id", "topic"],
        outputs=["ok", "subscription"],
        tags=["notification", "subscription"],
    ))
    specs.append(builder.register(
        name="notif-unsubscribe",
        handler=_notif_unsubscribe,
        version="1.0.0",
        description="Remove a notification subscription",
        inputs=["sub_id"],
        outputs=["ok", "removed"],
        tags=["notification", "subscription"],
    ))
    specs.append(builder.register(
        name="notif-send",
        handler=_notif_send,
        version="1.0.0",
        description="Send a notification to matching subscribers (rate-limited, template-aware)",
        inputs=["topic", "severity", "title", "body"],
        outputs=["ok", "delivered"],
        tags=["notification", "send"],
    ))
    specs.append(builder.register(
        name="notif-history",
        handler=_notif_history,
        version="1.0.0",
        description="Query notification history with optional channel/topic/severity filters",
        inputs=[],
        outputs=["ok", "notifications"],
        tags=["notification", "history"],
    ))
    specs.append(builder.register(
        name="notif-template-set",
        handler=_notif_template_set,
        version="1.0.0",
        description="Register or update a notification template with {var} placeholders",
        inputs=["name", "template"],
        outputs=["ok", "name"],
        tags=["notification", "template"],
    ))
    specs.append(builder.register(
        name="notif-template-list",
        handler=_notif_template_list,
        version="1.0.0",
        description="List all registered notification templates",
        inputs=[],
        outputs=["ok", "templates"],
        tags=["notification", "template"],
    ))
    return specs


# ─── Delegation Pack ─────────────────────────────────────────────────────

# In-memory delegation tracking
_delegation_store: dict[str, dict[str, Any]] = {}
_delegation_counter: int = 0


def _new_delegation_id() -> str:
    global _delegation_counter
    _delegation_counter += 1
    return f"deleg-{_delegation_counter:04d}"


async def _delegation_create(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a delegation: assign a task to a target agent with optional deadline."""
    task = payload.get("task", "").strip()
    target = payload.get("target_agent", "").strip()
    if not task or not target:
        return {"ok": False, "error": "task and target_agent are required"}

    global _delegation_store
    deadline = payload.get("deadline")  # optional epoch seconds
    parent_id = payload.get("parent_delegation_id")
    priority = payload.get("priority", "normal")
    metadata = payload.get("metadata", {})

    did = _new_delegation_id()
    record = {
        "id": did,
        "task": task,
        "target_agent": target,
        "status": "pending",  # pending → accepted → in_progress → done | failed | timed_out | rejected
        "priority": priority,
        "deadline": deadline,
        "parent_delegation_id": parent_id,
        "result": None,
        "created_at": time.time(),
        "updated_at": time.time(),
        "metadata": metadata,
        "chain_depth": 0,
    }

    # Track chain depth
    if parent_id and parent_id in _delegation_store:
        record["chain_depth"] = _delegation_store[parent_id]["chain_depth"] + 1

    _delegation_store[did] = record
    return {
        "ok": True,
        "delegation_id": did,
        "target_agent": target,
        "status": "pending",
        "chain_depth": record["chain_depth"],
    }


async def _delegation_accept(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept a pending delegation."""
    did = payload.get("delegation_id", "")
    record = _delegation_store.get(did)
    if not record:
        return {"ok": False, "error": f"delegation {did} not found"}
    if record["status"] != "pending":
        return {"ok": False, "error": f"delegation is {record['status']}, not pending"}
    record["status"] = "accepted"
    record["updated_at"] = time.time()
    return {"ok": True, "delegation_id": did, "status": "accepted"}


async def _delegation_reject(payload: dict[str, Any]) -> dict[str, Any]:
    """Reject a pending delegation with an optional reason."""
    did = payload.get("delegation_id", "")
    reason = payload.get("reason", "")
    record = _delegation_store.get(did)
    if not record:
        return {"ok": False, "error": f"delegation {did} not found"}
    if record["status"] != "pending":
        return {"ok": False, "error": f"delegation is {record['status']}, not pending"}
    record["status"] = "rejected"
    record["result"] = {"reason": reason}
    record["updated_at"] = time.time()
    return {"ok": True, "delegation_id": did, "status": "rejected"}


async def _delegation_complete(payload: dict[str, Any]) -> dict[str, Any]:
    """Mark a delegation as done with a result."""
    did = payload.get("delegation_id", "")
    result = payload.get("result", {})
    record = _delegation_store.get(did)
    if not record:
        return {"ok": False, "error": f"delegation {did} not found"}
    if record["status"] not in ("accepted", "in_progress"):
        return {"ok": False, "error": f"delegation is {record['status']}, cannot complete"}
    record["status"] = "done"
    record["result"] = result
    record["updated_at"] = time.time()
    return {"ok": True, "delegation_id": did, "status": "done"}


async def _delegation_fail(payload: dict[str, Any]) -> dict[str, Any]:
    """Mark a delegation as failed with error details."""
    did = payload.get("delegation_id", "")
    error = payload.get("error", "unknown error")
    record = _delegation_store.get(did)
    if not record:
        return {"ok": False, "error": f"delegation {did} not found"}
    if record["status"] in ("done", "rejected", "timed_out"):
        return {"ok": False, "error": f"delegation is already {record['status']}"}
    record["status"] = "failed"
    record["result"] = {"error": error}
    record["updated_at"] = time.time()
    return {"ok": True, "delegation_id": did, "status": "failed"}


async def _delegation_timeout_check(payload: dict[str, Any]) -> dict[str, Any]:
    """Check all delegations for timeouts, mark expired ones."""
    global _delegation_store
    now = time.time()
    timed_out = []
    for did, rec in _delegation_store.items():
        if rec["status"] in ("pending", "accepted", "in_progress") and rec.get("deadline"):
            if now > rec["deadline"]:
                rec["status"] = "timed_out"
                rec["result"] = {"error": "deadline exceeded"}
                rec["updated_at"] = now
                timed_out.append(did)
    return {"ok": True, "timed_out": timed_out, "count": len(timed_out)}


async def _delegation_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Get the full status of a delegation, including its chain."""
    did = payload.get("delegation_id", "")
    record = _delegation_store.get(did)
    if not record:
        return {"ok": False, "error": f"delegation {did} not found"}
    # Build chain
    chain = []
    parent = record.get("parent_delegation_id")
    while parent and parent in _delegation_store:
        pr = _delegation_store[parent]
        chain.append({"id": pr["id"], "task": pr["task"][:60], "target": pr["target_agent"], "status": pr["status"]})
        parent = pr.get("parent_delegation_id")
    # Find children
    children = [
        {"id": r["id"], "task": r["task"][:60], "target": r["target_agent"], "status": r["status"]}
        for r in _delegation_store.values()
        if r.get("parent_delegation_id") == did
    ]
    return {
        "ok": True,
        "delegation_id": did,
        "status": record["status"],
        "target_agent": record["target_agent"],
        "task": record["task"],
        "result": record["result"],
        "chain_depth": record["chain_depth"],
        "parent_chain": chain,
        "children": children,
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


async def _delegation_list(payload: dict[str, Any]) -> dict[str, Any]:
    """List delegations with optional filters."""
    status_filter = payload.get("status")
    target_filter = payload.get("target_agent")
    results = []
    for did, rec in _delegation_store.items():
        if status_filter and rec["status"] != status_filter:
            continue
        if target_filter and rec["target_agent"] != target_filter:
            continue
        results.append({
            "id": did,
            "task": rec["task"][:80],
            "target_agent": rec["target_agent"],
            "status": rec["status"],
            "priority": rec["priority"],
            "chain_depth": rec["chain_depth"],
        })
    return {"ok": True, "delegations": results, "total": len(results)}


async def _delegation_stats(payload: dict[str, Any]) -> dict[str, Any]:
    """Aggregate statistics across all delegations."""
    global _delegation_store
    counts: dict[str, int] = {}
    by_target: dict[str, int] = {}
    total_depth = 0
    for rec in _delegation_store.values():
        s = rec["status"]
        counts[s] = counts.get(s, 0) + 1
        t = rec["target_agent"]
        by_target[t] = by_target.get(t, 0) + 1
        total_depth += rec["chain_depth"]
    total = len(_delegation_store)
    avg_depth = total_depth / total if total else 0.0
    success_rate = counts.get("done", 0) / total if total else 0.0
    return {
        "ok": True,
        "total": total,
        "by_status": counts,
        "by_target": by_target,
        "success_rate": round(success_rate, 3),
        "avg_chain_depth": round(avg_depth, 2),
    }


def load_delegation_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load delegation capabilities — assign tasks to agents, track chains, collect results."""
    specs = []
    specs.append(builder.register(
        name="delegation-create",
        handler=_delegation_create,
        version="1.0.0",
        description="Create a task delegation to a target agent with optional deadline",
        inputs=["task", "target_agent"],
        outputs=["ok", "delegation_id", "status"],
        tags=["delegation", "task", "routing"],
    ))
    specs.append(builder.register(
        name="delegation-accept",
        handler=_delegation_accept,
        version="1.0.0",
        description="Accept a pending delegation",
        inputs=["delegation_id"],
        outputs=["ok", "delegation_id", "status"],
        tags=["delegation", "accept"],
    ))
    specs.append(builder.register(
        name="delegation-reject",
        handler=_delegation_reject,
        version="1.0.0",
        description="Reject a pending delegation with optional reason",
        inputs=["delegation_id"],
        outputs=["ok", "delegation_id", "status"],
        tags=["delegation", "reject"],
    ))
    specs.append(builder.register(
        name="delegation-complete",
        handler=_delegation_complete,
        version="1.0.0",
        description="Mark a delegation as done with a result payload",
        inputs=["delegation_id", "result"],
        outputs=["ok", "delegation_id", "status"],
        tags=["delegation", "complete"],
    ))
    specs.append(builder.register(
        name="delegation-fail",
        handler=_delegation_fail,
        version="1.0.0",
        description="Mark a delegation as failed with error details",
        inputs=["delegation_id", "error"],
        outputs=["ok", "delegation_id", "status"],
        tags=["delegation", "fail"],
    ))
    specs.append(builder.register(
        name="delegation-timeout-check",
        handler=_delegation_timeout_check,
        version="1.0.0",
        description="Check all active delegations for deadline expiry",
        inputs=[],
        outputs=["ok", "timed_out", "count"],
        tags=["delegation", "timeout"],
    ))
    specs.append(builder.register(
        name="delegation-status",
        handler=_delegation_status,
        version="1.0.0",
        description="Get delegation status including parent chain and child delegations",
        inputs=["delegation_id"],
        outputs=["ok", "status", "parent_chain", "children"],
        tags=["delegation", "status"],
    ))
    specs.append(builder.register(
        name="delegation-list",
        handler=_delegation_list,
        version="1.0.0",
        description="List delegations with optional status/target filters",
        inputs=[],
        outputs=["ok", "delegations", "total"],
        tags=["delegation", "list"],
    ))
    specs.append(builder.register(
        name="delegation-stats",
        handler=_delegation_stats,
        version="1.0.0",
        description="Aggregate statistics: success rate, chain depth, distribution by target",
        inputs=[],
        outputs=["ok", "total", "by_status", "success_rate"],
        tags=["delegation", "stats", "analytics"],
    ))
    return specs


def load_all_packs(builder: CapabilityBuilder, agent: Any | None = None) -> list[CapSpec]:
    """Load all available capability packs."""
    specs = []
    specs.extend(load_text_pack(builder))
    specs.extend(load_math_pack(builder))
    specs.extend(load_meta_pack(builder))
    specs.extend(load_data_pack(builder))
    specs.extend(load_monitor_pack(builder))
    specs.extend(load_encoding_pack(builder))
    specs.extend(load_planning_pack(builder))
    specs.extend(load_reasoning_pack(builder))
    specs.extend(load_memory_pack(builder))
    specs.extend(load_network_pack(builder, agent))
    specs.extend(load_tool_use_pack(builder))
    specs.extend(load_collaboration_pack(builder, agent))
    specs.extend(load_subscription_pack(builder))
    specs.extend(load_trust_pack(builder))
    specs.extend(load_research_pack(builder))
    specs.extend(load_audit_pack(builder))
    specs.extend(load_deliberation_pack(builder))
    specs.extend(load_orchestration_pack(builder))
    specs.extend(load_evaluation_pack(builder))
    specs.extend(load_learning_pack(builder))
    specs.extend(load_adapter_pack(builder))
    specs.extend(load_security_pack(builder))
    specs.extend(load_audience_analytics_pack(builder))
    specs.extend(load_resilience_pack(builder))
    specs.extend(load_fog_alert_pack(builder))
    specs.extend(load_notification_pack(builder))
    specs.extend(load_goal_decomposition_pack(builder))
    specs.extend(load_delegation_pack(builder))
    specs.extend(load_strategy_pack(builder))
    if agent is not None:
        specs.extend(load_routing_pack(builder, agent))
        specs.extend(load_fog_pack(builder, agent))
        specs.extend(load_localization_pack(builder, agent))
    return specs


# ─── Goal Decomposition Pack ────────────────────────────────────────────

# In-memory goal store for the pack
_goal_store: dict[str, dict[str, Any]] = {}
_goal_counter: int = 0


def _new_goal_id() -> str:
    global _goal_counter
    _goal_counter += 1
    return f"goal-{_goal_counter:04d}"


async def _goal_decompose(payload: dict[str, Any]) -> dict[str, Any]:
    """Decompose a goal into subtasks with optional dependency chains.

    Uses simple heuristic decomposition: splits on sentence boundaries,
    assigns sequential dependencies, estimates priority from keywords.
    """
    global _goal_store
    goal_text = payload.get("goal", "").strip()
    max_subtasks = payload.get("max_subtasks", 8)
    parent_id = payload.get("parent_id")

    if not goal_text:
        return {"ok": False, "error": "goal is required"}

    # Split into subtask-like chunks: by numbered items, then sentences
    import re as _re
    # Check for numbered/bulleted list
    items = _re.split(r'\n\s*(?:\d+[.)]\s*|[-*]\s*)', goal_text)
    items = [i.strip() for i in items if i.strip()]

    if len(items) <= 1:
        # Fall back to sentence splitting
        items = _re.split(r'[.!?]+\s+', goal_text)
        items = [i.strip() for i in items if i.strip()]

    if len(items) > max_subtasks:
        items = items[:max_subtasks]

    if not items:
        items = [goal_text]

    gid = _new_goal_id()
    # Priority heuristics
    priority_keywords = {"critical", "urgent", "important", "first", "asap", "must", "key", "essential"}
    subtasks = []
    for idx, item in enumerate(items):
        prio = "normal"
        low = item.lower()
        if any(kw in low for kw in priority_keywords):
            prio = "high"
        deps = [f"sub-{gid}-{idx - 1}"] if idx > 0 else []
        sub_id = f"sub-{gid}-{idx}"
        subtasks.append({
            "id": sub_id,
            "description": item,
            "status": "pending",
            "priority": prio,
            "depends_on": deps,
        })

    goal_record = {
        "id": gid,
        "goal": goal_text,
        "parent_id": parent_id,
        "subtasks": subtasks,
        "status": "planned",
        "created_at": time.time(),
    }
    _goal_store[gid] = goal_record
    return {"ok": True, "goal_id": gid, "subtasks": subtasks, "total": len(subtasks)}


async def _goal_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Get the status of a goal and its subtasks."""
    gid = payload.get("goal_id", "")
    goal = _goal_store.get(gid)
    if not goal:
        return {"ok": False, "error": f"goal {gid} not found"}
    done = sum(1 for s in goal["subtasks"] if s["status"] == "done")
    total = len(goal["subtasks"])
    goal["status"] = "done" if done == total else ("in_progress" if done > 0 else "planned")
    return {
        "ok": True,
        "goal_id": gid,
        "goal": goal["goal"],
        "status": goal["status"],
        "progress": f"{done}/{total}",
        "subtasks": goal["subtasks"],
    }


async def _goal_update_subtask(payload: dict[str, Any]) -> dict[str, Any]:
    """Update a subtask's status. Checks dependency ordering."""
    sub_id = payload.get("subtask_id", "")
    new_status = payload.get("status", "done")
    goal_id = payload.get("goal_id", "")

    goal = _goal_store.get(goal_id)
    if not goal:
        return {"ok": False, "error": f"goal {goal_id} not found"}

    target = None
    for s in goal["subtasks"]:
        if s["id"] == sub_id:
            target = s
            break
    if not target:
        return {"ok": False, "error": f"subtask {sub_id} not found in goal {goal_id}"}

    # Check dependencies are done
    if new_status == "done" and target["depends_on"]:
        for dep_id in target["depends_on"]:
            dep = next((s for s in goal["subtasks"] if s["id"] == dep_id), None)
            if dep and dep["status"] != "done":
                return {"ok": False, "error": f"dependency {dep_id} not done", "blocked_by": dep_id}

    target["status"] = new_status
    return {"ok": True, "subtask_id": sub_id, "status": new_status}


async def _goal_next(payload: dict[str, Any]) -> dict[str, Any]:
    """Get the next actionable subtask (dependencies met, not started)."""
    goal_id = payload.get("goal_id", "")
    goal = _goal_store.get(goal_id)
    if not goal:
        return {"ok": False, "error": f"goal {goal_id} not found"}

    candidates = []
    for s in goal["subtasks"]:
        if s["status"] != "pending":
            continue
        deps_met = all(
            next((d for d in goal["subtasks"] if d["id"] == dep), {}).get("status") == "done"
            for dep in s["depends_on"]
        )
        if deps_met:
            candidates.append(s)

    if not candidates:
        # Check if all done
        all_done = all(s["status"] == "done" for s in goal["subtasks"])
        if all_done:
            return {"ok": True, "completed": True, "message": "all subtasks done"}
        return {"ok": True, "blocked": True, "message": "no actionable subtasks — blocked"}

    # Prefer high priority
    candidates.sort(key=lambda s: 0 if s["priority"] == "high" else 1)
    return {"ok": True, "subtask": candidates[0]}


async def _goal_list(payload: dict[str, Any]) -> dict[str, Any]:
    """List all goals, optionally filtered by status."""
    status_filter = payload.get("status")
    results = []
    for gid, g in _goal_store.items():
        if status_filter and g["status"] != status_filter:
            continue
        done = sum(1 for s in g["subtasks"] if s["status"] == "done")
        results.append({
            "id": gid,
            "goal": g["goal"][:80],
            "status": g["status"],
            "progress": f"{done}/{len(g['subtasks'])}",
        })
    return {"ok": True, "goals": results, "total": len(results)}


async def _goal_merge(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge two goals, combining their subtasks with cross-dependencies."""
    g1_id = payload.get("goal_id_1", "")
    g2_id = payload.get("goal_id_2", "")
    g1 = _goal_store.get(g1_id)
    g2 = _goal_store.get(g2_id)
    if not g1 or not g2:
        return {"ok": False, "error": "both goal_id_1 and goal_id_2 must exist"}

    merged_id = _new_goal_id()
    merged_subtasks = []
    for s in g1["subtasks"]:
        merged_subtasks.append({**s, "id": f"sub-{merged_id}-{len(merged_subtasks)}", "depends_on": []})
    bridge_idx = len(merged_subtasks)
    for s in g2["subtasks"]:
        # Depend on last subtask of g1 as bridge
        deps = [f"sub-{merged_id}-{bridge_idx - 1}"] if bridge_idx > 0 else []
        merged_subtasks.append({**s, "id": f"sub-{merged_id}-{len(merged_subtasks)}", "depends_on": deps})

    _goal_store[merged_id] = {
        "id": merged_id,
        "goal": f"[merged] {g1['goal'][:40]} + {g2['goal'][:40]}",
        "parent_id": None,
        "subtasks": merged_subtasks,
        "status": "planned",
        "created_at": time.time(),
    }
    return {"ok": True, "merged_goal_id": merged_id, "total_subtasks": len(merged_subtasks)}


def load_goal_decomposition_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load goal decomposition capabilities — break goals into subtasks, track progress, manage dependencies."""
    specs = []
    specs.append(builder.register(
        name="goal-decompose",
        handler=_goal_decompose,
        version="1.0.0",
        description="Decompose a goal into ordered subtasks with dependency tracking",
        inputs=["goal"],
        outputs=["ok", "goal_id", "subtasks", "total"],
        tags=["goal", "decomposition", "planning"],
    ))
    specs.append(builder.register(
        name="goal-status",
        handler=_goal_status,
        version="1.0.0",
        description="Get goal status and subtask progress",
        inputs=["goal_id"],
        outputs=["ok", "goal_id", "status", "progress", "subtasks"],
        tags=["goal", "status"],
    ))
    specs.append(builder.register(
        name="goal-subtask-update",
        handler=_goal_update_subtask,
        version="1.0.0",
        description="Update a subtask status; enforces dependency ordering",
        inputs=["goal_id", "subtask_id", "status"],
        outputs=["ok", "subtask_id", "status"],
        tags=["goal", "subtask", "update"],
    ))
    specs.append(builder.register(
        name="goal-next",
        handler=_goal_next,
        version="1.0.0",
        description="Get the next actionable subtask (dependencies met, highest priority first)",
        inputs=["goal_id"],
        outputs=["ok", "subtask", "completed", "blocked"],
        tags=["goal", "next", "scheduling"],
    ))
    specs.append(builder.register(
        name="goal-list",
        handler=_goal_list,
        version="1.0.0",
        description="List all goals with optional status filter",
        inputs=[],
        outputs=["ok", "goals", "total"],
        tags=["goal", "list"],
    ))
    specs.append(builder.register(
        name="goal-merge",
        handler=_goal_merge,
        version="1.0.0",
        description="Merge two goals, combining subtasks with cross-dependencies",
        inputs=["goal_id_1", "goal_id_2"],
        outputs=["ok", "merged_goal_id", "total_subtasks"],
        tags=["goal", "merge", "composition"],
    ))
    return specs


# ─── Strategy Pack ───────────────────────────────────────────────────────
# Strategic decision-making: cost-benefit analysis, priority scoring,
# resource allocation, conflict resolution, and decision logging.

_strategy_decisions: dict[str, dict[str, Any]] = {}
_strategy_resources: dict[str, dict[str, Any]] = {}


def _new_decision_id() -> str:
    return f"dec-{uuid.uuid4().hex[:8]}"


async def _cost_benefit(payload: dict[str, Any]) -> dict[str, Any]:
    """Run a cost-benefit analysis on options.

    Each option should have 'costs' (list of {name, value}) and
    'benefits' (list of {name, value}). Returns net score and ranking.
    """
    options = payload.get("options", [])
    if not options:
        return {"ok": False, "error": "no options provided"}

    results = []
    for opt in options:
        name = opt.get("name", "unnamed")
        costs = opt.get("costs", [])
        benefits = opt.get("benefits", [])
        total_cost = sum(c.get("value", 0) for c in costs)
        total_benefit = sum(b.get("value", 0) for b in benefits)
        net = total_benefit - total_cost
        roi = (total_benefit / total_cost - 1.0) if total_cost > 0 else float("inf") if total_benefit > 0 else 0.0
        results.append({
            "name": name,
            "total_cost": total_cost,
            "total_benefit": total_benefit,
            "net_value": net,
            "roi": round(roi, 4),
            "costs": costs,
            "benefits": benefits,
        })

    results.sort(key=lambda r: r["net_value"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    recommendation = results[0]["name"] if results else None
    dec_id = _new_decision_id()
    _strategy_decisions[dec_id] = {
        "id": dec_id,
        "type": "cost_benefit",
        "options": results,
        "recommendation": recommendation,
        "created_at": time.time(),
    }

    return {
        "ok": True,
        "decision_id": dec_id,
        "analysis": results,
        "recommendation": recommendation,
        "total_options": len(results),
    }


async def _priority_score(payload: dict[str, Any]) -> dict[str, Any]:
    """Score and rank items by weighted criteria.

    Each item has 'name' and numeric properties. 'criteria' maps
    property names to weights. Returns weighted scores and ranking.
    """
    items = payload.get("items", [])
    criteria = payload.get("criteria", {})
    if not items or not criteria:
        return {"ok": False, "error": "items and criteria required"}

    total_weight = sum(criteria.values())
    if total_weight == 0:
        return {"ok": False, "error": "weights must sum to > 0"}

    results = []
    for item in items:
        name = item.get("name", "unnamed")
        score = 0.0
        breakdown = {}
        for prop, weight in criteria.items():
            val = item.get(prop, 0)
            if isinstance(val, (int, float)):
                normalized_weight = weight / total_weight
                contrib = val * normalized_weight
                score += contrib
                breakdown[prop] = {"value": val, "weight": weight, "contribution": round(contrib, 4)}

        results.append({"name": name, "score": round(score, 4), "breakdown": breakdown})

    results.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return {"ok": True, "rankings": results, "criteria": criteria, "total_items": len(results)}


async def _resource_allocate(payload: dict[str, Any]) -> dict[str, Any]:
    """Allocate a finite resource budget across competing demands.

    Uses proportional allocation based on priority scores. Supports
    minimum guarantees and caps per recipient.
    """
    budget = payload.get("budget", 0)
    demands = payload.get("demands", [])
    if budget <= 0 or not demands:
        return {"ok": False, "error": "budget > 0 and non-empty demands required"}

    # Validate and normalize priorities
    total_priority = 0.0
    valid_demands = []
    for d in demands:
        name = d.get("name", "unnamed")
        priority = max(d.get("priority", 1.0), 0.01)
        minimum = d.get("minimum", 0.0)
        cap = d.get("cap", budget)
        valid_demands.append({"name": name, "priority": priority, "minimum": minimum, "cap": cap})
        total_priority += priority

    # Phase 1: guarantee minimums
    remaining = budget
    allocations: list[dict[str, Any]] = []
    guaranteed = {}

    for d in valid_demands:
        guarantee = min(d["minimum"], remaining)
        guaranteed[d["name"]] = guarantee
        remaining -= guarantee

    # Phase 2: distribute remainder proportionally
    for d in valid_demands:
        proportional = (d["priority"] / total_priority) * remaining if total_priority > 0 else 0
        total_alloc = guaranteed[d["name"]] + proportional
        # Respect cap
        total_alloc = min(total_alloc, d["cap"])
        allocations.append({
            "name": d["name"],
            "allocation": round(total_alloc, 4),
            "priority": d["priority"],
            "share_pct": round(total_alloc / budget * 100, 2) if budget > 0 else 0,
        })

    total_allocated = sum(a["allocation"] for a in allocations)

    return {
        "ok": True,
        "budget": budget,
        "allocated": round(total_allocated, 4),
        "surplus": round(budget - total_allocated, 4),
        "allocations": allocations,
        "total_demands": len(allocations),
    }


async def _conflict_resolve(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve a conflict between competing proposals.

    Supports strategies: 'score' (highest score wins), 'consensus'
    (merge compatible parts), 'priority' (highest priority agent wins).
    """
    proposals = payload.get("proposals", [])
    strategy = payload.get("strategy", "score")
    context = payload.get("context", "")

    if len(proposals) < 2:
        return {"ok": False, "error": "need at least 2 proposals"}

    if strategy == "score":
        proposals.sort(key=lambda p: p.get("score", 0), reverse=True)
        winner = proposals[0]
        dec_id = _new_decision_id()
        _strategy_decisions[dec_id] = {
            "id": dec_id,
            "type": "conflict_resolution",
            "strategy": strategy,
            "winner": winner.get("name", "unnamed"),
            "proposals": proposals,
            "context": context,
            "created_at": time.time(),
        }
        return {
            "ok": True,
            "decision_id": dec_id,
            "strategy": strategy,
            "winner": winner.get("name", "unnamed"),
            "score": winner.get("score", 0),
            "rationale": f"Highest score ({winner.get('score', 0)}) among {len(proposals)} proposals",
        }

    elif strategy == "consensus":
        # Merge: collect all unique key-value pairs from proposals
        merged: dict[str, Any] = {}
        conflicts_list: list[str] = []
        for p in proposals:
            for k, v in p.items():
                if k in ("name", "score"):
                    continue
                if k in merged and merged[k] != v:
                    conflicts_list.append(f"{k}: {merged[k]} vs {v}")
                merged[k] = v

        dec_id = _new_decision_id()
        _strategy_decisions[dec_id] = {
            "id": dec_id,
            "type": "conflict_resolution",
            "strategy": strategy,
            "merged": merged,
            "conflicts": conflicts_list,
            "context": context,
            "created_at": time.time(),
        }
        return {
            "ok": True,
            "decision_id": dec_id,
            "strategy": strategy,
            "merged": merged,
            "conflicts": conflicts_list,
            "total_proposals": len(proposals),
        }

    elif strategy == "priority":
        proposals.sort(key=lambda p: p.get("priority", 0), reverse=True)
        winner = proposals[0]
        dec_id = _new_decision_id()
        return {
            "ok": True,
            "decision_id": dec_id,
            "strategy": strategy,
            "winner": winner.get("name", "unnamed"),
            "priority": winner.get("priority", 0),
            "rationale": f"Highest priority agent ({winner.get('priority', 0)})",
        }

    return {"ok": False, "error": f"unknown strategy: {strategy}"}


async def _decision_log(payload: dict[str, Any]) -> dict[str, Any]:
    """Query the decision history log."""
    decision_type = payload.get("type")
    limit = min(payload.get("limit", 20), 100)

    decisions = list(_strategy_decisions.values())
    if decision_type:
        decisions = [d for d in decisions if d.get("type") == decision_type]

    decisions.sort(key=lambda d: d.get("created_at", 0), reverse=True)
    decisions = decisions[:limit]

    return {
        "ok": True,
        "decisions": decisions,
        "total": len(decisions),
    }


async def _tradeoff_matrix(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a tradeoff matrix comparing options across dimensions.

    Returns a matrix showing how each option scores on each dimension,
    with dominance analysis (Pareto front).
    """
    options = payload.get("options", [])
    dimensions = payload.get("dimensions", [])  # list of dimension names

    if len(options) < 2 or not dimensions:
        return {"ok": False, "error": "need >= 2 options and dimensions"}

    matrix: list[dict[str, Any]] = []
    for opt in options:
        name = opt.get("name", "unnamed")
        scores = {}
        for dim in dimensions:
            scores[dim] = opt.get(dim, 0)
        matrix.append({"name": name, "scores": scores})

    # Pareto front: option A dominates B if >= on all dims and > on at least one
    dominated: set[str] = set()
    for i, a in enumerate(matrix):
        for j, b in enumerate(matrix):
            if i == j:
                continue
            a_scores = a["scores"]
            b_scores = b["scores"]
            all_ge = all(a_scores.get(d, 0) >= b_scores.get(d, 0) for d in dimensions)
            any_gt = any(a_scores.get(d, 0) > b_scores.get(d, 0) for d in dimensions)
            if all_ge and any_gt:
                dominated.add(b["name"])

    pareto_front = [m["name"] for m in matrix if m["name"] not in dominated]
    dominated_names = list(dominated)

    return {
        "ok": True,
        "matrix": matrix,
        "pareto_front": pareto_front,
        "dominated": dominated_names,
        "dimensions": dimensions,
    }


def load_strategy_pack(builder: CapabilityBuilder) -> list[CapSpec]:
    """Load strategy capabilities — cost-benefit analysis, priority scoring, resource allocation, conflict resolution."""
    specs = []
    specs.append(builder.register(
        name="cost-benefit",
        handler=_cost_benefit,
        version="1.0.0",
        description="Run cost-benefit analysis across options with ROI calculation",
        inputs=["options"],
        outputs=["ok", "decision_id", "analysis", "recommendation"],
        tags=["strategy", "decision", "analysis"],
    ))
    specs.append(builder.register(
        name="priority-score",
        handler=_priority_score,
        version="1.0.0",
        description="Score and rank items by weighted criteria",
        inputs=["items", "criteria"],
        outputs=["ok", "rankings", "criteria"],
        tags=["strategy", "priority", "ranking"],
    ))
    specs.append(builder.register(
        name="resource-allocate",
        handler=_resource_allocate,
        version="1.0.0",
        description="Allocate finite resource budget across competing demands with guarantees and caps",
        inputs=["budget", "demands"],
        outputs=["ok", "allocations", "budget", "surplus"],
        tags=["strategy", "resource", "allocation"],
    ))
    specs.append(builder.register(
        name="conflict-resolve",
        handler=_conflict_resolve,
        version="1.0.0",
        description="Resolve conflicts between proposals using score, consensus, or priority strategy",
        inputs=["proposals", "strategy"],
        outputs=["ok", "decision_id", "winner", "strategy"],
        tags=["strategy", "conflict", "resolution"],
    ))
    specs.append(builder.register(
        name="decision-log",
        handler=_decision_log,
        version="1.0.0",
        description="Query the decision history log with optional type filter",
        inputs=["type", "limit"],
        outputs=["ok", "decisions", "total"],
        tags=["strategy", "decision", "history"],
    ))
    specs.append(builder.register(
        name="tradeoff-matrix",
        handler=_tradeoff_matrix,
        version="1.0.0",
        description="Build a tradeoff matrix with Pareto front analysis across options",
        inputs=["options", "dimensions"],
        outputs=["ok", "matrix", "pareto_front", "dominated"],
        tags=["strategy", "tradeoff", "pareto"],
    ))
    return specs
