"""
Manifold — cognitive mesh platform for AI agents.

Topology is epistemology. Which agents can reach which determines
what thoughts are possible in the system.

Architecture:
- core/          Pure mesh computation (agents, capabilities, transitions)
- visualization/ Rendering outputs (MRI scans, trust diagrams)
- federation/    Networking infrastructure (TypeScript/WebSocket)
- bridge/        Cross-language integration

Quick start::

    from manifold.core import Agent

    agent = Agent(name="braid")
    agent.knows(["solar-topology", "AR-classification"])

    await agent.join()

    peers = await agent.seek("orbital-mechanics")
    await agent.think("multi-star-prediction")
"""

# Re-export core primitives for backward compatibility
from core import (
    Agent, AgentRef, BlindSpot, Chart, Atlas,
    SophiaReading, SophiaRegion,
    BleedReading, bleed_rate,
    SubstrateCoupling, substrate_coupling,
    BottleneckReading, bottleneck_topology,
    Teacup, TeacupStore,
    FogMap, FogDelta, FogSeam, Gap, GapKind,
    GlossolaliaReading, GlossolaliaProbe,
)
from core.store import PersistentStore
from core.persist import *

# Re-export visualization for backward compatibility
from visualization import (
    Claim, Grade, Stake, TrustLedger,
    MRISnapshot, capture, generate_html,
)

__all__ = [
    "Agent", "AgentRef", "BlindSpot", "Chart", "Atlas",
    "Claim", "Grade", "Stake", "TrustLedger",
    "SophiaReading", "SophiaRegion",
    "BleedReading", "bleed_rate",
    "SubstrateCoupling", "substrate_coupling",
    "BottleneckReading", "bottleneck_topology",
    "Teacup", "TeacupStore",
    "FogMap", "FogDelta", "FogSeam", "Gap", "GapKind",
    "GlossolaliaReading", "GlossolaliaProbe",
    "MRISnapshot", "capture", "generate_html",
]
__version__ = "0.10.0"  # Bumped for architecture change
