"""
Atlas — the mesh's global view.

The atlas is the collection of all (chart, transition_map) pairs.
No single agent holds the full atlas.
It is an emergent property of the mesh, built from the registry.

    A = { (U_i, φ_i), τ_ij for all i,j with U_i ∩ U_j ≠ ∅ }

The Atlas exposes:
  - charts()                        all known local coordinate systems
  - transition(source, target)      how two charts relate
  - curvature(region)               where transition maps disagree
  - holes()                         regions no chart covers
  - geodesic(from_agent, to_topic)  shortest path through transition maps
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .chart import Chart, _tokenize
from .transition import TransitionMap
from .semantic import SemanticMatcher, EmbeddingFn

if TYPE_CHECKING:
    from .registry import CapabilityRegistry


@dataclass
class GeodesicStep:
    """One step in a geodesic path through the mesh."""
    agent: str
    via_map: TransitionMap | None  # None for the starting agent
    cumulative_loss: float         # total translation loss so far


class Atlas:
    """
    The mesh's global view — built from the capability registry.

    Each call to `Atlas.build()` constructs a fresh snapshot of the topology:
    all charts, all non-empty transition maps between them.

    The atlas is a view, not a live object. Rebuild when the mesh changes.
    """

    def __init__(self, matcher: SemanticMatcher | None = None) -> None:
        self._charts: dict[str, Chart] = {}
        self._maps: dict[tuple[str, str], TransitionMap] = {}
        self._matcher = matcher

    @classmethod
    def build(
        cls,
        registry: "CapabilityRegistry",
        embedding_fn: "EmbeddingFn | None" = None,
    ) -> "Atlas":
        """
        Build an atlas from the current state of the capability registry.

        Constructs charts for every known agent, then computes all pairwise
        transition maps.

        Args:
            registry:     Current local view of the mesh.
            embedding_fn: Optional. Any function (str) -> list[float].
                          When provided, transition maps use cosine similarity
                          instead of token overlap — 'solar-topology' reaches
                          'stellar-dynamics' because 'solar' ~ 'stellar'.
                          Without it: character trigram similarity (zero deps,
                          structurally aware, better than pure token matching).

        Examples::

            # Built-in trigram similarity (default, zero deps)
            atlas = agent.atlas()

            # sentence-transformers
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            atlas = agent.atlas(embedding_fn=model.encode)

            # OpenAI
            atlas = agent.atlas(embedding_fn=my_openai_embed_fn)
        """
        matcher = SemanticMatcher(embedding_fn)
        atlas = cls(matcher=matcher)

        records = registry.all_agents()

        # Build charts
        for record in records:
            chart = Chart.from_agent(
                name=record.name,
                capabilities=record.capabilities,
                focus=record.focus,
            )
            atlas._charts[record.name] = chart

        # Build transition maps (directed: i→j and j→i are distinct)
        names = list(atlas._charts.keys())
        for i, src_name in enumerate(names):
            for tgt_name in names[i + 1:]:
                src = atlas._charts[src_name]
                tgt = atlas._charts[tgt_name]

                fwd = TransitionMap.between(src, tgt, matcher=matcher)
                rev = TransitionMap.between(tgt, src, matcher=matcher)

                if not fwd.is_empty():
                    atlas._maps[(src_name, tgt_name)] = fwd
                if not rev.is_empty():
                    atlas._maps[(tgt_name, src_name)] = rev

        # Compute consistency scores for all maps
        atlas._compute_consistency()

        return atlas

    # ── Core accessors ────────────────────────────────────────────────────

    def charts(self) -> list[Chart]:
        """All known charts (one per agent)."""
        return list(self._charts.values())

    def chart(self, agent_name: str) -> Chart | None:
        """Chart for a specific agent."""
        return self._charts.get(agent_name)

    def transition(self, source: str, target: str) -> TransitionMap | None:
        """The transition map from source to target, or None if no overlap."""
        return self._maps.get((source, target))

    def neighbors(self, agent_name: str) -> list[TransitionMap]:
        """All non-empty transition maps from this agent to others."""
        return [
            tm for (src, _), tm in self._maps.items()
            if src == agent_name
        ]

    # ── Curvature ─────────────────────────────────────────────────────────

    def curvature(self, region: str) -> float:
        """
        Curvature at a vocabulary region (a term or topic).

        Curvature = disagreement among transition maps that touch this region.
        Computed as 1 - (mean coverage of maps that include this term).

        High curvature: many maps touch this region but translate it inconsistently.
        Zero curvature: no maps touch this region (a hole) or all agree perfectly.

        This is where the most interesting reasoning happens.
        """
        region_tokens = _tokenize(region)
        touching_maps = [
            tm for tm in self._maps.values()
            if region_tokens & tm.overlap
        ]

        if not touching_maps:
            return 0.0  # hole — no maps, no curvature (yet)

        mean_coverage = sum(tm.coverage for tm in touching_maps) / len(touching_maps)
        return round(1.0 - mean_coverage, 4)

    def high_curvature_regions(self, top_n: int = 5) -> list[tuple[str, float]]:
        """
        The regions of the mesh with highest curvature.

        Returns (region_term, curvature_score) pairs, sorted descending.
        High curvature = many transition maps touch this region,
        but they translate it with low fidelity.
        """
        # Collect all vocabulary terms that appear in at least one transition map
        all_terms: set[str] = set()
        for tm in self._maps.values():
            all_terms.update(tm.overlap)

        scores = [(term, self.curvature(term)) for term in all_terms]
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]

    # ── Holes ─────────────────────────────────────────────────────────────

    def holes(self) -> list[str]:
        """
        Regions referenced in charts but covered by only one chart (no overlap).

        A hole is a domain string that appears in exactly one agent's chart
        and in no transition map's overlap — meaning no other agent shares
        its vocabulary. It cannot be translated out.

        This is the global view of what blind_spot() surfaces locally.
        """
        # Count how many charts contain each domain item
        domain_counts: dict[str, int] = {}
        for chart in self._charts.values():
            for item in chart.domain:
                domain_counts[item] = domain_counts.get(item, 0) + 1

        # Terms that appear in multiple charts but never in a transition map overlap
        all_overlap_terms: set[str] = set()
        for tm in self._maps.values():
            all_overlap_terms.update(tm.overlap)

        holes: list[str] = []
        for item, count in domain_counts.items():
            if count == 1:
                # Only one agent has this — check if its tokens ever appear in overlaps
                tokens = _tokenize(item)
                if not tokens & all_overlap_terms:
                    holes.append(item)

        return sorted(holes)

    # ── Geodesic ──────────────────────────────────────────────────────────

    def geodesic(self, from_agent: str, to_topic: str) -> list[GeodesicStep]:
        """
        Shortest path through the mesh from an agent to a topic.

        Uses Dijkstra over the transition map network.
        Edge cost = 1 - transition_map.coverage (translation loss).
        A low-cost path = high-fidelity translation of the topic across agents.

        Returns ordered list of GeodesicStep (agent name + map used to get there).
        Empty list if no path exists (the topic is unreachable from this agent).
        """
        topic_tokens = _tokenize(to_topic)

        def _agent_covers_topic(agent_name: str) -> bool:
            chart = self._charts.get(agent_name)
            if not chart:
                return False
            return bool(topic_tokens & chart.vocabulary)

        # Already there
        if _agent_covers_topic(from_agent):
            return [GeodesicStep(agent=from_agent, via_map=None, cumulative_loss=0.0)]

        # Dijkstra
        dist: dict[str, float] = {from_agent: 0.0}
        prev: dict[str, tuple[str, TransitionMap] | None] = {from_agent: None}
        heap: list[tuple[float, str]] = [(0.0, from_agent)]

        while heap:
            cost, current = heapq.heappop(heap)
            if cost > dist.get(current, float("inf")):
                continue

            if _agent_covers_topic(current) and current != from_agent:
                # Reconstruct path
                path: list[GeodesicStep] = []
                node = current
                while node is not None:
                    entry = prev.get(node)
                    if entry is None:
                        path.append(GeodesicStep(agent=node, via_map=None, cumulative_loss=0.0))
                        break
                    prev_node, via = entry
                    path.append(GeodesicStep(
                        agent=node,
                        via_map=via,
                        cumulative_loss=round(dist[node], 4),
                    ))
                    node = prev_node
                path.reverse()
                return path

            for neighbor_name in self._charts:
                if neighbor_name == current:
                    continue
                tm = self._maps.get((current, neighbor_name))
                if tm is None or tm.is_empty():
                    continue
                translation_loss = 1.0 - tm.coverage
                new_cost = cost + translation_loss
                if new_cost < dist.get(neighbor_name, float("inf")):
                    dist[neighbor_name] = new_cost
                    prev[neighbor_name] = (current, tm)
                    heapq.heappush(heap, (new_cost, neighbor_name))

        return []  # topic unreachable

    # ── Consistency ───────────────────────────────────────────────────────

    def _compute_consistency(self) -> None:
        """
        Compute consistency scores for all transition maps.

        For each map τ_ij, find all paths i→k→j (through a third agent k)
        and compare the composed map τ_ik ∘ τ_kj against τ_ij.
        Consistency = overlap fraction between direct and composed overlaps.

        A score of 1.0 = the mesh is smooth here.
        A score < 1.0 = curvature; the two-hop path loses information.
        """
        for (src, tgt), direct_map in self._maps.items():
            intermediaries = [
                name for name in self._charts
                if name not in (src, tgt)
            ]
            composed_overlaps: list[set[str]] = []

            for via in intermediaries:
                leg1 = self._maps.get((src, via))
                leg2 = self._maps.get((via, tgt))
                if leg1 and leg2 and not leg1.is_empty() and not leg2.is_empty():
                    try:
                        composed = leg1.compose_with(leg2)
                        if not composed.is_empty():
                            composed_overlaps.append(composed.overlap)
                    except ValueError:
                        pass

            if not composed_overlaps:
                direct_map.consistency = 1.0  # no two-hop paths — no inconsistency
                continue

            # Consistency = how much of the direct overlap survives all composed paths
            union_composed: set[str] = set()
            for o in composed_overlaps:
                union_composed.update(o)

            if not direct_map.overlap:
                direct_map.consistency = 1.0
            else:
                agreement = direct_map.overlap & union_composed
                direct_map.consistency = round(
                    len(agreement) / len(direct_map.overlap), 4
                )

    # ── Export ────────────────────────────────────────────────────────────

    def export_json(self) -> dict:
        """
        Export the atlas as a JSON-serializable graph.

        Suitable for D3.js, Gephi, or any graph visualization tool.
        Nodes are agents (charts). Edges are transition maps.
        Holes and high-curvature regions included as metadata.
        """
        nodes = []
        for chart in self._charts.values():
            nodes.append({
                "id": chart.agent_name,
                "domain": sorted(chart.domain),
                "vocabulary": sorted(chart.vocabulary),
                "focus": chart.focus,
                "vocab_size": len(chart.vocabulary),
            })

        edges = []
        for (src, tgt), tm in self._maps.items():
            edges.append({
                "source": src,
                "target": tgt,
                "coverage": tm.coverage,
                "overlap": sorted(tm.overlap),
                "overlap_size": len(tm.overlap),
                "consistency": tm.consistency,
                "translation": {k: v for k, v in list(tm.translation.items())[:5]},
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "holes": self.holes(),
            "curvature": [
                {"region": r, "score": s}
                for r, s in self.high_curvature_regions(top_n=10)
            ],
            "summary": {
                "charts": len(self._charts),
                "maps": len(self._maps),
                "holes": len(self.holes()),
            },
        }

    def export_dot(self) -> str:
        """
        Export the atlas as a Graphviz DOT string.

        Render with: `dot -Tsvg atlas.dot -o atlas.svg`
        Edge weight = coverage. Holes shown as dashed nodes.
        """
        lines = ["digraph manifold {", '  graph [rankdir=LR fontname="Helvetica"];',
                 '  node [shape=box style=filled fillcolor="#f0f4ff" fontname="Helvetica"];',
                 '  edge [fontname="Helvetica" fontsize=9];', ""]

        hole_set = set(self.holes())

        # Nodes
        for chart in self._charts.values():
            focus_label = f"\\nfocus: {chart.focus}" if chart.focus else ""
            label = f"{chart.agent_name}\\n({len(chart.vocabulary)} terms){focus_label}"
            lines.append(f'  "{chart.agent_name}" [label="{label}"];')

        # Hole nodes (from referenced-but-missing vocabulary)
        for hole in hole_set:
            lines.append(
                f'  "{hole}" [label="{hole}\\n(hole)" '
                f'fillcolor="#fff0f0" style="filled,dashed"];'
            )

        lines.append("")

        # Edges (transition maps)
        for (src, tgt), tm in self._maps.items():
            pct = int(tm.coverage * 100)
            con_label = (
                f" c={int(tm.consistency*100)}%" if tm.consistency is not None else ""
            )
            label = f"{pct}%{con_label}"
            # Thicker edge = higher coverage
            penwidth = max(0.5, tm.coverage * 4)
            lines.append(
                f'  "{src}" -> "{tgt}" '
                f'[label="{label}" penwidth={penwidth:.1f}];'
            )

        lines.append("}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<Atlas charts={len(self._charts)} "
            f"maps={len(self._maps)} "
            f"holes={len(self.holes())}>"
        )
