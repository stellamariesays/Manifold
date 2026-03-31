"""
MRI demo — generates a full diagnostic page for a three-agent cognitive mesh.

Creates agents: braid, stella, fog-mapper.

  braid       — mesh topology, coordination dynamics, emergence modelling
  stella      — coordination strategy, agent orchestration, mesh navigation
  fog-mapper  — topology gaps, blind-spot detection, uncertainty mapping

Vocabularies are crafted for rich overlap so all visual features appear:

  * transition map edges (braid↔stella, braid↔fog-mapper, stella↔fog-mapper)
  * Sophia heat regions at contested vocabulary (emergence, coordination, topology)
  * Bottleneck indicator on the highest-constraint node
  * Glossolalia sidebar from a braid/stella suppression probe
  * Fog gap zones from topics covered by only one agent

Run::

    python scripts/mri_demo.py
"""

from pathlib import Path

from manifold.atlas import Atlas
from manifold.registry import CapabilityRegistry
from manifold.mri import capture, generate_html

OUTPUT = Path(__file__).parent / "mri_output.html"


def _make_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()

    # braid — mesh topology specialist; shares 'coordination', 'dynamics',
    # 'emergence', 'topology', 'mesh', 'modeling' with others
    reg.register_self(
        name="braid",
        capabilities=[
            "mesh-theory",
            "topology-analysis",
            "coordination-dynamics",
            "pattern-recognition",
            "signal-processing",
            "curvature-detection",
            "emergence-modeling",
            "transition-mapping",
            "quantum-substrate-theory",   # unique → becomes a hole
        ],
        address="mem://braid",
    )

    # stella — conversational/strategy layer; shares 'coordination', 'dynamics',
    # 'emergence', 'topology', 'mesh', 'modeling', 'analysis' with others
    reg.register_self(
        name="stella",
        capabilities=[
            "coordination-strategy",
            "dynamics-modeling",
            "agent-orchestration",
            "mesh-navigation",
            "emergence-monitoring",
            "context-modeling",
            "conversational-topology",
            "seam-analysis",
            "deep-semantic-routing",     # unique → becomes a hole
        ],
        address="mem://stella",
    )

    # fog-mapper — gap & blind-spot specialist; shares 'topology', 'emergence',
    # 'pattern', 'analysis', 'modeling' with others
    reg.register_self(
        name="fog-mapper",
        capabilities=[
            "topology-gaps",
            "pattern-voids",
            "uncertainty-mapping",
            "blind-spot-detection",
            "fog-analysis",
            "knowledge-boundaries",
            "emergence-signals",
            "void-detection",
            "liminal-cartography",       # unique → becomes a hole
        ],
        address="mem://fog-mapper",
    )

    return reg


def main() -> None:
    reg = _make_registry()
    atlas = Atlas.build(reg)

    snapshot = capture(
        atlas,
        agent_a="braid",
        agent_b="stella",
        coordination_pressure=0.0,   # full suppression → tongues mode
    )

    html = generate_html(snapshot)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"MRI generated → {OUTPUT}")


if __name__ == "__main__":
    main()
