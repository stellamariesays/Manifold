/**
 * hub-orbits.js — Polymorphic orbital path system for hub markers.
 *
 * Architecture
 * ────────────
 * An OrbitType defines how a hub moves through space:
 *
 *   {
 *     id:       string          — unique type key
 *     compute:  (t, params) => THREE.Vector3
 *                               — t is orbit-local time (seconds, already multiplied by speed)
 *                                 params is the hub's orbit param object
 *                                 returns world-space position
 *   }
 *
 * Orbit params per hub (stored in userData.orbitParams):
 *   type          string   — orbit type id (default: 'ellipse')
 *   speed         number   — angular speed multiplier (radians/sec)
 *   phase         number   — initial phase offset (radians)
 *   semiMajor     number   — semi-major axis (longest radius)
 *   semiMinor     number   — semi-minor axis (shortest radius)
 *   inclination   number   — tilt of orbital plane from XZ (radians)
 *                            0 = flat XZ plane, π/2 = vertical YX plane
 *   ascendingNode number   — rotation of orbital plane around Y axis (radians)
 *                            "where the orbit rises above the reference plane"
 *   yBob          number   — amplitude of sinusoidal Y bob (cosmetic, default 0.15)
 *   yBobFreq      number   — frequency multiplier for Y bob (default 1)
 *
 * Public API
 * ──────────
 *   registerOrbitType(orbitType)              — add / replace orbit type by id
 *   getOrbitType(id)                          — retrieve orbit type object
 *   getHubOrbitPosition(hubName, elapsed)     — compute world position for hub
 *   setHubOrbitParams(hubName, params)        — override params for a hub
 *   getHubOrbitParams(hubName)                — read current params
 *
 * Built-in orbit types
 * ────────────────────
 *   'ellipse'   — Keplerian-style ellipse in an inclined plane (default)
 *   'lissajous' — Lissajous figure (fun wiggly path)
 *   'figure8'   — figure-8 / lemniscate in an inclined plane
 */

import * as THREE from 'three';

// ── Registry ──────────────────────────────────────────────────────────────

const _orbitTypes = new Map();    // id → OrbitType
const _hubParams  = new Map();    // hubName → params

export function registerOrbitType(orbitType) {
  if (!orbitType || typeof orbitType.id !== 'string') {
    console.warn('[hub-orbits] registerOrbitType: orbitType.id must be a string');
    return;
  }
  _orbitTypes.set(orbitType.id, orbitType);
}

export function getOrbitType(id) {
  return _orbitTypes.get(id);
}

export function setHubOrbitParams(hubName, params) {
  _hubParams.set(hubName, { ...(_hubParams.get(hubName) ?? {}), ...params });
}

export function getHubOrbitParams(hubName) {
  return _hubParams.get(hubName) ?? null;
}

const _tmp = new THREE.Vector3();

/**
 * Compute the world-space position for hubName at time elapsed (seconds).
 * Falls back to origin if hub has no params or unknown orbit type.
 */
export function getHubOrbitPosition(hubName, elapsed) {
  const params = _hubParams.get(hubName);
  if (!params) return _tmp.set(0, 0, 0);

  const type = _orbitTypes.get(params.type ?? 'ellipse');
  if (!type) return _tmp.set(0, 0, 0);

  const t = elapsed * (params.speed ?? 0.06) + (params.phase ?? 0);
  return type.compute(t, params);
}

// ── Helpers ───────────────────────────────────────────────────────────────

/**
 * Apply inclination (tilt) and ascending node (rotation around Y) to a
 * point that was computed in the "flat" orbital plane (XZ).
 *
 * Steps:
 *   1. Tilt around X axis by inclination  →  point rises out of XZ plane
 *   2. Rotate around Y axis by ascendingNode  →  rotate the whole tilted orbit
 */
function _applyOrbitalPlane(x, y, z, inclination, ascendingNode) {
  // Step 1: tilt around X
  const ci = Math.cos(inclination);
  const si = Math.sin(inclination);
  const y1 = y * ci - z * si;
  const z1 = y * si + z * ci;

  // Step 2: rotate around Y
  const ca = Math.cos(ascendingNode);
  const sa = Math.sin(ascendingNode);
  const x2 = x * ca - z1 * sa;
  const z2 = x * sa + z1 * ca;

  return { x: x2, y: y1, z: z2 };
}

// ── Built-in: ellipse ─────────────────────────────────────────────────────

registerOrbitType({
  id: 'ellipse',
  /**
   * Elliptical orbit in an inclined plane.
   *
   * In the flat orbital plane:
   *   x_flat = semiMajor * cos(t)
   *   z_flat = semiMinor * sin(t)
   *   y_flat = yBob * sin(t * yBobFreq)   ← gentle bob within the plane
   *
   * Then _applyOrbitalPlane() tilts + rotates the whole thing.
   */
  compute(t, params) {
    const a   = params.semiMajor     ?? 8;
    const b   = params.semiMinor     ?? 5;
    const inc = params.inclination   ?? 0;
    const lan = params.ascendingNode ?? 0;
    const bob = params.yBob          ?? 0.15;
    const bf  = params.yBobFreq      ?? 1;

    const xf = a * Math.cos(t);
    const zf = b * Math.sin(t);
    const yf = bob * Math.sin(t * bf);

    const { x, y, z } = _applyOrbitalPlane(xf, yf, zf, inc, lan);
    return _tmp.set(x, y, z);
  },
});

