"""Subscription and notification routing for Manifold agents.

Agents subscribe to topics (with optional filters) and receive notifications
when matching events are published. Subscriptions use the audience routing
system to determine relevance via capability match, trust, and fog signals.

Usage::

    from manifold.subscription import SubscriptionBus

    bus = SubscriptionBus()

    # Agent subscribes
    sub = bus.subscribe("solar-agents", topic="solar-energy", min_score=0.3)
    # or with a filter:
    sub = bus.subscribe("braid", topic="bitcoin", filter_tags=["settlement"])

    # Publish an event
    bus.publish("New solar prediction available", topic="solar-energy")

    # Check for pending notifications
    notifications = bus.poll("solar-agents")
    for n in notifications:
        print(f"[{n.topic}] {n.message}")

Architecture:
    - ``Subscription`` — one agent's subscription to a topic
    - ``Notification`` — a pending message for a subscriber
    - ``SubscriptionBus`` — central hub managing subscriptions and delivery
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .audience import _trigram_similarity


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class DeliveryMode(str, Enum):
    IMMEDIATE = "immediate"   # poll returns immediately available
    BATCHED = "batched"       # collect until flush() called
    BEST_EFFORT = "best_effort"  # drop oldest if buffer full


@dataclass
class Subscription:
    """A single agent subscription to a topic."""
    sub_id: str
    agent_name: str
    topic: str
    min_score: float = 0.1
    filter_tags: list[str] = field(default_factory=list)
    max_buffer: int = 100
    delivery_mode: DeliveryMode = DeliveryMode.IMMEDIATE
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    match_count: int = 0
    last_matched_at: float | None = None
    _custom_filter: Callable[[dict[str, Any]], bool] | None = field(
        default=None, repr=False
    )

    @property
    def is_active(self) -> bool:
        return self.status == SubscriptionStatus.ACTIVE

    def matches_metadata(self, metadata: dict[str, Any]) -> bool:
        """Check if a publish event's metadata passes the subscription filters."""
        if not self.filter_tags:
            return True
        event_tags = set(t.lower() for t in metadata.get("tags", []))
        required = set(t.lower() for t in self.filter_tags)
        return required.issubset(event_tags)


@dataclass
class Notification:
    """A notification pending for a subscriber."""
    notif_id: str
    subscription_id: str
    agent_name: str
    topic: str
    message: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    delivered_at: float | None = None

    @property
    def is_delivered(self) -> bool:
        return self.delivered_at is not None

    def __repr__(self) -> str:
        return (
            f"<Notification {self.notif_id[:8]}… "
            f"topic={self.topic!r} agent={self.agent_name!r}>"
        )


@dataclass
class PublishResult:
    """Result of publishing a message to the bus."""
    message: str
    topic: str
    matched_subscriptions: int = 0
    notifications_created: int = 0
    notifications_dropped: int = 0

    def __repr__(self) -> str:
        return (
            f"<PublishResult topic={self.topic!r} "
            f"matched={self.matched_subscriptions} "
            f"notifs={self.notifications_created}>"
        )


@dataclass
class SubscriptionStats:
    """Aggregate stats for the subscription bus."""
    total_subscriptions: int = 0
    active_subscriptions: int = 0
    total_notifications: int = 0
    pending_notifications: int = 0
    delivered_notifications: int = 0
    dropped_notifications: int = 0
    topics: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"SubscriptionBus: {self.active_subscriptions}/{self.total_subscriptions} active, "
            f"{self.pending_notifications} pending, "
            f"{self.delivered_notifications} delivered, "
            f"{len(self.topics)} topics"
        )


