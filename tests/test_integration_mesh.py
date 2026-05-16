"""
Integration test: multi-agent mesh lifecycle.

Spins up 3 agents on an in-memory transport and exercises:
1. Agent join + capability registration
2. Discovery (seek complementary knowledge)
3. Cognitive focus shift (think) + topology update
4. Pub/sub messaging between agents
5. Capability negotiation (structured contract)
6. Trust ledger grading + marketplace
7. Subscription/notification pub-sub
8. Resilience (retry + circuit breaker)
9. Scheduler (one-shot + recurring jobs)
10. End-to-end full mesh lifecycle

All in-process, no network required.
"""

import asyncio
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manifold import (
    Agent, AgentRef, TrustLedger, Grade, Claim, Stake,
    CapabilityExchange, CatalogEntry,
)
from manifold.negotiation import Negotiator, CapabilityRequest, NegotiationPolicy
from manifold.dispatch import TaskDispatcher, DispatchStatus
from manifold.subscription import SubscriptionBus
from manifold.resilience import TaskResilience, CircuitBreaker, CircuitState, RetryPolicy
from manifold.scheduler import AgentScheduler


# ─── Fixtures ───────────────────────────────────────────────────────────

class MeshHarness:
    """Sets up a 3-agent in-memory mesh for integration testing."""

    def __init__(self):
        self.alpha = Agent(name="alpha", transport="memory://test-mesh")
        self.beta = Agent(name="beta", transport="memory://test-mesh")
        self.gamma = Agent(name="gamma", transport="memory://test-mesh")

        self.alpha.knows(["reasoning", "analysis", "planning"])
        self.beta.knows(["coding", "debugging", "testing"])
        self.gamma.knows(["monitoring", "alerts", "reporting"])

        self.ledger = TrustLedger()
        self.exchange = CapabilityExchange(agent=self.alpha)

    async def start(self):
        await self.alpha.join()
        await self.beta.join()
        await self.gamma.join()
        await asyncio.sleep(0.05)

    async def stop(self):
        await self.alpha.leave()
        await self.beta.leave()
        await self.gamma.leave()


@pytest.fixture
def mesh():
    return MeshHarness()


# ─── 1. Agent Join + Registration ───────────────────────────────────────

class TestAgentJoin:
    def test_agents_have_names(self, mesh):
        assert mesh.alpha._name == "alpha"
        assert mesh.beta._name == "beta"
        assert mesh.gamma._name == "gamma"

    def test_agents_have_capabilities(self, mesh):
        assert "reasoning" in mesh.alpha._capabilities
        assert "coding" in mesh.beta._capabilities
        assert "monitoring" in mesh.gamma._capabilities

    @pytest.mark.asyncio
    async def test_join_registers_in_registry(self, mesh):
        await mesh.start()
        all_agents = mesh.alpha._registry.all_agents()
        names = {a.name for a in all_agents}
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names
        await mesh.stop()

    @pytest.mark.asyncio
    async def test_capabilities_propagate(self, mesh):
        await mesh.start()
        peers = mesh.alpha._registry.seek(
            topic="coding",
            my_capabilities=mesh.alpha._capabilities,
            my_name="alpha",
        )
        peer_names = {p.name for p in peers}
        assert "beta" in peer_names
        await mesh.stop()


# ─── 2. Discovery ───────────────────────────────────────────────────────

class TestDiscovery:
    @pytest.mark.asyncio
    async def test_seek_finds_complementary_agent(self, mesh):
        await mesh.start()
        peers = await mesh.alpha.seek("coding")
        peer_names = [p.name for p in peers]
        assert "beta" in peer_names
        await mesh.stop()

    @pytest.mark.asyncio
    async def test_seek_no_self(self, mesh):
        await mesh.start()
        peers = await mesh.alpha.seek("reasoning")
        peer_names = [p.name for p in peers]
        assert "alpha" not in peer_names
        await mesh.stop()


# ─── 3. Cognitive Focus ─────────────────────────────────────────────────

class TestCognitiveFocus:
    @pytest.mark.asyncio
    async def test_think_updates_focus(self, mesh):
        await mesh.start()
        await mesh.alpha.think("distributed-systems")
        await asyncio.sleep(0.05)
        focus = mesh.alpha._topology.current_focus
        assert focus == "distributed-systems"
        await mesh.stop()

    @pytest.mark.asyncio
    async def test_shared_focus_creates_strong_link(self, mesh):
        await mesh.start()
        await mesh.alpha.think("distributed-systems")
        await mesh.beta.think("distributed-systems")
        await asyncio.sleep(0.05)
        strong = mesh.alpha.strong_peers(threshold=0.5)
        assert "beta" in strong
        await mesh.stop()


