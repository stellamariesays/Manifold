/**
 * animation.js — Clean animation loop.
 * Rotates agents around their hubs, pulses hub rings. That's it.
 */

import * as THREE from 'three';
import { agentGroups, getScene, getCamera, getRenderer } from './scene.js';

let animationFrame = 0;

export function animate() {
  requestAnimationFrame(animate);
  animationFrame++;

  const elapsed = performance.now() / 1000;
  const _scene = getScene();
  const _camera = getCamera();
  const renderer = getRenderer();
  if (!_scene || !_camera || !renderer) return;

  // Orbit agents around hubs
  agentGroups.forEach((group) => {
    const ud = group.userData;
    if (!ud.hubCenter) return;

    const angle = ud.baseOrbitAngle + elapsed * ud.orbitSpeed * ud.orbitDirection;
    group.position.x = ud.hubCenter.x + Math.cos(angle) * ud.orbitRadius;
    group.position.y = ud.hubCenter.y + ud.orbitHeight;
    group.position.z = ud.hubCenter.z + Math.sin(angle) * ud.orbitRadius;
  });

  // Pulse hub rings
  _scene.traverse((child) => {
    if (child.userData && child.userData.type === 'hub-ring') {
      const phase = child.userData.pulsePhase || 0;
      const pulse = 0.9 + Math.sin(elapsed * 1.5 + phase) * 0.15;
      child.scale.setScalar(pulse);
      child.material.opacity = 0.12 + Math.sin(elapsed * 1.5 + phase) * 0.08;
      if (_camera) child.lookAt(_camera.position);
    }
  });

  // Update controls
  if (window.cameraControls) window.cameraControls.update();

  renderer.render(_scene, _camera);
}

export function animateDataHighways() {}
export function createDataPulse() {}
