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
| `nexal.js` | **Entry point / Orchestrator** — imports all modules, calls `init()`, `loadAgentsAndBuild()`, wires bridge event handlers. Only file that imports both layers. |
| `bridge.js` | **Event bus** — the ONLY communication channel between 3D and 2D. Zero imports. `emit/on/off`. |
| `geometry.js` | `makeKleinBottleGeometry`, `makeMobiusStripGeometry` — 3D layer only |
| `scene.js` | `init()`, `buildSpiderWeb()`, `buildAgentTopologies()`, `buildCentralNexus()`, `CONSTRAINT_CONFIG` — 3D layer only |
| `animation.js` | `animate()`, `animateDataHighways()`, `createDataPulse()` — 3D layer only |
| `ui.js` | `updateAgentsList()`, `updateStatusPanel()`, `showAgentDetails()`, `showHubDetails()`, `hideDetailPanel()` — 2D layer only |
| `data.js` | `loadAgentsAndBuild()` — fetches `/api/mesh`, falls back to demo agents, emits `mesh-updated` on bridge |

**Global state** (by convention, on `window`): `THREE`, `camera`, `cameraControls`, `isMobile`, `mobileBrightnessBoost`, `agentGroups`, `hubCenters`, `_webGroup`, `_webRings`, `_dataHighways`, `_constraintSystem`, `_meshData`, `_createDataPulse`. Note: `_renderer`, `_camera`, `_scene` are no longer on window — use `getRenderer()`, `getCamera()`, `getScene()` exported from scene.js.

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

## 3D/2D Boundary

The Nexal UI has a strict architectural boundary between its 3D rendering layer
and its 2D HUD layer. This enables parallel development without collisions.

### What is bridge.js?

`public/nexal/bridge.js` is a lightweight EventEmitter that is the **only**
communication channel between the 3D and 2D layers. Neither layer imports the
other — they only import `bridge` and talk via events.

This means Stella can edit `ui.js` at the same time Eddie edits `scene.js`
without merge conflicts or accidental coupling.

### Which files belong to which layer?

| File | Layer | Rule |
|------|-------|------|
| `scene.js` | **3D only** | May touch `document.getElementById('scene')` for the canvas. No other DOM. No ui.js imports. |
| `animation.js` | **3D only** | No DOM touches. No ui.js imports. |
| `geometry.js` | **3D only** | Pure math + Three.js. No DOM, no bridge, no ui. |
| `ui.js` | **2D only** | Pure DOM manipulation. No Three.js imports. No scene/animation imports. |
| `bridge.js` | **Neutral** | Zero imports. Pure EventEmitter. |
| `data.js` | **Neutral** | Fetches data, emits `mesh-updated` on bridge. No Three.js, no DOM (except via bridge). |
| `nexal.js` | **Orchestrator** | The ONLY file that imports from both layers. Wires bridge listeners. |

### The Rule

> **Never import across the boundary. Always use bridge.**

If the 3D layer needs to tell the 2D layer something (e.g. user clicked an
agent), it calls `bridge.emit('agent-selected', { agent })`. The 2D layer
has a listener registered in `nexal.js` that calls `showAgentDetails(agent)`.

If the 2D layer needs to tell the 3D layer something (e.g. highlight an agent),
it calls `bridge.emit('highlight-agent', { agentId })`. The 3D layer has a
listener in `nexal.js`.

### Defined bridge events

**3D → 2D (3D layer emits, 2D layer listens):**
- `agent-selected` — payload: `{ agent }` — user clicked an agent mesh
- `hub-hovered` — payload: `{ hub }` — user clicked a hub marker
- `mesh-updated` — payload: `{ agents }` — data loaded, populate the HUD
- `frame` — payload: `{ elapsed }` — each animation frame (optional)

**2D → 3D (2D layer emits, 3D layer listens):**
- `panel-closed` — user dismissed the detail panel
- `highlight-agent` — payload: `{ agentId }` — 2D requests 3D highlight

### How to add a new cross-layer interaction

1. **Decide direction**: is 3D telling 2D, or 2D telling 3D?
2. **Pick a name**: lowercase-kebab, descriptive (e.g. `'fog-pulse-started'`)
3. **Emit in the source layer** with a payload
4. **Register a listener in nexal.js** that routes the event to the target layer
5. **Add a boundary.test.js assertion** if it's a new import that would violate the boundary
6. **Document the event** in the bridge.js comment block at the top

Example — 3D layer wants to tell 2D that a data pulse completed:
```js
// In animation.js (3D layer):
import { bridge } from './bridge.js';
bridge.emit('pulse-completed', { capability: capabilityName, destHub });

// In nexal.js (orchestrator):
bridge.on('pulse-completed', ({ capability, destHub }) => {
  showPulseNotification(capability, destHub); // ui.js function
});
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
