"""
Tests for fog_client — event parsing, subscriber, timeseries, status, registry.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fog_client.types import (
    EventType, FogEvent,
    SeamShiftData, DarkPressureData, FogVolumeData, MeshMutationData,
)
from fog_client.subscriber import FogSubscriber
from fog_client.timeseries import query_timeseries, TimeseriesEntry
from fog_client.status import RelayStatus
from fog_client.registry import AgentRegistry, AgentProfile


# ── Event Parsing ─────────────────────────────────────────────────────────────

class TestEventParsing:

    def test_parse_seam_shift(self):
        payload = {
            "type": "seam.shift",
            "timestamp": "2026-05-04T19:21:00Z",
            "data": {
                "seam": "void-watcher↔sentry",
                "previous": 0.95,
                "current": 1.0,
                "delta": 0.05,
            }
        }
        event = FogEvent.from_dict(payload)
        assert event.type == EventType.SEAM_SHIFT
        assert isinstance(event.data, SeamShiftData)
        assert event.data.seam == "void-watcher↔sentry"
        assert event.data.delta == 0.05
        assert event.data.direction == "diverging"

    def test_parse_dark_pressure(self):
        payload = {
            "type": "dark.pressure",
            "timestamp": "2026-05-04T19:22:00Z",
            "data": {
                "circle_id": "dc-hog-001",
                "pressure": 0.72,
                "previous_pressure": 0.45,
                "delta": 0.27,
                "new": False,
            }
        }
        event = FogEvent.from_dict(payload)
        assert event.type == EventType.DARK_PRESSURE
        assert isinstance(event.data, DarkPressureData)
        assert event.data.circle_id == "dc-hog-001"
        assert not event.data.is_new

    def test_parse_dark_pressure_new(self):
        payload = {
            "type": "dark.pressure",
            "timestamp": "2026-05-04T20:00:00Z",
            "data": {
                "circle_id": "dc-relay-003",
                "pressure": 0.9,
                "new": True,
            }
        }
        event = FogEvent.from_dict(payload)
        assert event.data.is_new

    def test_parse_fog_volume(self):
        payload = {
            "type": "fog.volume",
            "timestamp": "2026-05-04T19:30:00Z",
            "data": {
                "total_gaps": 23,
                "previous_gaps": 28,
                "delta": -5,
                "by_domain": {"physics": 8, "solar": 12, "mesh": 3},
            }
        }
        event = FogEvent.from_dict(payload)
        assert event.type == EventType.FOG_VOLUME
        assert isinstance(event.data, FogVolumeData)
        assert event.data.direction == "clearing"
        assert event.data.by_domain["solar"] == 12

    def test_parse_mesh_mutation(self):
        payload = {
            "type": "mesh.mutation",
            "timestamp": "2026-05-04T19:35:00Z",
            "data": {
                "mutation_type": "peer_join",
                "agent": "braid@hog",
                "hub": "hog",
            }
        }
        event = FogEvent.from_dict(payload)
        assert event.type == EventType.MESH_MUTATION
        assert event.data.agent == "braid@hog"

    def test_parse_preserves_raw(self):
        payload = {
            "type": "seam.shift",
            "timestamp": "2026-05-04T19:21:00Z",
            "data": {"seam": "a↔b", "previous": 0.5, "current": 0.6, "delta": 0.1,
                     "extra_field": "preserved"},
        }
        event = FogEvent.from_dict(payload)
        assert event.raw == payload
        assert event.raw["data"]["extra_field"] == "preserved"

    def test_parse_unknown_data_fields_filtered(self):
        """Extra fields in data that don't match the dataclass are dropped."""
        payload = {
            "type": "seam.shift",
            "timestamp": "2026-05-04T19:21:00Z",
            "data": {
                "seam": "a↔b",
                "previous": 0.5,
                "current": 0.6,
                "delta": 0.1,
                "totally_made_up": True,
            }
        }
        event = FogEvent.from_dict(payload)
        assert isinstance(event.data, SeamShiftData)
        assert not hasattr(event.data, "totally_made_up")

    def test_seam_direction_converging(self):
        data = SeamShiftData(seam="a↔b", previous=0.8, current=0.6, delta=-0.2)
        assert data.direction == "converging"

    def test_seam_direction_stable(self):
        data = SeamShiftData(seam="a↔b", previous=0.5, current=0.5, delta=0.0)
        assert data.direction == "stable"

    def test_fog_volume_deepening(self):
        data = FogVolumeData(total_gaps=30, previous_gaps=25, delta=5)
        assert data.direction == "deepening"


