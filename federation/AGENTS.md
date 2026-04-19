# Manifold Federation — Coding Agent Guide

## Project Overview
Manifold is a federated mesh network for AI agents. Agents register capabilities, route tasks, and coordinate across hubs.

## Architecture
- **TypeScript** source in `src/` — compiled to `dist/` via `tsc --build`
- **Python** agent runner in `src/runtime/agent-runner.py`
- **Tests**: `vitest` in `tests/` — run with `npx vitest run` (individual: `npx vitest run tests/X.test.ts`)
- **⚠️ Pi has limited RAM (~4GB)** — running the full test suite at once causes OOM. Test individual files.
- After any code change, run `npm run build` to update `dist/` (the server loads from dist)

## Key Files
- `src/server/index.ts` — ManifoldServer (main server class)
- `src/server/rest-api.ts` — Express REST API endpoints
- `src/server/capability-index.ts` — In-memory agent/capability tracking
- `src/server/task-router.ts` — Task routing and execution
- `src/server/mesh-sync.ts` — Inter-hub mesh state sync
- `src/protocol/messages.ts` — All protocol message types
- `src/shared/types.ts` — Shared interfaces (AgentResult, etc.)
- `src/identity/` — MeshPass cryptographic identity (Phase 1)
- `src/gate/` — The Gate authentication gateway (Phase 1)
- `standalone.mts` — Server entry point (loads from dist/)

## Code Style
- TypeScript strict mode
- Classes with private/public methods
- No external crypto deps beyond Node built-ins (for identity, uses @noble/ed25519 and scrypt)
- Logs use `this.log()` pattern (prefixes with hub name)
- REST handlers follow `_methodName(req, res)` pattern

## Current State (2026-04-19)
- Phase 1 (MeshPass Identity) is complete and merged
- 168 unit tests pass
- Live federation running: satelliteA, HOG, thefog hubs
- 22 agents registered across 3 hubs
- Task routing works end-to-end
