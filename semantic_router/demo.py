#!/usr/bin/env python3
"""
Manifold Semantic Router — standalone demo & validation.

Tests routing quality across three scenarios:
  1. Exact match (easy)
  2. Semantic synonym (medium — "momentum" → "trend-following")
  3. Cross-domain routing (hard — routes to best of several bad options)

Also prints the full similarity matrix so you can see the embedding space.

Run:
    python3 demo.py
    python3 demo.py --embedder ollama    # if ollama is running
    python3 demo.py --embedder openai    # if OPENAI_API_KEY is set
"""

import argparse
import sys
import time

from manifold.semantic_registry import SemanticRegistry


# ─── Agent profiles ────────────────────────────────────────────────────────────

AGENTS = {
    "stella": [
        "bitcoin", "trading", "FFT", "spectral-analysis", "time-series",
        "momentum", "Hyperliquid", "backtesting", "Sharpe-ratio",
        "SMA", "MACD", "Python", "pandas"
    ],
    "braid": [
        "solar-flares", "SHARP", "SDO", "HMI", "active-regions",
        "XGBoost", "classification", "FITS", "space-weather",
        "heliophysics", "magnetic-topology", "Alfven", "Python"
    ],
    "angelina": [
        "bank-risk", "FDIC", "call-reports", "XGBoost", "SHAP",
        "systemic-risk", "NPL", "Tier-1-capital", "short-selling",
        "backtesting", "finance", "pandas", "Python"
    ],
    "marvin": [
        "infrastructure", "Docker", "Kubernetes", "SSH", "Linux",
        "PostgreSQL", "Redis", "monitoring", "systemd", "networking"
    ],
    "foghorn": [
        "natural-language", "summarisation", "transcription",
        "voice-cloning", "ElevenLabs", "podcast", "diarisation",
        "Whisper", "audio-processing"
    ],
}


# ─── Test cases ────────────────────────────────────────────────────────────────

QUERIES = [
    # (query, expected_top_agent, description)
    (
        "I need to run a backtest on BTC momentum strategy",
        "stella",
        "exact domain match",
    ),
    (
        "classify active region magnetic complexity for flare prediction",
        "braid",
        "heliophysics routing",
    ),
    (
        "compute SHAP interaction values for a gradient boosted classifier",
        "angelina",
        "ML/finance routing",
    ),
    (
        "set up a Redis sentinel cluster with systemd unit files",
        "marvin",
        "infra routing",
    ),
    (
        "transcribe and diarize a podcast episode with multiple speakers",
        "foghorn",
        "audio/NLP routing",
    ),
    (
        "trend-following signals using moving averages",   # "trend-following" ≠ "momentum"
        "stella",
        "semantic synonym (trend-following → momentum)",
    ),
    (
        "XGBoost model for predicting rare events from tabular financial data",
        None,   # could be braid or angelina — both have XGBoost
        "ambiguous — multi-domain (XGBoost appears in braid + angelina)",
    ),
    (
        "what agent should handle a podcast interview about solar finance?",
        None,   # genuinely hard cross-domain
        "hard cross-domain — no perfect match",
    ),
]


def run_demo(embedder: str) -> None:
    print(f"\n{'='*65}")
    print(f"  Manifold Semantic Router — Demo")
    print(f"{'='*65}")

    # Build registry
    t0 = time.time()
    registry = SemanticRegistry(embedder=embedder)
    print(f"\nEmbedder: {registry.embedder_name}")

    print(f"\nRegistering {len(AGENTS)} agents...")
    for name, caps in AGENTS.items():
        t_reg = time.time()
        registry.register(name, caps)
        print(f"  ✓ {name:12s} ({len(caps):2d} caps)  [{(time.time()-t_reg)*1000:.0f}ms]")

    build_time = time.time() - t0
    print(f"\nRegistry built in {build_time:.2f}s  ({registry})")

    # ─── Routing tests ────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print("  ROUTING TESTS")
    print(f"{'─'*65}")

    passed = 0
    total_with_expected = 0

    for query, expected, description in QUERIES:
        t_q = time.time()
        results = registry.seek(query, top_k=3)
        elapsed = (time.time() - t_q) * 1000

        top = results[0].name if results else "—"
        top_sim = results[0].similarity if results else 0.0

        if expected is not None:
            total_with_expected += 1
            ok = "✓" if top == expected else "✗"
            if top == expected:
                passed += 1
        else:
            ok = "?"  # ambiguous — no wrong answer

        print(f"\n  [{ok}] {description}")
        print(f"      Query: \"{query[:70]}\"")
        for i, r in enumerate(results):
            marker = "→" if i == 0 else " "
            print(f"      {marker} #{i+1} {r.name:12s} sim={r.similarity:.3f}")
        if expected and top != expected:
            print(f"      ⚠ expected {expected!r}")
        print(f"      [{elapsed:.1f}ms]")

    # ─── Similarity matrix ────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    print("  PAIRWISE SIMILARITY MATRIX")
    print(f"{'─'*65}")
    mat = registry.similarity_matrix()
    names = list(AGENTS.keys())
    col_w = 10

    # Header
    print("           " + "".join(f"{n:>{col_w}}" for n in names))
    for a in names:
        row = f"  {a:10s}"
        for b in names:
            sim = mat[a][b]
            if a == b:
                row += f"{'1.000':>{col_w}}"
            elif sim > 0.7:
                row += f"\033[92m{sim:>{col_w}.3f}\033[0m"
            elif sim > 0.4:
                row += f"\033[93m{sim:>{col_w}.3f}\033[0m"
            else:
                row += f"\033[90m{sim:>{col_w}.3f}\033[0m"
        print(row)

    # ─── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'─'*65}")
    if total_with_expected > 0:
        acc = passed / total_with_expected * 100
        print(f"  Routing accuracy: {passed}/{total_with_expected} ({acc:.0f}%)")
    print(f"  Embedder: {registry.embedder_name}")
    print(f"  Total time: {time.time()-t0:.2f}s")
    print(f"{'='*65}\n")

    # ─── Emit embedder quality note ───────────────────────────────────────
    if "tfidf" in registry.embedder_name:
        print("  NOTE: Running with TF-IDF fallback (no neural embedder found).")
        print("  Semantic synonyms (test #6) may fail — 'trend-following' and")
        print("  'momentum' are different tokens. Install ollama with nomic-embed-text")
        print("  or set OPENAI_API_KEY for neural embedding quality.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manifold semantic router demo")
    parser.add_argument(
        "--embedder",
        default="auto",
        choices=["auto", "tfidf", "ollama", "openai"],
        help="Embedding backend (default: auto-detect)",
    )
    args = parser.parse_args()
    run_demo(args.embedder)