# ── Subscriber ────────────────────────────────────────────────────────────────

class TestSubscriber:

    def test_subscribe_chainable(self):
        client = FogSubscriber("ws://localhost:8790")
        result = client.subscribe(["seam.shift", "dark.pressure"])
        assert result is client
        assert EventType.SEAM_SHIFT in client._subscriptions
        assert EventType.DARK_PRESSURE in client._subscriptions

    def test_unsubscribe(self):
        client = FogSubscriber("ws://localhost:8790")
        client.subscribe(["seam.shift", "dark.pressure"])
        client.unsubscribe(["dark.pressure"])
        assert EventType.DARK_PRESSURE not in client._subscriptions
        assert EventType.SEAM_SHIFT in client._subscriptions

    def test_on_decorator(self):
        client = FogSubscriber("ws://localhost:8790")

        @client.on("seam.shift")
        async def handler(event):
            pass

        assert handler in client._handlers[EventType.SEAM_SHIFT]

    def test_on_any(self):
        client = FogSubscriber("ws://localhost:8790")

        async def handler(event):
            pass

        client.on_any(handler)
        assert handler in client._wildcard_handlers

    def test_recent_events(self):
        client = FogSubscriber("ws://localhost:8790")
        event = FogEvent(
            type=EventType.SEAM_SHIFT,
            timestamp=datetime.now(timezone.utc),
            data=SeamShiftData(seam="a↔b", previous=0.5, current=0.6, delta=0.1),
        )
        client._ring_buffer.append(event)
        assert len(client.recent_events()) == 1

    @pytest.mark.asyncio
    async def test_dispatch_calls_handlers(self):
        client = FogSubscriber("ws://localhost:8790")
        received = []

        @client.on("seam.shift")
        async def handler(event):
            received.append(event)

        event = FogEvent(
            type=EventType.SEAM_SHIFT,
            timestamp=datetime.now(timezone.utc),
            data=SeamShiftData(seam="a↔b", previous=0.5, current=0.6, delta=0.1),
        )
        await client._dispatch(event)
        assert len(received) == 1
        assert received[0].data.seam == "a↔b"

    @pytest.mark.asyncio
    async def test_dispatch_calls_wildcard(self):
        client = FogSubscriber("ws://localhost:8790")
        received = []

        async def wildcard_handler(event):
            received.append(event)

        client.on_any(wildcard_handler)

        event = FogEvent(
            type=EventType.FOG_VOLUME,
            timestamp=datetime.now(timezone.utc),
            data=FogVolumeData(total_gaps=10, previous_gaps=8, delta=2),
        )
        await client._dispatch(event)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_handler_error_doesnt_crash(self):
        client = FogSubscriber("ws://localhost:8790")

        @client.on("seam.shift")
        async def bad_handler(event):
            raise RuntimeError("boom")

        good_received = []

        @client.on("seam.shift")
        async def good_handler(event):
            good_received.append(event)

        event = FogEvent(
            type=EventType.SEAM_SHIFT,
            timestamp=datetime.now(timezone.utc),
            data=SeamShiftData(seam="a↔b", previous=0.5, current=0.6, delta=0.1),
        )
        await client._dispatch(event)  # should not raise
        assert len(good_received) == 1

    @pytest.mark.asyncio
    async def test_handle_raw_single_event(self):
        client = FogSubscriber("ws://localhost:8790")
        client.subscribe(["seam.shift"])
        received = []

        @client.on("seam.shift")
        async def handler(event):
            received.append(event)

        raw = json.dumps({
            "type": "seam.shift",
            "timestamp": "2026-05-04T19:21:00Z",
            "data": {"seam": "x↔y", "previous": 0.3, "current": 0.4, "delta": 0.1}
        })
        await client._handle_raw(raw)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_handle_raw_replay_batch(self):
        client = FogSubscriber("ws://localhost:8790")
        client.subscribe(["seam.shift", "dark.pressure"])
        received = []

        @client.on("seam.shift")
        async def handler(event):
            received.append(event)

        batch = [
            {"type": "seam.shift", "timestamp": "2026-05-04T19:20:00Z",
             "data": {"seam": "a↔b", "previous": 0.5, "current": 0.6, "delta": 0.1}},
            {"type": "seam.shift", "timestamp": "2026-05-04T19:21:00Z",
             "data": {"seam": "c↔d", "previous": 0.2, "current": 0.3, "delta": 0.1}},
            {"type": "dark.pressure", "timestamp": "2026-05-04T19:22:00Z",
             "data": {"circle_id": "dc-001", "pressure": 0.8, "new": True}},
        ]
        await client._handle_raw(json.dumps(batch))
        assert len(received) == 2  # only seam.shift events

    @pytest.mark.asyncio
    async def test_unsubscribed_events_filtered(self):
        client = FogSubscriber("ws://localhost:8790")
        client.subscribe(["seam.shift"])
        received = []

        @client.on_any
        async def handler(event):
            received.append(event)

        raw = json.dumps({
            "type": "fog.volume",
            "timestamp": "2026-05-04T19:21:00Z",
            "data": {"total_gaps": 10, "previous_gaps": 10, "delta": 0}
        })
        await client._handle_raw(raw)
        assert len(received) == 0  # filtered out


