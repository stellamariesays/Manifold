/**
 * nexal.js — Entry point. Wires all modules together via bridge.
 *
 * This is the ONLY file that imports from both the 3D layer and the 2D layer.
 * Neither layer imports the other — all cross-boundary communication goes
 * through bridge.js.
 *
 * Import order:
 *   1. bridge.js  — must exist before anyone emits
 *   2. scene.js   — sets up scene/camera/renderer
 *   3. animation.js — needs CONSTRAINT_CONFIG and agentGroups from scene.js
 *   4. ui.js, data.js — pure functions, no cross-layer deps
 */
import { bridge } from './bridge.js';
import { init, buildSpiderWeb, buildAgentTopologies, buildCentralNexus, getCamera, getRenderer, getScene, getClickableObjects } from './scene.js';
import { animate } from './animation.js';
import { updateAgentsList, updateStatusPanel, showAgentDetails, showHubDetails, hideDetailPanel } from './ui.js';
import { loadAgentsAndBuild } from './data.js';
import * as THREE from 'three';

// ── Bootstrap ──────────────────────────────────────────────────────────────

// init() sets up scene, camera, renderer, lighting, OrbitControls
init();

// ── Bridge: 2D layer listens to 3D events ─────────────────────────────────

// When mesh data arrives, populate the HUD agent list and status panel
bridge.on('mesh-updated', ({ agents, rtt }) => {
  updateAgentsList(agents);
  updateStatusPanel(agents, rtt);
});

// When user clicks an agent in 3D space, show the detail panel
bridge.on('agent-selected', ({ agent }) => {
  showAgentDetails(agent);
});

// When user clicks a hub marker in 3D space, show hub details
bridge.on('hub-hovered', ({ hub }) => {
  showHubDetails(hub);
});

// ── Bridge: 3D layer listens to 2D events ─────────────────────────────────

// When user closes the detail panel, the 3D layer can deselect the highlight
bridge.on('panel-closed', () => {
  // No-op for now — 3D layer can respond here if highlighting is added
});

// When 2D requests a 3D highlight (future feature)
bridge.on('highlight-agent', ({ agentId }) => {
  // Future: find the matching agentGroup and pulse it
  console.log('[nexal] highlight-agent requested:', agentId);
});

// ── Load data and start the scene ─────────────────────────────────────────

loadAgentsAndBuild({
  buildSpiderWeb,
  buildAgentTopologies,
  buildCentralNexus,
  animate,
});

// ── Window Event Handlers ─────────────────────────────────────────────────
// These live here (not in scene.js or ui.js) because they need both
// 3D state (camera, raycaster) and the bridge to route results.

window.addEventListener('resize', () => {
  const camera = getCamera();
  const renderer = getRenderer();
  if (!camera || !renderer) return;
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

window.addEventListener('click', (event) => {
  const camera = getCamera();
  if (!camera) return;

  const mouse = new THREE.Vector2(
    (event.clientX / window.innerWidth) * 2 - 1,
    -(event.clientY / window.innerHeight) * 2 + 1,
  );

  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(mouse, camera);

  const intersects = raycaster.intersectObjects(getClickableObjects());
  if (intersects.length > 0) {
    const obj = intersects[0].object;
    if (obj.userData && obj.userData.agent) {
      // Emit on bridge — ui.js listener (wired above) will call showAgentDetails
      bridge.emit('agent-selected', { agent: obj.userData.agent });
    } else if (obj.userData && obj.userData.type === 'hub') {
      bridge.emit('hub-hovered', { hub: obj.userData.hubInfo });
    }
  } else {
    hideDetailPanel();
    bridge.emit('panel-closed');
  }
});

window.addEventListener('mousemove', (event) => {
  if (window._constraintSystem && window._constraintSystem.frameCount % 120 === 0) {
    console.log('Mouse event fired - system exists:', !!window._constraintSystem, 'enabled:', !!window._constraintSystem.mouseInteractionEnabled);
  }

  if (window._constraintSystem && window._constraintSystem.mouseInteractionEnabled) {
    const system = window._constraintSystem;

    system.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    system.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    if (window.camera) {
      system.raycaster.setFromCamera(system.mouse, window.camera);

      const plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
      const intersectPoint = new THREE.Vector3();

      if (system.raycaster.ray.intersectPlane(plane, intersectPoint)) {
        system.mousePosition.copy(intersectPoint);
        system.mousePosition.add(system.group.position);
      }
    }
  }
});
