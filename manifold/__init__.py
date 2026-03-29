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
from .teacup import Teacup, TeacupStore
from .fog import FogMap, FogDelta, FogSeam, Gap, GapKind

__all__ = [
    "Agent", "AgentRef", "BlindSpot", "Chart", "Atlas",
    "Claim", "Grade", "Stake", "TrustLedger",
    "SophiaReading", "SophiaRegion",
    "Teacup", "TeacupStore",
    "FogMap", "FogDelta", "FogSeam", "Gap", "GapKind",
]
__version__ = "0.8.0"
