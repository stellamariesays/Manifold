#!/usr/bin/env python3
"""
Manifold Mesh Health Monitor

Continuously monitors federation health: hub connectivity, agent liveness,
task throughput, and latency. Reports anomalies.

Can run standalone or as a federation agent.

Usage:
    python agents/mesh-health-agent.py [--interval 60] [--hub ws://localhost:8768]
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from dataclasses import dataclass, field

HUB_URL = "http://localhost:8768"


def _utcnow():
    return datetime.now(timezone.utc)


@dataclass
class HubHealth:
    name: str
    url: str
    reachable: bool = False
    latency_ms: float = 0.0
    agent_count: int = 0
    active_tasks: int = 0
    uptime_seconds: float = 0.0
    error: str = ""


@dataclass
class MeshHealthReport:
    timestamp: str = ""
    hubs: list = field(default_factory=list)
    total_agents: int = 0
    total_active_tasks: int = 0
    issues: list = field(default_factory=list)
    score: float = 0.0  # 0-100 overall health


def check_hub(url: str, timeout: float = 5.0) -> HubHealth:
    """Check a single hub's health."""
    health = HubHealth(name=url.split("//")[1].split(":")[0], url=url)
    start = time.monotonic()

    try:
        req = urllib.request.Request(f"{url}/api/status", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            health.latency_ms = (time.monotonic() - start) * 1000
            health.reachable = True
            health.agent_count = len(data.get("agents", []))
            health.active_tasks = data.get("active_tasks", 0)
            health.uptime_seconds = data.get("uptime_seconds", 0)
            health.name = data.get("hub", health.name)
    except urllib.error.ConnectionError:
        health.error = "Connection refused"
    except urllib.error.TimeoutError:
        health.error = "Timeout"
    except Exception as e:
        health.error = str(e)

    return health


def generate_report(hubs: list[str]) -> MeshHealthReport:
    """Generate a full mesh health report."""
    report = MeshHealthReport(timestamp=_utcnow().isoformat())

    for hub_url in hubs:
        hub_url_http = hub_url.replace("ws://", "http://").replace("wss://", "https://").rstrip("/")
        h = check_hub(hub_url_http)
        report.hubs.append(h)
        report.total_agents += h.agent_count
        report.total_active_tasks += h.active_tasks

        if not h.reachable:
            report.issues.append(f"🔴 Hub {h.name} unreachable: {h.error}")
        elif h.latency_ms > 1000:
            report.issues.append(f"🟡 Hub {h.name} slow: {h.latency_ms:.0f}ms")
        elif h.agent_count == 0:
            report.issues.append(f"🟡 Hub {h.name} has no agents")

    # Calculate health score
    if report.hubs:
        reachable = sum(1 for h in report.hubs if h.reachable)
        report.score = (reachable / len(report.hubs)) * 100
        # Bonus for agents
        report.score = min(100, report.score + report.total_agents * 2)
        # Penalty for issues
        report.score -= len(report.issues) * 5

    report.score = max(0, min(100, report.score))
    return report


def render_report(report: MeshHealthReport) -> str:
    """Render a terminal-friendly health report."""
    lines = []
    lines.append("╔══════════════════════════════════════════════════════╗")
    lines.append("║       MANIFOLD MESH HEALTH MONITOR                   ║")
    lines.append(f"║  {report.timestamp[:19]}                        ║")
    lines.append("╠══════════════════════════════════════════════════════╣")

    # Overall score
    if report.score >= 90:
        status_icon = "🟢"
    elif report.score >= 60:
        status_icon = "🟡"
    else:
        status_icon = "🔴"

    lines.append(f"║  Overall Health: {status_icon} {report.score:.0f}/100")
    lines.append(f"║  Hubs: {len(report.hubs)}  Agents: {report.total_agents}  Tasks: {report.total_active_tasks}")
    lines.append("╠══════════════════════════════════════════════════════╣")

    for h in report.hubs:
        icon = "🟢" if h.reachable else "🔴"
        lines.append(f"║  {icon} {h.name}")
        if h.reachable:
            lines.append(f"║     Latency: {h.latency_ms:.0f}ms  Agents: {h.agent_count}  Tasks: {h.active_tasks}")
        else:
            lines.append(f"║     Error: {h.error}")

    if report.issues:
        lines.append("╠══════════════════════════════════════════════════════╣")
        lines.append("║  ISSUES:")
        for issue in report.issues:
            lines.append(f"║  {issue}")

    lines.append("╚══════════════════════════════════════════════════════╝")
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Manifold Mesh Health Monitor")
    parser.add_argument("--hub", default="ws://localhost:8768", help="Hub URL")
    parser.add_argument("--interval", type=int, default=0, help="Repeat interval (0=once)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    hubs = [args.hub]

    while True:
        report = generate_report(hubs)

        if args.json:
            out = {
                "timestamp": report.timestamp,
                "score": report.score,
                "total_agents": report.total_agents,
                "total_active_tasks": report.total_active_tasks,
                "hubs": [
                    {
                        "name": h.name,
                        "reachable": h.reachable,
                        "latency_ms": h.latency_ms,
                        "agent_count": h.agent_count,
                        "active_tasks": h.active_tasks,
                        "error": h.error,
                    }
                    for h in report.hubs
                ],
                "issues": report.issues,
            }
            print(json.dumps(out, indent=2))
        else:
            print(render_report(report))

        if args.interval <= 0:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
