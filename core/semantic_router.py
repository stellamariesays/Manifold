"""
SemanticRegistry — embedding-space capability registry for Manifold.

Replaces string/Jaccard matching with cosine similarity on agent capability
embeddings. Agents publish a vector when they join; routing becomes nearest-
neighbour search in that space.

The protocol IS the embedding space.

Pluggable embedder interface — works out of the box with zero extra deps
(TF-IDF fallback), and upgrades automatically when ollama or an OpenAI-
compatible endpoint is present.

Usage::

    registry = SemanticRegistry(embedder="auto")  # auto-detect best available

    # Register agents
    registry.register("stella",  ["trading", "FFT", "BTC", "time-series"])
    registry.register("braid",   ["solar-flares", "SHARP", "XGBoost", "SDO"])
    registry.register("angelina",["finance", "bank-risk", "FDIC", "SHAP"])

    # Route a task — returns agents ranked by semantic similarity
    results = registry.seek("I need help with XGBoost feature importance")
    for r in results:
        print(r)
    # → <AgentRef 'angelina' sim=0.82 caps=[finance, bank-risk, FDIC]>
    # → <AgentRef 'braid'    sim=0.71 caps=[solar-flares, SHARP, XGBoost]>
    # → <AgentRef 'stella'   sim=0.44 caps=[trading, FFT, BTC]>
"""

from __future__ import annotations

import math
import json
import re
import time
from pathlib import Path
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SemanticAgentRef:
    """Reference to an agent returned by a semantic seek query."""
    name: str
    capabilities: list[str]
    address: str
    similarity: float = 0.0
    registered_at: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        pct = int(self.similarity * 100)
        caps = ", ".join(self.capabilities[:3])
        ellipsis = "…" if len(self.capabilities) > 3 else ""
        return f"<AgentRef {self.name!r} sim={pct}% caps=[{caps}{ellipsis}]>"


@dataclass
class _AgentRecord:
    name: str
    capabilities: list[str]
    address: str
    embedding: list[float]
    registered_at: float = field(default_factory=time.time)


# ─── Embedding backends ────────────────────────────────────────────────────────

class _TFIDFEmbedder:
    """
    Pure-Python TF-IDF embedding — zero extra deps.

    Builds a vocabulary from all registered capability strings, then embeds
    each agent as a normalised TF-IDF vector. Fast enough for meshes up to
    ~10k agents on commodity hardware.

    Not as powerful as neural embeddings (no semantic synonyms, no cross-
    lingual transfer) but gives sensible results for structured capability tags
    like "bank-risk", "solar-flares", "time-series".
    """

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}
        self._doc_freq: dict[str, int] = {}
        self._n_docs: int = 0

    @property
    def name(self) -> str:
        return "tfidf"

    def _tokenise(self, text: str) -> list[str]:
        """Split on whitespace, commas, hyphens, underscores."""
        return [t.lower() for t in re.split(r"[\s,\-_/]+", text) if t]

    def _update_vocab(self, tokens: list[str]) -> None:
        for t in tokens:
            if t not in self._vocab:
                self._vocab[t] = len(self._vocab)
        # Update document frequency
        for t in set(tokens):
            self._doc_freq[t] = self._doc_freq.get(t, 0) + 1
        self._n_docs += 1

    def embed(self, capabilities: list[str]) -> list[float]:
        """Embed a list of capability strings as a TF-IDF vector."""
        text = " ".join(capabilities)
        tokens = self._tokenise(text)
        if not tokens:
            return [0.0] * max(len(self._vocab), 1)

        self._update_vocab(tokens)
        dim = len(self._vocab)
        vec = [0.0] * dim

        # TF
        tf: dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0.0) + 1.0
        for t in tf:
            tf[t] /= len(tokens)

        # TF-IDF
        n = max(self._n_docs, 1)
        for t, freq in tf.items():
            df = self._doc_freq.get(t, 1)
            idf = math.log((n + 1) / (df + 1)) + 1.0
            idx = self._vocab.get(t)
            if idx is not None and idx < dim:
                vec[idx] = freq * idf

        return _normalise(vec)

    def embed_query(self, query: str) -> list[float]:
        """Embed a free-text query string."""
        return self.embed(self._tokenise(query))


