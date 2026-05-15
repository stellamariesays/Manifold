"""Capability graph — routing and discovery through capability relationships."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class CapabilityGraph:
    """Directed graph linking agents to capabilities and capabilities to each other."""

    def __init__(self):
        # agent -> set of capabilities
        self._agent_caps: dict[str, set[str]] = defaultdict(set)
        # capability -> set of agents providing it
        self._cap_agents: dict[str, set[str]] = defaultdict(set)
        # capability -> set of related capabilities (directed edges)
        self._cap_edges: dict[str, set[str]] = defaultdict(set)

    def add_capability(self, agent_id: str, capability: str) -> None:
        self._agent_caps[agent_id].add(capability)
        self._cap_agents[capability].add(agent_id)

    def add_relation(self, from_cap: str, to_cap: str) -> None:
        """Add a directed edge between capabilities."""
        self._cap_edges[from_cap].add(to_cap)

    def get_providers(self, capability: str) -> list[str]:
        return sorted(self._cap_agents.get(capability, set()))

    def get_agent_capabilities(self, agent_id: str) -> list[str]:
        return sorted(self._agent_caps.get(agent_id, set()))

    def find_path(self, from_cap: str, to_cap: str) -> list[str]:
        """BFS through capability relations to find a path."""
        if from_cap == to_cap:
            return [from_cap]
        visited = {from_cap}
        queue = deque([(from_cap, [from_cap])])
        while queue:
            current, path = queue.popleft()
            for neighbor in self._cap_edges.get(current, set()):
                if neighbor == to_cap:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return []

    def get_reachable(self, agent_id: str) -> set[str]:
        """All capabilities reachable from an agent (own + via relations)."""
        result = set()
        for cap in self._agent_caps.get(agent_id, set()):
            result.add(cap)
            # BFS from each capability
            visited = {cap}
            queue = deque([cap])
            while queue:
                current = queue.popleft()
                for neighbor in self._cap_edges.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        result.add(neighbor)
                        queue.append(neighbor)
        return result

    def shortest_path(self, agent_a: str, agent_b: str) -> list[str]:
        """BFS between agents through shared capabilities. Returns agent capability chain."""
        start_caps = self._agent_caps.get(agent_a, set())
        target_caps = self._agent_caps.get(agent_b, set())
        if not start_caps or not target_caps:
            return []

        # Check direct overlap
        overlap = start_caps & target_caps
        if overlap:
            return [agent_a, agent_b]

        # BFS: agent -> cap -> agent -> cap ...
        visited_agents = {agent_a}
        visited_caps: set[str] = set()
        # queue holds (current_agent, path_of_agents)
        queue = deque([(agent_a, [agent_a])])

        while queue:
            current_agent, path = queue.popleft()
            for cap in self._agent_caps.get(current_agent, set()):
                if cap in visited_caps:
                    continue
                visited_caps.add(cap)
                # Also explore related capabilities
                all_caps = {cap}
                bfs_q = deque([cap])
                while bfs_q:
                    c = bfs_q.popleft()
                    for related in self._cap_edges.get(c, set()):
                        if related not in all_caps:
                            all_caps.add(related)
                            bfs_q.append(related)

                for c in all_caps:
                    for next_agent in self._cap_agents.get(c, set()):
                        if next_agent in visited_agents:
                            continue
                        new_path = path + [next_agent]
                        if next_agent == agent_b:
                            return new_path
                        visited_agents.add(next_agent)
                        queue.append((next_agent, new_path))
        return []

    def subgraph(self, capabilities: set[str]) -> CapabilityGraph:
        """Extract a subgraph containing only the specified capabilities."""
        g = CapabilityGraph()
        for cap in capabilities:
            for agent in self._cap_agents.get(cap, set()):
                g.add_capability(agent, cap)
            for related in self._cap_edges.get(cap, set()):
                if related in capabilities:
                    g.add_relation(cap, related)
        return g

    def to_dict(self) -> dict:
        return {
            "agent_caps": {a: sorted(caps) for a, caps in self._agent_caps.items()},
            "cap_edges": {c: sorted(e) for c, e in self._cap_edges.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> CapabilityGraph:
        g = cls()
        for agent, caps in data.get("agent_caps", {}).items():
            for cap in caps:
                g.add_capability(agent, cap)
        for cap, edges in data.get("cap_edges", {}).items():
            for e in edges:
                g.add_relation(cap, e)
        return g

    @property
    def agent_count(self) -> int:
        return len(self._agent_caps)

    @property
    def capability_count(self) -> int:
        return len(self._cap_agents)
