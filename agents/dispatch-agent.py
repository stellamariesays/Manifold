#!/usr/bin/env python3
"""dispatch-agent — Intelligent task routing using audience-based dispatch.

Routes incoming tasks to the best-matched agent on the Manifold mesh using
multi-signal audience routing (capability, trust, focus, fog gap, topology).

Commands:
  status       — Show dispatcher status and stats
  route        — Route a task topic to the best agent
  history      — Show recent dispatch history
  distribution — Show task distribution across agents
"""

import json
import sys

from manifold.agent import Agent
from manifold.dispatch import TaskDispatcher, DispatchStatus


def _make_dispatcher():
    """Create a dispatcher bound to an in-memory agent with known mesh peers."""
    agent = Agent(name="dispatcher", transport="memory://dispatch")
    agent.knows(["task-routing", "audience-dispatch", "mesh-orchestration"])
    return agent, TaskDispatcher(agent, min_score=0.05)


def _populate_mesh(agent):
    """Populate the dispatcher's registry with known mesh agents."""
    peers = [
        {
            "name": "braid",
            "capabilities": [
                "solar-flare-prediction",
                "signal-processing",
                "lifecycle-modeling",
                "active-region-classification",
            ],
            "address": "memory://dispatch",
            "focus": "solar-flare-prediction",
        },
        {
            "name": "btc-signals",
            "capabilities": [
                "bitcoin-analysis",
                "technical-analysis",
                "breakout-detection",
                "signal-composition",
            ],
            "address": "memory://dispatch",
            "focus": "bitcoin-analysis",
        },
        {
            "name": "manifold",
            "capabilities": [
                "agent-topology",
                "atlas-building",
                "cognitive-mesh",
                "geodesic-routing",
            ],
            "address": "memory://dispatch",
            "focus": None,
        },
        {
            "name": "infra",
            "capabilities": [
                "system-administration",
                "deployment",
                "security-hardening",
                "monitoring",
            ],
            "address": "memory://dispatch",
            "focus": "monitoring",
        },
        {
            "name": "deploy",
            "capabilities": [
                "api-deployment",
                "manifest-generation",
                "multi-project-orchestration",
            ],
            "address": "memory://dispatch",
            "focus": None,
        },
    ]
    import asyncio

    for peer in peers:
        asyncio.get_event_loop().run_until_complete(
            agent._on_registry_announcement(peer)
        )


def cmd_status():
    agent, dispatcher = _make_dispatcher()
    _populate_mesh(agent)
    report = agent.audience("solar-flare-prediction")
    return {
        "agent": "dispatch",
        "status": "ok",
        "capabilities": [
            "task-routing",
            "audience-dispatch",
            "mesh-orchestration",
            "fallback-routing",
            "dispatch-history",
        ],
        "mesh_size": len(report.entries),
        "stats": dispatcher.stats(),
    }


def cmd_route():
    if len(sys.argv) < 3:
        return {"error": "usage: dispatch-agent route <topic>"}
    topic = sys.argv[2]
    agent, dispatcher = _make_dispatcher()
    _populate_mesh(agent)

    report = agent.audience(topic, min_score=0.0)
    result = {
        "topic": topic,
        "candidates": [
            {
                "name": e.name,
                "score": round(e.score, 3),
                "signals": [s.value for s in e.signals],
                "capabilities": e.capabilities,
            }
            for e in report.entries[:5]
        ],
        "total": report.total_candidates,
    }
    if report.entries:
        result["best_match"] = report.entries[0].name
    return result


def cmd_history():
    return {"agent": "dispatch", "history": [], "note": "History requires a running dispatch session"}


def cmd_distribution():
    return {"agent": "dispatch", "distribution": {}, "note": "Distribution requires a running dispatch session"}


COMMANDS = {
    "status": cmd_status,
    "ping": lambda: {"agent": "dispatch", "pong": True},
    "route": cmd_route,
    "history": cmd_history,
    "distribution": cmd_distribution,
}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in COMMANDS:
        print(json.dumps(COMMANDS[cmd](), indent=2))
    else:
        print(json.dumps({"agent": "dispatch", "error": f"unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
