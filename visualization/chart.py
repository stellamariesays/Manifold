"""
Chart — an agent's local coordinate system.

A chart (U_i, φ_i) is the agent's local view of knowledge space:
  - domain (U_i): the set of topics this agent can express
  - vocabulary (φ_i): the tokenized coordinate system it uses to encode them

The agent IS the chart. It knows its own domain well.
It cannot directly observe the global shape of the mesh.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _tokenize(s: str) -> set[str]:
    """Tokenize a capability or topic string into vocabulary terms."""
    return set(s.lower().replace("-", " ").replace("_", " ").split())


def _vocab_from(capabilities: list[str], focus: str | None = None) -> set[str]:
    """Build vocabulary from capabilities and optional focus."""
    vocab: set[str] = set()
    for cap in capabilities:
        vocab.update(_tokenize(cap))
    if focus:
        vocab.update(_tokenize(focus))
    return vocab


@dataclass
class Chart:
    """
    An agent's local coordinate system.

    domain      — the set of capability + focus strings this agent can express
    vocabulary  — tokenized vocabulary of the domain (the coordinate basis)
    focus       — current cognitive center (shifts the chart's emphasis)
    agent_name  — who holds this chart
    """

    agent_name: str
    domain: set[str] = field(default_factory=set)
    vocabulary: set[str] = field(default_factory=set)
    focus: str | None = None

    @classmethod
    def from_agent(
        cls,
        name: str,
        capabilities: list[str],
        focus: str | None = None,
    ) -> "Chart":
        """Build a chart from an agent's declared capabilities and current focus."""
        domain = set(capabilities)
        if focus:
            domain.add(focus)
        vocab = _vocab_from(capabilities, focus)
        return cls(agent_name=name, domain=domain, vocabulary=vocab, focus=focus)

    def overlap_with(self, other: "Chart") -> set[str]:
        """
        Vocabulary overlap with another chart.

        The overlap is the region of topic space both agents can speak to.
        A large overlap = same domain, same vocabulary.
        An empty overlap = completely foreign territories.
        """
        return self.vocabulary & other.vocabulary

    def overlap_fraction(self, other: "Chart") -> float:
        """
        What fraction of this chart's vocabulary overlaps with the other?

        0.0 = no shared vocabulary (completely foreign)
        1.0 = the other chart contains everything in this one
        """
        if not self.vocabulary:
            return 0.0
        return len(self.overlap_with(other)) / len(self.vocabulary)

    def distance_to(self, other: "Chart") -> float:
        """
        Topological distance to another chart.

        0.0 = identical vocabulary (same region)
        1.0 = no shared vocabulary (maximally distant)

        Based on Jaccard distance: 1 - |A ∩ B| / |A ∪ B|
        """
        union = self.vocabulary | other.vocabulary
        if not union:
            return 0.0
        intersection = self.vocabulary & other.vocabulary
        return round(1.0 - len(intersection) / len(union), 4)

    def __repr__(self) -> str:
        focus_str = f" focus={self.focus!r}" if self.focus else ""
        return (
            f"<Chart {self.agent_name!r}"
            f" domain={len(self.domain)}"
            f" vocab={len(self.vocabulary)}"
            f"{focus_str}>"
        )
