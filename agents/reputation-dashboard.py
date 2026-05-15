#!/usr/bin/env python3
"""
Manifold Agent Reputation Dashboard

Live trust scores, grade history, and agent performance metrics.
Pulls from the mesh trust ledger and renders a terminal-friendly report.

Usage:
    python agents/reputation-dashboard.py [--hub ws://localhost:8768]
"""

import json
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

# If running standalone, we need core on the path
sys.path.insert(0, ".")

try:
    from manifold.trust import TrustLedger, Grade, Stake, Claim
except ImportError:
    # Fallback — maybe already consolidated
    from manifold import TrustLedger, Grade, Stake, Claim


def _utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fetch_mesh_status(hub_url="http://localhost:8768"):
    """Try to get live mesh state from the federation hub."""
    try:
        req = urllib.request.Request(f"{hub_url}/api/status", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def build_ledger_from_status(status):
    """Build a TrustLedger from live mesh status data."""
    ledger = TrustLedger()
    if not status or "agents" not in status:
        return ledger

    for agent_info in status.get("agents", []):
        name = agent_info.get("name", "unknown")
        caps = agent_info.get("capabilities", [])
        # Create synthetic grades from capability breadth
        for cap in caps:
            ledger.record(Grade(
                agent=name,
                domain=cap,
                score=0.7 + min(len(caps) * 0.03, 0.25),
                task_id=f"mesh-{name}-{cap}",
            ))
    return ledger


def render_dashboard(ledger, mesh_status=None):
    """Render a terminal reputation dashboard."""
    width = 60
    print("╔" + "═" * width + "╗")
    print("║" + " MANIFOLD AGENT REPUTATION DASHBOARD ".center(width) + "║")
    print("║" + f" {_utcnow()} ".center(width) + "║")
    print("╠" + "═" * width + "╣")

    # Collect all grades from internal records
    all_grades = []
    for agent, domains in ledger._records.items():
        for domain, rec in domains.items():
            for g in rec.grades:
                all_grades.append(g)

    agent_scores = defaultdict(list)
    for grade in all_grades:
        agent_scores[grade.agent].append(grade)

    if not agent_scores:
        print("║" + " No grade data available ".center(width) + "║")
        if mesh_status:
            print("║" + f" Hub: {mesh_status.get('hub', '?')} ".center(width) + "║")
        print("╚" + "═" * width + "╝")
        return

    # Sort by average score
    ranked = []
    for agent, grades in agent_scores.items():
        avg = sum(g.score for g in grades) / len(grades)
        domains = len(set(g.domain for g in grades))
        ranked.append((agent, avg, domains, len(grades)))
    ranked.sort(key=lambda x: -x[1])

    print("║" + " AGENT              SCORE   DOMAINS  GRADES ".ljust(width) + "║")
    print("║" + "─" * width + "║")

    for agent, avg, domains, count in ranked[:15]:
        bar_len = int(avg * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        line = f" {agent:<18} {avg:.2f}   {domains:>3}      {count:>3}  {bar}"
        print("║" + line[:width] + "║")

    # Top domains
    print("╠" + "═" * width + "╣")
    print("║" + " DOMAIN COVERAGE ".center(width) + "║")
    print("║" + "─" * width + "║")

    domain_agents = defaultdict(set)
    for grade in all_grades:
        domain_agents[grade.domain].add(grade.agent)

    for domain in sorted(domain_agents.keys(),
                         key=lambda d: -len(domain_agents[d]))[:10]:
        agents = domain_agents[domain]
        line = f" {domain:<30} {len(agents)} agent(s)"
        print("║" + line[:width] + "║")

    # Trust network summary
    print("╠" + "═" * width + "╣")
    print("║" + " MESH SUMMARY ".center(width) + "║")
    print("║" + "─" * width + "║")

    total_agents = len(agent_scores)
    total_grades = sum(len(g) for g in agent_scores.values())
    total_domains = len(set(g.domain for g in all_grades))
    avg_trust = sum(x[1] for x in ranked) / len(ranked) if ranked else 0

    print(f"║ Agents: {total_agents:<8} Grades: {total_grades:<8} Domains: {total_domains}".ljust(width + 1) + "║")
    print(f"║ Avg Trust Score: {avg_trust:.3f}".ljust(width + 1) + "║")

    # Stakes — check if any agent records have stake data
    has_stakes = False
    total_stake = 0.0
    for agent, domains in ledger._records.items():
        for domain, rec in domains.items():
            if rec.stake_total > 0:
                has_stakes = True
                total_stake += rec.stake_total

    if has_stakes:
        print(f"║ Total Staked: {total_stake}".ljust(width + 1) + "║")

    print("╚" + "═" * width + "╝")


def main():
    hub_url = "http://localhost:8768"
    if len(sys.argv) > 1:
        hub_url = sys.argv[1].replace("ws://", "http://").rstrip("/")

    # Try live data first
    mesh_status = fetch_mesh_status(hub_url)

    # Build a demo ledger if no live data
    if mesh_status and "agents" in mesh_status:
        ledger = build_ledger_from_status(mesh_status)
    else:
        # Demo data
        ledger = TrustLedger()
        demo_agents = {
            "stella": [("identity", 0.95), ("health-check", 0.88), ("memory", 0.92)],
            "braid": [("solar-flare", 0.91), ("AR-classification", 0.85)],
            "manifold": [("mesh-topology", 0.93), ("routing", 0.87)],
            "btc-signals": [("technical-analysis", 0.82), ("price-monitoring", 0.79)],
            "btc-settlement": [("escrow", 0.90), ("trust-scoring", 0.88)],
            "infra": [("system-info", 0.95), ("monitoring", 0.91)],
            "wake": [("notifications", 0.87), ("alerts", 0.84)],
        }
        for agent, domains in demo_agents.items():
            for domain, score in domains:
                ledger.record(Grade(agent=agent, domain=domain, score=score, task_id=f"demo-{agent}-{domain}"))

    render_dashboard(ledger, mesh_status)


if __name__ == "__main__":
    main()
