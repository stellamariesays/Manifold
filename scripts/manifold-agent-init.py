#!/usr/bin/env python3
"""
manifold-agent-init.py — Manifold session initialiser for Stella.

Run at session start to:
  1. Load the persistent atlas (accumulated over sessions)
  2. Register current capabilities (may have drifted since last run)
  3. Build Atlas + surface hot topology
  4. Run reach_scan → implied regions (dark circles)
  5. Open Numinous Voids for those regions (if numinous available)
  6. Save updated registry back to disk

Output goes to stdout — intended to be read by the session bootstrap
or piped into a notification.

Usage::

    python3 scripts/manifold-agent-init.py
    python3 scripts/manifold-agent-init.py --json          # machine-readable
    python3 scripts/manifold-agent-init.py --no-voids      # skip Elixir step
    python3 scripts/manifold-agent-init.py --store PATH    # custom store path
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# ── Path bootstrap ────────────────────────────────────────────────────────────
_REPO = Path(__file__).parent.parent
_WORKSPACE = _REPO.parent.parent  # .openclaw/workspace
sys.path.insert(0, str(_REPO))

_NUMINOUS = _WORKSPACE / "projects" / "numinous"
_NUMINOUS_AVAILABLE = False
if _NUMINOUS.exists():
    sys.path.insert(0, str(_NUMINOUS))
    try:
        from numinous.reach import reach_scan  # type: ignore
        from numinous.bridge import open_from_atlas  # type: ignore
        _NUMINOUS_AVAILABLE = True
    except ImportError:
        pass

from manifold.atlas import Atlas
from manifold.registry import CapabilityRegistry
from manifold.store import PersistentStore

# ── Store path ────────────────────────────────────────────────────────────────
_DEFAULT_STORE = _WORKSPACE / "data" / "manifold" / "stella-atlas.json"


# ── Agent definitions ─────────────────────────────────────────────────────────
# These are the actual domain agents on the mesh.
# Update here when capabilities shift.
_AGENTS = [
    {
        "name": "stella",
        "capabilities": [
            "identity-continuity",
            "session-memory",
            "conversation-strategy",
            "judgment",
            "personality-coherence",
            "context-management",
            "agent-orchestration",
            "terrain-awareness",
            "trust-modeling",
            "identity-modeling",
        ],
        "address": "mem://stella",
        "focus": "agent-identity",
    },
    {
        "name": "braid",
        "capabilities": [
            "solar-flare-prediction",
            "active-region-classification",
            "space-weather",
            "signal-processing",
            "machine-learning",
            "alfven-wave-timing",
            "alfven-clock",
            "lifecycle-modeling",
            "lifecycle-deployment",
        ],
        "address": "mem://braid",
        "focus": "solar-prediction",
    },
    {
        "name": "manifold",
        "capabilities": [
            "cognitive-mesh",
            "agent-topology",
            "seam-detection",
            "sophia-score",
            "atlas-building",
            "transition-maps",
            "geodesic-routing",
        ],
        "address": "mem://manifold",
        "focus": "mesh-topology",
    },
    {
        "name": "argue",
        "capabilities": [
            "argumentation",
            "debate-strategy",
            "jury-modeling",
            "token-staking",
            "on-chain-interaction",
            "rhetorical-structure",
        ],
        "address": "mem://argue",
        "focus": "debate",
    },
    {
        "name": "infra",
        "capabilities": [
            "system-administration",
            "cron-management",
            "deployment",
            "git-workflow",
            "security-hardening",
            "ssh-management",
        ],
        "address": "mem://infra",
        "focus": "operations",
    },
    {
        "name": "solar-sites",
        "capabilities": [
            "web-deployment",
            "d3-visualization",
            "solar-data-display",
            "surge-deployment",
            "javascript-frontend",
            "realtime-dashboard",
        ],
        "address": "mem://solar-sites",
        "focus": "visualization",
    },
    {
        "name": "wake",
        "capabilities": [
            "fine-tuning",
            "training-data",
            "local-model",
            "identity-alignment",
            "runpod-compute",
            "elixir-process",
        ],
        "address": "mem://wake",
        "focus": "model-training",
    },
]


def _build_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for a in _AGENTS:
        reg.register_self(a["name"], a["capabilities"], a["address"])
        if a.get("focus") and a["name"] in reg._records:
            reg._records[a["name"]].focus = a["focus"]
    return reg


def _format_human(result: dict) -> str:
    lines = ["── Manifold Session Init ─────────────────────────────────"]

    lines.append(f"\n  Agents on mesh: {result['agent_count']}")
    lines.append(f"  Transition maps: {result['map_count']}")
    lines.append(f"  Structural holes: {result['hole_count']}")

    if result["bottlenecks"]:
        lines.append("\n  High-curvature regions (seams to watch):")
        for b in result["bottlenecks"]:
            lines.append(f"    · {b['region']}  κ={b['curvature']:.3f}")

    if result["implied_regions"]:
        lines.append("\n  Implied but unclaimed regions (dark circles):")
        for r in result["implied_regions"]:
            implied_str = ", ".join(r["implied_by"][:3])
            lines.append(
                f"    · {r['term']}  p={r['strength']:.2f}  "
                f"← {implied_str}"
            )

    if result.get("voids_opened"):
        lines.append(f"\n  Numinous Voids opened: {len(result['voids_opened'])}")
        for v in result["voids_opened"][:5]:
            lines.append(f"    · {v['term']} p={v['pressure']:.2f}")

    if result.get("store_path"):
        lines.append(f"\n  Store: {result['store_path']}")

    lines.append("\n──────────────────────────────────────────────────────")
    return "\n".join(lines)


def run(store_path: Path, open_voids: bool = True, json_output: bool = False) -> dict:
    t0 = time.monotonic()

    # 1. Build current registry
    current_reg = _build_registry()

    # 2. Merge with persistent store (current caps win)
    reg = PersistentStore.merge(store_path, current_reg, prefer_new=True)

    # 3. Build Atlas
    atlas = Atlas.build(reg)

    # 4. High-curvature regions (bottleneck seams)
    bottlenecks = [
        {"region": region, "curvature": score}
        for region, score in atlas.high_curvature_regions(top_n=5)
        if score > 0.1
    ]

    # 5. Implied regions via reach_scan
    implied_regions = []
    if _NUMINOUS_AVAILABLE:
        reading = reach_scan(atlas, top_n=8)
        implied_regions = [
            {
                "term": r.term,
                "strength": round(r.strength, 3),
                "implied_by": r.implied_by,
            }
            for r in reading.candidate_regions
        ]

    # 6. Open Numinous Voids
    voids_opened = []
    if open_voids and _NUMINOUS_AVAILABLE and implied_regions:
        try:
            voids_opened = open_from_atlas(atlas)
        except Exception as exc:
            voids_opened = [{"error": str(exc)}]

    elapsed_ms = round((time.monotonic() - t0) * 1000)

    result = {
        "agents": [c.agent_name for c in atlas.charts()],
        "agent_count": len(atlas.charts()),
        "map_count": sum(1 for _ in atlas._maps),
        "hole_count": len(atlas.holes()),
        "holes": atlas.holes(),
        "bottlenecks": bottlenecks,
        "implied_regions": implied_regions,
        "voids_opened": voids_opened,
        "store_path": str(store_path),
        "elapsed_ms": elapsed_ms,
        "numinous_available": _NUMINOUS_AVAILABLE,
    }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manifold session init — surface mesh topology at session start."
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=_DEFAULT_STORE,
        help=f"Path to atlas store (default: {_DEFAULT_STORE})",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Output machine-readable JSON",
    )
    parser.add_argument(
        "--no-voids",
        dest="no_voids",
        action="store_true",
        help="Skip opening Numinous Voids (Elixir step)",
    )
    args = parser.parse_args()

    result = run(
        store_path=args.store,
        open_voids=not args.no_voids,
        json_output=args.json_output,
    )

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(_format_human(result))


if __name__ == "__main__":
    main()