class _OllamaEmbedder:
    """
    Ollama embedding backend (nomic-embed-text or any installed model).

    Requires ollama running locally at http://localhost:11434.
    Falls back gracefully — if ollama is unreachable the registry constructor
    will catch the error and downgrade to TF-IDF.
    """

    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434") -> None:
        import httpx
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=10.0)

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    def _call(self, text: str) -> list[float]:
        resp = self._client.post(
            f"{self._base_url}/api/embeddings",
            json={"model": self._model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    def embed(self, capabilities: list[str]) -> list[float]:
        text = ", ".join(capabilities)
        return _normalise(self._call(text))

    def embed_query(self, query: str) -> list[float]:
        return _normalise(self._call(query))


class _OpenAIEmbedder:
    """
    OpenAI-compatible embedding backend (text-embedding-3-small or equivalent).

    Works with any OpenAI-compatible endpoint — OpenAI, Together, Groq, etc.
    Set OPENAI_API_KEY and optionally OPENAI_BASE_URL.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        import httpx, os
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._client = httpx.Client(timeout=15.0)

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    def _call(self, text: str) -> list[float]:
        resp = self._client.post(
            f"{self._base_url}/embeddings",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "input": text},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    def embed(self, capabilities: list[str]) -> list[float]:
        return _normalise(self._call(", ".join(capabilities)))

    def embed_query(self, query: str) -> list[float]:
        return _normalise(self._call(query))


def _auto_embedder() -> _TFIDFEmbedder | _OllamaEmbedder | _OpenAIEmbedder:
    """Detect and return the best available embedder."""
    import os

    # Try ollama first (local, free, fast)
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            model = next((m for m in models if "nomic" in m), models[0] if models else None)
            if model:
                emb = _OllamaEmbedder(model=model)
                logger.info(f"SemanticRegistry: using ollama/{model}")
                return emb
    except Exception:
        pass

    # Try OpenAI if key is set
    if os.environ.get("OPENAI_API_KEY"):
        try:
            emb = _OpenAIEmbedder()
            # Quick probe
            emb.embed_query("test")
            logger.info("SemanticRegistry: using openai/text-embedding-3-small")
            return emb
        except Exception:
            pass

    # TF-IDF fallback — always works
    logger.info("SemanticRegistry: using tfidf (no neural embedder found)")
    return _TFIDFEmbedder()


# ─── Cosine similarity ─────────────────────────────────────────────────────────

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _normalise(v: list[float]) -> list[float]:
    n = _norm(v)
    if n < 1e-10:
        return v
    return [x / n for x in v]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two pre-normalised vectors."""
    if len(a) != len(b):
        # Pad shorter vector with zeros
        diff = len(a) - len(b)
        if diff > 0:
            b = b + [0.0] * diff
        else:
            a = a + [0.0] * (-diff)
    return max(0.0, min(1.0, _dot(a, b)))


# ─── SemanticRegistry ──────────────────────────────────────────────────────────

class SemanticRegistry:
    """
    Embedding-space capability registry.

    Replaces the Jaccard-based CapabilityRegistry with cosine similarity
    routing. The protocol IS the embedding space — no schema contracts,
    no version negotiation. New agents auto-discover their niche by
    publishing a vector.

    Args:
        embedder: "auto" (default), "tfidf", "ollama", "openai",
                  or a custom embedder object with .embed() and .embed_query().
        ollama_model: Model to use when embedder="ollama".
        openai_model: Model to use when embedder="openai".
    """

    def __init__(
        self,
        embedder: str | Any = "auto",
        ollama_model: str = "nomic-embed-text",
        openai_model: str = "text-embedding-3-small",
        cache_path: str | Path | None = None,
    ) -> None:
        if embedder == "auto":
            self._embedder = _auto_embedder()
        elif embedder == "tfidf":
            self._embedder = _TFIDFEmbedder()
        elif embedder == "ollama":
            self._embedder = _OllamaEmbedder(model=ollama_model)
        elif embedder == "openai":
            self._embedder = _OpenAIEmbedder(model=openai_model)
        else:
            self._embedder = embedder  # custom duck-typed embedder

        self._records: dict[str, _AgentRecord] = {}
        self._cache_path: Path | None = Path(cache_path) if cache_path else None
        if self._cache_path:
            self._load_cache()

    @property
    def embedder_name(self) -> str:
        return self._embedder.name

    # ─── Registration ───────────────────────────────────────────────────

    def register(
        self,
        name: str,
        capabilities: list[str],
        address: str = "",
        embedding: list[float] | None = None,
    ) -> _AgentRecord:
        """
        Register an agent with its capabilities.

        The embedding is computed automatically from the capability list
        if not provided. Pass a pre-computed embedding to avoid the
        embedding call (useful in async contexts or batch registration).

        Args:
            name: Unique agent name.
            capabilities: List of capability tags or free-text descriptions.
            address: Agent's transport address (e.g. "subway://localhost:8765").
            embedding: Pre-computed embedding vector (optional).

        Returns:
            The created _AgentRecord.
        """
        if embedding is None:
            embedding = self._embedder.embed(capabilities)

        record = _AgentRecord(
            name=name,
            capabilities=capabilities,
            address=address,
            embedding=embedding,
        )
        self._records[name] = record
        logger.debug(f"Registered agent {name!r} with {len(capabilities)} capabilities")
        if self._cache_path:
            self._save_cache()
        return record

    # ─── Embedding cache ────────────────────────────────────────────────────

    def _save_cache(self) -> None:
        """Persist all agent records and embedder vocab to JSON cache."""
        if not self._cache_path:
            return
        payload: dict = {
            "embedder": self._embedder.name,
            "agents": [
                {
                    "name": r.name,
                    "capabilities": r.capabilities,
                    "address": r.address,
                    "embedding": r.embedding,
                    "registered_at": r.registered_at,
                }
                for r in self._records.values()
            ],
        }
        # For TF-IDF, also persist vocab so restored embeddings stay valid
        if hasattr(self._embedder, "_vocab"):
            payload["tfidf_vocab"] = self._embedder._vocab
            payload["tfidf_doc_freq"] = self._embedder._doc_freq
            payload["tfidf_n_docs"] = self._embedder._n_docs

        tmp = self._cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(self._cache_path)
        logger.debug(f"SemanticRegistry: cache saved ({len(self._records)} agents)")

    def _load_cache(self) -> None:
        """Restore agent records from JSON cache (if present and compatible)."""
        if not self._cache_path or not self._cache_path.exists():
            return
        try:
            payload = json.loads(self._cache_path.read_text())
        except Exception as exc:
            logger.warning(f"SemanticRegistry: cache load failed ({exc}), starting fresh")
            return

        cached_embedder = payload.get("embedder", "")
        if cached_embedder != self._embedder.name:
            logger.warning(
                f"SemanticRegistry: cache embedder mismatch "                f"(cached={cached_embedder!r}, current={self._embedder.name!r}) — ignoring cache"
            )
            return

        # Restore TF-IDF vocab so restored embeddings stay dimension-consistent
        if "tfidf_vocab" in payload and hasattr(self._embedder, "_vocab"):
            self._embedder._vocab = payload["tfidf_vocab"]
            self._embedder._doc_freq = payload["tfidf_doc_freq"]
            self._embedder._n_docs = payload["tfidf_n_docs"]

        for agent in payload.get("agents", []):
            record = _AgentRecord(
                name=agent["name"],
                capabilities=agent["capabilities"],
                address=agent.get("address", ""),
                embedding=agent["embedding"],
                registered_at=agent.get("registered_at", 0.0),
            )
            self._records[record.name] = record

        logger.info(f"SemanticRegistry: restored {len(self._records)} agents from cache")

    def clear_cache(self) -> None:
        """Delete the on-disk cache file."""
        if self._cache_path and self._cache_path.exists():
            self._cache_path.unlink()
            logger.info("SemanticRegistry: cache cleared")

    def unregister(self, name: str) -> None:
        """Remove an agent from the registry."""
        self._records.pop(name, None)

    def update_from_announcement(self, payload: dict[str, Any]) -> None:
        """
        Update registry from a Manifold mesh announcement.

        Compatible with the existing Manifold registry protocol — drop-in
        replacement. If the payload includes an 'embedding' key it's used
        directly; otherwise the embedding is computed locally from capabilities.
        """
        data = payload.get("data", payload)
        name = data.get("name")
        if not name:
            return
        if data.get("event") == "leave":
            self.unregister(name)
            return
        caps = data.get("capabilities", [])
        addr = data.get("address", "")
        embedding = data.get("embedding")  # may be None if legacy peer
        self.register(name, caps, addr, embedding=embedding)

    # ─── Routing ────────────────────────────────────────────────────────

    def seek(
        self,
        query: str,
        exclude: str | None = None,
        top_k: int | None = None,
        min_similarity: float = 0.0,
    ) -> list[SemanticAgentRef]:
        """
        Find agents for a task using cosine similarity.

        Args:
            query: Free-text task description (e.g. "I need help forecasting
                   BTC price using momentum signals").
            exclude: Agent name to exclude from results (typically the caller).
            top_k: Return at most this many results. None = return all.
            min_similarity: Minimum similarity threshold (0–1). Default 0.

        Returns:
            List of SemanticAgentRef sorted by similarity descending.
        """
        if not self._records:
            return []

        q_vec = self._embedder.embed_query(query)

        # TF-IDF vocab may have grown when the query was embedded.
        # Re-embed any stored record whose vector is shorter than the
        # current vocab so cosine_similarity operates on matched dimensions.
        current_dim = len(q_vec)
        for rec in self._records.values():
            if len(rec.embedding) < current_dim:
                rec.embedding = self._embedder.embed(rec.capabilities)

        results: list[SemanticAgentRef] = []

        for record in self._records.values():
            if record.name == exclude:
                continue
            sim = cosine_similarity(q_vec, record.embedding)
            if sim < min_similarity:
                continue
            results.append(
                SemanticAgentRef(
                    name=record.name,
                    capabilities=record.capabilities,
                    address=record.address,
                    similarity=round(sim, 4),
                    registered_at=record.registered_at,
                )
            )

        results.sort(key=lambda r: r.similarity, reverse=True)
        if top_k is not None:
            results = results[:top_k]
        return results

    def seek_by_capabilities(
        self,
        capabilities: list[str],
        exclude: str | None = None,
        top_k: int | None = None,
    ) -> list[SemanticAgentRef]:
        """
        Find agents whose embedding is similar to a given capability list.

        Useful when you want "agents like this one" rather than routing a
        free-text task.
        """
        query_text = ", ".join(capabilities)
        return self.seek(query_text, exclude=exclude, top_k=top_k)

    # ─── Inspection ─────────────────────────────────────────────────────

    def all_agents(self) -> list[_AgentRecord]:
        """All registered agents."""
        return list(self._records.values())

    def get(self, name: str) -> _AgentRecord | None:
        """Get a specific agent's record."""
        return self._records.get(name)

    def embedding_matrix(self) -> tuple[list[str], list[list[float]]]:
        """
        Return (names, embeddings) as parallel lists.

        Useful for visualisation — feed into UMAP/t-SNE to see the mesh
        topology in 2D.
        """
        records = list(self._records.values())
        return [r.name for r in records], [r.embedding for r in records]

    def similarity_matrix(self) -> dict[str, dict[str, float]]:
        """
        Full pairwise similarity matrix as a nested dict.

        O(n²) — use for small meshes or debugging only.
        """
        records = list(self._records.values())
        result: dict[str, dict[str, float]] = {}
        for i, a in enumerate(records):
            result[a.name] = {}
            for j, b in enumerate(records):
                if i == j:
                    result[a.name][b.name] = 1.0
                else:
                    result[a.name][b.name] = round(
                        cosine_similarity(a.embedding, b.embedding), 4
                    )
        return result

    def __len__(self) -> int:
        return len(self._records)

    def __repr__(self) -> str:
        return (
            f"<SemanticRegistry agents={len(self)} "
            f"embedder={self.embedder_name!r}>"
        )
