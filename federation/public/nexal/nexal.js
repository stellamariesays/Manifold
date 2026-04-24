/**
 * nexal.js — Entry point. Wires all modules together.
 *
 * Import order matters:
 *   1. scene.js  — must run first to set up scene/camera/renderer
 *   2. animation.js — needs CONSTRAINT_CONFIG and agentGroups from scene.js
 *   3. ui.js, data.js — pure functions, no deps
 */
import { init, buildSpiderWeb, buildAgentTopologies, buildCentralNexus } from './scene.js';
import { animate } from './animation.js';
import { updateAgentsList, updateStatusPanel, showAgentDetails, showHubDetails, hideDetailPanel } from './ui.js';
import { loadAgentsAndBuild } from './data.js';
import * as THREE from 'three';

// ── Bootstrap ──────────────────────────────────────────────────────────────

// init() sets up scene, camera, renderer, lighting, OrbitControls
init();

// loadAgentsAndBuild fetches mesh data then calls the build/update functions
loadAgentsAndBuild({
  buildSpiderWeb,
  buildAgentTopologies,
  buildCentralNexus,
  updateAgentsList,
  updateStatusPanel,
  animate,
});

// ── Event Handlers ─────────────────────────────────────────────────────────

// These need scene.js globals (camera, clickableObjects) that are set up by init()
// We import them lazily here via the getter.
import { getCamera, getClickableObjects } from './scene.js';

window.addEventListener('resize', () => {
  const camera = getCamera();
  const renderer = /** @type {import('three').WebGLRenderer} */ (window._renderer);
  if (!camera) return;
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  // renderer is kept on window by scene.js for resize handler
  if (window._renderer) {
    window._renderer.setSize(window.innerWidth, window.innerHeight);
  }
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
      showAgentDetails(obj.userData.agent);
    } else if (obj.userData && obj.userData.type === 'hub') {
      showHubDetails(obj.userData.hubInfo);
    }
  } else {
    hideDetailPanel();
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
