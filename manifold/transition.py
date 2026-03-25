"""
TransitionMap — how knowledge translates between overlapping charts.

τ_ij : U_i ∩ U_j → U_j

The transition map is the seam. Not the edge weight. Not the gap score.
The actual translation function between two local views.

For each term in the source chart's vocabulary that exists in the overlap,
the map records which terms in the target chart's vocabulary it corresponds to.

Default: character trigram similarity (structural; zero deps).
          catches 'solar' ~ 'stellar', 'topology' ~ 'topological'.

With embeddings: full semantic similarity via cosine distance.
                 pass embedding_fn to Atlas.build() or Agent.atlas().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .chart import Chart

if TYPE_CHECKING:
    from .semantic import SemanticMatcher


@dataclass
class TransitionMap:
    """
    The translation function between two overlapping charts.

    source, target  — agent names
    overlap         — vocabulary terms shared by both charts
    coverage        — |overlap| / |source.vocabulary|
                      how much of the source can be expressed in the target
    translation     — for each overlap term, which target-domain strings use it
                      { "solar": ["solar-topology", "solar-ejection-prediction"] }
    consistency     — how faithfully the translation composes (filled by Atlas)
                      None until the atlas has computed it
    """

    source: str
    target: str
    overlap: set[str]
    coverage: float
    translation: dict[str, list[str]] = field(default_factory=dict)
    consistency: float | None = None  # filled by atlas.compute_curvature()

    @classmethod
    def between(
        cls,
        source_chart: Chart,
        target_chart: Chart,
        matcher: "SemanticMatcher | None" = None,
    ) -> "TransitionMap":
        """
        Compute the transition map from source_chart to target_chart.

        Without a matcher: exact token intersection (original behaviour).
        With a matcher:    semantic overlap via trigrams or embeddings —
                           'solar-topology' overlaps with 'stellar-dynamics'
                           because 'solar' ~ 'stellar'.

        The translation maps each overlap term to the domain strings in the
        target chart that are semantically near it.
        """
        if matcher is not None:
            overlap = matcher.semantic_overlap(
                source_chart.vocabulary, target_chart.vocabulary
            )
            translation = matcher.semantic_translation(
                overlap, source_chart.domain, target_chart.domain
            )
        else:
            # Fast path: exact token intersection
            overlap = source_chart.overlap_with(target_chart)
            translation = {}
            for term in overlap:
                targets = [
                    cap for cap in target_chart.domain
                    if term in cap.lower().replace("-", " ").replace("_", " ")
                ]
                if targets:
                    translation[term] = targets

        coverage = (
            round(len(overlap) / len(source_chart.vocabulary), 4)
            if source_chart.vocabulary
            else 0.0
        )

        return cls(
            source=source_chart.agent_name,
            target=target_chart.agent_name,
            overlap=overlap,
            coverage=coverage,
            translation=translation,
        )

    def compose_with(self, other: "TransitionMap") -> "TransitionMap":
        """
        Compose this map (i→j) with another (j→k) to get i→k.

        The composed map's overlap is the terms in self's overlap that
        also appear in the other map's overlap — terms that survive both
        translation steps.

        Used by the Atlas to check consistency:
        if τ_ij ∘ τ_jk disagrees with τ_ik, there is curvature.
        """
        if self.target != other.source:
            raise ValueError(
                f"Cannot compose: self.target={self.target!r} "
                f"!= other.source={other.source!r}"
            )

        # Terms that survive both translations
        composed_overlap = self.overlap & other.overlap

        # Composed translation: source term → final target domain strings
        composed_translation: dict[str, list[str]] = {}
        for term in composed_overlap:
            # What does self map 'term' to in j's domain?
            j_strings = self.translation.get(term, [])
            # What does other map from j's domain to k's domain?
            k_strings: list[str] = []
            for j_str in j_strings:
                # tokenize j_str and find matches in other's translation
                j_tokens = set(j_str.lower().replace("-", " ").split())
                for j_token in j_tokens:
                    k_strings.extend(other.translation.get(j_token, []))
            if k_strings:
                composed_translation[term] = list(set(k_strings))

        composed_coverage = (
            round(len(composed_overlap) / len(self.overlap), 4)
            if self.overlap
            else 0.0
        )

        return TransitionMap(
            source=self.source,
            target=other.target,
            overlap=composed_overlap,
            coverage=composed_coverage,
            translation=composed_translation,
        )

    def is_empty(self) -> bool:
        """True if the two charts have no vocabulary overlap."""
        return len(self.overlap) == 0

    def __repr__(self) -> str:
        pct = int(self.coverage * 100)
        con_str = (
            f" consistency={int(self.consistency * 100)}%"
            if self.consistency is not None
            else ""
        )
        return (
            f"<TransitionMap {self.source!r}→{self.target!r} "
            f"coverage={pct}% overlap={len(self.overlap)}{con_str}>"
        )
