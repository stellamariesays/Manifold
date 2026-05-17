"""Tests for fog alert capability pack — rule CRUD, evaluation, cooldown, history."""

import asyncio
import pytest
import time

from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_fog_alert_pack
from manifold.agent import Agent


# Helper to build a fresh builder with the fog alert pack loaded
def _builder():
    agent = Agent(name="test-alert-agent")
    builder = CapabilityBuilder(agent)
    load_fog_alert_pack(builder)
    return builder


def _invoke(builder, name, payload):
    r = asyncio.run(builder.invoke(name, payload))
    if r.ok:
        return {"ok": True, **r.output}
    return {"ok": False, "error": r.error}


@pytest.fixture(autouse=True)
def _clear_rules():
    """Clear global alert state between tests."""
    from manifold import capability_pack as cp
    cp._fog_alert_rules.clear()
    cp._fog_alert_history.clear()
    yield
    cp._fog_alert_rules.clear()
    cp._fog_alert_history.clear()


class TestAlertCreate:
    def test_create_basic_rule(self):
        b = _builder()
        result = _invoke(b, "fog-alert-create", {
            "name": "seam-high",
            "event_type": "seam.shift",
            "condition": {"field": "data.delta", "op": "gt", "value": 0.5},
            "severity": "critical",
        })
        assert result["ok"] is True
        assert result["rule"]["name"] == "seam-high"
        assert result["rule"]["event_type"] == "seam.shift"
        assert result["rule"]["severity"] == "critical"
        assert result["rule"]["enabled"] is True
        assert result["total_rules"] == 1

    def test_create_default_severity(self):
        b = _builder()
        result = _invoke(b, "fog-alert-create", {
            "name": "r1",
            "event_type": "dark.pressure",
            "condition": {"field": "data.pressure", "op": "gt", "value": 0.8},
        })
        assert result["ok"] is True
        assert result["rule"]["severity"] == "warning"

    def test_create_duplicate_fails(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "dup",
            "event_type": "seam.shift",
            "condition": {"field": "data.delta", "op": "gt", "value": 0.5},
        })
        result = _invoke(b, "fog-alert-create", {
            "name": "dup",
            "event_type": "seam.shift",
            "condition": {"field": "data.delta", "op": "gt", "value": 0.5},
        })
        assert result["ok"] is False
        assert "already exists" in result["error"]

    def test_create_missing_name(self):
        b = _builder()
        result = _invoke(b, "fog-alert-create", {
            "event_type": "seam.shift",
            "condition": {"field": "data.delta", "op": "gt", "value": 0.5},
        })
        assert result["ok"] is False

    def test_create_invalid_event_type(self):
        b = _builder()
        result = _invoke(b, "fog-alert-create", {
            "name": "bad",
            "event_type": "invalid.type",
            "condition": {"field": "data.x", "op": "gt", "value": 0},
        })
        assert result["ok"] is False

    def test_create_invalid_condition(self):
        b = _builder()
        result = _invoke(b, "fog-alert-create", {
            "name": "bad",
            "event_type": "seam.shift",
            "condition": {"field": "data.delta"},  # missing op and value
        })
        assert result["ok"] is False

    def test_create_invalid_op(self):
        b = _builder()
        result = _invoke(b, "fog-alert-create", {
            "name": "bad",
            "event_type": "seam.shift",
            "condition": {"field": "data.delta", "op": "xxx", "value": 0},
        })
        assert result["ok"] is False


class TestAlertDelete:
    def test_delete_existing(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "del-me",
            "event_type": "fog.volume",
            "condition": {"field": "data.delta", "op": "lt", "value": -5},
        })
        result = _invoke(b, "fog-alert-delete", {"name": "del-me"})
        assert result["ok"] is True
        assert result["deleted"] == "del-me"
        assert result["total_rules"] == 0

    def test_delete_nonexistent(self):
        b = _builder()
        result = _invoke(b, "fog-alert-delete", {"name": "ghost"})
        assert result["ok"] is False


