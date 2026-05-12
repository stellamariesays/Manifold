"""
Agent registry integration for richer fog seam data.

The relay computes seams from capability-based fog (which agents claim what).
This module hooks into the Manifold agent registry to provide richer seam
data using actual agent blind spots and topology, not just declared capabilities.
"""

import json
import urllib.request
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .types import EventType, FogEvent, SeamShiftData


@dataclass
class AgentProfile:
    """Richer agent info from the registry."""
    name: str
    hub: str
    capabilities: List[str] = field(default_factory=list)
    seams: List[str] = field(default_factory=list)
    last_seen: Optional[str] = None
    blind_spots: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)

    @property
    def has_rich_data(self) -> bool:
        """True if this agent has more than just capability data."""
        return bool(self.blind_spots or self.seams)


class AgentRegistry:
    """
    Client for the Manifold agent registry.

    Supplements relay events with actual agent topology — blind spots,
    known domains, seam connections — for richer fog analysis.
    """

    def __init__(self, manifold_url: str = "http://localhost:8768"):
        self._base_url = manifold_url.rstrip("/")
        self._cache: Dict[str, AgentProfile] = {}

    def refresh(self) -> Dict[str, AgentProfile]:
        """
        Fetch current agent roster from Manifold REST API.
        Updates the internal cache.
        """
        try:
            req = urllib.request.Request(f"{self._base_url}/mesh")
            with urllib.request.urlopen(req, timeout=10) as resp:
                mesh_data = json.loads(resp.read())
        except Exception:
            return self._cache

        agents = mesh_data.get("agents", [])
        self._cache.clear()

        for agent_info in agents:
            profile = AgentProfile(
                name=agent_info.get("name", ""),
                hub=agent_info.get("hub", ""),
                capabilities=agent_info.get("capabilities", []),
                seams=agent_info.get("seams", []),
                last_seen=agent_info.get("lastSeen"),
                blind_spots=agent_info.get("blind_spots", []),
                domains=agent_info.get("domains", []),
            )
            self._cache[profile.name] = profile

        return self._cache

    def get_agent(self, name: str) -> Optional[AgentProfile]:
        """Look up an agent by name. Returns cached data."""
        return self._cache.get(name)

    def enrich_seam_event(self, event: FogEvent) -> Dict[str, Any]:
        """
        Enrich a seam.shift event with agent registry data.

        Returns a dict with:
        - original event data
        - agent profiles for both sides of the seam
        - combined blind spots
        - domain overlap
        """
        if event.type != EventType.SEAM_SHIFT:
            return {}

        data: SeamShiftData = event.data
        seam_parts = data.seam.split("↔")
        if len(seam_parts) != 2:
            return {"raw_seam": data.seam}

        agent_a_name, agent_b_name = seam_parts
        agent_a = self.get_agent(agent_a_name)
        agent_b = self.get_agent(agent_b_name)

        return {
            "seam": data.seam,
            "delta": data.delta,
            "direction": data.direction,
            "agent_a": {
                "name": agent_a_name,
                "capabilities": agent_a.capabilities if agent_a else [],
                "blind_spots": agent_a.blind_spots if agent_a else [],
                "domains": agent_a.domains if agent_a else [],
                "has_rich_data": agent_a.has_rich_data if agent_a else False,
            },
            "agent_b": {
                "name": agent_b_name,
                "capabilities": agent_b.capabilities if agent_b else [],
                "blind_spots": agent_b.blind_spots if agent_b else [],
                "domains": agent_b.domains if agent_b else [],
                "has_rich_data": agent_b.has_rich_data if agent_b else False,
            },
            "combined_blind_spots": list(set(
                (agent_a.blind_spots if agent_a else [])
                + (agent_b.blind_spots if agent_b else [])
            )),
            "domain_overlap": list(set(
                (agent_a.domains if agent_a else [])
            ) & set(
                (agent_b.domains if agent_b else [])
            )),
        }

    @property
    def agents(self) -> Dict[str, AgentProfile]:
        return dict(self._cache)
