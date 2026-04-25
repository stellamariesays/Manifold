/**
 * fog-behaviors.js — Polymorphic behavior system for the central fog (constraint system).
 *
 * Architecture
 * ────────────
 * A FogBehavior is a plain object:
 *
 *   {
 *     id:       string          — unique key, used to register / remove
 *     enabled:  boolean         — can be toggled without removal
 *     weight:   number          — 0–1, blends this behavior's output (default 1)
 *     update:   (ctx) => void   — called every animation frame
 *   }
 *
 * ctx passed to update():
 *   {
 *     elapsed:   number          — seconds since page load
 *     delta:     number          — seconds since last frame
 *     system:    object          — window._constraintSystem
 *     hubGroups: THREE.Group[]   — only the isOrbitingHub groups from agentGroups
 *     THREE:     THREE           — three.js namespace
 *   }
 *
 * Public API
 * ──────────
 *   registerFogBehavior(behavior)         — add / replace behavior by id
 *   unregisterFogBehavior(id)             — remove by id
 *   setFogBehaviorEnabled(id, bool)       — toggle without removing
 *   setFogBehaviorWeight(id, weight)      — 0–1 blend factor
 *   runFogBehaviors(elapsed, delta)       — called once per frame by animation.js
 *   getFogBehaviors()                     — inspect the registry
 *
 * Built-in behaviors (registered automatically on module load)
 * ─────────────────────────────────────────────────────────────
 *   "follow-hub-centroid"   — fog drifts toward the mean world position of all
 *                             orbiting hub markers (smooth lerp, configurable)
 */

import * as THREE from 'three';
import { agentGroups } from './scene.js';

// ── Registry ──────────────────────────────────────────────────────────────

const _registry = new Map();   // id → behavior object
let _lastElapsed = 0;

export function registerFogBehavior(behavior) {
  if (!behavior || typeof behavior.id !== 'string') {
    console.warn('[fog-behaviors] registerFogBehavior: behavior.id must be a string');
    return;
  }
  _registry.set(behavior.id, {
    enabled: true,
    weight: 1,
    ...behavior,
  });
}

export function unregisterFogBehavior(id) {
  _registry.delete(id);
}

export function setFogBehaviorEnabled(id, enabled) {
  const b = _registry.get(id);
  if (b) b.enabled = enabled;
}

export function setFogBehaviorWeight(id, weight) {
  const b = _registry.get(id);
  if (b) b.weight = Math.max(0, Math.min(1, weight));
}

export function getFogBehaviors() {
  return Array.from(_registry.values());
}

// ── Frame runner ──────────────────────────────────────────────────────────

export function runFogBehaviors(elapsed) {
  const system = window._constraintSystem;
  if (!system) return;

  const delta = elapsed - _lastElapsed;
  _lastElapsed = elapsed;

  // Collect only the hub marker groups (isOrbitingHub)
  const hubGroups = agentGroups.filter(g => g.userData && g.userData.isOrbitingHub);

  const ctx = {
    elapsed,
    delta: Math.min(delta, 0.1),   // clamp to avoid huge jumps after tab focus
    system,
    hubGroups,
    THREE,
  };

  _registry.forEach(behavior => {
    if (!behavior.enabled || behavior.weight <= 0) return;
    try {
      behavior.update(ctx);
    } catch (err) {
      console.error(`[fog-behaviors] error in behavior "${behavior.id}":`, err);
    }
  });
}

// ── Built-in: follow-hub-centroid ─────────────────────────────────────────

/**
 * Smoothly moves the fog group toward the weighted centroid of all orbiting
 * hub markers.
 *
 * Config (editable on the behavior object after registration):
 *   lerpSpeed     number   0–1  How quickly the fog chases the centroid (0.02 = slow)
 *   yScale        number        Vertical influence factor (0 = fog ignores Y of hubs)
 *   maxDrift      number        Maximum displacement from scene origin in any axis
 *   basePosition  Vector3       The "rest" position the fog returns to when no hubs exist
 */
const followHubCentroid = {
  id: 'follow-hub-centroid',
  lerpSpeed: 0.02,       // tune: higher = snappier chase
  yScale: 0.3,           // hubs orbit at various heights; damp vertical pull
  maxDrift: 4.0,         // scene units — fog won't wander too far from origin
  basePosition: new THREE.Vector3(0, 1, 0),

  update(ctx) {
    const { system, hubGroups, THREE } = ctx;

    if (hubGroups.length === 0) return;

    // Compute centroid of all orbiting hub markers
    const centroid = new THREE.Vector3();
    hubGroups.forEach(hub => centroid.add(hub.position));
    centroid.divideScalar(hubGroups.length);

    // Apply yScale to reduce vertical thrash
    centroid.y = this.basePosition.y + (centroid.y - this.basePosition.y) * this.yScale;

    // Clamp to maxDrift radius from scene origin
    if (centroid.length() > this.maxDrift) {
      centroid.normalize().multiplyScalar(this.maxDrift);
    }

    // Blend weight: if behavior.weight < 1, interpolate toward a proportional target
    const speed = this.lerpSpeed * (ctx.delta * 60) * (this.weight ?? 1);

    system.group.position.lerp(centroid, Math.min(speed, 1));
  },
};

// Register on module load
registerFogBehavior(followHubCentroid);