class TestAlertToggle:
    def test_toggle_off(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "t1",
            "event_type": "seam.shift",
            "condition": {"field": "data.delta", "op": "gt", "value": 0},
        })
        result = _invoke(b, "fog-alert-toggle", {"name": "t1"})
        assert result["ok"] is True
        assert result["enabled"] is False

    def test_toggle_back_on(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "t2",
            "event_type": "seam.shift",
            "condition": {"field": "data.delta", "op": "gt", "value": 0},
        })
        _invoke(b, "fog-alert-toggle", {"name": "t2"})
        result = _invoke(b, "fog-alert-toggle", {"name": "t2"})
        assert result["enabled"] is True

    def test_toggle_nonexistent(self):
        b = _builder()
        result = _invoke(b, "fog-alert-toggle", {"name": "nope"})
        assert result["ok"] is False


class TestAlertList:
    def test_list_empty(self):
        b = _builder()
        result = _invoke(b, "fog-alert-list", {})
        assert result["ok"] is True
        assert result["rules"] == []
        assert result["total"] == 0

    def test_list_multiple(self):
        b = _builder()
        for i in range(3):
            _invoke(b, "fog-alert-create", {
                "name": f"rule-{i}",
                "event_type": "seam.shift",
                "condition": {"field": "data.delta", "op": "gt", "value": i * 0.1},
            })
        result = _invoke(b, "fog-alert-list", {})
        assert result["total"] == 3


class TestAlertEvaluate:
    def test_eval_matching_rule(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "high-delta",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0.5},
        })
        result = _invoke(b, "fog-alert-eval", {
            "event": {
                "type": "seam.shift",
                "data": {"seam": "a↔b", "delta": 0.9, "previous": 0.1, "current": 1.0},
            }
        })
        assert result["ok"] is True
        assert len(result["matches"]) == 1
        assert result["matches"][0]["rule"] == "high-delta"
        assert result["matches"][0]["fired"] is True

    def test_eval_no_match(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "high-delta",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0.5},
        })
        result = _invoke(b, "fog-alert-eval", {
            "event": {
                "type": "seam.shift",
                "data": {"delta": 0.1},
            }
        })
        assert len(result["matches"]) == 0

    def test_eval_wrong_event_type(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "seam-only",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0},
        })
        result = _invoke(b, "fog-alert-eval", {
            "event": {
                "type": "dark.pressure",
                "data": {"pressure": 0.9},
            }
        })
        assert len(result["matches"]) == 0

    def test_eval_disabled_rule_skipped(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "disabled",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0},
        })
        _invoke(b, "fog-alert-toggle", {"name": "disabled"})
        result = _invoke(b, "fog-alert-eval", {
            "event": {
                "type": "seam.shift",
                "data": {"delta": 1.0},
            }
        })
        assert len(result["matches"]) == 0

    def test_eval_cooldown_prevents_fire(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "cd-test",
            "event_type": "fog.volume",
            "condition": {"field": "delta", "op": "gt", "value": 0},
            "cooldown": 300,  # 5 minutes
        })
        # First eval fires
        r1 = _invoke(b, "fog-alert-eval", {
            "event": {"type": "fog.volume", "data": {"delta": 10}},
        })
        assert r1["matches"][0]["fired"] is True
        # Second eval blocked by cooldown
        r2 = _invoke(b, "fog-alert-eval", {
            "event": {"type": "fog.volume", "data": {"delta": 10}},
        })
        assert r2["matches"][0]["fired"] is False
        assert r2["matches"][0]["cooldown_remaining"] > 0

    def test_eval_dotted_field_path(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "deep-field",
            "event_type": "dark.pressure",
            "condition": {"field": "pressure", "op": "gte", "value": 0.7},
        })
        result = _invoke(b, "fog-alert-eval", {
            "event": {
                "type": "dark.pressure",
                "data": {"pressure": 0.8},
            }
        })
        assert len(result["matches"]) == 1
        assert result["matches"][0]["fired"] is True

    def test_eval_multiple_rules_different_severities(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "info-rule",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0},
            "severity": "info",
        })
        _invoke(b, "fog-alert-create", {
            "name": "crit-rule",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0.8},
            "severity": "critical",
        })
        result = _invoke(b, "fog-alert-eval", {
            "event": {
                "type": "seam.shift",
                "data": {"delta": 0.9},
            }
        })
        assert len(result["matches"]) == 2
        severities = {m["severity"] for m in result["matches"]}
        assert severities == {"info", "critical"}


