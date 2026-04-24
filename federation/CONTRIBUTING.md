# Contributing to Manifold Federation

Welcome. This doc covers the module map, how to add routes, how to work on the
Nexal UI, and what Stella needs to know to work on this repo over the weekend
without stepping on Eddie's work.

---

## Module Map

### Server — `src/server/`

| File | Responsibility |
|------|---------------|
| `rest-api.ts` | **Entry point** — lifecycle (start/stop), wiring of all route modules. Edit this only if you need to change startup order or add a new router. |
| `routes/nexal.ts` | Public nexal/topology UI handlers (`/nexal`, `/nexal_test`, `/topology`, etc.) |
| `routes/agents.ts` | Agent register / heartbeat / deregister / list / get |
| `routes/tasks.ts` | Task submit / status / pending / history + legacy `/query` and `/route` |
| `routes/attestation.ts` | All `/attestation/*` and `/registration/*` endpoints |
| `routes/detection.ts` | All `/detection*` and `/detections*` and `/trust` endpoints |
| `routes/mesh.ts` | `/mesh`, `/peers`, `/capabilities`, `/dark-circles`, `/status`, `/metrics`, `/gossip` |
| `routes/teacups.ts` | `/teacups` and `/teacup/:id/score` |
| `routes/dashboard.ts` | `GET /dashboard` — HTML overview, inline template |
| `capability-index.ts` | Capability registry and bloom filter |
| `peer-registry.ts` | Peer tracking |
| `mesh-sync.ts` | Cross-hub state sync |
| `task-router.ts` | Task dispatch and lifecycle |
| `task-history.ts` | Persistent task record |
| `metrics.ts` | Metrics collection |
| `detection-coord.ts` | Detection claim coordination |
| `security.ts` | API key auth, rate limiting |
| `signing-middleware.ts` | Request signing |

### Nexal UI — `public/nexal/`

| File | Responsibility |
|------|---------------|
| `index.html` | HTML skeleton, CSS, importmap. No inline JS. |
| `nexal.js` | **Entry point** — imports all modules, calls `init()`, `loadAgentsAndBuild()`, wires event handlers. |
| `geometry.js` | `makeKleinBottleGeometry`, `makeMobiusStripGeometry` |
| `scene.js` | `init()`, `buildSpiderWeb()`, `buildAgentTopologies()`, `buildCentralNexus()`, `CONSTRAINT_CONFIG` |
| `animation.js` | `animate()`, `animateDataHighways()`, `createDataPulse()` |
| `ui.js` | `updateAgentsList()`, `updateStatusPanel()`, `showAgentDetails()`, `showHubDetails()`, `hideDetailPanel()` |
| `data.js` | `loadAgentsAndBuild()` — fetches `/api/mesh`, falls back to demo agents |

**Global state** (by convention, on `window`): `THREE`, `camera`, `cameraControls`, `isMobile`, `mobileBrightnessBoost`, `agentGroups`, `hubCenters`, `_webGroup`, `_webRings`, `_dataHighways`, `_constraintSystem`, `_meshData`, `_renderer`, `_createDataPulse`.

**Important**: modules are standard ES modules. The importmap in index.html maps `"three"` to the unpkg CDN build. All imports use bare specifier `'three'` or relative paths like `'./geometry.js'`.

---

## How to Add a Route

1. Pick or create the right file under `src/server/routes/`.
2. Add a handler function (plain function, not a class method).
3. Register it in the `buildXxxRouter()` function's router.
4. The `deps` object is wired in `rest-api.ts` `_setup()` — add whatever you need from there.
5. Run `npm run build` to verify no TS errors.

Example — adding `GET /widgets`:

```typescript
// src/server/routes/mesh.ts (or a new widgets.ts)
router.get('/widgets', (req, res) => _widgets(req, res, deps))

function _widgets(_req: Request, res: Response, { capIndex }: MeshRouterDeps): void {
  res.json({ widgets: capIndex.getAllAgents().map(a => a.name) })
}
```

Then in `rest-api.ts` if you made a new file:
```typescript
import { buildWidgetsRouter } from './routes/widgets.js'
// ... in _setup():
buildWidgetsRouter(router, { get capIndex() { return self.capIndex } })
```

---

## How to Work on Nexal UI

All JS is now in `public/nexal/*.js` as ES modules. The server serves the
`public/` directory as static files — just save and reload the browser.

**No build step** for the UI. Changes are live instantly.

**Deploying to relay VPS** (for live nexal.network):
```bash
scp -o StrictHostKeyChecking=no \
  /home/marvin/projects/manifold/federation/public/nexal/index.html \
  root@100.126.234.73:/opt/Manifold/federation/public/nexal/index.html
```
*(Note: the relay reads index.html on each request. The JS module files are
served statically from the same public/nexal/ dir. When you add new .js files,
you need to scp them too, or sync the whole directory.)*

For geometry changes: edit `geometry.js`.
For adding a new animation: edit `animation.js`, export the function, import in `nexal.js`.
For new HUD panels: edit `ui.js` and add the DOM in `index.html`.

---

## Build & Test

```bash
# TypeScript compile (required after any .ts change)
npm run build

# Run tests
npm test

# Start local hub (hog config)
./start-hog.sh

# Start local hub (satellite A)
./start-satelitea.sh
```

Build output goes to `dist/`. The server entry point is `dist/server/index.js`.

---

## What Stella Should Know

- **Eddie owns**: TypeScript server code, `dist/`, deployment scripts, relay config.
- **Stella owns**: Nexal UI JS (`public/nexal/*.js`), visual design, UX, HTML.
- **Shared**: `index.html` structure (coordinate if changing), `CONTRIBUTING.md`.

**Do not** edit `public/nexal/index.html.bak*` or `*.backup` — they're deleted
and covered by `.gitignore`. Start fresh from `index.html`.

**Detection ledger files** live in `data/detection-ledger-*.jsonl` (gitignored).
Don't commit them.

**The relay VPS** at `100.126.234.73` runs a separate install at `/opt/Manifold/`.
Do not touch server code there. Only push `public/nexal/` HTML/JS files.

---

## Repo Structure Quick Reference

```
federation/
├── src/
│   ├── server/
│   │   ├── rest-api.ts          # Bootstrap/wiring
│   │   ├── routes/              # One file per domain
│   │   └── *.ts                 # Core services
│   ├── protocol/                # Message types
│   └── attestation/             # Attestation engine
├── public/
│   └── nexal/                   # 3D visualization UI
│       ├── index.html
│       ├── nexal.js             # Entry point
│       ├── scene.js
│       ├── animation.js
│       ├── geometry.js
│       ├── ui.js
│       └── data.js
├── dist/                        # Build output (gitignored)
├── data/                        # Runtime data (mostly gitignored)
├── tests/                       # Vitest test suite
└── docs/                        # Architecture docs
```
