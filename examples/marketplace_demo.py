#!/usr/bin/env python3
"""
Manifold Capability Marketplace Demo

Shows how agents register capabilities, discover peers, bid on tasks,
and get selected via trust-weighted scoring.

This demonstrates the core economic loop of the Manifold mesh:
1. Agents register what they can do (capabilities)
2. A task arrives with requirements
3. Agents stake and bid
4. Trust ledger ranks and selects the best agent
5. Task is dispatched, completed, and graded

Usage:
    python examples/marketplace_demo.py
"""

import sys
import os
import random
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from core.trust import TrustLedger, Grade, Claim, Stake
    from core.agent import Agent
    from core.registry import AgentRef
except ImportError:
    from manifold import TrustLedger, Grade, Claim, Stake
    Agent = object
    from manifold import AgentRef


# ── Marketplace types ──────────────────────────────────────────────────

@dataclass
class TaskRequest:
    """A task that needs an agent."""
    id: str
    domain: str
    description: str
    max_stake: float = 100.0
    timeout_ms: int = 30000
    required_capabilities: list[str] = field(default_factory=list)


@dataclass
class AgentBid:
    """An agent's bid for a task."""
    agent: str
    stake: float
    claimed_score: float  # what the agent claims it can deliver
    capabilities: list[str]
    latency_estimate_ms: float = 0.0


@dataclass
class TaskResult:
    """Outcome of a completed task."""
    task_id: str
    agent: str
    success: bool
    score: float  # 0.0–1.0
    output: str
    latency_ms: float


