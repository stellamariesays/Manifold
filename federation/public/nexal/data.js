/**
 * data.js — Federation mesh data loading.
 * Exports: loadAgentsAndBuild
 *
 * Neutral layer: no Three.js, no DOM touches, no UI imports.
 * After a successful (or fallback) fetch it emits 'mesh-updated' on bridge
 * and calls the 3D build callbacks. bridge.js is the only cross-layer dep.
 */
import { bridge } from './bridge.js';

/**
 * @param {{ buildSpiderWeb, buildAgentTopologies, buildCentralNexus, animate }} callbacks
 */
export async function loadAgentsAndBuild(callbacks) {
  let agents = [];
  let meshData = null;

  try {
    const response = await fetch('/mesh');
    meshData = await response.json();
    if (meshData && meshData.agents) {
      agents = meshData.agents;
      // Store mesh data globally for data highways (animation.js reads it)
      // Guard: window is undefined in Node.js test environments
      if (typeof window !== 'undefined') window._meshData = meshData;
      console.log('Mesh data loaded:', meshData.agents.length, 'agents,',
                  meshData.darkCircles ? meshData.darkCircles.length : 0, 'darkCircles');
    }
  } catch (e) {
    console.log('Using demo agents (API offline)');
    agents = [
      // HOG Hub (green)
      { id: 'solar-detect', hub: 'hog', capabilities: ['monitoring'], position: [-8, 2, -2] },
      { id: 'solar-sites', hub: 'hog', capabilities: ['web-deploy'], position: [-6, 0, -1] },
      { id: 'cron-monitor', hub: 'hog', capabilities: ['scheduling'], position: [-7, -1, 0] },

      // TRILLIAN Hub (purple)
      { id: 'stella', hub: 'trillian', capabilities: ['guidance'], position: [6, 3, 0] },
      { id: 'manifold', hub: 'trillian', capabilities: ['topology'], position: [8, 1, 1] },
      { id: 'argue', hub: 'trillian', capabilities: ['debate'], position: [7, 0, -2] },
      { id: 'braid', hub: 'trillian', capabilities: ['solar-prediction'], position: [5, 2, 2] },

      // THEFOG Hub (purple)
      { id: 'void-watcher', hub: 'thefog', capabilities: ['void-scan'], position: [0, 4, 8] },
      { id: 'reach-scanner', hub: 'thefog', capabilities: ['mesh-probe'], position: [-1, 3, 6] },
      { id: 'sentry', hub: 'thefog', capabilities: ['monitoring'], position: [1, 5, 7] },
      { id: 'sophia', hub: 'thefog', capabilities: ['void-depth'], position: [0, 6, 5] },
    ];
  }

  // Build the 3D scene
  callbacks.buildSpiderWeb();
  callbacks.buildAgentTopologies(agents);
  callbacks.buildCentralNexus();

  // Notify the 2D layer (and anyone else who cares) via bridge
  bridge.emit('mesh-updated', { agents, rtt: 0 });

  // Start animation loop
  callbacks.animate();

  // Start periodic mesh polling
  startMeshPolling(callbacks);
}

let _pollTimer = null;
let _lastPollTime = 0;

/**
 * Poll /api/mesh every 5 seconds, measure RTT, and update global state.
 */
export function startMeshPolling(callbacks) {
  if (_pollTimer) clearInterval(_pollTimer);

  _pollTimer = setInterval(async () => {
    try {
      const t0 = performance.now();
      const response = await fetch('/mesh');
      const rtt = Math.round(performance.now() - t0);
      const meshData = await response.json();
      _lastPollTime = Date.now();

      if (meshData && meshData.agents) {
        if (typeof window !== 'undefined') {
          window._meshData = meshData;
          window._meshRTT = rtt;
          window._meshLastPoll = _lastPollTime;
        }

        const agents = meshData.agents;
        callbacks.buildAgentTopologies(agents);
        bridge.emit('mesh-updated', { agents, rtt });
      }
    } catch (e) {
      // Silently ignore poll failures — keep existing data
      console.warn('Mesh poll failed:', e.message);
    }
  }, 5000);
}

export function getLastPollTime() {
  return _lastPollTime;
}