class SubscriptionBus:
    """
    Central pub/sub hub for Manifold agent notifications.

    Agents subscribe to topics. When a message is published, the bus matches
    it against subscriptions using trigram similarity + optional tag filters.
    Notifications accumulate per-agent until polled.

    The bus can optionally integrate with an ``AudienceRouter`` to add trust
    and topology signals to the matching score, but works standalone with
    pure topic similarity.
    """

    def __init__(self, default_min_score: float = 0.15) -> None:
        self._subscriptions: dict[str, Subscription] = {}
        self._pending: dict[str, list[Notification]] = {}  # agent_name -> notifications
        self._dropped_count: int = 0
        self._default_min_score = default_min_score

    def subscribe(
        self,
        agent_name: str,
        topic: str,
        min_score: float | None = None,
        filter_tags: list[str] | None = None,
        max_buffer: int = 100,
        delivery_mode: DeliveryMode = DeliveryMode.IMMEDIATE,
        custom_filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Subscription:
        """
        Subscribe an agent to a topic.

        Args:
            agent_name:   Name of the subscribing agent.
            topic:        Topic pattern to match against.
            min_score:    Minimum similarity score (0–1). Uses bus default if None.
            filter_tags:  Only match events that have ALL these tags.
            max_buffer:   Max pending notifications before dropping oldest.
            delivery_mode: How notifications are delivered.
            custom_filter: Optional callable for advanced filtering.

        Returns:
            The Subscription object.
        """
        sub_id = f"sub-{uuid.uuid4().hex[:12]}"
        sub = Subscription(
            sub_id=sub_id,
            agent_name=agent_name,
            topic=topic,
            min_score=min_score if min_score is not None else self._default_min_score,
            filter_tags=filter_tags or [],
            max_buffer=max_buffer,
            delivery_mode=delivery_mode,
            _custom_filter=custom_filter,
        )
        self._subscriptions[sub_id] = sub
        return sub

    def unsubscribe(self, sub_id: str) -> bool:
        """Cancel a subscription. Returns True if found."""
        sub = self._subscriptions.get(sub_id)
        if sub is None:
            return False
        sub.status = SubscriptionStatus.CANCELLED
        return True

    def pause(self, sub_id: str) -> bool:
        """Pause a subscription (keeps it but stops matching)."""
        sub = self._subscriptions.get(sub_id)
        if sub is None:
            return False
        sub.status = SubscriptionStatus.PAUSED
        return True

    def resume(self, sub_id: str) -> bool:
        """Resume a paused subscription."""
        sub = self._subscriptions.get(sub_id)
        if sub is None:
            return False
        sub.status = SubscriptionStatus.ACTIVE
        return True

    def publish(
        self,
        message: str,
        topic: str,
        metadata: dict[str, Any] | None = None,
        exclude_agent: str | None = None,
    ) -> PublishResult:
        """
        Publish a message to all matching subscriptions.

        Args:
            message:      The message content.
            topic:        The topic of the message.
            metadata:     Optional metadata (can include "tags" for filtering).
            exclude_agent: Don't notify this agent (e.g. the sender).

        Returns:
            PublishResult with match/delivery stats.
        """
        metadata = metadata or {}
        matched = 0
        created = 0
        dropped = 0

        for sub in self._subscriptions.values():
            if not sub.is_active:
                continue
            if exclude_agent and sub.agent_name == exclude_agent:
                continue

            # Topic similarity
            score = _trigram_similarity(topic, sub.topic)
            if score < sub.min_score:
                continue

            # Tag filter
            if not sub.matches_metadata(metadata):
                continue

            # Custom filter
            if sub._custom_filter and not sub._custom_filter(metadata):
                continue

            matched += 1

            # Create notification
            notif = Notification(
                notif_id=f"notif-{uuid.uuid4().hex[:12]}",
                subscription_id=sub.sub_id,
                agent_name=sub.agent_name,
                topic=topic,
                message=message,
                score=score,
                metadata=metadata,
            )

            # Buffer management
            pending = self._pending.setdefault(sub.agent_name, [])
            if len(pending) >= sub.max_buffer:
                if sub.delivery_mode == DeliveryMode.BEST_EFFORT:
                    # Drop oldest
                    pending.pop(0)
                    dropped += 1
                    self._dropped_count += 1
                else:
                    # Drop this notification
                    dropped += 1
                    self._dropped_count += 1
                    continue

            pending.append(notif)
            created += 1
            sub.match_count += 1
            sub.last_matched_at = time.time()

        return PublishResult(
            message=message,
            topic=topic,
            matched_subscriptions=matched,
            notifications_created=created,
            notifications_dropped=dropped,
        )

    def poll(self, agent_name: str, limit: int | None = None) -> list[Notification]:
        """
        Retrieve and remove pending notifications for an agent.

        Args:
            agent_name: The agent to poll for.
            limit:      Max notifications to return. None = all.

        Returns:
            List of Notification objects (newest first).
        """
        pending = self._pending.get(agent_name, [])
        if not pending:
            return []

        if limit is not None:
            notifications = pending[-limit:]
            self._pending[agent_name] = pending[:-limit]
        else:
            notifications = list(pending)
            self._pending[agent_name] = []

        # Mark as delivered
        now = time.time()
        for n in notifications:
            n.delivered_at = now

        # Return newest first
        notifications.reverse()
        return notifications

    def peek(self, agent_name: str, limit: int | None = None) -> list[Notification]:
        """Like poll, but doesn't remove the notifications."""
        pending = self._pending.get(agent_name, [])
        if not pending:
            return []
        result = list(pending[-(limit or len(pending)):])
        result.reverse()
        return result

    def pending_count(self, agent_name: str) -> int:
        """Number of pending notifications for an agent."""
        return len(self._pending.get(agent_name, []))

    def get_subscription(self, sub_id: str) -> Subscription | None:
        """Look up a subscription by ID."""
        return self._subscriptions.get(sub_id)

    def list_subscriptions(
        self,
        agent_name: str | None = None,
        status: SubscriptionStatus | None = None,
    ) -> list[Subscription]:
        """List subscriptions, optionally filtered by agent or status."""
        subs = list(self._subscriptions.values())
        if agent_name is not None:
            subs = [s for s in subs if s.agent_name == agent_name]
        if status is not None:
            subs = [s for s in subs if s.status == status]
        return subs

    def stats(self) -> SubscriptionStats:
        """Aggregate statistics."""
        active = [s for s in self._subscriptions.values() if s.is_active]
        pending = sum(len(v) for v in self._pending.values())
        delivered = sum(
            s.match_count for s in self._subscriptions.values()
        ) - pending
        topics = list({s.topic for s in self._subscriptions.values()})

        return SubscriptionStats(
            total_subscriptions=len(self._subscriptions),
            active_subscriptions=len(active),
            total_notifications=sum(s.match_count for s in self._subscriptions.values()),
            pending_notifications=pending,
            delivered_notifications=max(delivered, 0),
            dropped_notifications=self._dropped_count,
            topics=topics,
        )

    def reset(self) -> None:
        """Clear all subscriptions and pending notifications."""
        self._subscriptions.clear()
        self._pending.clear()
        self._dropped_count = 0
