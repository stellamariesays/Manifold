# Context Handoff — 2026-03-31 09:15 WITA
**Session hit 99% context. Resume from here.**

---

## Session Summary
Solar sphere (solarsphere.surge.sh / globe.html) — heavy UI work this session.

---

## What Was Done (this session)

### 1. Carrington far-side fix (renderOrder)
- **Root cause:** Globe sphere is `transparent: true, opacity: 0.80` → in THREE.js transparent pass. Far-side markers sorted back-to-front, sphere rendered OVER them.
- **Fix:** `renderOrder = 999` on all far-side Carrington markers + track ghost dots/arcs. Also bumped far-side opacity 0.18→0.32.
- **Commit:** `f6ff0d4` — "Fix Carrington far-side: renderOrder=999 forces draw after transparent sphere"

### 2. SolarWatch iframe fix
- Was pointing at `solarsphere.surge.sh` (splash page — needs click to enter).
- **Fix:** Changed to `solarsphere.surge.sh/globe.html?embed=1` — loads globe directly.
- **File:** `scripts/solar/generate_watch_site.py` line 917
- **Commit:** `12b7bd3` — "solarwatch: load globe.html directly, not splash index"

### 3. BRAID IDs (B1, B26) as primary labels
- `arLabel()` now returns `B1` from `BRAID-00001`, `H{harp_num}` fallback.
- Popup: B-label in header, `HARP 13377 · NOAA AR 14401` as secondary context row, BRAID ID no longer redundantly shown in body.
- CME sim notification updated to use `arLabel(ar)`.
- **Commit:** `a9f308d`

### 4. Carrington orbit rings (rotation projection)
- Each BR now shows: near-side arc (bright, lon ∈ [-90,+90]) + far-side arc (dim, lon ∈ [90,270]) + dot at current position.
- Lets you track each BR as it rotates past Earth, behind the sun, and back.
- **Commit:** `2dce3a1`

---

## Carrington Coordinate System (verified correct)
- `ar_registry.py` formula: `cl_ar = (cl_earth + lon_fwt) % 360`
- Correct L0: `L0 = cl_ar - lon_fwt = carrington_lon - lon_fwt` (NOT lon_fwt + carrington_lon)
- Correct current_lon: `carrington_lon - L0`
- `carrington-gen.py` already uses the correct formula (comment: "BRAID formula: CL_AR = L0 + lon_fwt → L0 = CL_AR - lon_fwt")
- Verified: all active HARPs match live lon_fwt within ±0.1°

---

## Carrington Color
- Uses cluster colors for ALL HARPs (active + historical) — no more amber for historical
- `baseHex = display_prob ? probColor() : COLORS[cluster_label] || '#5588aa'`

---

## Additional Fixes (same session, after handoff)

### 5. Carrington opacity fix
- Root cause: orbit rings (transparent, renderOrder=8) render in transparent pass AFTER opaque dots, blending over them at 30% → dots looked dim
- Fix: near-side dots now `transparent:true, opacity:1.0, renderOrder:50` — renders after rings in transparent pass, depth test restores full opacity
- Commit: `1c3326e`

### 6. JSOC 28-day backfill in carrington-gen.py
- Used `drms` library to query `hmi.sharp_720s_nrt[][start/28d@1d]`
- Computes Carrington lon from T_REC timestamp + LON_FWT using Carrington rotation formula
- Result: 47 → 87 HARPs, coverage 224° → 346° (gap: 135° → 13.8°)
- `drms` installed in `~/solar-venv` — runs via deploy cron
- carrington-gen.py updated on HOG (not in git — solar-collector has no git repo)

## Pending (from this session)
- Hal asked about the orbit rings — check if visually clear after he reviews
- The 90° position discrepancy Hal mentioned is resolved (coordinate formula was already fixed, was stale data earlier)

---

## Deploy State
- `solarsphere.surge.sh/globe.html` — current as of 01:13 UTC March 31
- `solarwatch.surge.sh` — current, points to globe.html directly
- HOG cron deploys solarsites repo every 15 min

---

## Load Order (Next Session)
1. `memory/terrain-delta.md`
2. `OPERATING.md`
3. This file (`memory/2026-03-31-0915-context-handoff.md`)
4. `memory/2026-03-31.md` (if written)
