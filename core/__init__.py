"""
Manifold Core — mesh topology and computation.

Pure mesh primitives: agents, capabilities, transitions, curvature.
"""

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
from .topology import *
from .transition import *
from .semantic import *
from .store import *
from .persist import *

__all__ = [
    "Agent", "AgentRef", "BlindSpot", "Chart", "Atlas",
    "SophiaReading", "SophiaRegion",
    "BleedReading", "bleed_rate",
    "SubstrateCoupling", "substrate_coupling",
    "BottleneckReading", "bottleneck_topology",
    "Teacup", "TeacupStore",
    "FogMap", "FogDelta", "FogSeam", "Gap", "GapKind",
    "GlossolaliaReading", "GlossolaliaProbe",
]
