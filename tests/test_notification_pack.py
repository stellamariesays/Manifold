"""Tests for the notification capability pack."""

import asyncio
import pytest


def _make_builder():
    from manifold.capability_builder import CapabilityBuilder
    from manifold.capability_pack import load_notification_pack

    builder = CapabilityBuilder.__new__(CapabilityBuilder)
    builder._caps = {}
    builder._agent = None
    load_notification_pack(builder)
    return builder


def _run(coro):
    return asyncio.run(coro)


class TestNotificationChannel:
    def setup_method(self):
        """Reset in-memory state before each test."""
        from manifold import capability_pack as cp
        cp._notification_channels.clear()
        cp._notification_subs.clear()
        cp._notification_queue.clear()
        cp._notification_templates.clear()
        cp._notification_rate_limits.clear()

    def test_register_channel(self):
        builder = _make_builder()
        handler = builder._caps["notif-channel-register"].handler
        result = _run(handler({"channel_id": "slack-ops", "type": "webhook", "config": {"url": "https://hooks.slack.com/x"}}))
        assert result["ok"] is True
        assert result["channel"]["channel_id"] == "slack-ops"
        assert result["channel"]["type"] == "webhook"

    def test_register_channel_invalid_type(self):
        builder = _make_builder()
        handler = builder._caps["notif-channel-register"].handler
        result = _run(handler({"channel_id": "ch1", "type": "carrier_pigeon"}))
        assert result["ok"] is False
        assert "Invalid type" in result["error"]

    def test_register_channel_duplicate(self):
        builder = _make_builder()
        handler = builder._caps["notif-channel-register"].handler
        _run(handler({"channel_id": "ch1", "type": "email", "config": {"email": "a@b.c"}}))
        result = _run(handler({"channel_id": "ch1", "type": "email", "config": {"email": "d@e.f"}}))
        assert result["ok"] is False

    def test_list_channels(self):
        builder = _make_builder()
        reg = builder._caps["notif-channel-register"].handler
        lst = builder._caps["notif-channel-list"].handler
        _run(reg({"channel_id": "ch1", "type": "email", "config": {}}))
        _run(reg({"channel_id": "ch2", "type": "webhook", "config": {}}))
        result = _run(lst({}))
        assert result["ok"] is True
        assert result["total"] == 2

    def test_remove_channel(self):
        builder = _make_builder()
        reg = builder._caps["notif-channel-register"].handler
        rm = builder._caps["notif-channel-remove"].handler
        _run(reg({"channel_id": "ch1", "type": "email", "config": {}}))
        result = _run(rm({"channel_id": "ch1"}))
        assert result["ok"] is True
        assert result["removed"] == "ch1"
        # Verify gone
        assert _run(builder._caps["notif-channel-list"].handler({}))["total"] == 0

    def test_remove_channel_cascades_subs(self):
        builder = _make_builder()
        reg = builder._caps["notif-channel-register"].handler
        sub = builder._caps["notif-subscribe"].handler
        rm = builder._caps["notif-channel-remove"].handler
        _run(reg({"channel_id": "ch1", "type": "email", "config": {}}))
        _run(sub({"channel_id": "ch1", "topic": "alerts", "sub_id": "s1"}))
        result = _run(rm({"channel_id": "ch1"}))
        assert result["subs_removed"] == 1


class TestNotificationSubscribe:
    def setup_method(self):
        from manifold import capability_pack as cp
        cp._notification_channels.clear()
        cp._notification_subs.clear()
        cp._notification_queue.clear()
        cp._notification_templates.clear()
        cp._notification_rate_limits.clear()

    def _setup_channel(self, builder):
        handler = builder._caps["notif-channel-register"].handler
        _run(handler({"channel_id": "ch1", "type": "email", "config": {"email": "ops@example.com"}}))

    def test_subscribe(self):
        builder = _make_builder()
        self._setup_channel(builder)
        handler = builder._caps["notif-subscribe"].handler
        result = _run(handler({"channel_id": "ch1", "topic": "alerts"}))
        assert result["ok"] is True
        assert result["subscription"]["channel_id"] == "ch1"
        assert result["subscription"]["topic"] == "alerts"

    def test_subscribe_missing_channel(self):
        builder = _make_builder()
        handler = builder._caps["notif-subscribe"].handler
        result = _run(handler({"channel_id": "nope", "topic": "alerts"}))
        assert result["ok"] is False

    def test_unsubscribe(self):
        builder = _make_builder()
        self._setup_channel(builder)
        sub = builder._caps["notif-subscribe"].handler
        unsub = builder._caps["notif-unsubscribe"].handler
        res = _run(sub({"channel_id": "ch1", "topic": "*", "sub_id": "s1"}))
        assert res["ok"] is True
        result = _run(unsub({"sub_id": "s1"}))
        assert result["ok"] is True
        assert result["removed"] == "s1"


