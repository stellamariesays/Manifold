"""
Manifold — cognitive mesh layer for AI agents.

Topology is epistemology. Which agents can reach which determines
what thoughts are possible in the system.

Quick start::

    from manifold import Agent

    agent = Agent(name="braid")
    agent.knows(["solar-topology", "AR-classification"])

    await agent.join()

    peers = await agent.seek("orbital-mechanics")
    await agent.think("multi-star-prediction")
"""

from .agent import Agent
from .registry import AgentRef
from .blindspot import BlindSpot
from .chart import Chart
from .atlas import Atlas
from .trust import Claim, Grade, Stake, TrustLedger
from .sophia import SophiaReading, SophiaRegion
from .bleed import BleedReading, bleed_rate
from .substrate import SubstrateCoupling, substrate_coupling
from .bottleneck import BottleneckReading, bottleneck_topology
from .teacup import Teacup, TeacupStore
from .fog import FogMap, FogDelta, FogSeam, Gap, GapKind
from .glossolalia import GlossolaliaReading, GlossolaliaProbe
from .mri import MRISnapshot, capture, generate_html

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
__version__ = "0.9.0"