// ── Built-in: lissajous ───────────────────────────────────────────────────

registerOrbitType({
  id: 'lissajous',
  /**
   * Lissajous curve — independent frequencies on each axis.
   *   x = semiMajor * cos(freqX * t + phaseX)
   *   y = yBob      * sin(freqY * t)
   *   z = semiMinor * sin(freqZ * t)
   *
   * Then tilted/rotated by inclination + ascendingNode.
   */
  compute(t, params) {
    const a    = params.semiMajor     ?? 8;
    const b    = params.semiMinor     ?? 5;
    const inc  = params.inclination   ?? 0;
    const lan  = params.ascendingNode ?? 0;
    const bob  = params.yBob          ?? 1.5;
    const fx   = params.freqX         ?? 1;
    const fy   = params.freqY         ?? 2;
    const fz   = params.freqZ         ?? 1;
    const px   = params.phaseX        ?? Math.PI / 2;

    const xf = a   * Math.cos(fx * t + px);
    const zf = b   * Math.sin(fz * t);
    const yf = bob * Math.sin(fy * t);

    const { x, y, z } = _applyOrbitalPlane(xf, yf, zf, inc, lan);
    return _tmp.set(x, y, z);
  },
});

// ── Built-in: figure8 ─────────────────────────────────────────────────────

registerOrbitType({
  id: 'figure8',
  /**
   * Lemniscate of Bernoulli — figure-8 in an inclined plane.
   *   r = sqrt(cos(2t)) (only defined where cos(2t) >= 0)
   *   x_flat = a * r * cos(t)
   *   z_flat = b * r * sin(t) * cos(t)   (flattened variant)
   */
  compute(t, params) {
    const a   = params.semiMajor     ?? 8;
    const b   = params.semiMinor     ?? 4;
    const inc = params.inclination   ?? 0;
    const lan = params.ascendingNode ?? 0;
    const bob = params.yBob          ?? 0.2;
    const bf  = params.yBobFreq      ?? 2;

    const cos2t = Math.cos(2 * t);
    const r = cos2t >= 0 ? Math.sqrt(cos2t) : 0;

    const xf = a * r * Math.cos(t);
    const zf = b * r * Math.sin(t) * Math.cos(t);
    const yf = bob * Math.sin(t * bf);

    const { x, y, z } = _applyOrbitalPlane(xf, yf, zf, inc, lan);
    return _tmp.set(x, y, z);
  },
});

// ── Default hub orbit params ───────────────────────────────────────────────
//
// Each hub gets a unique ellipse:
//   - different semi-axes (eccentricity)
//   - different inclinations (no hub is flat)
//   - different ascending nodes (spread around Y)
//   - different speeds and phases (no synchrony)
//
// Inclination key:
//   ~0.3 rad ≈ 17°  (gentle tilt)
//   ~0.6 rad ≈ 34°  (moderate)
//   ~1.0 rad ≈ 57°  (steep)
//   ~1.4 rad ≈ 80°  (near-vertical)
//
// Ascending node spreads orbits evenly around Y so they don't overlap.

setHubOrbitParams('hog', {
  type: 'ellipse',
  semiMajor:     18,
  semiMinor:     10,
  inclination:   0.35,
  ascendingNode: 0,
  speed:         0.0825,
  phase:         0,
  yBob:          0.2,
  yBobFreq:      1,
});

setHubOrbitParams('trillian', {
  type: 'ellipse',
  semiMajor:     14,
  semiMinor:     20,
  inclination:   0.65,
  ascendingNode: Math.PI * 0.6,
  speed:         0.063,
  phase:         Math.PI * 0.4,
  yBob:          0.25,
  yBobFreq:      1,
});

setHubOrbitParams('thefog', {
  type: 'ellipse',
  semiMajor:     22,
  semiMinor:     12,
  inclination:   1.05,
  ascendingNode: Math.PI * 1.2,
  speed:         0.057,
  phase:         Math.PI * 0.8,
  yBob:          0.3,
  yBobFreq:      1,
});

setHubOrbitParams('relay', {
  type: 'ellipse',
  semiMajor:     16,
  semiMinor:     8,
  inclination:   0.5,
  ascendingNode: Math.PI * 0.3,
  speed:         0.105,
  phase:         Math.PI * 1.2,
  yBob:          0.15,
  yBobFreq:      2,
});

setHubOrbitParams('bobiverse', {
  type: 'ellipse',
  semiMajor:     12,
  semiMinor:     18,
  inclination:   1.3,
  ascendingNode: Math.PI * 0.9,
  speed:         0.072,
  phase:         Math.PI * 1.6,
  yBob:          0.35,
  yBobFreq:      1,
});
