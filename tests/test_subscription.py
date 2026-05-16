"""Tests for manifold.subscription — pub/sub notification routing."""

import time
import pytest
from manifold.subscription import (
    SubscriptionBus,
    SubscriptionStatus,
    DeliveryMode,
    Notification,
    Subscription,
)


@pytest.fixture
def bus():
    return SubscriptionBus(default_min_score=0.15)


class TestSubscribe:
    def test_basic_subscribe(self, bus):
        sub = bus.subscribe("solar-agents", topic="solar-energy")
        assert sub.agent_name == "solar-agents"
        assert sub.topic == "solar-energy"
        assert sub.is_active
        assert sub.min_score == 0.15  # bus default

    def test_subscribe_with_options(self, bus):
        sub = bus.subscribe(
            "braid",
            topic="bitcoin",
            min_score=0.4,
            filter_tags=["settlement", "lightning"],
            max_buffer=50,
            delivery_mode=DeliveryMode.BATCHED,
        )
        assert sub.min_score == 0.4
        assert sub.filter_tags == ["settlement", "lightning"]
        assert sub.max_buffer == 50
        assert sub.delivery_mode == DeliveryMode.BATCHED

    def test_multiple_agents_same_topic(self, bus):
        s1 = bus.subscribe("agent-a", topic="weather")
        s2 = bus.subscribe("agent-b", topic="weather")
        assert s1.sub_id != s2.sub_id
        assert len(bus.list_subscriptions()) == 2


class TestUnsubscribe:
    def test_unsubscribe(self, bus):
        sub = bus.subscribe("agent-x", topic="data")
        assert bus.unsubscribe(sub.sub_id)
        assert sub.status == SubscriptionStatus.CANCELLED
        assert not sub.is_active

    def test_unsubscribe_unknown(self, bus):
        assert not bus.unsubscribe("nonexistent")


class TestPauseResume:
    def test_pause_resume(self, bus):
        sub = bus.subscribe("agent-y", topic="test")
        assert bus.pause(sub.sub_id)
        assert sub.status == SubscriptionStatus.PAUSED
        assert not sub.is_active

        assert bus.resume(sub.sub_id)
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.is_active

    def test_pause_unknown(self, bus):
        assert not bus.pause("nonexistent")


class TestPublish:
    def test_basic_publish_and_poll(self, bus):
        bus.subscribe("agent-a", topic="solar-energy", min_score=0.1)
        result = bus.publish("New solar prediction!", topic="solar-energy-panel-update")
        assert result.matched_subscriptions == 1
        assert result.notifications_created == 1

        notifs = bus.poll("agent-a")
        assert len(notifs) == 1
        assert notifs[0].message == "New solar prediction!"
        assert notifs[0].topic == "solar-energy-panel-update"

    def test_no_match(self, bus):
        bus.subscribe("agent-a", topic="bitcoin-price", min_score=0.5)
        result = bus.publish("Hello", topic="weather-forecast")
        assert result.matched_subscriptions == 0
        assert result.notifications_created == 0

    def test_multiple_subscribers(self, bus):
        bus.subscribe("agent-a", topic="data-pipeline", min_score=0.1)
        bus.subscribe("agent-b", topic="data-pipeline", min_score=0.1)
        bus.subscribe("agent-c", topic="solar-panel", min_score=0.1)

        result = bus.publish("Pipeline update", topic="data-pipeline-update")
        assert result.matched_subscriptions == 2
        assert result.notifications_created == 2

    def test_exclude_agent(self, bus):
        bus.subscribe("sender", topic="chat", min_score=0.1)
        bus.subscribe("receiver", topic="chat", min_score=0.1)

        result = bus.publish("Hello!", topic="chat-message", exclude_agent="sender")
        assert result.matched_subscriptions == 1
        assert bus.pending_count("sender") == 0
        assert bus.pending_count("receiver") == 1

    def test_paused_subscription_skipped(self, bus):
        sub = bus.subscribe("agent-z", topic="alerts", min_score=0.1)
        bus.pause(sub.sub_id)
        result = bus.publish("Alert!", topic="alerts-critical")
        assert result.matched_subscriptions == 0


class TestFilterTags:
    def test_tag_filter_match(self, bus):
        bus.subscribe("agent-a", topic="data", min_score=0.1, filter_tags=["urgent"])
        result = bus.publish("Data!", topic="data-update", metadata={"tags": ["urgent", "realtime"]})
        assert result.matched_subscriptions == 1

    def test_tag_filter_no_match(self, bus):
        bus.subscribe("agent-a", topic="data", min_score=0.1, filter_tags=["urgent"])
        result = bus.publish("Data!", topic="data-update", metadata={"tags": ["info"]})
        assert result.matched_subscriptions == 0

    def test_tag_filter_all_required(self, bus):
        bus.subscribe("agent-a", topic="data", min_score=0.1, filter_tags=["urgent", "bitcoin"])
        # Only one tag present
        result = bus.publish("Data!", topic="data-update", metadata={"tags": ["urgent"]})
        assert result.matched_subscriptions == 0

    def test_tag_filter_no_tags_in_event(self, bus):
        bus.subscribe("agent-a", topic="data", min_score=0.1, filter_tags=["urgent"])
        result = bus.publish("Data!", topic="data-update")
        assert result.matched_subscriptions == 0