# ── Backoff ───────────────────────────────────────────────────────────────────

class TestBackoff:

    def test_backoff_increases(self):
        client = FogSubscriber("ws://localhost:8790", backoff_base=1.0, backoff_max=60.0)
        client._reconnect_attempts = 0
        d0 = client._compute_backoff()
        client._reconnect_attempts = 3
        d3 = client._compute_backoff()
        assert d3 > d0

    def test_backoff_capped(self):
        client = FogSubscriber("ws://localhost:8790", backoff_base=1.0, backoff_max=10.0)
        client._reconnect_attempts = 20
        d = client._compute_backoff()
        assert d <= 10.0 + 1.0  # max + jitter


# ── Timeseries ────────────────────────────────────────────────────────────────

class TestTimeseries:

    def _write_jsonl(self, tmpdir: Path, filename: str, events: list):
        filepath = tmpdir / filename
        with open(filepath, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")
        return filepath

    def test_query_range(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events = [
                {"type": "seam.shift", "timestamp": "2026-05-04T10:00:00Z",
                 "data": {"seam": "a↔b", "previous": 0.5, "current": 0.6, "delta": 0.1}},
                {"type": "seam.shift", "timestamp": "2026-05-04T12:00:00Z",
                 "data": {"seam": "c↔d", "previous": 0.2, "current": 0.3, "delta": 0.1}},
                {"type": "fog.volume", "timestamp": "2026-05-04T14:00:00Z",
                 "data": {"total_gaps": 10, "previous_gaps": 12, "delta": -2}},
            ]
            self._write_jsonl(Path(tmpdir), "2026-05-04.jsonl", events)

            results = query_timeseries(
                from_ts=datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc),
                to_ts=datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc),
                data_dir=tmpdir,
            )
            assert len(results) == 2  # only events before 13:00

    def test_query_type_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            events = [
                {"type": "seam.shift", "timestamp": "2026-05-04T10:00:00Z",
                 "data": {"seam": "a↔b", "previous": 0.5, "current": 0.6, "delta": 0.1}},
                {"type": "fog.volume", "timestamp": "2026-05-04T11:00:00Z",
                 "data": {"total_gaps": 10, "previous_gaps": 12, "delta": -2}},
            ]
            self._write_jsonl(Path(tmpdir), "2026-05-04.jsonl", events)

            results = query_timeseries(
                from_ts=datetime(2026, 5, 4, 0, 0, tzinfo=timezone.utc),
                event_types=["seam.shift"],
                data_dir=tmpdir,
            )
            assert len(results) == 1
            assert results[0].event.type == EventType.SEAM_SHIFT

    def test_query_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = query_timeseries(
                from_ts=datetime(2026, 5, 4, tzinfo=timezone.utc),
                data_dir=tmpdir,
            )
            assert results == []


