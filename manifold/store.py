"""
PersistentStore — save and load the capability registry between sessions.

The atlas is rebuilt from the registry on every session start. The registry
is the durable part: who is on the mesh, what they know, where they are.

Usage::

    from manifold.store import PersistentStore

    # Load at session start
    reg = PersistentStore.load("data/manifold/stella-atlas.json")

    # ... register current session capabilities ...
    reg.register_self("stella", [...], "mem://stella")

    # Build atlas, run scan, do work ...

    # Save at session end (merge: new registration wins for same name)
    PersistentStore.save("data/manifold/stella-atlas.json", reg)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .registry import CapabilityRegistry


class PersistentStore:
    """
    File-backed persistence for the CapabilityRegistry.

    JSON format::

        {
            "agents": [
                {
                    "name": "stella",
                    "capabilities": ["identity-continuity", ...],
                    "address": "mem://stella",
                    "focus": null
                }
            ],
            "saved_at": "2026-03-31T05:33:00+00:00",
            "version": 1
        }
    """

    VERSION = 1

    @staticmethod
    def load(path: str | Path) -> CapabilityRegistry:
        """
        Load a CapabilityRegistry from disk.

        Returns an empty registry if the file doesn't exist yet.
        """
        p = Path(path)
        reg = CapabilityRegistry()

        if not p.exists():
            return reg

        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return reg

        for agent in data.get("agents", []):
            name = agent.get("name")
            caps = agent.get("capabilities", [])
            address = agent.get("address", f"store://{name}")
            if name:
                reg.register_self(name, caps, address)
                # Re-apply focus if present
                if agent.get("focus") and name in reg._records:
                    reg._records[name].focus = agent["focus"]

        return reg

    @staticmethod
    def save(path: str | Path, registry: CapabilityRegistry, dark_circles: list | None = None) -> None:
        """
        Save a CapabilityRegistry to disk.

        Creates parent directories as needed.
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        agents = []
        for record in registry.all_agents():
            agents.append({
                "name": record.name,
                "capabilities": record.capabilities,
                "address": record.address,
                "focus": record.focus,
            })

        data = {
            "agents": agents,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "version": PersistentStore.VERSION,
        }

        if dark_circles:
            data["dark_circles"] = dark_circles

        p.write_text(json.dumps(data, indent=2))

    @staticmethod
    def merge(
        path: str | Path,
        registry: CapabilityRegistry,
        prefer_new: bool = True,
    ) -> CapabilityRegistry:
        """
        Load existing store, merge with the given registry, save, and return.

        When ``prefer_new=True`` (default), the passed registry wins on conflicts.
        When ``prefer_new=False``, the stored version of an agent wins.

        Use this at session start to accumulate capability drift over time::

            # Fresh capabilities declared in code
            reg = CapabilityRegistry()
            reg.register_self("stella", current_caps, "mem://stella")

            # Merge with what was known last session — grows the mesh over time
            reg = PersistentStore.merge("data/manifold/stella-atlas.json", reg)
        """
        stored = PersistentStore.load(path)

        merged = CapabilityRegistry()

        if prefer_new:
            # Start from stored, overwrite with new
            for record in stored.all_agents():
                merged.register_self(record.name, record.capabilities, record.address)
                if record.focus and record.name in merged._records:
                    merged._records[record.name].focus = record.focus
            for record in registry.all_agents():
                merged.register_self(record.name, record.capabilities, record.address)
                if record.focus and record.name in merged._records:
                    merged._records[record.name].focus = record.focus
        else:
            # Start from new, overwrite with stored (stored wins)
            for record in registry.all_agents():
                merged.register_self(record.name, record.capabilities, record.address)
            for record in stored.all_agents():
                merged.register_self(record.name, record.capabilities, record.address)

        PersistentStore.save(path, merged, dark_circles=PersistentStore._load_dark_circles(path))
        return merged

    @staticmethod
    def _load_dark_circles(path):
        """Extract dark_circles from existing store file."""
        p = Path(path)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            return data.get("dark_circles")
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def summary(path: str | Path) -> dict:
        """
        Quick summary of what's in a store file (without building an Atlas).

        Returns::

            {
                "agents": ["stella", "braid", ...],
                "count": 7,
                "saved_at": "2026-03-31T05:33:00+00:00"
            }
        """
        p = Path(path)
        if not p.exists():
            return {"agents": [], "count": 0, "saved_at": None}

        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return {"agents": [], "count": 0, "saved_at": None, "error": "parse error"}

        agents = [a["name"] for a in data.get("agents", []) if a.get("name")]
        return {
            "agents": agents,
            "count": len(agents),
            "saved_at": data.get("saved_at"),
        }
