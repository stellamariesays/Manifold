# Context Handoff — 2026-03-31 11:04 WITA
**Reason:** 87% context hit — hard stop per HEARTBEAT.md
**Session:** main telegram Skynet2

---

## Objective
Build **manifold.surge.sh** — a cool landing page using the BRAID intro graphic style or other animations from https://10et-site.pages.dev/heroes/

---

## What Was Done
1. Fetched the 10et-site heroes page — available animation styles:
   - Wireframe Torus, Fluid Smoke, Gravity Text, Scroll Compound, 3D Scaffold
   - SATOR Dissolve, SATOR Cross, Constellation, Particle Build
2. An `index.html` **already exists** at `~/manifold-deploy/index.html` on HOG — JetBrains Mono font, dark bg (#05080a), canvas animation, Georgia serif title, basic MANIFOLD page. ~12.3KB.
3. **Surge deploy is broken** — exit code 255 on every attempt from both Trillian and HOG. Non-interactive env var approach (`SURGE_LOGIN` / `SURGE_TOKEN`) also fails. The solar sphere deploy script (piped to log file) works, but direct SSH invocation hangs then 255s. This is likely a surge TTY/interactive auth issue on new domain claim.

---

## Blockers
- **Surge 255 bug:** The `npx surge . manifold.surge.sh` command always exits 255 regardless of how it's called. Possible causes:
  1. Surge v0.27.3 is broken for non-TTY sessions
  2. The domain `manifold.surge.sh` needs to be initially claimed through a TTY (interactive) session
  3. HOG cron deploy mechanism works because scripts use `>> log 2>&1` redirect — haven't confirmed if this actually succeeds either

---

## Next Steps (fresh session)
1. **Fix the deploy first** — two options:
   - A) SSH to HOG with PTY (`pty:true`) and run `npx surge . manifold.surge.sh` interactively
   - B) Trigger the HOG cron deploy script for manifold (if one exists) or add one similar to solarsphere
   - C) Use GitHub Pages instead — push to stellamariesays/Manifold and enable Pages
2. **Once deploy works** — build the actual page:
   - Inspect the BRAID intro style from https://solarwatch.surge.sh or existing BRAID splash (index.html on solarsites)
   - Inspiration: 10et Particle Build or Constellation animation style
   - Content: MANIFOLD mesh visualization — Sophia score, seams, agent density, node connections
   - Design language: dark, monospace, particles — same family as the solar sphere

---

## Key Files
- `~/manifold-deploy/index.html` on HOG — current WIP page (12.3KB, basic)
- BRAID splash: `~/solar-sphere/index.html` on HOG (particle sun animation for reference)
- 10et source: https://github.com/402goose/tenet-docs (per the heroes page)

---

## Load Order (Next Session)
1. `memory/terrain-delta.md`
2. `OPERATING.md`
3. This file
