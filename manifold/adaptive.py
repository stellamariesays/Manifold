"""Adaptive routing — self-tuning audience weights from dispatch feedback.

Learns which signals (capability, focus, trust, fog_gap, topology) matter
most for each topic by observing dispatch outcomes. Sits on top of the
existing ``AudiencePipeline`` and adjusts weights over time.

How it works:

1. Before each dispatch, record the current weights and the top candidate.
2. After each dispatch, feed the outcome (success / failure / latency) back.
3. On success, boost the weights of signals that contributed to the winner.
4. On failure, dampen them slightly.
5. Periodically decay old observations so the model adapts to topology changes.

The result: agents that get better at routing the more they dispatch, without
any manual weight tuning.

Usage::

    from manifold.adaptive import AdaptiveRouter

    router = AdaptiveRouter(agent)
    report = router.route("solar-prediction")
    # ... dispatch to report.entries[0] ...
    router.feedback(report.entries[0].name, success=True, latency_ms=120.0)

    # Check what the router has learned
    for topic, weights in router.learned_weights().items():
        print(f"{topic}: {weights}")

    # Export / import for persistence
    state = router.export_state()
    router.import_state(state)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from .audience import AudienceEntry, AudienceReport, AudienceRouter, Signal
from .audience_pipeline import AudiencePipeline


# ─── Data structures ──────────────────────────────────────────────────────

@dataclass
class Observation:
    """One dispatch outcome observation."""
    topic: str
    agent_name: str
    signals: list[Signal]
    weights: dict[str, float]
    score: float
    success: bool
    latency_ms: float
    timestamp: float


@dataclass
class TopicModel:
    """Per-topic learned weight adjustments."""
    topic: str
    adjustments: dict[str, float]  # signal name -> cumulative adjustment
    observations: int = 0
    successes: int = 0
    last_updated: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.observations if self.observations else 0.0

    def decay(self, factor: float = 0.95) -> None:
        """Decay adjustments toward zero (forget old data)."""
        for key in self.adjustments:
            self.adjustments[key] *= factor


@dataclass
class AdaptiveReport:
    """Routing result with adaptation metadata."""
    base_report: Any  # AudienceReport or PipelineReport
    applied_weights: dict[str, float]
    topic: str

    @property
    def entries(self) -> list[AudienceEntry]:
        return self.base_report.entries

    @property
    def primary(self) -> AudienceEntry | None:
        return self.entries[0] if self.entries else None

    def summary(self) -> str:
        w = ", ".join(f"{k}={v:.2f}" for k, v in sorted(self.applied_weights.items()))
        lines = [
            f"Adaptive route for '{self.topic}' [weights: {w}]",
            f"  {len(self.entries)} candidates",
        ]
        for e in self.entries[:5]:
            sigs = "+".join(s.value for s in e.signals)
            lines.append(f"  {e.name}: {e.score:.2f} [{sigs}]")
        return "\n".join(lines)


# ─── Adaptive Router ──────────────────────────────────────────────────────

class AdaptiveRouter:
    """
    Self-tuning audience router that learns from dispatch outcomes.

    Wraps ``AudiencePipeline`` (or ``AudienceRouter``) and maintains
    per-topic weight models. After each dispatch, call ``feedback()``
    with the outcome. The router adjusts weights so future dispatches
    to similar topics are more likely to pick the right agent.

    Args:
        agent:        The routing agent.
        learning_rate:  How aggressively to adjust weights (0–1).
        decay_factor:   How much to decay old observations (per decay call).
        max_history:    Max observations to keep in memory.
    """

    # Baseline weights (same as AudienceRouter defaults)
    BASE_WEIGHTS: dict[str, float] = {
        "capability": 0.35,
        "focus": 0.25,
        "trust": 0.20,
        "fog_gap": 0.10,
        "topology": 0.10,
    }

    def __init__(
        self,
        agent: Any,
        learning_rate: float = 0.15,
        decay_factor: float = 0.95,
        max_history: int = 500,
    ) -> None:
        self._agent = agent
        self._learning_rate = learning_rate
        self._decay_factor = decay_factor
        self._max_history = max_history
        self._models: dict[str, TopicModel] = {}
        self._history: list[Observation] = []
        self._decay_counter: int = 0

    # ─── Routing ────────────────────────────────────────────────────

    def _topic_key(self, topic: str) -> str:
        """Normalize topic for model lookup (trigram-ish bucketing)."""
        # Use first two words as the topic key — coarse enough to share
        # observations across similar topics, fine enough to differentiate
        parts = topic.lower().replace("-", " ").replace("_", " ").split()
        return " ".join(parts[:2]) if len(parts) >= 2 else topic.lower()

    def _get_weights(self, topic: str) -> dict[str, float]:
        """Compute adjusted weights for a topic."""
        key = self._topic_key(topic)
        model = self._models.get(key)
        if model is None:
            return dict(self.BASE_WEIGHTS)

        # Start from base, apply adjustments
        weights: dict[str, float] = {}
        for sig, base in self.BASE_WEIGHTS.items():
            adj = model.adjustments.get(sig, 0.0)
            weights[sig] = max(0.01, base + adj)

        # Normalize
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        return weights

    def route(
        self,
        topic: str,
        min_score: float = 0.0,
        exclude_self: bool = True,
        max_results: int | None = None,
    ) -> AdaptiveReport:
        """
        Route with learned weights for the topic.

        Falls back to base weights if no observations exist for this topic.
        """
        weights = self._get_weights(topic)
        pipeline = AudiencePipeline(self._agent, weights=weights)
        base_report = pipeline.route(
            topic, min_score=min_score, exclude_self=exclude_self,
            max_results=max_results,
        )
        return AdaptiveReport(
            base_report=base_report,
            applied_weights=weights,
            topic=topic,
        )

    # ─── Feedback ───────────────────────────────────────────────────

    def feedback(
        self,
        agent_name: str,
        topic: str,
        success: bool,
        latency_ms: float = 0.0,
        entry: AudienceEntry | None = None,
    ) -> None:
        """
        Feed back a dispatch outcome.

        Call this after a dispatch completes (success or failure). The router
        adjusts weights for the topic based on which signals contributed to
        the dispatched agent's score.

        Args:
            agent_name:   Name of the agent that was dispatched to.
            topic:        The topic that was routed for.
            success:      Did the dispatch succeed?
            latency_ms:   How long the dispatch took (for latency-aware tuning).
            entry:        The AudienceEntry that was dispatched (for signal info).
                          If None, the router records a minimal observation.
        """
        key = self._topic_key(topic)

        # Record observation
        obs = Observation(
            topic=topic,
            agent_name=agent_name,
            signals=list(entry.signals) if entry else [],
            weights=self._get_weights(topic),
            score=entry.score if entry else 0.0,
            success=success,
            latency_ms=latency_ms,
            timestamp=time.time(),
        )
        self._history.append(obs)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Get or create model
        if key not in self._models:
            self._models[key] = TopicModel(
                topic=key,
                adjustments={sig: 0.0 for sig in self.BASE_WEIGHTS},
            )
        model = self._models[key]
        model.observations += 1
        if success:
            model.successes += 1
        model.last_updated = time.time()

        # Adjust weights based on which signals contributed
        if entry and entry.signals:
            lr = self._learning_rate
            # Latency bonus: faster = stronger positive signal
            latency_factor = 1.0
            if success and latency_ms > 0:
                # Good: <500ms, OK: <2000ms, Slow: >2000ms
                latency_factor = max(0.5, min(1.5, 2000.0 / max(latency_ms, 1.0)))

            for sig in Signal:
                sig_key = sig.value
                if sig in entry.signals:
                    # This signal contributed
                    if success:
                        model.adjustments[sig_key] += lr * latency_factor
                    else:
                        model.adjustments[sig_key] -= lr * 0.5
                else:
                    # This signal didn't contribute — slight opposite nudge
                    if success:
                        model.adjustments[sig_key] -= lr * 0.1
                    else:
                        model.adjustments[sig_key] += lr * 0.05

        # Periodic decay
        self._decay_counter += 1
        if self._decay_counter >= 20:
            self._decay_counter = 0
            for m in self._models.values():
                m.decay(self._decay_factor)

    # ─── Query helpers ──────────────────────────────────────────────

    def learned_weights(self) -> dict[str, dict[str, float]]:
        """Return all learned weight adjustments, keyed by topic."""
        result: dict[str, dict[str, float]] = {}
        for key, model in self._models.items():
            # Compose final weights
            weights: dict[str, float] = {}
            for sig, base in self.BASE_WEIGHTS.items():
                adj = model.adjustments.get(sig, 0.0)
                weights[sig] = round(base + adj, 4)
            # Normalize
            total = sum(weights.values())
            if total > 0:
                weights = {k: round(v / total, 4) for k, v in weights.items()}
            result[key] = weights
        return result

    def topic_stats(self, topic: str) -> dict[str, Any] | None:
        """Stats for a specific topic."""
        key = self._topic_key(topic)
        model = self._models.get(key)
        if model is None:
            return None
        return {
            "topic": model.topic,
            "observations": model.observations,
            "successes": model.successes,
            "success_rate": round(model.success_rate, 3),
            "adjustments": dict(model.adjustments),
            "last_updated": model.last_updated,
        }

    def stats(self) -> dict[str, Any]:
        """Overall adaptive router statistics."""
        total_obs = len(self._history)
        total_success = sum(1 for o in self._history if o.success)
        return {
            "topics_learned": len(self._models),
            "total_observations": total_obs,
            "overall_success_rate": round(total_success / total_obs, 3) if total_obs else 0.0,
            "learning_rate": self._learning_rate,
            "decay_factor": self._decay_factor,
        }

    # ─── Persistence ────────────────────────────────────────────────

    def export_state(self) -> dict[str, Any]:
        """Export router state for persistence."""
        return {
            "models": {
                key: {
                    "topic": m.topic,
                    "adjustments": m.adjustments,
                    "observations": m.observations,
                    "successes": m.successes,
                    "last_updated": m.last_updated,
                }
                for key, m in self._models.items()
            },
            "history_count": len(self._history),
            "learning_rate": self._learning_rate,
            "decay_factor": self._decay_factor,
        }

    def import_state(self, state: dict[str, Any]) -> None:
        """Import router state from persistence."""
        for key, data in state.get("models", {}).items():
            model = TopicModel(
                topic=data["topic"],
                adjustments=data.get("adjustments", {}),
                observations=data.get("observations", 0),
                successes=data.get("successes", 0),
                last_updated=data.get("last_updated", 0.0),
            )
            self._models[key] = model
        self._learning_rate = state.get("learning_rate", self._learning_rate)
        self._decay_factor = state.get("decay_factor", self._decay_factor)

    # ─── Reset ──────────────────────────────────────────────────────

    def reset(self, topic: str | None = None) -> None:
        """Reset learned weights for a topic, or all topics."""
        if topic:
            key = self._topic_key(topic)
            self._models.pop(key, None)
        else:
            self._models.clear()
            self._history.clear()
