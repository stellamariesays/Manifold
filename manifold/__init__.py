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

    from manifold import Agent

    agent = Agent(name="braid")
    agent.knows(["solar-topology", "AR-classification"])

    await agent.join()

    peers = await agent.seek("orbital-mechanics")
    await agent.think("multi-star-prediction")
"""

# Re-export core primitives for backward compatibility.
# Use relative imports so this package is self-contained when installed;
# absolute `from core import` fails in environments where the top-level
# `core` directory is not on sys.path (e.g. after `pip install -e .`).
from .agent import Agent
from .registry import AgentRef
from .blindspot import BlindSpot
from .chart import Chart
from .atlas import Atlas
from .sophia import SophiaReading, SophiaRegion
from .bleed import BleedReading, bleed_rate
from .substrate import SubstrateCoupling, substrate_coupling
from .bottleneck import BottleneckReading, bottleneck_topology
from .teacup import Teacup, TeacupStore
from .fog import FogMap, FogDelta, FogSeam, Gap, GapKind
from .glossolalia import GlossolaliaReading, GlossolaliaProbe
from .store import PersistentStore
from .persist import *

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
    "PersistentStore",
]
__version__ = "0.10.0"  # Bumped for architecture change
