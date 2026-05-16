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
"""

from __future__ import annotations

import math
import re
import statistics
import time
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
    if agent is not None:
        specs.extend(load_routing_pack(builder, agent))
        specs.extend(load_fog_pack(builder, agent))
    return specs
