from .base import Transport
from .memory import MemoryTransport

# SubwayTransport is optional — only available with Subway mesh access.
# Import it explicitly if you need it: from manifold.bridge.subway import SubwayTransport
try:
    from .subway import SubwayTransport
    _SUBWAY_AVAILABLE = True
except ImportError:
    _SUBWAY_AVAILABLE = False

__all__ = ["Transport", "MemoryTransport"]
