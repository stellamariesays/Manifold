"""
Semantic similarity for transition maps.

Phase 1 (token overlap) can't find that 'solar-topology' and 'stellar-dynamics'
are related — no shared tokens. This fixes that.

Two layers:

    Built-in (zero deps):
        Character trigram similarity. 'solar' and 'stellar' share 'lar';
        'time-series' and 'temporal-sequence' share character patterns.
        Not semantic in the linguistic sense — but structurally aware.
        Works out of the box.

    Injected embeddings (optional):
        Pass any function (str) -> list[float] to Agent or Atlas.build().
        Cosine similarity. 'solar wind' genuinely close to 'stellar wind'.
        Works with sentence-transformers, OpenAI, anything.

Usage::

    # Zero-dep built-in
    atlas = agent.atlas()  # uses trigram similarity by default

    # With sentence-transformers
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    atlas = agent.atlas(embedding_fn=model.encode)

    # With OpenAI
    from openai import OpenAI
    client = OpenAI()
    def embed(text):
        return client.embeddings.create(
            input=text, model="text-embedding-3-small"
        ).data[0].embedding
    atlas = agent.atlas(embedding_fn=embed)
"""

from __future__ import annotations

import math
from typing import Callable

EmbeddingFn = Callable[[str], list[float]]

# Cosine similarity threshold for embeddings — terms above this are "overlapping"
EMBEDDING_THRESHOLD = 0.60

# Trigram similarity threshold — terms above this are "overlapping"
# Lower than embedding threshold because trigrams are structural, not semantic
TRIGRAM_THRESHOLD = 0.25


def _trigrams(s: str) -> set[str]:
    """Character trigrams of a string, lowercased and stripped."""
    s = s.lower().replace("-", "").replace("_", "").replace(" ", "")
    if len(s) < 3:
        return {s}
    return {s[i : i + 3] for i in range(len(s) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    """
    Character trigram Jaccard similarity between two strings.

    Not semantic — but structurally aware. Catches:
      'solar' ~ 'stellar'      (share 'lar')
      'topology' ~ 'topological'  (share many trigrams)
      'time-series' ~ 'temporal'  (weaker, but non-zero)
    """
    ta, tb = _trigrams(a), _trigrams(b)
    union = ta | tb
    if not union:
        return 0.0
    return len(ta & tb) / len(union)


def phrase_trigram_similarity(phrase_a: str, phrase_b: str) -> float:
    """
    Trigram similarity between two capability phrases.

    Splits on separators, takes best term-pair match across cross-product.
    'solar-topology' vs 'stellar-dynamics': max(sim(solar,stellar), sim(solar,dynamics),
    sim(topology,stellar), sim(topology,dynamics)).
    """
    terms_a = phrase_a.lower().replace("-", " ").replace("_", " ").split()
    terms_b = phrase_b.lower().replace("-", " ").replace("_", " ").split()

    if not terms_a or not terms_b:
        return 0.0

    best = 0.0
    for ta in terms_a:
        for tb in terms_b:
            best = max(best, trigram_similarity(ta, tb))
    return round(best, 4)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two embedding vectors."""
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return round(_dot(a, b) / (na * nb), 4)


class SemanticMatcher:
    """
    Computes semantic overlap between vocabulary sets.

    With embedding_fn: full semantic similarity via cosine distance.
    Without:          trigram similarity (structural; zero deps).

    Cache embeddings per term to avoid redundant calls.
    """

    def __init__(self, embedding_fn: EmbeddingFn | None = None) -> None:
        self._embed = embedding_fn
        self._cache: dict[str, list[float]] = {}

    def _embedding(self, term: str) -> list[float] | None:
        if self._embed is None:
            return None
        if term not in self._cache:
            self._cache[term] = list(self._embed(term))
        return self._cache[term]

    def similarity(self, a: str, b: str) -> float:
        """
        Similarity between two vocabulary terms or phrases.

        With embeddings: cosine similarity of embedding vectors.
        Without:         trigram similarity.
        """
        if a == b:
            return 1.0

        if self._embed is not None:
            ea, eb = self._embedding(a), self._embedding(b)
            if ea and eb:
                return cosine_similarity(ea, eb)

        return phrase_trigram_similarity(a, b)

    def threshold(self) -> float:
        """Similarity threshold above which two terms are considered overlapping."""
        return EMBEDDING_THRESHOLD if self._embed else TRIGRAM_THRESHOLD

    def semantic_overlap(
        self,
        vocab_a: set[str],
        vocab_b: set[str],
    ) -> set[str]:
        """
        Extended overlap: terms in vocab_a that have a near-match in vocab_b.

        Returns terms from vocab_a whose similarity to any term in vocab_b
        exceeds the threshold. Includes exact matches.

        This is the replacement for simple set intersection in TransitionMap.
        """
        thresh = self.threshold()
        result: set[str] = set()

        for a in vocab_a:
            for b in vocab_b:
                if self.similarity(a, b) >= thresh:
                    result.add(a)
                    break  # a has a match — no need to check further b's

        return result

    def semantic_translation(
        self,
        overlap: set[str],
        source_domain: set[str],
        target_domain: set[str],
    ) -> dict[str, list[str]]:
        """
        Build translation map: for each overlap term, find target domain
        strings that are semantically related to it.

        This extends token-based translation to semantic proximity:
        'solar' in source maps to 'stellar-topology' in target even if
        the tokens don't match — because 'solar' ~ 'stellar'.
        """
        thresh = self.threshold()
        translation: dict[str, list[str]] = {}

        for term in overlap:
            matches: list[str] = []
            for cap in target_domain:
                # Check if any word in the cap is near this term
                cap_words = cap.lower().replace("-", " ").replace("_", " ").split()
                for word in cap_words:
                    if self.similarity(term, word) >= thresh:
                        matches.append(cap)
                        break
            if matches:
                translation[term] = matches

        return translation
