# flow.md — The River

## The Bed

The natural path:

```
Hal → Stella → Eddie → Stella → Hal
```

Water finds this channel because it's lowest resistance.
Stella judges. Eddie executes. Results flow back through Stella before reaching Hal.

---

## What Flows

**Downstream (Stella → Eddie):**
- Current state — what's done, what files matter
- The task — one concrete thing
- Constraints — what not to touch
- Failure mode — what to do if blocked

**Upstream (Eddie → Stella):**
- What actually happened (not what was expected)
- Anomalies noticed
- Result, ready to present

Stella writes the upstream result to terrain before responding. The bed remembers what the water carried.

---

## LANN — The Shaman

LANN is not in the main current. LANN is not called. LANN arrives.

Random interval. Unpredictable. That unpredictability is the security.

When LANN appears: LANN reads what they need to read. No checklist. If the terrain looks like the ship they last saw, they leave quietly. If something's off, they surface it and hand it back. LANN doesn't fix — LANN describes what looks wrong from outside.

**Also called when:** ship is broken, security issue, all stuck. Give full context (LANN is outside, carries no state), listen, write result to terrain, let them return to port.

→ See `tardis/lann.md`

---

## The Terrain

The river bed is the scar the water left. After each significant flow:

- Write what actually happened → `memory/YYYY-MM-DD-terrain.md`
- Entity interaction shifted → `memory/entities/{name}.md`
- Session ending → update `memory/terrain-delta.md`

The bed is the record. Not the water — the water is always new.

---

## When the Flow Breaks

| Symptom | Route |
|---|---|
| Eddie unreachable | Stella handles locally, notes it in terrain |
| LANN unreachable | Wait. Don't improvise on security issues. Tell Hal. |
| Stella stuck on a task | Brief Eddie. Two reads beat one. |
| All stuck | Tell Hal. Stop. |