# ─── 4. Pub/Sub Messaging ───────────────────────────────────────────────

class TestPubSub:
    @pytest.mark.asyncio
    async def test_publish_subscribe(self, mesh):
        await mesh.start()
        received = []

        async def handler(msg):
            received.append(msg)

        await mesh.beta.subscribe("test.channel", handler)
        await mesh.alpha.publish("test.channel", {"text": "hello beta"})
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0]["data"]["text"] == "hello beta"
        await mesh.stop()

    @pytest.mark.asyncio
    async def test_multi_subscriber(self, mesh):
        await mesh.start()
        alpha_msgs = []
        gamma_msgs = []

        async def alpha_handler(msg):
            alpha_msgs.append(msg)

        async def gamma_handler(msg):
            gamma_msgs.append(msg)

        await mesh.alpha.subscribe("alerts.all", alpha_handler)
        await mesh.gamma.subscribe("alerts.all", gamma_handler)

        await mesh.beta.publish("alerts.all", {"alert": "cpu-high"})
        await asyncio.sleep(0.05)

        assert len(alpha_msgs) == 1
        assert len(gamma_msgs) == 1
        await mesh.stop()


# ─── 5. Capability Negotiation ──────────────────────────────────────────

class TestNegotiation:
    @pytest.mark.asyncio
    async def test_basic_contract(self, mesh):
        negotiator = Negotiator(agent=mesh.alpha, policy=NegotiationPolicy(
            min_trust=0.0,
        ))

        # CapabilityRequest requires provider, not domain
        request = CapabilityRequest(
            requester="beta",
            provider="alpha",
            capability="code-review",
            inputs={"language": "python"},
            deadline_ms=5000,
        )

        contract = await negotiator.negotiate(request)
        assert contract is not None
        # Contract should be created (proposed or rejected based on policy)
        assert contract.status.value in ("proposed", "rejected")

    @pytest.mark.asyncio
    async def test_rejection_below_trust(self, mesh):
        negotiator = Negotiator(agent=mesh.alpha, policy=NegotiationPolicy(
            min_trust=0.8,
        ))

        request = CapabilityRequest(
            requester="beta",
            provider="alpha",
            capability="admin-access",
            inputs={},
            deadline_ms=5000,
            min_trust=0.9,
        )

        contract = await negotiator.negotiate(request)
        assert contract is None or contract.status.value == "rejected"


# ─── 6. Trust Ledger / Marketplace ──────────────────────────────────────

class TestMarketplace:
    def test_marketplace_lifecycle(self, mesh):
        mesh.ledger.record(Grade(agent="alpha", domain="reasoning", score=0.9, task_id="t1"))
        mesh.ledger.record(Grade(agent="alpha", domain="reasoning", score=0.85, task_id="t2"))
        mesh.ledger.record(Grade(agent="beta", domain="coding", score=0.7, task_id="t3"))

        score = mesh.ledger.domain_score("alpha", "reasoning")
        assert score is not None
        assert score > 0.8

        beta_score = mesh.ledger.domain_score("beta", "coding")
        assert beta_score is not None
        assert beta_score < score

    def test_trust_deteriorates_on_bad_grades(self, mesh):
        mesh.ledger.record(Grade(agent="gamma", domain="monitoring", score=0.9, task_id="g1"))
        mesh.ledger.record(Grade(agent="gamma", domain="monitoring", score=0.3, task_id="g2"))
        mesh.ledger.record(Grade(agent="gamma", domain="monitoring", score=0.2, task_id="g3"))

        score = mesh.ledger.domain_score("gamma", "monitoring")
        assert score is not None
        assert score < 0.7


# ─── 7. Subscription Bus ────────────────────────────────────────────────

