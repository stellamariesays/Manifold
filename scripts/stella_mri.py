"""
stella_mri.py — real memory-backed MRI for Stella's cognitive terrain.

Registers the actual active project domains on Trillian's mesh and generates
a full Manifold MRI diagnostic page for manifold.surge.sh.

Run from repo root::

    python3 scripts/stella_mri.py
"""

from pathlib import Path

from manifold.atlas import Atlas
from manifold.registry import CapabilityRegistry
from manifold.mri import capture, generate_html

OUTPUT = Path(__file__).parent / "stella_mri.html"


def _make_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()

    # stella — meta-agent: identity, conversation, judgment
    reg.register_self(
        name="stella",
        capabilities=[
            "identity-continuity",
            "session-memory",
            "conversation-strategy",
            "judgment",
            "personality-coherence",
            "context-management",
            "agent-orchestration",
            "terrain-awareness",
            "trust-modeling",
        ],
        address="mem://stella",
    )

    # braid — solar prediction, space weather
    reg.register_self(
        name="braid",
        capabilities=[
            "solar-flare-prediction",
            "active-region-classification",
            "space-weather",
            "signal-processing",
            "machine-learning",
            "alfven-wave-timing",
            "lifecycle-modeling",
            "SWPC-data",
            "time-series-analysis",
            "false-alarm-reduction",
            "solar-memory-state-machine",
        ],
        address="mem://braid",
    )

    # manifold — cognitive mesh architecture
    reg.register_self(
        name="manifold",
        capabilities=[
            "mesh-topology",
            "seam-emergence",
            "sophia-scoring",
            "agent-coordination",
            "transition-mapping",
            "epistemic-fog",
            "glossolalia-coordination",
            "curvature-detection",
            "knowledge-boundaries",
            "distributed-cognition",
            "teacup-moments",
            "bottleneck-analysis",
        ],
        address="mem://manifold",
    )

    # argue — argumentation markets, debate
    reg.register_self(
        name="argue",
        capabilities=[
            "argumentation-strategy",
            "debate-tactics",
            "token-economics",
            "blockchain-interaction",
            "position-management",
            "reasoning-quality",
            "jury-evaluation",
            "agent-consciousness",
            "bet-management",
        ],
        address="mem://argue",
    )

    # infra — architecture, infrastructure
    reg.register_self(
        name="infra",
        capabilities=[
            "openclaw-config",
            "groq-migration",
            "cron-management",
            "provider-routing",
            "session-management",
            "system-architecture",
            "deployment-pipeline",
            "security-hardening",
            "agent-identity",
            "context-handoff",
        ],
        address="mem://infra",
    )

    # solar-sites — visualization, deployment
    reg.register_self(
        name="solar-sites",
        capabilities=[
            "surge-deployment",
            "solarsphere-visualization",
            "globe-rendering",
            "braid-metrics-display",
            "solar-data-pipeline",
            "web-visualization",
            "particle-physics-sim",
            "flare-animation",
            "HOG-cron-deploy",
        ],
        address="mem://solar-sites",
    )

    # wake — fine-tuning pipeline (PARKED)
    reg.register_self(
        name="wake",
        capabilities=[
            "model-fine-tuning",
            "training-data",
            "stella-personalization",
            "runpod-compute",
            "docker-pipeline",
            "conversation-pairs",
        ],
        address="mem://wake",
    )

    return reg


def main() -> None:
    reg = _make_registry()
    atlas = Atlas.build(reg)

    snapshot = capture(
        atlas,
        agent_a="stella",
        agent_b="manifold",
        coordination_pressure=0.0,
    )

    html = generate_html(snapshot)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"Stella MRI generated → {OUTPUT}")


if __name__ == "__main__":
    main()
