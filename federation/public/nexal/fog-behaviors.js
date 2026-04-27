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
let _lastElapsed = null;       // null = not yet initialized (skip first frame)

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

  // Skip first frame to avoid huge delta spike (elapsed since page load)
  if (_lastElapsed === null) { _lastElapsed = elapsed; return; }

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
 * Smoothly moves the fog group toward a weighted attractor derived from the
 * orbiting hub markers.
 *
 * mode: 'centroid'  — pull toward mean position of all hubs (subtle, near-origin)
 * mode: 'nearest'   — pull toward the single closest hub to fog's current position
 * mode: 'named'     — pull toward a specific named hub (see primaryHub)
 * mode: 'weighted'  — weighted sum: each hub contributes inverse-distance weight
 *
 * Config (editable on the behavior object after registration):
 *   mode          string   'weighted' | 'centroid' | 'nearest' | 'named'
 *   primaryHub    string   hub name for 'named' mode (default: 'thefog')
 *   lerpSpeed     number   0–1  How quickly the fog chases the target (0.04 default)
 *   yScale        number        Vertical influence factor (0 = fog ignores Y of hubs)
 *   maxDrift      number        Maximum displacement from scene origin in any axis
 *   basePosition  Vector3       The "rest" position the fog returns to when no hubs exist
 */
const followHubCentroid = {
  id: 'follow-hub-centroid',
  mode: 'named',         // track Sophia's hub (thefog) directly
  primaryHub: 'thefog',
  lerpSpeed: 0.015,      // gentle chase — fog lags behind hub noticeably
  yScale: 0.2,           // damp vertical pull significantly
  maxDrift: 2.5,         // scene units from basePosition — subtle drift only
  basePosition: new THREE.Vector3(0, 1, 0),

  _target: new THREE.Vector3(0, 1, 0),  // reused each frame

  update(ctx) {
    const { system, hubGroups } = ctx;

    if (hubGroups.length === 0) return;

    const fogPos = system.group.position;
    const target = this._target;
    target.copy(this.basePosition);

    if (this.mode === 'centroid') {
      // Simple mean — tends to stay near origin when hubs are symmetric
      target.set(0, 0, 0);
      hubGroups.forEach(hub => target.add(hub.position));
      target.divideScalar(hubGroups.length);

    } else if (this.mode === 'nearest') {
      // Closest hub — fog snaps toward whichever hub is nearest
      let minDist = Infinity;
      hubGroups.forEach(hub => {
        const d = fogPos.distanceTo(hub.position);
        if (d < minDist) { minDist = d; target.copy(hub.position); }
      });

    } else if (this.mode === 'named') {
      // Follow a specific named hub
      const named = hubGroups.find(h => h.userData.hubName === this.primaryHub);
      if (named) target.copy(named.position);
      else {
        // fallback to centroid
        target.set(0, 0, 0);
        hubGroups.forEach(hub => target.add(hub.position));
        target.divideScalar(hubGroups.length);
      }

    } else {
      // 'weighted' — inverse-distance weighting from fog center
      // Hubs closer to the fog pull harder; produces visible drift
      target.set(0, 0, 0);
      let totalWeight = 0;
      hubGroups.forEach(hub => {
        const d = Math.max(fogPos.distanceTo(hub.position), 0.5);
        const w = 1 / (d * d);   // inverse-square: strong pull when close
        target.addScaledVector(hub.position, w);
        totalWeight += w;
      });
      if (totalWeight > 0) target.divideScalar(totalWeight);
    }

    // Scale the target displacement — don't chase the hub all the way there,
    // just drift toward it by a fraction (maxDrift controls how far from base)
    const displacement = target.clone().sub(this.basePosition);
    const dispLen = displacement.length();
    if (dispLen > 0) {
      const scale = Math.min(dispLen, this.maxDrift) / dispLen;
      target.copy(this.basePosition).addScaledVector(displacement, scale * 0.25);
    }

    // Apply yScale — reduce vertical thrash
    target.y = this.basePosition.y + (target.y - this.basePosition.y) * this.yScale;

    // Smooth chase
    const speed = this.lerpSpeed * (ctx.delta * 60) * (this.weight ?? 1);
    fogPos.lerp(target, Math.min(speed, 1));

    // Hard clamp: never let the fog stray more than maxDrift from basePosition
    const actualDisp = fogPos.clone().sub(this.basePosition);
    if (actualDisp.length() > this.maxDrift) {
      fogPos.copy(this.basePosition).addScaledVector(actualDisp.normalize(), this.maxDrift);
    }
  },
};

// Register on module load (disabled — pulse-to-sophia handles group movement)
registerFogBehavior({ ...followHubCentroid, enabled: false });

// ── Built-in: pulse-to-sophia ─────────────────────────────────────────────

/**
 * Every ~0.5s, lerps the entire fog GROUP toward Sophia's current orbital
 * position, then lerps back to base. No per-node math — just moves the group.
 *
 * Config:
 *   pullFraction  0–1   How far toward Sophia to move (0.3 = 30% of the way)
 *   cyclePeriod   secs  Full out-and-back period
 *   stretchRatio  0–1   Fraction of cycle spent moving out (rest = returning)
 */
const pulseToSophia = {
  id: 'pulse-to-sophia',
  pullFraction: 0.35,
  cyclePeriod: 0.5,
  stretchRatio: 0.55,

  _base: null,

  update(ctx) {
    const { system, hubGroups, elapsed } = ctx;
    if (!system) return;

    const sophia = hubGroups.find(h => h.userData.hubName === 'thefog');
    if (!sophia) return;

    // Capture base position once (the follow-hub-centroid behavior moves it,
    // so snapshot it at the start of each cycle instead)
    if (!this._base) this._base = system.group.position.clone();

    const cyclePos = (elapsed % this.cyclePeriod) / this.cyclePeriod;
    const t = cyclePos < this.stretchRatio
      ? cyclePos / this.stretchRatio                        // 0→1 stretching out
      : 1 - (cyclePos - this.stretchRatio) / (1 - this.stretchRatio); // 1→0 retracting

    // Smooth with ease
    const eased = t * t * (3 - 2 * t);

    // At the start of each cycle, re-snapshot base from current group position
    if (cyclePos < 0.02) {
      this._base.copy(system.group.position);
    }

    // Target = lerp from base toward Sophia by pullFraction
    system.group.position.lerpVectors(
      this._base,
      sophia.position,
      eased * this.pullFraction,
    );
  },
};

registerFogBehavior(pulseToSophia);