# ── Status ────────────────────────────────────────────────────────────────────

class TestRelayStatus:

    def test_uptime_human_hours(self):
        status = RelayStatus(
            connected=True, uptime_seconds=7384, subscribers=2,
            events_emitted=150, last_event_timestamp=None,
            last_event_type=None, ring_buffer_size=100, relay_url="http://localhost:8790",
        )
        assert status.uptime_human == "2h 3m"

    def test_uptime_human_minutes(self):
        status = RelayStatus(
            connected=True, uptime_seconds=185, subscribers=1,
            events_emitted=50, last_event_timestamp=None,
            last_event_type=None, ring_buffer_size=100, relay_url="http://localhost:8790",
        )
        assert status.uptime_human == "3m 5s"

    def test_summary(self):
        status = RelayStatus(
            connected=True, uptime_seconds=3600, subscribers=3,
            events_emitted=200, last_event_timestamp=None,
            last_event_type=None, ring_buffer_size=100, relay_url="http://localhost:8790",
        )
        s = status.summary()
        assert "🟢" in s
        assert "1h 0m" in s


# ── Registry ──────────────────────────────────────────────────────────────────

class TestAgentRegistry:

    def test_enrich_seam_event(self):
        registry = AgentRegistry()
        registry._cache = {
            "void-watcher": AgentProfile(
                name="void-watcher", hub="hog",
                capabilities=["detection"], blind_spots=["solar-flare"],
                domains=["detection", "mesh"],
            ),
            "sentry": AgentProfile(
                name="sentry", hub="thefog",
                capabilities=["monitoring"], blind_spots=["orbital-mech"],
                domains=["monitoring", "physics"],
            ),
        }

        event = FogEvent(
            type=EventType.SEAM_SHIFT,
            timestamp=datetime.now(timezone.utc),
            data=SeamShiftData(seam="void-watcher↔sentry", previous=0.9, current=1.0, delta=0.1),
        )
        enriched = registry.enrich_seam_event(event)
        assert enriched["agent_a"]["blind_spots"] == ["solar-flare"]
        assert enriched["agent_b"]["blind_spots"] == ["orbital-mech"]
        assert "solar-flare" in enriched["combined_blind_spots"]
        assert "orbital-mech" in enriched["combined_blind_spots"]
        # void-watcher domains: [detection, mesh], sentry domains: [monitoring, physics] — no overlap
        assert enriched["domain_overlap"] == []

    def test_enrich_non_seam_event(self):
        registry = AgentRegistry()
        event = FogEvent(
            type=EventType.FOG_VOLUME,
            timestamp=datetime.now(timezone.utc),
            data=FogVolumeData(total_gaps=10, previous_gaps=8, delta=2),
        )
        assert registry.enrich_seam_event(event) == {}

    def test_agent_profile_rich_data(self):
        profile = AgentProfile(
            name="braid", hub="hog",
            blind_spots=["quantum"], domains=["physics"],
        )
        assert profile.has_rich_data

    def test_agent_profile_no_rich_data(self):
        profile = AgentProfile(name="braid", hub="hog")
        assert not profile.has_rich_data