class TestNotificationSend:
    def setup_method(self):
        from manifold import capability_pack as cp
        cp._notification_channels.clear()
        cp._notification_subs.clear()
        cp._notification_queue.clear()
        cp._notification_templates.clear()
        cp._notification_rate_limits.clear()

    def _setup(self, builder):
        reg = builder._caps["notif-channel-register"].handler
        sub = builder._caps["notif-subscribe"].handler
        _run(reg({"channel_id": "ch1", "type": "webhook", "config": {"url": "https://example.com/hook"}}))
        _run(reg({"channel_id": "ch2", "type": "email", "config": {"email": "admin@test.com"}}))
        _run(sub({"channel_id": "ch1", "topic": "alerts", "sub_id": "s1"}))
        _run(sub({"channel_id": "ch2", "topic": "*", "min_severity": "warning", "sub_id": "s2"}))

    def test_send_matching_subscribers(self):
        builder = _make_builder()
        self._setup(builder)
        handler = builder._caps["notif-send"].handler
        result = _run(handler({"topic": "alerts", "severity": "info", "title": "Test", "body": "Hello"}))
        assert result["ok"] is True
        # ch1 subscribes to "alerts" at info level, ch2 subscribes to "*" at warning level
        assert result["total_channels"] == 1
        assert result["delivered"][0]["channel_id"] == "ch1"
        assert result["delivered"][0]["status"] == "sent"

    def test_send_critical_reaches_all(self):
        builder = _make_builder()
        self._setup(builder)
        handler = builder._caps["notif-send"].handler
        result = _run(handler({"topic": "alerts", "severity": "critical", "title": "Panic", "body": "Now!"}))
        assert result["total_channels"] == 2
        statuses = {d["channel_id"]: d["status"] for d in result["delivered"]}
        assert statuses["ch1"] == "sent"
        assert statuses["ch2"] == "sent"

    def test_send_no_matching_subs(self):
        builder = _make_builder()
        self._setup(builder)
        handler = builder._caps["notif-send"].handler
        result = _run(handler({"topic": "unknown-topic", "severity": "info", "title": "X", "body": "Y"}))
        assert result["total_channels"] == 0
        assert result["delivered"] == []


class TestNotificationTemplates:
    def setup_method(self):
        from manifold import capability_pack as cp
        cp._notification_channels.clear()
        cp._notification_subs.clear()
        cp._notification_queue.clear()
        cp._notification_templates.clear()
        cp._notification_rate_limits.clear()

    def test_template_set_and_list(self):
        builder = _make_builder()
        set_h = builder._caps["notif-template-set"].handler
        list_h = builder._caps["notif-template-list"].handler
        _run(set_h({"name": "alert", "template": "Alert: {event} at {time}"}))
        result = _run(list_h({}))
        assert result["ok"] is True
        assert result["templates"]["alert"] == "Alert: {event} at {time}"

    def test_send_with_template(self):
        builder = _make_builder()
        reg = builder._caps["notif-channel-register"].handler
        sub = builder._caps["notif-subscribe"].handler
        tmpl = builder._caps["notif-template-set"].handler
        send = builder._caps["notif-send"].handler
        hist = builder._caps["notif-history"].handler

        _run(reg({"channel_id": "ch1", "type": "in_app", "config": {}}))
        _run(sub({"channel_id": "ch1", "topic": "*", "sub_id": "s1"}))
        _run(tmpl({"name": "deploy", "template": "Deployed {service} version {version}"}))

        result = _run(send({
            "topic": "deploy",
            "severity": "info",
            "title": "Deploy",
            "template": "deploy",
            "template_vars": {"service": "api", "version": "2.0"},
        }))
        assert result["ok"] is True

        # Check history for expanded body
        hist_result = _run(hist({}))
        assert hist_result["total"] == 1
        assert hist_result["notifications"][0]["body"] == "Deployed api version 2.0"


class TestNotificationHistory:
    def setup_method(self):
        from manifold import capability_pack as cp
        cp._notification_channels.clear()
        cp._notification_subs.clear()
        cp._notification_queue.clear()
        cp._notification_templates.clear()
        cp._notification_rate_limits.clear()

    def test_history_with_filters(self):
        builder = _make_builder()
        reg = builder._caps["notif-channel-register"].handler
        sub = builder._caps["notif-subscribe"].handler
        send = builder._caps["notif-send"].handler
        hist = builder._caps["notif-history"].handler

        _run(reg({"channel_id": "ch1", "type": "webhook", "config": {}}))
        _run(sub({"channel_id": "ch1", "topic": "*", "sub_id": "s1"}))

        _run(send({"topic": "alerts", "severity": "info", "title": "A1", "body": "B1"}))
        _run(send({"topic": "deploys", "severity": "critical", "title": "A2", "body": "B2"}))

        # Filter by topic
        r = _run(hist({"topic": "alerts"}))
        assert r["total"] == 1
        assert r["notifications"][0]["topic"] == "alerts"

        # Filter by severity
        r = _run(hist({"severity": "critical"}))
        assert r["total"] == 1
        assert r["notifications"][0]["severity"] == "critical"

        # Filter by channel
        r = _run(hist({"channel_id": "ch1"}))
        assert r["total"] == 2
