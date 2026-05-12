# Numinous

Functional memory layer for the Manifold mesh.

## Why

Agents waste tokens brute-forcing infrastructure questions. "Where's Sophia? What IP? What SSH key?" — the answers exist in terrain files, but nobody reads them first.

Numinous fixes the loop. Pure functions, immutable terrain, typed queries. One command gets you the answer. Zero tokens wasted.

## Design

- **Immutable terrain** — every transform returns a new Terrain, original untouched
- **Typed schema** — Machine, Agent, Project, Decision. If it doesn't type-check, it doesn't exist.
- **Pure queries** — `(terrain) → result`. No side effects. Composable.
- **Audit trail** — every change recorded as a TerrainChange with who, what, when, why.
- **CLI** — agents can call `numinous ssh thefog` and get the answer immediately.

## Usage

```bash
# Full mesh status
numinous status

# SSH command + context for a machine
numinous ssh thefog
numinous ssh hog

# Full context for an agent
numinous context eddie
numinous context sophia

# What's blocked?
numinous blockers

# Find anything by name
numinous query thefog
numinous query braid
numinous query "Manifold Federation"

# Raw JSON dump
numinous json
```

## Architecture

```
numinous/
  src/
    terrain/
      schema.ts      — Pure type definitions (Machine, Agent, Project, Terrain)
      loader.ts      — Pure functions to load terrain from disk
      query.ts       — Pure composable query functions
      transform.ts   — Pure immutable transforms with change tracking
    cli.ts           — CLI interface
    index.ts         — Library exports
```

## As a Library

```typescript
import { loadTerrain, Query, Transform } from 'numinous';

const terrain = loadTerrain('./memory');

// Query: where's sophia?
const ctx = Query.getSSHContext('thefog')(terrain);
console.log(ctx.command);  // ssh -i ~/.ssh/id_ed25519_trillian sophia@192.168.64.5

// Transform: update a machine (returns new terrain, original unchanged)
const { terrain: updated, changes } = Transform.updateMachine(
  'thefog',
  { status: 'live' },
  'stella'
)(terrain);

// changes = [{ op: 'update', path: 'machines.thefog.status', from: 'unknown', to: 'live', ... }]
```

## Build

```bash
cd numinous
npm install
npm run build
```

## Principles

1. **Read before act** — always check terrain before attempting infrastructure tasks
2. **Update after learn** — if you discover something not in terrain, update and push
3. **Immutable by default** — transforms return new state, never mutate
4. **Type-safe** — the schema is the contract
5. **Composable** — query functions compose: `getAgentsByHub('hog')(getLiveMachines(terrain))`

## What's Next

- [ ] io-ts runtime validation (parse-time type checking, not just compile-time)
- [ ] Auto-sync terrain to git after transforms
- [ ] Terrain diff command (what changed between two states)
- [ ] Federation protocol integration (live terrain from mesh, not just files)
- [ ] Skill wrapper so any OpenClaw agent can `numinous query <x>` natively
