/**
 * Numinous — Functional memory layer for Manifold mesh agents.
 * 
 * Exports pure functions for querying and transforming terrain.
 * No IO here — this is the library interface.
 * CLI is in cli.ts.
 */

export { loadTerrain } from './terrain/loader.js';
export * as Query from './terrain/query.js';
export * as Transform from './terrain/transform.js';
export type * from './terrain/schema.js';
