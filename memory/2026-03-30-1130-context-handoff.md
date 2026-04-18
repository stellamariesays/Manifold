# Context Handoff — 2026-03-30 11:30 WITA

## Why this exists
Main session hit 92%+ context. Handing off to fresh session.

## What this session did
- Fixed SolarSphere deploy architecture: HOG cron pulls from GitHub solarsites repo; Trillian workspace changes must go there to survive. Restored BRAID splash (index.html) → ENTER → globe.html structure.
- Flare animation v3: dual ribbons, loop arcade, EIT wave, white-hot particles.
- Redesigned BRAID splash: particles now attract to cursor, form sun shape (core + ring + 8 rays) around mouse.
- Terrain-delta and daily log (2026-03-30.md) updated.

## Pending task
**Redesign all solar sites.** Brief at: `data/research/2026-03-30-solar-sites-redesign.md`

Read that file first. It has everything: design system, per-site specs, deploy workflow, accurate BRAID metrics.

## Key files to read on startup
1. `memory/terrain-delta.md`
2. `OPERATING.md`
3. `data/research/2026-03-30-solar-sites-redesign.md` ← the brief

## Groq migration still blocked
- Config: `groq:default` profile added, primary model `groq/llama-3.3-70b-versatile`
- Blocker: apiKey in auth profile returns "invalid config" on config.patch
- Groq key was shared in group chat — needs rotation once stable
- Not urgent if Anthropic is working

## SSH to HOG
`ssh -i ~/.ssh/id_ed25519 marvin@100.70.172.34`

## Surge token
`161326cdb6cb122b5efbf71f9e8f4dce`

## Deploy: solarsphere (sphere only — HOG cron handles this)
- index.html = splash, globe.html = sphere
- HOG cron deploys from ~/solarsites GitHub repo every 15min
- Push changes to GitHub repo on HOG, not directly to surge
