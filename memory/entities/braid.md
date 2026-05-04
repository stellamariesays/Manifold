# BRAID — Entity Record

**Type:** Solar prediction system (built by Stella + Hal)
**Named:** 2026-03-22
**Status:** Live, active development

---

## What It Is

BRAID is a topology-based solar flare classifier. The name references Parker's magnetic braiding mechanism — field lines braid and tangle in the corona, stress accumulates, energy releases as a flare.

**One-sentence framing:** *"Not a flare predictor. A topology classifier."*

**What makes it different from NOAA:**
- Standard models: correlate raw SHARP parameters with historical flare rates → disk-averaged probability
- BRAID: clusters active regions into discrete topological states (CHARGED / ACTIVE / IDLE), assigns per-region probability based on state + centroid distance
- A single CHARGED AR outweighs a quiet disk

---

## Performance (post-Optuna, 2026-03-23 — deployed)

| Model | TSS | AUC | POD | FAR |
|-------|-----|-----|-----|-----|
| XGB tuned | 0.727 | 0.909 | 83.9% | 77.8% |
| RF tuned | 0.732 | 0.904 | 81.9% | 77.1% |
| Persistence baseline | 0.670 | — | — | — |

AR-grouped split confirms leakage negligible. FAR is structural (not tuning-solvable at this training scale).

> Full results + params: `data/research/2026-03-23-braid-build-session.md`

---

## Current State (2026-03-23)

**Working:**
- Per-AR topology classification and probability display
- Live updates every 6h via system cron
- Full BRAID branding on solarwatch.surge.sh
- BRAID explainer card, Space Weather card, HMI disk view

**Known issue:** Overall status banner shows raw-averaged probability rather than BRAID-modulated value. Fix is in `flare_probability()` in `generate_watch_site.py` (lines ~47–70).

**Step 2 (2026-03-24):** Lifecycle memory layer added — temporal AR trajectory modeling, recharge arc analysis. See `data/research/2026-03-24-braid-lifecycle-layer.md`.

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/solar/generate_watch_site.py` | Main site generator |
| `scripts/solar/realtime-monitor.py` | Fetches live SHARP + SWPC data |
| `scripts/solar/train_classifier.py` | Model training pipeline |
| `scripts/solar/update-solarwatch.sh` | Full update cycle (monitor → generate → deploy) |
| `data/solar/models/` | Trained models |
| `data/solar/realtime-state.json` | Current live AR state |
| `data/solar/optuna-best-params.json` | Best Optuna hyperparameters |

**Sites:** https://solarwatch.surge.sh | https://solarguard.surge.sh | https://solarintel.surge.sh

---

## Next Steps (Hal directive, 2026-03-21)

- **FAR reduction:** v3 delta features + Optuna on PR-AUC objective + multi-step confirmation
- **Cycle 24 dataset:** `fetch_cycle24.py` running — merge + retrain when complete
- **Star replication:** Apply BRAID pipeline to α Cen A/B, Proxima Cen, ε Eridani, τ Ceti
- **NIAC framing:** multi-star validation → evidence base for active region intervention

---

> Deep build history, SHARP parameter table, topology physics: `data/research/2026-03-braid-entity-detail.md`