class CapabilityMarketplace:
    """
    The marketplace where agents offer and consume capabilities.

    Trust-weighted selection: agents with better history get preference.
    Staking ensures skin in the game — bad outcomes cost you.
    """

    def __init__(self, ledger: TrustLedger):
        self.ledger = ledger
        self.agents: dict[str, AgentRef] = {}
        self.completed_tasks: list[TaskResult] = []

    def register_agent(self, ref: AgentRef, capabilities: list[str]):
        """Register an agent with its capabilities."""
        self.agents[ref.name] = ref
        for cap in capabilities:
            self.ledger.record(Grade(
                agent=ref.name,
                domain=cap,
                score=0.5,  # starting score, will be updated
                task_id=f"registration-{ref.name}-{cap}",
            ))

    def submit_task(self, task: TaskRequest) -> Optional[TaskResult]:
        """
        Full task lifecycle: solicit bids → rank → dispatch → grade.
        """
        print(f"\n{'='*60}")
        print(f"📋 TASK: {task.description}")
        print(f"   Domain: {task.domain}  ID: {task.id}")
        print(f"{'='*60}")

        # 1. Solicit bids from capable agents
        bids = self._solicit_bids(task)
        if not bids:
            print("   ❌ No agents bid on this task")
            return None

        print(f"\n   Bids received: {len(bids)}")
        for b in bids:
            print(f"   • {b.agent}: stake={b.stake:.0f}, claim={b.claimed_score:.2f}, "
                  f"caps={b.capabilities}")

        # 2. Rank bids using trust-weighted scoring
        ranked = self._rank_bids(bids, task.domain)
        winner = ranked[0]
        print(f"\n   🏆 Winner: {winner.agent} (trust score: {self._trust_score(winner.agent, task.domain):.3f})")

        # 3. Simulate task execution
        result = self._execute_task(task, winner)
        print(f"\n   {'✅' if result.success else '❌'} Result: score={result.score:.2f}, "
              f"latency={result.latency_ms:.0f}ms")
        print(f"   Output: {result.output[:100]}")

        # 4. Grade and update trust
        grade = Grade(
            agent=result.agent,
            domain=task.domain,
            score=result.score,
            task_id=task.id,
        )
        self.ledger.record(grade)

        # Check if stake should be forfeited
        if result.score < 0.5:
            print(f"   ⚠️  Score below threshold — stake forfeited!")

        trust_after = self._trust_score(result.agent, task.domain)
        print(f"   Trust score after: {trust_after:.3f}")

        self.completed_tasks.append(result)
        return result

    def _solicit_bids(self, task: TaskRequest) -> list[AgentBid]:
        """Agents that have the right capabilities submit bids."""
        bids = []
        for name, ref in self.agents.items():
            # Check if agent has relevant capabilities
            relevant = self._relevant_capabilities(name, task.domain)
            if not relevant:
                continue

            trust = self._trust_score(name, task.domain)
            stake = min(task.max_stake, 10 + trust * 90)
            claimed = min(1.0, trust + random.uniform(-0.1, 0.15))

            bids.append(AgentBid(
                agent=name,
                stake=stake,
                claimed_score=max(0.1, claimed),
                capabilities=relevant,
                latency_estimate_ms=random.uniform(50, 500),
            ))
        return bids

    def _rank_bids(self, bids: list[AgentBid], domain: str) -> list[AgentBid]:
        """Rank bids by trust-weighted score."""
        def score_bid(bid: AgentBid) -> float:
            trust = self._trust_score(bid.agent, domain)
            # Weight: 60% trust history, 25% stake, 15% claimed score
            return trust * 0.6 + (bid.stake / 100) * 0.25 + bid.claimed_score * 0.15

        return sorted(bids, key=score_bid, reverse=True)

    def _execute_task(self, task: TaskRequest, winner: AgentBid) -> TaskResult:
        """Simulate task execution with some variance."""
        trust = self._trust_score(winner.agent, task.domain)
        # Higher trust → more consistent good results
        score = max(0.0, min(1.0, trust + random.gauss(0, 0.15)))
        success = score >= 0.5

        outputs = {
            "technical-analysis": f"RSI: {random.randint(30,70)}, MACD: {'bullish' if score > 0.5 else 'bearish'}, Signal: {'BUY' if score > 0.7 else 'HOLD' if score > 0.4 else 'SELL'}",
            "mesh-topology": f"Mesh health: {score*100:.0f}%, {random.randint(5,25)} active agents, {random.randint(1,5) if score < 0.6 else 0} issues detected",
            "solar-flare": f"Flare class: {random.choice(['C', 'M', 'X'])}{random.randint(1,9)}, Probability: {score*100:.0f}%",
            "system-info": f"CPU: {random.randint(20,95)}%, Memory: {random.randint(30,85)}%, Disk: {random.randint(40,80)}%",
            "settlement": f"Tx confirmed: {'YES' if success else 'NO'}, {random.randint(1,6)} confirmations, fee: {random.uniform(0.0001, 0.001):.6f} BTC",
            "monitoring": f"All systems {'nominal' if success else 'WARNING: elevated latency'}, uptime: {random.randint(1,90)}d",
        }

        return TaskResult(
            task_id=task.id,
            agent=winner.agent,
            success=success,
            score=score,
            output=outputs.get(task.domain, f"Completed with score {score:.2f}"),
            latency_ms=winner.latency_estimate_ms * (1 + random.uniform(-0.3, 0.3)),
        )

    def _trust_score(self, agent: str, domain: str) -> float:
        """Get agent's trust score for a domain."""
        score = self.ledger.domain_score(agent, domain)
        return score if score is not None else 0.3  # default for unknown

    def _relevant_capabilities(self, agent: str, domain: str) -> list[str]:
        """Find agent capabilities relevant to a domain."""
        cap_map = {
            "technical-analysis": ["technical-analysis", "price-monitoring", "signals"],
            "mesh-topology": ["mesh-topology", "routing", "monitoring"],
            "solar-flare": ["solar-flare", "AR-classification"],
            "system-info": ["system-info", "monitoring", "health-check"],
            "settlement": ["escrow", "trust-scoring", "settlement"],
            "monitoring": ["monitoring", "system-info", "health-check", "alerts"],
        }
        relevant_domains = cap_map.get(domain, [domain])

        result = []
        for rec_domain in self.ledger._records.get(agent, {}):
            if rec_domain in relevant_domains:
                result.append(rec_domain)
        return result

    def print_leaderboard(self):
        """Print the current trust leaderboard."""
        print(f"\n{'='*60}")
        print("📊 CAPABILITY MARKETPLACE — TRUST LEADERBOARD")
        print(f"{'='*60}")

        rankings = []
        for agent in self.agents:
            scores = []
            for domain in self.ledger._records.get(agent, {}):
                s = self.ledger.domain_score(agent, domain)
                if s is not None:
                    scores.append(s)
            avg = sum(scores) / len(scores) if scores else 0
            domains = len(self.ledger._records.get(agent, {}))
            rankings.append((agent, avg, domains))

        rankings.sort(key=lambda x: -x[1])

        print(f"\n{'Agent':<20} {'Trust':>6} {'Domains':>8} {'Bar'}")
        print("-" * 60)
        for agent, avg, domains in rankings:
            bar_len = int(avg * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            print(f"{agent:<20} {avg:>5.3f} {domains:>8}  {bar}")

        print(f"\nTasks completed: {len(self.completed_tasks)}")
        success_rate = sum(1 for t in self.completed_tasks if t.success) / max(len(self.completed_tasks), 1)
        print(f"Success rate: {success_rate*100:.1f}%")


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║        MANIFOLD CAPABILITY MARKETPLACE DEMO                 ║")
    print("║     Trust-weighted agent selection with skin in the game    ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    ledger = TrustLedger()
    market = CapabilityMarketplace(ledger)

    # Register agents with their capabilities
    agents = {
        "stella": ["identity", "memory", "health-check"],
        "braid": ["solar-flare", "AR-classification"],
        "manifold": ["mesh-topology", "routing"],
        "btc-signals": ["technical-analysis", "price-monitoring", "signals"],
        "btc-settlement": ["escrow", "trust-scoring", "settlement"],
        "infra": ["system-info", "monitoring", "health-check"],
        "wake": ["alerts", "monitoring"],
    }

    print("\n📦 Registering agents...")
    for name, caps in agents.items():
        ref = AgentRef(name=name, capabilities=caps, address=f"satelliteA/{name}")
        market.register_agent(ref, caps)
        print(f"   ✓ {name}: {', '.join(caps)}")

    # Seed some history so trust scores differentiate
    print("\n📈 Seeding trust history...")
    history = [
        ("btc-signals", "technical-analysis", 0.85),
        ("btc-signals", "technical-analysis", 0.78),
        ("btc-signals", "price-monitoring", 0.91),
        ("btc-signals", "signals", 0.72),
        ("btc-settlement", "escrow", 0.95),
        ("btc-settlement", "settlement", 0.88),
        ("btc-settlement", "trust-scoring", 0.82),
        ("infra", "system-info", 0.93),
        ("infra", "monitoring", 0.89),
        ("infra", "health-check", 0.96),
        ("stella", "identity", 0.91),
        ("stella", "memory", 0.87),
        ("stella", "health-check", 0.84),
        ("braid", "solar-flare", 0.79),
        ("braid", "AR-classification", 0.83),
        ("manifold", "mesh-topology", 0.90),
        ("manifold", "routing", 0.86),
        ("wake", "alerts", 0.75),
        ("wake", "monitoring", 0.71),
    ]
    for agent, domain, score in history:
        ledger.record(Grade(agent=agent, domain=domain, score=score,
                           task_id=f"seed-{agent}-{domain}-{random.randint(1,999)}"))

    # Run tasks through the marketplace
    tasks = [
        TaskRequest(id="t1", domain="technical-analysis",
                   description="Analyze BTC/USD for breakout signals"),
        TaskRequest(id="t2", domain="mesh-topology",
                   description="Map current mesh topology and detect partitions"),
        TaskRequest(id="t3", domain="settlement",
                   description="Settle BTC escrow tx #4a7f2b"),
        TaskRequest(id="t4", domain="system-info",
                   description="SatelliteA system health check"),
        TaskRequest(id="t5", domain="monitoring",
                   description="Fleet-wide monitoring sweep"),
        TaskRequest(id="t6", domain="solar-flare",
                   description="Predict solar flare probability next 48h"),
        TaskRequest(id="t7", domain="technical-analysis",
                   description="ETH momentum analysis"),
        TaskRequest(id="t8", domain="settlement",
                   description="Process batch settlement for 3 pending TXs"),
    ]

    for task in tasks:
        market.submit_task(task)

    # Final leaderboard
    market.print_leaderboard()

    print("\n✅ Marketplace demo complete. The mesh learns. The mesh adapts.")


if __name__ == "__main__":
    main()
