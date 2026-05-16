"""Audience pipeline demo — composable routing with stages.

Shows how AudiencePipeline chains filters, boosts, limits, and splits
for production-grade message routing.

Run: python3 examples/audience_pipeline_demo.py
"""

from manifold.agent import Agent
from manifold.audience import Signal
from manifold.audience_pipeline import AudiencePipeline


def main():
    # Create a mesh with diverse agents
    agents = {}
    for name, caps, focus in [
        ("braid", ["solar-flare-prediction", "signal-processing", "lifecycle-modeling"], "solar flares"),
        ("btc-signals", ["bitcoin-analysis", "technical-analysis", "breakout-detection"], "bitcoin markets"),
        ("manifold", ["agent-topology", "atlas-building", "cognitive-mesh"], None),
        ("infra", ["system-administration", "deployment", "security-hardening", "monitoring"], "monitoring"),
        ("dispatch", ["task-routing", "audience-dispatch", "mesh-orchestration"], "task routing"),
    ]:
        a = Agent(name)
        a.knows(caps)
        agents[name] = a

    shared = agents["braid"]._registry
    for a in agents.values():
        a._registry = shared

    for name, a in agents.items():
        caps = a._capabilities
        focus_map = {n: f for n, _, f in [
            ("braid", [], "solar flares"),
            ("btc-signals", [], "bitcoin markets"),
            ("manifold", [], None),
            ("infra", [], "monitoring"),
            ("dispatch", [], "task routing"),
        ] if n == name}
        shared.register_self(name, caps, "local")
        if focus_map.get(name):
            shared._records[name].focus = focus_map[name]

    agents["braid"]._strong_peers = ["dispatch", "infra"]

    print("=" * 60)
    print("AUDIENCE PIPELINE DEMO")
    print("=" * 60)

    # 1. Basic pipeline
    print("\n📌 Basic pipeline — route 'solar flare prediction':")
    pipeline = AudiencePipeline(agents["braid"])
    report = pipeline.route("solar flare prediction")
    print(report.summary())

    # 2. Filtered — only agents with signal-processing
    print("\n📌 Filtered — only 'signal-processing' capable agents:")
    pipeline = AudiencePipeline(agents["braid"]).filter(
        lambda e: any("signal" in c.lower() for c in e.capabilities)
    )
    report = pipeline.route("signal analysis")
    print(report.summary())

    # 3. Boosted — prefer trusted agents
    print("\n📌 Boosted — prefer agents with trust signal:")
    pipeline = AudiencePipeline(agents["braid"]).boost(
        lambda e: e.name == "dispatch", factor=2.0, reason="preferred dispatcher"
    )
    report = pipeline.route("task assignment")
    print(report.summary())

    # 4. Chained pipeline with limit
    print("\n📌 Chained — filter + boost + limit(2):")
    pipeline = (
        AudiencePipeline(agents["braid"])
        .filter(lambda e: e.score > 0.0)
        .boost(lambda e: "solar" in " ".join(e.capabilities).lower(), factor=1.5)
        .limit(2)
    )
    report = pipeline.route("solar energy forecasting")
    print(report.summary())

    # 5. Split pipeline — primary vs fallback
    print("\n📌 Split — primary (score > 0.1) vs fallback:")
    pipeline = AudiencePipeline(agents["braid"]).split(
        "priority",
        {
            "primary": lambda e: e.score > 0.1,
            "fallback": lambda e: True,  # everything else
        },
    )
    report = pipeline.route("prediction")
    print(report.summary())

    # 6. Diversity pipeline
    print("\n📌 Diversity — ensure varied capabilities:")
    pipeline = AudiencePipeline(agents["braid"]).diversity(max_overlap=0.3, max_per_cluster=1)
    report = pipeline.route("analysis")
    print(report.summary())

    # 7. Require signal
    print("\n📌 Require CAPABILITY signal only:")
    pipeline = AudiencePipeline(agents["braid"]).require_signal(Signal.CAPABILITY)
    report = pipeline.route("monitoring")
    print(report.summary())

    print("\n" + "=" * 60)
    print("Demo complete.")


if __name__ == "__main__":
    main()
