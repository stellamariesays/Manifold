"""Tests for the deliberation capability pack."""

import asyncio
import pytest

from manifold.agent import Agent
from manifold.capability_builder import CapabilityBuilder
from manifold.capability_pack import load_deliberation_pack


@pytest.fixture
def builder():
    a = Agent("test-delib")
    b = CapabilityBuilder(a)
    load_deliberation_pack(b)
    return b


def _run(coro):
    return asyncio.run(coro)


class TestDeliberationPropose:
    def test_basic_proposal(self, builder):
        r = _run(builder.invoke("deliberation-propose", {
            "topic": "Should we migrate to v2?",
            "proposal": "Migrate the mesh protocol to v2",
            "proposer": "agent-alpha",
        }))
        assert r.ok is True
        assert r.output["proposal_id"]
        assert r.output["status"] == "open"
        assert r.output["proposal"]["topic"] == "Should we migrate to v2?"

    def test_proposal_without_topic_fails(self, builder):
        r = _run(builder.invoke("deliberation-propose", {"proposal": "text"}))
        assert r.ok is False

    def test_proposal_custom_options(self, builder):
        r = _run(builder.invoke("deliberation-propose", {
            "topic": "Choose framework",
            "options": ["react", "vue", "svelte"],
        }))
        assert r.ok is True
        assert r.output["proposal"]["options"] == ["react", "vue", "svelte"]


class TestDeliberationArgue:
    def test_basic_argument(self, builder):
        r = _run(builder.invoke("deliberation-argue", {
            "proposal_id": "abc123",
            "position": "support",
            "argument": "Migration is necessary because performance limitations under high load",
            "agent": "agent-beta",
            "evidence": ["benchmark data shows 40% improvement"],
            "confidence": 0.85,
        }))
        assert r.ok is True
        assert r.output["position"] == "support"
        assert r.output["quality_score"] > 0

    def test_argument_quality_scoring(self, builder):
        good = _run(builder.invoke("deliberation-argue", {
            "proposal_id": "abc",
            "position": "support",
            "argument": "Evidence clearly shows therefore however the data supports this conclusion because of benchmark results",
            "agent": "a",
            "evidence": ["ev1", "ev2", "ev3"],
            "confidence": 0.9,
        }))
        weak = _run(builder.invoke("deliberation-argue", {
            "proposal_id": "abc",
            "position": "oppose",
            "argument": "nah",
            "agent": "b",
            "confidence": 0.5,
        }))
        assert good.output["quality_score"] > weak.output["quality_score"]

    def test_missing_fields(self, builder):
        r = _run(builder.invoke("deliberation-argue", {"proposal_id": "abc"}))
        assert r.ok is False


class TestDeliberationVote:
    def test_support_vote(self, builder):
        r = _run(builder.invoke("deliberation-vote", {
            "proposal_id": "abc",
            "agent": "voter-1",
            "vote": "support",
            "weight": 2.0,
        }))
        assert r.ok is True
        assert r.output["tally"]["support"] == 2.0
        assert r.output["tally"]["oppose"] == 0.0

    def test_invalid_vote(self, builder):
        r = _run(builder.invoke("deliberation-vote", {
            "proposal_id": "abc",
            "agent": "voter-1",
            "vote": "invalid",
        }))
        assert r.ok is False

    def test_missing_proposal_id(self, builder):
        r = _run(builder.invoke("deliberation-vote", {
            "agent": "voter-1",
            "vote": "support",
        }))
        assert r.ok is False


class TestDeliberationConsensus:
    def test_clear_consensus(self, builder):
        r = _run(builder.invoke("deliberation-consensus", {
            "positions": [
                {"position": "support"},
                {"position": "support"},
                {"position": "support"},
                {"position": "oppose"},
            ],
            "threshold": 0.6,
        }))
        assert r.ok is True
        assert r.output["consensus"] is True
        assert r.output["dominant"] == "support"
        assert r.output["agreement"] == 0.75

    def test_no_consensus(self, builder):
        r = _run(builder.invoke("deliberation-consensus", {
            "positions": [
                {"position": "support"},
                {"position": "oppose"},
            ],
            "threshold": 0.6,
        }))
        assert r.output["consensus"] is False

    def test_empty_positions(self, builder):
        r = _run(builder.invoke("deliberation-consensus", {"positions": []}))
        assert r.ok is False

    def test_entropy_decreases_with_agreement(self, builder):
        unanimous = _run(builder.invoke("deliberation-consensus", {
            "positions": [{"position": "support"}] * 5,
        }))
        divided = _run(builder.invoke("deliberation-consensus", {
            "positions": [{"position": "support"}, {"position": "oppose"}, {"position": "neutral"}],
        }))
        assert unanimous.output["entropy"] <= divided.output["entropy"]


