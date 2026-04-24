/**
 * bridge.js — The ONLY communication channel between the 3D and 2D layers.
 *
 * Neither layer imports the other. All cross-boundary communication goes
 * through bridge.emit() / bridge.on() / bridge.off().
 *
 * Events the 3D layer EMITS (2D layer listens):
 *   'agent-selected'  — payload: { agent }
 *   'hub-hovered'     — payload: { hub }
 *   'mesh-updated'    — payload: { agents, hubs }
 *   'frame'           — payload: { elapsed } (each animation frame)
 *
 * Events the 2D layer EMITS (3D layer listens):
 *   'panel-closed'    — user dismissed detail panel
 *   'highlight-agent' — payload: { agentId } — 2D requests 3D highlight
 *
 * No external dependencies. No imports from scene / animation / ui.
 */

const _listeners = new Map();

export const bridge = {
  /**
   * Emit an event to all registered listeners.
   * @param {string} event
   * @param {*} [payload]
   */
  emit(event, payload) {
    const cbs = _listeners.get(event);
    if (!cbs || cbs.size === 0) return;
    // Iterate a snapshot so off() inside a callback is safe
    for (const cb of [...cbs]) {
      try {
        cb(payload);
      } catch (err) {
        console.error(`[bridge] Error in listener for "${event}":`, err);
      }
    }
  },

  /**
   * Register a listener for an event.
   * @param {string} event
   * @param {function} cb
   */
  on(event, cb) {
    if (!_listeners.has(event)) _listeners.set(event, new Set());
    _listeners.get(event).add(cb);
  },

  /**
   * Remove a previously registered listener.
   * @param {string} event
   * @param {function} cb
   */
  off(event, cb) {
    const cbs = _listeners.get(event);
    if (cbs) cbs.delete(cb);
  },
};