class TestAlertHistory:
    def test_history_empty(self):
        b = _builder()
        result = _invoke(b, "fog-alert-history", {})
        assert result["ok"] is True
        assert result["history"] == []

    def test_history_after_fires(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "h1",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0},
            "severity": "critical",
        })
        _invoke(b, "fog-alert-eval", {
            "event": {"type": "seam.shift", "data": {"delta": 0.5}},
        })
        result = _invoke(b, "fog-alert-history", {})
        assert result["total"] == 1
        assert result["history"][0]["rule"] == "h1"
        assert result["history"][0]["severity"] == "critical"

    def test_history_severity_filter(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "info-r",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0},
            "severity": "info",
        })
        _invoke(b, "fog-alert-create", {
            "name": "crit-r",
            "event_type": "dark.pressure",
            "condition": {"field": "pressure", "op": "gt", "value": 0},
            "severity": "critical",
        })
        _invoke(b, "fog-alert-eval", {
            "event": {"type": "seam.shift", "data": {"delta": 1}},
        })
        _invoke(b, "fog-alert-eval", {
            "event": {"type": "dark.pressure", "data": {"pressure": 0.5}},
        })
        result = _invoke(b, "fog-alert-history", {"severity": "critical"})
        assert result["total"] == 1
        assert result["history"][0]["rule"] == "crit-r"

    def test_history_limit(self):
        b = _builder()
        _invoke(b, "fog-alert-create", {
            "name": "lim",
            "event_type": "fog.volume",
            "condition": {"field": "delta", "op": "gt", "value": 0},
        })
        for i in range(5):
            # Manually bypass cooldown by setting last_fired to 0
            from manifold import capability_pack as cp
            cp._fog_alert_rules["lim"]["last_fired"] = 0
            _invoke(b, "fog-alert-eval", {
                "event": {"type": "fog.volume", "data": {"delta": i + 1}},
            })
        result = _invoke(b, "fog-alert-history", {"limit": 2})
        assert len(result["history"]) == 2


class TestAlertEndToEnd:
    def test_full_lifecycle(self):
        """Create → list → eval → history → disable → eval (no fire) → delete."""
        b = _builder()

        # Create
        r = _invoke(b, "fog-alert-create", {
            "name": "lifecycle",
            "event_type": "seam.shift",
            "condition": {"field": "delta", "op": "gt", "value": 0.3},
            "severity": "warning",
            "topic": "mesh-ops",
        })
        assert r["ok"]

        # List
        r = _invoke(b, "fog-alert-list", {})
        assert r["total"] == 1

        # Eval triggers
        r = _invoke(b, "fog-alert-eval", {
            "event": {"type": "seam.shift", "data": {"delta": 0.5}},
        })
        assert len(r["matches"]) == 1
        assert r["matches"][0]["fired"] is True

        # History shows fire
        r = _invoke(b, "fog-alert-history", {})
        assert r["total"] == 1

        # Disable
        r = _invoke(b, "fog-alert-toggle", {"name": "lifecycle"})
        assert r["enabled"] is False

        # Eval no longer matches
        from manifold import capability_pack as cp
        cp._fog_alert_rules["lifecycle"]["last_fired"] = 0  # bypass cooldown
        r = _invoke(b, "fog-alert-eval", {
            "event": {"type": "seam.shift", "data": {"delta": 0.5}},
        })
        assert len(r["matches"]) == 0

        # Delete
        r = _invoke(b, "fog-alert-delete", {"name": "lifecycle"})
        assert r["ok"]
        r = _invoke(b, "fog-alert-list", {})
        assert r["total"] == 0