class TestCustomFilter:
    def test_custom_filter_pass(self, bus):
        bus.subscribe(
            "agent-a", topic="events", min_score=0.1,
            custom_filter=lambda meta: meta.get("priority", 0) > 5,
        )
        result = bus.publish("High prio!", topic="events-update", metadata={"priority": 8})
        assert result.matched_subscriptions == 1

    def test_custom_filter_reject(self, bus):
        bus.subscribe(
            "agent-a", topic="events", min_score=0.1,
            custom_filter=lambda meta: meta.get("priority", 0) > 5,
        )
        result = bus.publish("Low prio!", topic="events-update", metadata={"priority": 2})
        assert result.matched_subscriptions == 0


class TestPoll:
    def test_poll_removes_notifications(self, bus):
        bus.subscribe("agent-a", topic="test-topic", min_score=0.1)
        bus.publish("msg1", topic="test-topic-update")
        bus.publish("msg2", topic="test-topic-update")

        notifs = bus.poll("agent-a")
        assert len(notifs) == 2

        # Second poll returns empty
        notifs2 = bus.poll("agent-a")
        assert len(notifs2) == 0

    def test_poll_with_limit(self, bus):
        bus.subscribe("agent-a", topic="test-topic", min_score=0.1)
        for i in range(5):
            bus.publish(f"msg{i}", topic="test-topic-update")

        notifs = bus.poll("agent-a", limit=2)
        assert len(notifs) == 2
        assert bus.pending_count("agent-a") == 3

    def test_poll_empty(self, bus):
        notifs = bus.poll("unknown-agent")
        assert notifs == []

    def test_poll_marks_delivered(self, bus):
        bus.subscribe("agent-a", topic="test-topic", min_score=0.1)
        bus.publish("msg", topic="test-topic-update")

        notifs = bus.poll("agent-a")
        assert len(notifs) == 1
        assert notifs[0].is_delivered
        assert notifs[0].delivered_at is not None


class TestPeek:
    def test_peek_doesnt_remove(self, bus):
        bus.subscribe("agent-a", topic="test-topic", min_score=0.1)
        bus.publish("msg", topic="test-topic-update")

        notifs = bus.peek("agent-a")
        assert len(notifs) == 1
        assert bus.pending_count("agent-a") == 1

    def test_peek_empty(self, bus):
        assert bus.peek("noone") == []


class TestBufferOverflow:
    def test_best_effort_drops_oldest(self, bus):
        bus.subscribe(
            "agent-a", topic="test-topic", min_score=0.1,
            max_buffer=3, delivery_mode=DeliveryMode.BEST_EFFORT,
        )
        for i in range(5):
            bus.publish(f"msg{i}", topic="test-topic-update")

        notifs = bus.poll("agent-a")
        assert len(notifs) == 3
        # Newest messages kept
        messages = [n.message for n in notifs]
        assert "msg4" in messages
        assert "msg2" in messages

    def test_immediate_mode_drops_newest(self, bus):
        bus.subscribe(
            "agent-a", topic="test-topic", min_score=0.1,
            max_buffer=2, delivery_mode=DeliveryMode.IMMEDIATE,
        )
        for i in range(5):
            bus.publish(f"msg{i}", topic="test-topic-update")

        notifs = bus.poll("agent-a")
        assert len(notifs) == 2


class TestStats:
    def test_stats_empty(self, bus):
        stats = bus.stats()
        assert stats.total_subscriptions == 0
        assert stats.active_subscriptions == 0

    def test_stats_after_activity(self, bus):
        bus.subscribe("agent-a", topic="solar", min_score=0.1)
        bus.subscribe("agent-b", topic="bitcoin", min_score=0.1)
        bus.publish("Solar update", topic="solar-panel-update")
        bus.poll("agent-a")

        stats = bus.stats()
        assert stats.total_subscriptions == 2
        assert stats.active_subscriptions == 2
        assert stats.total_notifications == 1
        assert stats.delivered_notifications == 1
        assert stats.pending_notifications == 0
        assert "solar" in stats.topics
        assert "bitcoin" in stats.topics

    def test_stats_summary(self, bus):
        bus.subscribe("agent-a", topic="test", min_score=0.1)
        stats = bus.stats()
        assert "1/1 active" in stats.summary()


class TestListSubscriptions:
    def test_list_all(self, bus):
        bus.subscribe("a", topic="t1")
        bus.subscribe("b", topic="t2")
        assert len(bus.list_subscriptions()) == 2

    def test_list_by_agent(self, bus):
        bus.subscribe("a", topic="t1")
        bus.subscribe("a", topic="t2")
        bus.subscribe("b", topic="t3")
        assert len(bus.list_subscriptions(agent_name="a")) == 2

    def test_list_by_status(self, bus):
        sub = bus.subscribe("a", topic="t1")
        bus.subscribe("b", topic="t2")
        bus.pause(sub.sub_id)
        assert len(bus.list_subscriptions(status=SubscriptionStatus.ACTIVE)) == 1
        assert len(bus.list_subscriptions(status=SubscriptionStatus.PAUSED)) == 1


class TestReset:
    def test_reset(self, bus):
        bus.subscribe("a", topic="t1", min_score=0.1)
        bus.publish("msg", topic="t1-update")
        bus.reset()
        assert len(bus.list_subscriptions()) == 0
        assert bus.pending_count("a") == 0


class TestSubscriptionMatches:
    def test_tag_match(self):
        sub = Subscription(
            sub_id="test",
            agent_name="a",
            topic="test",
            filter_tags=["urgent", "realtime"],
        )
        assert sub.matches_metadata({"tags": ["urgent", "realtime", "extra"]})
        assert not sub.matches_metadata({"tags": ["urgent"]})
        assert not sub.matches_metadata({})

    def test_no_filter_tags_matches_all(self):
        sub = Subscription(sub_id="test", agent_name="a", topic="test")
        assert sub.matches_metadata({"tags": ["anything"]})
        assert sub.matches_metadata({})