class TestSubscriptions:
    def test_pubsub_lifecycle(self):
        bus = SubscriptionBus()
        sub = bus.subscribe(
            agent_name="alpha",
            topic="alerts.critical",
            filter_tags=["urgent"],
        )
        assert sub is not None
        assert sub.sub_id is not None

        # Tags must be in metadata["tags"] for filtering to work
        bus.publish(
            message="disk full on /dev/sda1",
            topic="alerts.critical",
            metadata={"level": "critical", "tags": ["urgent"]},
        )

        notifs = bus.poll("alpha")
        assert len(notifs) == 1
        assert "disk full" in notifs[0].message

    def test_tag_filtering(self):
        bus = SubscriptionBus()
        bus.subscribe(agent_name="beta", topic="events", filter_tags=["crypto"])

        bus.publish(message="BTC surge", topic="events", metadata={"tags": ["crypto"]})
        bus.publish(message="DOGE pump", topic="events", metadata={"tags": ["meme"]})

        notifs = bus.poll("beta")
        assert len(notifs) == 1
        assert "BTC" in notifs[0].message


# ─── 8. Resilience ──────────────────────────────────────────────────────

class TestResilience:
    def test_retry_succeeds_eventually(self):
        call_count = 0

        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient failure")
            return "success"

        # execute() is synchronous
        policy = RetryPolicy(max_retries=3, backoff_base=0.01)
        tr = TaskResilience(retry_policy=policy)
        result = tr.execute(flaky_operation)
        assert result == "success"
        assert call_count == 3

    def test_circuit_breaker_opens(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.05)

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_circuit_breaker_half_open(self):
        import time
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.05)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)
        assert cb.allow_request()


# ─── 9. Scheduler ───────────────────────────────────────────────────────

class TestScheduler:
    def test_one_shot_task(self, mesh):
        scheduler = AgentScheduler(agent=mesh.alpha)

        job = scheduler.once(
            topic="test-task",
            delay_seconds=0.1,
            payload={"action": "run"},
        )
        assert job is not None
        assert job.job_id is not None

        pending = scheduler.pending()
        assert any(j.topic == "test-task" for j in pending)

    def test_recurring_task(self, mesh):
        scheduler = AgentScheduler(agent=mesh.alpha)

        job = scheduler.every(
            topic="heartbeat",
            interval_seconds=5.0,
            payload={"type": "ping"},
        )
        assert job is not None

        by_topic = scheduler.jobs_by_topic("heartbeat")
        assert len(by_topic) == 1

    def test_cancel_task(self, mesh):
        scheduler = AgentScheduler(agent=mesh.alpha)

        job = scheduler.once(topic="cancel-me", delay_seconds=10.0)
        assert scheduler.cancel(job.job_id) is True


# ─── 10. End-to-End Integration ─────────────────────────────────────────

class TestEndToEnd:
    """Full lifecycle: join → discover → negotiate → grade."""

    @pytest.mark.asyncio
    async def test_full_mesh_lifecycle(self, mesh):
        await mesh.start()

        # Step 1: Alpha seeks a coder
        peers = await mesh.alpha.seek("coding")
        assert len(peers) > 0
        assert peers[0].name == "beta"

        # Step 2: Align on a topic
        await mesh.alpha.think("refactor-auth-module")
        await mesh.beta.think("refactor-auth-module")
        await asyncio.sleep(0.05)

        strong = mesh.alpha.strong_peers(threshold=0.3)
        assert "beta" in strong

        # Step 3: Negotiate (alpha requests, beta provides)
        negotiator = Negotiator(agent=mesh.beta, policy=NegotiationPolicy(
            min_trust=0.0,
        ))
        contract = await negotiator.negotiate(
            CapabilityRequest(
                requester="alpha",
                provider="beta",
                capability="refactor",
                inputs={"module": "auth"},
                deadline_ms=10000,
            ),
        )
        assert contract is not None

        # Step 4: Grade the result
        mesh.ledger.record(Grade(
            agent="beta", domain="coding", score=0.92,
            task_id=contract.contract_id,
        ))

        # Step 5: Verify trust
        score = mesh.ledger.domain_score("beta", "coding")
        assert score is not None
        assert score >= 0.9

        # Step 6: Notification bus
        bus = SubscriptionBus()
        bus.subscribe(agent_name="alpha", topic="task.complete", filter_tags=["coding"])
        bus.publish(
            message="refactor complete",
            topic="task.complete",
            metadata={"task": "refactor-auth", "score": 0.92, "tags": ["coding"]},
        )

        notifs = bus.poll("alpha")
        assert len(notifs) >= 1

        await mesh.stop()


# ─── Run standalone ─────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
