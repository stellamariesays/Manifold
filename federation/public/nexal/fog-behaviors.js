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

// Register on module load
registerFogBehavior(followHubCentroid);

// ── Built-in: stretch-to-hubs ─────────────────────────────────────────────

/**
 * Elastically stretches the fog nodes toward each orbiting hub's live world
 * position, making the cloud visually reach out toward each hub.
 *
 * Each fog node calculates a weighted pull from every hub based on the node's
 * "facing direction" toward that hub. Nodes on the side closest to a hub
 * stretch toward it; nodes on the opposite side are unaffected.
 *
 * Config:
 *   stretchStrength   number   Max node displacement per hub (scene units). Default 3.0
 *   falloff           number   How quickly the pull falls off with hub distance. Default 0.12
 *   recoverySpeed     number   0–1 lerp speed back to original position. Default 0.06
 *   maxNodeDisplace   number   Hard cap on per-node total displacement. Default 4.5
 *   nodeParticipation number   Fraction of nodes that participate (0–1). Default 0.65
 */
const stretchToHubs = {
  id: 'stretch-to-hubs',
  stretchStrength: 3.0,
  falloff: 0.12,
  recoverySpeed: 0.06,
  maxNodeDisplace: 4.5,
  nodeParticipation: 0.65,

  // Per-node persistent stretch targets (lazy-init)
  _nodeTargets: null,
  _hubWorldPositions: [],

  update(ctx) {
    const { system, hubGroups, THREE } = ctx;
    if (!system || hubGroups.length === 0) return;

    const nodes = system.nodes;
    const groupPos = system.group.position;   // fog group world position

    // Lazy-init per-node targets
    if (!this._nodeTargets || this._nodeTargets.length !== nodes.length) {
      this._nodeTargets = nodes.map(n => ({ sx: 0, sy: 0, sz: 0 }));
      // Seed participation flag deterministically so it doesn't flicker
      nodes.forEach((n, i) => { n._stretchParticipates = (i / nodes.length) < this.nodeParticipation; });
    }

    // Collect hub world positions (hub markers orbit, so read from live group.position)
    const hubs = hubGroups.map(h => ({
      name: h.userData.hubName,
      wx: h.position.x,
      wy: h.position.y,
      wz: h.position.z,
    }));

    nodes.forEach((node, i) => {
      if (!node._stretchParticipates) return;
      const t = this._nodeTargets[i];

      // Node world pos = group pos + node local pos (group scale=1 after intro)
      const nwx = groupPos.x + node.x;
      const nwy = groupPos.y + node.y;
      const nwz = groupPos.z + node.z;

      let totalSx = 0, totalSy = 0, totalSz = 0;

      hubs.forEach(hub => {
        // Vector from node world pos to hub world pos
        const dx = hub.wx - nwx;
        const dy = hub.wy - nwy;
        const dz = hub.wz - nwz;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) + 0.001;

        // Only nodes "facing" the hub (positive dot with direction from fog origin to hub) get pulled
        const fx = hub.wx - groupPos.x;
        const fy = hub.wy - groupPos.y;
        const fz = hub.wz - groupPos.z;
        const fLen = Math.sqrt(fx * fx + fy * fy + fz * fz) + 0.001;
        // Node direction from fog origin
        const nLen = Math.sqrt(node.x * node.x + node.y * node.y + node.z * node.z) + 0.001;
        const dot = (node.x * fx + node.y * fy + node.z * fz) / (nLen * fLen);
        if (dot < 0) return;  // node faces away — skip

        // Soft falloff by distance: closer hubs stretch harder
        const pull = this.stretchStrength * dot * Math.exp(-this.falloff * dist * dist);

        totalSx += (dx / dist) * pull;
        totalSy += (dy / dist) * pull;
        totalSz += (dz / dist) * pull;
      });

      // Clamp total displacement
      const totalLen = Math.sqrt(totalSx * totalSx + totalSy * totalSy + totalSz * totalSz);
      if (totalLen > this.maxNodeDisplace) {
        const s = this.maxNodeDisplace / totalLen;
        totalSx *= s; totalSy *= s; totalSz *= s;
      }

      // Lerp toward target (smooth, not instant)
      t.sx += (totalSx - t.sx) * 0.08;
      t.sy += (totalSy - t.sy) * 0.08;
      t.sz += (totalSz - t.sz) * 0.08;

      // Apply directly to the mesh instance position (fog behaviors run after
      // the constraint physics loop has already written node positions to meshes,
      // so we add the stretch delta directly here for the current frame).
      const mesh = system.nodeInstances[i];
      if (mesh) {
        mesh.position.x += t.sx;
        mesh.position.y += t.sy;
        mesh.position.z += t.sz;
      }

      // Also store on node so constraint lines pick it up (they read node.stretchX
      // in the *next* physics pass — acceptable one-frame lag on lines).
      node.stretchX = (node.stretchX || 0) + t.sx;
      node.stretchY = (node.stretchY || 0) + t.sy;
      node.stretchZ = (node.stretchZ || 0) + t.sz;
    });
  },
};

registerFogBehavior(stretchToHubs);
