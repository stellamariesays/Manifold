"""Tests for the monitoring and encoding capability packs."""

import asyncio
import math
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_monitor_pack, load_encoding_pack


@pytest.fixture
def builder():
    a = Agent("test-monitor")
    return CapabilityBuilder(a)


# ─── Monitor Pack ───────────────────────────────────────────────────────


class TestThresholdAlert:
    def test_all_within_bounds(self, builder):
        load_monitor_pack(builder)
        result = asyncio.run(builder.invoke("monitor-threshold", {
                "metrics": {"cpu": 45, "mem": 60},
                "rules": {"cpu": {"min": 0, "max": 100}, "mem": {"min": 0, "max": 100}},
            })
        )
        assert result.ok is True
        assert result.output["ok"] is True
        assert result.output["alerts"] == []

    def test_breach_triggers_alert(self, builder):
        load_monitor_pack(builder)
        result = asyncio.run(builder.invoke("monitor-threshold", {
                "metrics": {"cpu": 99},
                "rules": {"cpu": {"min": 0, "max": 90}},
            })
        )
        assert result.ok is True
        assert result.output["ok"] is False
        assert len(result.output["alerts"]) == 1
        assert result.output["alerts"][0]["metric"] == "cpu"

    def test_warn_zone(self, builder):
        load_monitor_pack(builder)
        result = asyncio.run(builder.invoke("monitor-threshold", {
                "metrics": {"cpu": 85},
                "rules": {"cpu": {"min": 0, "max": 100, "warn_max": 80}},
            })
        )
        assert result.output["ok"] is True  # warning, not critical
        assert len(result.output["warnings"]) == 1


class TestHeartbeat:
    def test_healthy_agents(self, builder):
        load_monitor_pack(builder)
        now = 1000.0
        result = asyncio.run(builder.invoke("monitor-heartbeat", {
                "agents": {
                    "a": {"last_seen": now - 60},
                    "b": {"last_seen": now - 120},
                },
                "now": now,
            })
        )
        assert result.output["ok"] is True
        assert result.output["healthy_count"] == 2

    def test_stale_and_dead(self, builder):
        load_monitor_pack(builder)
        now = 1000.0
        result = asyncio.run(builder.invoke("monitor-heartbeat", {
                "agents": {
                    "fresh": {"last_seen": now - 60},
                    "stale": {"last_seen": now - 400},
                    "dead": {"last_seen": now - 1000},
                },
                "now": now,
                "stale_seconds": 300,
                "dead_seconds": 900,
            })
        )
        assert result.output["healthy_count"] == 1
        assert result.output["stale_count"] == 1
        assert result.output["dead_count"] == 1
        assert result.output["ok"] is False


class TestAnomaly:
    def test_no_anomalies(self, builder):
        load_monitor_pack(builder)
        values = [10.0 + (i % 5) * 0.01 for i in range(50)]
        result = asyncio.run(builder.invoke("monitor-anomaly", {"values": values})
        )
        assert result.output["ok"] is True
        assert result.output["anomaly_count"] == 0

    def test_detects_spike(self, builder):
        load_monitor_pack(builder)
        values = [10.0] * 30 + [100.0] + [10.0] * 10
        result = asyncio.run(builder.invoke("monitor-anomaly", {"values": values, "z_threshold": 2.0})
        )
        assert result.output["anomaly_count"] >= 1


# ─── Encoding Pack ──────────────────────────────────────────────────────


class TestBase64:
    def test_encode_decode_roundtrip(self, builder):
        load_encoding_pack(builder)
        enc = asyncio.run(builder.invoke("encode-base64", {"data": "hello manifold"})
        )
        assert enc.output["ok"] is True
        dec = asyncio.run(builder.invoke("encode-base64", {"data": enc.output["result"], "direction": "decode"})
        )
        assert dec.output["result"] == "hello manifold"


class TestJson:
    def test_parse_and_serialize(self, builder):
        load_encoding_pack(builder)
        parsed = asyncio.run(builder.invoke("encode-json", {"text": '{"key": "value", "num": 42}'})
        )
        assert parsed.output["ok"] is True
        assert parsed.output["result"]["num"] == 42

        serialized = asyncio.run(builder.invoke("encode-json", {"object": parsed.output["result"], "direction": "serialize"})
        )
        assert serialized.output["ok"] is True
        assert "42" in serialized.output["result"]

    def test_invalid_json(self, builder):
        load_encoding_pack(builder)
        result = asyncio.run(builder.invoke("encode-json", {"text": "{invalid json"})
        )
        assert result.output["ok"] is False


class TestCsv:
    def test_parse_and_serialize(self, builder):
        load_encoding_pack(builder)
        csv_text = "name,age\nAlice,30\nBob,25"
        parsed = asyncio.run(builder.invoke("encode-csv", {"text": csv_text})
        )
        assert parsed.output["count"] == 2
        assert parsed.output["records"][0]["name"] == "Alice"

        serialized = asyncio.run(builder.invoke("encode-csv", {"records": parsed.output["records"], "direction": "serialize"})
        )
        assert serialized.output["ok"] is True
        assert "Alice" in serialized.output["text"]


class TestUrlEncode:
    def test_encode_decode_roundtrip(self, builder):
        load_encoding_pack(builder)
        enc = asyncio.run(builder.invoke("encode-url", {"text": "hello world&foo=bar"})
        )
        assert enc.output["ok"] is True
        dec = asyncio.run(builder.invoke("encode-url", {"text": enc.output["result"], "direction": "decode"})
        )
        assert dec.output["result"] == "hello world&foo=bar"
