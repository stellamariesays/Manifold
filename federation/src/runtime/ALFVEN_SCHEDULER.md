# Alfvén Recharge Scheduler

Context-fatigue-aware agent routing for Manifold federation.

## Motivation

Every agent federation framework treats agents as stateless between tasks.
They're not.

After a heavy multi-step task, an LLM agent's context is soft-degraded —
lost-in-the-middle effects, KV cache pressure, attention dilution — even when
technically "free." Routing the next complex job to an exhausted agent produces
worse results than waiting a few minutes for a fresher one.

BRAID's solar active-region model gives us the right analogy: magnetic energy
depletes after a flare eruption, then recharges via Alfvén waves before another
eruption is possible. We apply the same curve to agent context state.

## Model

```
recovery_score(t) = 1 - (1 - score_after_last_task) * e^(-λ * Δt_minutes)
```

- `λ` — recovery rate constant, tuned per agent archetype
- `Δt` — minutes since last task completed
- Score ∈ [0.0, 1.0], 1.0 = fully recovered

Heavy tasks drain score proportional to tokens consumed. Light tasks barely dent it.

### Recovery archetypes

| Archetype | λ     | Time to 63% recovery |
|-----------|-------|---------------------|
| `fast`    | 0.10  | ~10 min             |
| `medium`  | 0.04  | ~25 min             |
| `slow`    | 0.015 | ~67 min             |

### Complexity thresholds

| Complexity | Min score required |
|------------|-------------------|
| `quick`    | 0.10              |
| `medium`   | 0.40              |
| `deep`     | 0.70              |

## Usage

```python
from alfven_scheduler import AlfvenScheduler

scheduler = AlfvenScheduler()

# Log a completed task
scheduler.log_task("manifold", tokens=28000, complexity="deep", task_label="atlas rebuild")

# Route next task to best available agent
result = scheduler.route("deep", candidates=["manifold", "btc-signals", "infra"])
# → {"agent": "btc-signals", "score": 0.967, "eligible_count": 2, ...}

# Check all scores
for agent in scheduler.status():
    print(f"{agent['agent']}: {agent['score']:.3f} (ETA full: {agent['eta_full_recovery_min']:.0f}m)")
```

## CLI

```bash
python3 alfven_scheduler.py status          # print all agent scores
python3 alfven_scheduler.py route deep      # who to route next deep task to
python3 alfven_scheduler.py                 # run demo
```

## Wiring into agent-runner.py

To automatically track load from real traffic, call `log_task()` in the task
completion handler inside `agent-runner.py`:

```python
from alfven_scheduler import AlfvenScheduler
_scheduler = AlfvenScheduler()

# In task completion callback:
_scheduler.log_task(
    agent_id=agent_name,
    tokens=result.get("tokens_used", 0),
    complexity=task.get("complexity", "medium"),
    task_label=task.get("command"),
)

# In task routing / dispatch selection:
best = _scheduler.route(
    complexity=task.get("complexity", "medium"),
    candidates=list(available_agents.keys()),
)
chosen_agent = best["agent"]
```

## Storage

Load events persist to `stella.db` → `agent_load_events` table.
No external deps — stdlib only (`math`, `sqlite3`, `time`).

## What makes this novel

No current federation framework (LangGraph, AutoGen, CrewAI, Manifold prior to
this PR) models context fatigue as a routing constraint. They all assume agents
reset between tasks. This scheduler is the first to treat recovery state as a
first-class scheduling primitive.
