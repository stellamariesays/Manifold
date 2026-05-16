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


# ─── Convenience ────────────────────────────────────────────────────────

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
    if agent is not None:
        specs.extend(load_routing_pack(builder, agent))
        specs.extend(load_fog_pack(builder, agent))
    return specs
