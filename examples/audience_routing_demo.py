"""Audience routing demo — message targeting with multi-signal blending.

Shows how AudienceRouter blends capability match, focus, trust, fog gap,
and topology signals to find the right audience for any topic.

Run: python3 examples/audience_routing_demo.py
"""

from manifold.agent import Agent
from manifold.audience import AudienceRouter


def main():
    # Create a mesh with diverse agents
    alice = Agent("alice")
    alice.knows(["solar-prediction", "weather-forecast"])
    bob = Agent("bob")
    bob.knows(["battery-optimization", "grid-balancing"])
    carol = Agent("carol")
    carol.knows(["solar-prediction", "panel-diagnostics"])
    dave = Agent("dave")
    dave.knows(["nlp-sentiment", "text-summarization"])

    # Share a single registry across all agents
    shared_registry = alice._registry
    for a in [bob, carol, dave]:
        a._registry = shared_registry

    # Register all agents
    for a in [alice, bob, carol, dave]:
        shared_registry.register_self(a._name, a._capabilities, getattr(a, '_address', 'local'))

    # Set focus for some agents (what they're currently working on)
    alice._registry._records["alice"].focus = "solar energy forecasting"
    bob._registry._records["bob"].focus = "grid load management"
    carol._registry._records["carol"].focus = "solar panel maintenance"

    # Wire up topology (strong peers)
    alice._strong_peers = ["carol", "bob"]

    # Route from alice's perspective
    router = AudienceRouter(alice)

    print("=" * 60)
    print("AUDIENCE ROUTING DEMO")
    print("=" * 60)

    # Route for a solar topic — expect carol and bob to score high
    print("\n📡 Routing for 'solar energy prediction':")
    report = router.route("solar energy prediction")
    print(report.summary())

    # Route for grid management
    print("\n📡 Routing for 'grid load balancing':")
    report = router.route("grid load balancing")
    print(report.summary())

    # Route for NLP task — dave should match
    print("\n📡 Routing for 'text sentiment analysis':")
    report = router.route("text sentiment analysis")
    print(report.summary())

    # With min_score threshold
    print("\n📡 Routing for 'solar panels' (min_score=0.1):")
    report = router.route("solar panels", min_score=0.1)
    print(report.summary())
    print(f"  Excluded: {report.excluded}")

    # Custom weights — prioritize trust
    print("\n📡 Routing with trust-heavy weights:")
    trust_router = AudienceRouter(alice, weights={
        "capability": 0.10,
        "focus": 0.10,
        "trust": 0.60,
        "fog_gap": 0.10,
        "topology": 0.10,
    })
    report = trust_router.route("solar energy")
    print(report.summary())

    # Show top-N
    print("\n📡 Top 2 for 'energy forecasting':")
    report = router.route("energy forecasting", max_results=2)
    for entry in report.top(2):
        print(f"  {entry}")

    print("\n" + "=" * 60)
    print(f"Total agents in mesh: {len(alice._registry._records)}")
    print("Demo complete.")


if __name__ == "__main__":
    main()
