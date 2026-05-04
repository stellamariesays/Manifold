# thefog cron fix — 2026-04-16

## Problem
Sophia's thefog (100.124.38.123) loaded 0 cron jobs after first boot. Reach-scan heartbeat wasn't running.

## Root cause
The original `jobs.json` had a legacy format job — used `jobId` field instead of `id`, and had no `state` object. On boot:
1. Cron subsystem loaded the legacy job, normalized `jobId` → `id` in memory
2. Crashed: `TypeError: Cannot read properties of undefined (reading 'runningAtMs')` — tried to access `state.runningAtMs` when `state` was undefined
3. Crash path wrote back empty store: `{"version":1,"jobs":[]}`
4. Every subsequent restart re-triggered the wipe cycle

## Fix applied
- Restored job from `jobs.json.bak` (had the legacy format)
- Gateway normalized it on load — wrote canonical format with proper `state` object
- Restarted gateway: `cron: started, jobs:1` ✓

## Upstream issue
OpenClaw cron subsystem doesn't tolerate missing `state` on jobs and writes empty store on crash. Should either:
- Default missing `state` to `{}`
- Skip store write on initialization error

## Teacup
Sophia's cron was wiping itself on every boot — legacy job format crashed the loader, which wrote an empty store as it died. Fixed by restore + gateway normalization. Upstream should handle missing `state` gracefully.