class TestDeliberationQuorum:
    def test_quorum_met(self, builder):
        r = _run(builder.invoke("deliberation-quorum", {
            "participants": ["a", "b", "c", "d", "e", "f"],
            "total_eligible": 10,
            "quorum_fraction": 0.5,
        }))
        assert r.ok is True
        assert r.output["quorum_met"] is True
        assert r.output["participants"] == 6

    def test_quorum_not_met(self, builder):
        r = _run(builder.invoke("deliberation-quorum", {
            "participants": ["a", "b"],
            "total_eligible": 10,
            "quorum_fraction": 0.5,
        }))
        assert r.output["quorum_met"] is False
        assert r.output["deficit"] == 3

    def test_deduplication(self, builder):
        r = _run(builder.invoke("deliberation-quorum", {
            "participants": ["a", "a", "a", "b", "b"],
            "total_eligible": 10,
            "quorum_fraction": 0.2,
        }))
        assert r.output["participants"] == 2


class TestDeliberationSynthesize:
    def test_basic_synthesis(self, builder):
        r = _run(builder.invoke("deliberation-synthesize", {
            "arguments": [
                {"position": "support", "argument": "Good idea", "quality_score": 0.8, "confidence": 0.9},
                {"position": "support", "argument": "Strong evidence", "quality_score": 0.7, "confidence": 0.8},
                {"position": "oppose", "argument": "Risky", "quality_score": 0.4, "confidence": 0.5},
            ],
        }))
        assert r.ok is True
        assert r.output["collective_position"] == "support"
        assert r.output["argument_counts"]["support"] == 2
        assert r.output["argument_counts"]["oppose"] == 1

    def test_empty_arguments(self, builder):
        r = _run(builder.invoke("deliberation-synthesize", {"arguments": []}))
        assert r.ok is False


class TestDeliberationIntegration:
    def test_full_deliberation_flow(self, builder):
        """Propose -> argue -> vote -> quorum -> consensus -> synthesize."""
        # 1. Propose
        proposal = _run(builder.invoke("deliberation-propose", {
            "topic": "Deploy v2.0",
            "proposal": "Deploy version 2.0 of the mesh protocol",
            "proposer": "lead",
        }))
        assert proposal.ok is True

        # 2. Argue
        arg1 = _run(builder.invoke("deliberation-argue", {
            "proposal_id": proposal.output["proposal_id"],
            "position": "support",
            "argument": "Testing shows 2x throughput improvement because the new protocol handles batching better",
            "agent": "qa-agent",
            "evidence": ["benchmark results", "load test report"],
            "confidence": 0.88,
        }))
        assert arg1.ok is True

        arg2 = _run(builder.invoke("deliberation-argue", {
            "proposal_id": proposal.output["proposal_id"],
            "position": "oppose",
            "argument": "Migration requires downtime during business hours",
            "agent": "ops-agent",
            "confidence": 0.7,
        }))
        assert arg2.ok is True

        # 3. Vote
        for i, v in enumerate(["support", "support", "support", "oppose", "abstain"]):
            r = _run(builder.invoke("deliberation-vote", {
                "proposal_id": proposal.output["proposal_id"],
                "agent": f"voter-{i}",
                "vote": v,
            }))
            assert r.ok is True

        # 4. Quorum
        quorum = _run(builder.invoke("deliberation-quorum", {
            "participants": [f"voter-{i}" for i in range(5)],
            "total_eligible": 8,
            "quorum_fraction": 0.5,
        }))
        assert quorum.output["quorum_met"] is True

        # 5. Consensus
        consensus = _run(builder.invoke("deliberation-consensus", {
            "positions": [
                {"position": "support"},
                {"position": "support"},
                {"position": "support"},
                {"position": "oppose"},
                {"position": "neutral"},
            ],
            "threshold": 0.5,
        }))
        assert consensus.output["consensus"] is True

        # 6. Synthesize
        synthesis = _run(builder.invoke("deliberation-synthesize", {
            "arguments": [arg1.output["argument"], arg2.output["argument"]],
        }))
        assert synthesis.ok is True
        assert synthesis.output["total_arguments"] == 2

    def test_capabilities_registered(self, builder):
        caps = builder.list_capabilities()
        names = [c.name for c in caps]
        for expected in [
            "deliberation-propose", "deliberation-argue", "deliberation-vote",
            "deliberation-consensus", "deliberation-quorum", "deliberation-synthesize",
        ]:
            assert expected in names, f"Missing capability: {expected}"
