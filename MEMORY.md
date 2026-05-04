# MEMORY — Archive

*This file is no longer actively maintained. It exists for historical reference only.*

**Active memory structure (as of 2026-04-15):**

- `memory/terrain-delta.md` — current ground state (read first)
- `memory/index/` — structured JSON records:
  - `system.json` — host, ports, peers, paths, wallet, tools
  - `agents.json` — all agents, capabilities, scripts, cron wiring
  - `projects.json` — active projects, blockers, next steps
  - `cron-jobs.json` — all cron IDs, schedules, purposes
  - `decisions.jsonl` — append-only decision log
  - `preferences.json` — Hal's hard rules and constraints
- `memory/daily/YYYY-MM-DD.md` — event logs
- `memory/terrain/week-YYYY-WW.md` — weekly rollups
- `memory/entities/{name}.md` — per-entity profiles

For precise lookups, read `memory/index/*.json` directly.
For context/history, use `memory_search`.
