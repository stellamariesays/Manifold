/**
 * animation.js — Main animation loop and data highway system.
 * 3D LAYER ONLY. No imports from ui.js. No DOM touches.
 *
 * Exports: animate, animateDataHighways, createDataPulse
 *
 * Reads scene state via proper exports from scene.js (getScene, getCamera,
 * getRenderer) — no window._renderer / window._camera / window._scene globals.
 *
 * Still reads these window globals set by scene.js (legacy, non-DOM state):
 *   window.agentGroups, window._constraintSystem, window._webRings,
 *   window._dataHighways, window._meshData, window.cameraControls,
 *   window.camera, window.mobileBrightnessBoost, window.hubCenters
 */
import * as THREE from 'three';
import { CONSTRAINT_CONFIG, agentGroups, getScene, getCamera, getRenderer } from './scene.js';

// Global frame counter (read by animateDataHighways)
let animationFrame = 0;

export function animate() {
  requestAnimationFrame(animate);
  animationFrame++;

  const elapsed = performance.now() / 1000;

  // Animate agents and hub centers
  agentGroups.forEach((group, idx) => {
    const userData = group.userData;

    if (userData && userData.isHubCenter && userData.isOrbitingHub) {
      const orbitTime = elapsed * userData.orbitSpeed;
      const currentAngle = userData.orbitAngle + orbitTime;

      const orbitalX = Math.cos(currentAngle) * userData.orbitRadius;
      const orbitalZ = Math.sin(currentAngle) * userData.orbitRadius;
      const orbitalY = userData.orbitHeight + Math.sin(elapsed * 0.3 + idx) * 0.2;

      group.position.set(orbitalX, orbitalY, orbitalZ);

      const hubName = userData.hubName;
      if (window._dataHighways && window._dataHighways.hubCenters[hubName]) {
        window._dataHighways.hubCenters[hubName] = new THREE.Vector3(orbitalX, orbitalY, orbitalZ);
      }
      if (window.hubCenters && window.hubCenters[hubName]) {
        window.hubCenters[hubName] = { x: orbitalX, y: orbitalY, z: orbitalZ };
      }

      const pulse = 1 + Math.sin(elapsed * 2 + idx) * 0.1;
      group.scale.setScalar(pulse);

    } else if (userData && userData.isHubCenter) {
      const pulse = 1 + Math.sin(elapsed * 2 + idx) * 0.15;
      group.scale.setScalar(pulse);

    } else if (userData && userData.hubCenter) {
      const orbitTime = elapsed * userData.orbitSpeed * userData.orbitDirection;
      const currentAngle = userData.baseOrbitAngle + orbitTime;

      let currentHubPos = userData.hubCenter;
      if (window.hubCenters && window.hubCenters[userData.agent.hub]) {
        currentHubPos = window.hubCenters[userData.agent.hub];
      }

      const orbitalX = currentHubPos.x + Math.cos(currentAngle) * userData.orbitRadius;
      const orbitalZ = currentHubPos.z + Math.sin(currentAngle) * userData.orbitRadius;
      const orbitalY = currentHubPos.y + userData.orbitHeight + Math.sin(elapsed * 0.5 + userData.agentIndexInHub) * 0.1;

      group.position.set(orbitalX, orbitalY, orbitalZ);
      group.rotation.y += 0.005 + idx * 0.001;
      group.rotation.x += 0.003;
    }
  });

  if (window._centralSphere) {
    window._centralSphere.rotation.y += 0.003;
    window._centralSphere.rotation.x += 0.001;
  }

  // Animate pulsing hub rings
  scene.traverse((child) => {
    if (child.userData && child.userData.type === 'hub-ring') {
      const phase = child.userData.pulsePhase || 0;
      const pulseFactor = 0.8 + Math.sin(elapsed * 1.5 + phase) * 0.4;
      child.scale.setScalar(pulseFactor);
      child.material.opacity = 0.15 + Math.sin(elapsed * 1.5 + phase) * 0.25;
      child.lookAt(camera.position);
    }
  });

  // Animate constraint network physics
  if (window._constraintSystem) {
    const system = window._constraintSystem;
    system.frameCount++;

    // Intro: shrink from huge to normal
    if (system.introAnimation) {
      const currentTime = performance.now();
      if (system.startTime === null) {
        system.startTime = currentTime;
        console.log('Starting intro animation at scale:', system.initialScale);
      }
      const elapsedIntro = currentTime - system.startTime;
      if (elapsedIntro < system.introDuration) {
        const progress = elapsedIntro / system.introDuration;
        const easeOut = 1 - Math.pow(1 - progress, 3);
        system.group.scale.setScalar(system.initialScale + (system.targetScale - system.initialScale) * easeOut);
      } else {
        system.group.scale.setScalar(system.targetScale);
        system.currentScale = system.targetScale;
        system.introAnimation = false;
        console.log('Intro animation complete - switching to stable mode');
        CONSTRAINT_CONFIG.springStrength = CONSTRAINT_CONFIG.stableSpringStrength;
        CONSTRAINT_CONFIG.damping = CONSTRAINT_CONFIG.stableDamping;
        if (!system.mouseInteractionEnabled) {
          system.mouseInteractionEnabled = true;
          console.log('Mouse interaction enabled after intro completion');
        }
      }
    }

    const nodes = system.nodes;
    const constraints = system.constraints;

    // Black hole mouse interaction
    if (CONSTRAINT_CONFIG.followMouse && system.mousePosition && system.mouseInteractionEnabled) {
      let nodesAffected = 0;
      nodes.forEach(node => {
        const dx = system.mousePosition.x - node.x;
        const dy = system.mousePosition.y - node.y;
        const dz = system.mousePosition.z - node.z;
        const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (distance < CONSTRAINT_CONFIG.mouseRadius && distance > 0.1) {
          nodesAffected++;
          const eventHorizon = 0.5;
          const forceMultiplier = distance < eventHorizon ? 10.0 : 1.0;
          const force = (CONSTRAINT_CONFIG.mouseForce / (distance + 0.5)) * forceMultiplier;
          node.vx += (dx / distance) * force * 0.05;
          node.vy += (dy / distance) * force * 0.05;
          node.vz += (dz / distance) * force * 0.05;
        }
      });
      if (system.frameCount % 60 === 0 && nodesAffected > 0) {
        console.log('Black hole affecting', nodesAffected, 'nodes');
      }
    }

    // Proximity shrinking
    if (CONSTRAINT_CONFIG.shrinkOnProximity && system.mousePosition && system.mouseInteractionEnabled && !system.introAnimation) {
      const systemCenter = system.group.position;
      const mouseDistance = system.mousePosition.distanceTo(systemCenter);
      if (mouseDistance < CONSTRAINT_CONFIG.shrinkRadius) {
        const proximityRatio = mouseDistance / CONSTRAINT_CONFIG.shrinkRadius;
        system.targetProximityScale = CONSTRAINT_CONFIG.minShrinkScale + (1.0 - CONSTRAINT_CONFIG.minShrinkScale) * proximityRatio;
      } else {
        system.targetProximityScale = 1.0;
      }
      system.currentScale += (system.targetProximityScale - system.currentScale) * 0.05;
      system.group.scale.setScalar(system.currentScale);
    }

    // Particle emission
    if (CONSTRAINT_CONFIG.particleEmissions && system.hubPositions.length > 0 && !system.introAnimation) {
      const currentTime = performance.now();
      if (currentTime - system.lastEmissionTime >= CONSTRAINT_CONFIG.emissionInterval) {
        system.lastEmissionTime = currentTime;
        const targetHubs = [];

        for (let i = 0; i < CONSTRAINT_CONFIG.particlesPerEmission; i++) {
          let targetHub, targetHubIndex;
          if (Math.random() < CONSTRAINT_CONFIG.thefogPreference) {
            const thefogHub = system.hubPositions.find(hub => hub.isThefog);
            if (thefogHub) {
              targetHub = thefogHub;
              targetHubIndex = system.hubPositions.indexOf(thefogHub);
            } else {
              targetHubIndex = Math.floor(Math.random() * system.hubPositions.length);
              targetHub = system.hubPositions[targetHubIndex];
            }
          } else {
            targetHubIndex = Math.floor(Math.random() * system.hubPositions.length);
            targetHub = system.hubPositions[targetHubIndex];
          }

          targetHubs.push({ index: targetHubIndex, hubInfo: targetHub, position: targetHub.position });

          const particleGeometry = new THREE.SphereGeometry(CONSTRAINT_CONFIG.particleSize, 8, 6);
          const particleColor = targetHub.isThefog ? 0x8800ff : 0x00e5ff;
          const particleMaterial = new THREE.MeshBasicMaterial({ color: particleColor, transparent: true, opacity: 0.8 });
          const particleMesh = new THREE.Mesh(particleGeometry, particleMaterial);
          particleMesh.position.copy(system.group.position);

          const particle = {
            mesh: particleMesh,
            startPos: system.group.position.clone(),
            targetPos: targetHub.position.clone(),
            progress: 0.0,
            speed: CONSTRAINT_CONFIG.particleSpeed,
            targetHubIndex,
            isThefog: targetHub.isThefog,
          };

          system.particles.push(particle);
          system.particleGroup.add(particleMesh);
        }

        // Stretch effects
        if (CONSTRAINT_CONFIG.meshStretch && targetHubs.length > 0) {
          targetHubs.forEach(targetHub => {
            const systemCenter = system.group.position;
            const stretchDirection = new THREE.Vector3().copy(targetHub.position).sub(systemCenter).normalize();

            const isThefogConnection = targetHub.hubInfo.isThefog;
            const effectiveStrength = isThefogConnection
              ? CONSTRAINT_CONFIG.stretchMagnitude * CONSTRAINT_CONFIG.thefogStretchBoost
              : CONSTRAINT_CONFIG.stretchMagnitude;
            const effectiveDuration = isThefogConnection
              ? CONSTRAINT_CONFIG.stretchDuration * CONSTRAINT_CONFIG.thefogDurationBoost
              : CONSTRAINT_CONFIG.stretchDuration;

            system.activeStretchEffects.push({
              direction: stretchDirection,
              strength: effectiveStrength,
              startTime: currentTime,
              duration: effectiveDuration,
              buildup: 0.0,
              decay: 1.0,
              buildupPhase: true,
              buildupDuration: effectiveDuration * 0.5,
              hubTarget: targetHub.position.clone(),
              isThefog: isThefogConnection,
              concentrated: isThefogConnection,
            });
          });
        }
      }

      system.particles = system.particles.filter(particle => {
        particle.progress += particle.speed;
        if (particle.progress >= 1.0) {
          system.particleGroup.remove(particle.mesh);
          return false;
        }
        particle.mesh.position.lerpVectors(particle.startPos, particle.targetPos, particle.progress);
        return true;
      });
    }

    // Mesh stretching
    if (CONSTRAINT_CONFIG.meshStretch && system.activeStretchEffects.length > 0) {
      const currentTime = performance.now();
      system.activeStretchEffects = system.activeStretchEffects.filter(effect => {
        const elapsed = currentTime - effect.startTime;
        const progress = elapsed / effect.duration;
        if (progress >= 1.0) return false;
        if (effect.buildupPhase) {
          const buildupProgress = Math.min(elapsed / effect.buildupDuration, 1.0);
          effect.buildup = buildupProgress * CONSTRAINT_CONFIG.stretchSpeed;
          if (buildupProgress >= 1.0) { effect.buildupPhase = false; effect.buildup = 1.0; }
        } else {
          const decayStart = effect.buildupDuration;
          const decayElapsed = elapsed - decayStart;
          const decayDuration = effect.duration - decayStart;
          const decayProgress = decayElapsed / decayDuration;
          effect.decay = 1.0 - (decayProgress * decayProgress);
        }
        return true;
      });

      system.nodes.forEach((node, i) => {
        const originalPos = system.originalNodePositions[i];
        node.lightening = 0;
        let totalStretchX = 0, totalStretchY = 0, totalStretchZ = 0;

        system.activeStretchEffects.forEach(effect => {
          const nodeFromCenter = new THREE.Vector3(originalPos.x, originalPos.y, originalPos.z);
          const dot = nodeFromCenter.dot(effect.direction);
          if (dot > 0) {
            let participates = true;
            if (effect.concentrated) {
              const nodeDistance = nodeFromCenter.length();
              const alignment = nodeDistance > 0 ? dot / nodeDistance : 0;
              participates = alignment > CONSTRAINT_CONFIG.thefogConcentration;
              if (participates && Math.random() > CONSTRAINT_CONFIG.thefogParticipation) participates = false;
            }
            if (participates) {
              const currentStrength = effect.buildupPhase
                ? effect.strength * effect.buildup
                : effect.strength * effect.decay;
              const baseStretchAmount = dot * currentStrength;
              const hubDirection = new THREE.Vector3()
                .copy(effect.hubTarget)
                .sub(new THREE.Vector3(originalPos.x, originalPos.y, originalPos.z))
                .normalize();
              const hubPull = baseStretchAmount * 0.3;
              const stretchX = effect.direction.x * baseStretchAmount + hubDirection.x * hubPull;
              const stretchY = effect.direction.y * baseStretchAmount + hubDirection.y * hubPull;
              const stretchZ = effect.direction.z * baseStretchAmount + hubDirection.z * hubPull;
              totalStretchX += stretchX; totalStretchY += stretchY; totalStretchZ += stretchZ;
              if (CONSTRAINT_CONFIG.stretchLighting) {
                const stretchMagnitude = Math.sqrt(stretchX*stretchX + stretchY*stretchY + stretchZ*stretchZ);
                const lightening = Math.min(stretchMagnitude / (effect.strength * 0.5), 1.0) * CONSTRAINT_CONFIG.maxLightening;
                node.lightening = Math.max(node.lightening || 0, lightening);
              }
            }
          }
        });

        node.stretchX = totalStretchX;
        node.stretchY = totalStretchY;
        node.stretchZ = totalStretchZ;
      });
    } else {
      system.nodes.forEach(node => { node.stretchX = 0; node.stretchY = 0; node.stretchZ = 0; node.lightening = 0; });
    }

    // Constraint physics
    constraints.forEach(constraint => {
      const nodeA = nodes[constraint.nodeA], nodeB = nodes[constraint.nodeB];
      const dx = nodeB.x - nodeA.x, dy = nodeB.y - nodeA.y, dz = nodeB.z - nodeA.z;
      const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (distance > 0) {
        const difference = (constraint.restLength - distance) / distance;
        const force = difference * CONSTRAINT_CONFIG.springStrength;
        const offsetX = dx * force * 0.5, offsetY = dy * force * 0.5, offsetZ = dz * force * 0.5;
        nodeA.vx -= offsetX; nodeA.vy -= offsetY; nodeA.vz -= offsetZ;
        nodeB.vx += offsetX; nodeB.vy += offsetY; nodeB.vz += offsetZ;
      }
    });

    nodes.forEach((node, i) => {
      if (!node.fixed) {
        if (CONSTRAINT_CONFIG.constraintRatio > 0) {
          node.vx += (node.ox - node.x) * CONSTRAINT_CONFIG.constraintRatio * 0.05;
          node.vy += (node.oy - node.y) * CONSTRAINT_CONFIG.constraintRatio * 0.05;
          node.vz += (node.oz - node.z) * CONSTRAINT_CONFIG.constraintRatio * 0.05;
        }
        node.vy += 0.0002;
        node.x += node.vx; node.y += node.vy; node.z += node.vz;
        node.vx *= CONSTRAINT_CONFIG.damping; node.vy *= CONSTRAINT_CONFIG.damping; node.vz *= CONSTRAINT_CONFIG.damping;

        const maxDrift = 5.0;
        if (Math.abs(node.x) > maxDrift || Math.abs(node.y) > maxDrift || Math.abs(node.z) > maxDrift) {
          node.vx += (0 - node.x) * 0.01; node.vy += (0 - node.y) * 0.01; node.vz += (0 - node.z) * 0.01;
        }

        if (system.nodeInstances[i]) {
          const visualX = node.x + (node.stretchX || 0);
          const visualY = node.y + (node.stretchY || 0);
          const visualZ = node.z + (node.stretchZ || 0);
          system.nodeInstances[i].position.set(visualX, visualY, visualZ);

          if (CONSTRAINT_CONFIG.stretchLighting && node.lightening > 0) {
            const baseOpacity = CONSTRAINT_CONFIG.nodeOpacity;
            system.nodeInstances[i].material.opacity = Math.max(baseOpacity * (1.0 - node.lightening), 0.1);
            if (node.lightening > 0.2) {
              system.nodeInstances[i].material.emissive.setHex(0x4422ff);
              system.nodeInstances[i].material.emissiveIntensity = node.lightening * 0.8;
            } else {
              system.nodeInstances[i].material.emissive.setHex(0x000000);
              system.nodeInstances[i].material.emissiveIntensity = 0;
            }
            system.nodeInstances[i].material.needsUpdate = true;
          } else {
            system.nodeInstances[i].material.opacity = CONSTRAINT_CONFIG.nodeOpacity;
            system.nodeInstances[i].material.emissive.setHex(0x000000);
            system.nodeInstances[i].material.emissiveIntensity = 0;
            system.nodeInstances[i].material.needsUpdate = true;
          }
        }
      }
    });

    // Update constraint lines
    if (system.constraintLines) {
      const linePositions = system.constraintLines.geometry.attributes.position.array;
      constraints.forEach((constraint, i) => {
        const nodeA = nodes[constraint.nodeA], nodeB = nodes[constraint.nodeB];
        const i6 = i * 6;
        linePositions[i6] = nodeA.x + (nodeA.stretchX || 0);
        linePositions[i6 + 1] = nodeA.y + (nodeA.stretchY || 0);
        linePositions[i6 + 2] = nodeA.z + (nodeA.stretchZ || 0);
        linePositions[i6 + 3] = nodeB.x + (nodeB.stretchX || 0);
        linePositions[i6 + 4] = nodeB.y + (nodeB.stretchY || 0);
        linePositions[i6 + 5] = nodeB.z + (nodeB.stretchZ || 0);
      });
      system.constraintLines.geometry.attributes.position.needsUpdate = true;
    }
  }

  animateDataHighways(elapsed);

  // Spider web waves
  if (window._webRings) {
    window._webRings.forEach(ring => {
      const userData = ring.userData;
      const positions = ring.geometry.attributes.position.array;
      const originalPos = userData.originalPositions;

      const waveSpeed1 = elapsed * 0.8, waveSpeed2 = elapsed * 1.2, waveSpeed3 = elapsed * 0.6;
      const waveAmp = 0.15 * (userData.radius / 12);

      for (let i = 0; i <= userData.segmentCount; i++) {
        const i3 = i * 3;
        const angle = (i / userData.segmentCount) * Math.PI * 2;
        const wave1 = Math.sin(waveSpeed1 + angle * 3) * waveAmp;
        const wave2 = Math.sin(waveSpeed2 + angle * 2 + userData.ringIndex * 0.5) * (waveAmp * 0.6);
        const wave3 = Math.cos(waveSpeed3 + angle * 4 + userData.radius * 0.1) * (waveAmp * 0.4);
        positions[i3] = originalPos[i3];
        positions[i3 + 1] = wave1 + wave2 + wave3;
        positions[i3 + 2] = originalPos[i3 + 2];
      }
      ring.geometry.attributes.position.needsUpdate = true;
    });
  }

  if (window.cameraControls) window.cameraControls.update();

  const renderer = getRenderer();
  const camera = getCamera();
  const scene = getScene();
  renderer.render(scene, camera);
}

// ──────── DATA HIGHWAY SYSTEM ─────────────────────────────────────────────

export function animateDataHighways(elapsed) {
  const highways = window._dataHighways;
  if (!highways || !window._meshData || !window._webGroup) return;

  const currentTime = performance.now();

  if (currentTime - highways.lastPulseTime > 2000) {
    highways.lastPulseTime = currentTime;

    const highPressureCapabilities = window._meshData.darkCircles
      ? window._meshData.darkCircles.filter(cap => cap.pressure > 0.3)
      : [];

    highPressureCapabilities.forEach(capability => {
      const capType = _getCapabilityType(capability.name);
      const color = highways.capabilityColors[capType] || highways.capabilityColors.default;
      const hubPressures = Object.entries(capability.byHub).sort((a, b) => b[1] - a[1]);
      if (hubPressures.length >= 2) {
        const sourceHub = hubPressures[0][0];
        const destHub = hubPressures[1][0];
        console.log(`Data highway: Creating pulse ${capability.name} (${capability.pressure.toFixed(2)}) ${sourceHub} → ${destHub}`);
        createDataPulse(sourceHub, destHub, color, capability.pressure, capability.name);
      }
    });
  }

  highways.connections.forEach((connectionA, indexA) => {
    highways.connections.forEach((connectionB, indexB) => {
      if (indexA < indexB && connectionA.pulseSphere && connectionB.pulseSphere) {
        const posA = connectionA.pulseSphere.position, posB = connectionB.pulseSphere.position;
        const distance = posA.distanceTo(posB);
        const bothInWeb = Math.abs(posA.y + 2.5) < 1.0 && Math.abs(posB.y + 2.5) < 1.0;
        if (bothInWeb && distance < 2.5) {
          connectionA.pulseSphere.material.emissiveIntensity = 3.0;
          connectionB.pulseSphere.material.emissiveIntensity = 3.0;
          connectionA.pulseSphere.scale.setScalar(0.8);
          connectionB.pulseSphere.scale.setScalar(0.8);
          connectionA.pulseSphere.material.opacity = 1.0;
          connectionB.pulseSphere.material.opacity = 1.0;
        }
      }
    });
  });

  highways.connections = highways.connections.filter(connection => {
    const age = currentTime - connection.startTime;
    if (age <= connection.lifetime) {
      connection.progress += connection.speed;

      if (connection.pulseSphere && connection.pathPoints && connection.pathPoints.length > 1) {
        const totalSegments = connection.pathPoints.length - 1;
        const scaledProgress = connection.progress * totalSegments;
        const segmentIndex = Math.floor(scaledProgress);
        const localProgress = scaledProgress - segmentIndex;

        let currentPos;
        if (segmentIndex >= totalSegments) {
          currentPos = connection.pathPoints[connection.pathPoints.length - 1];
        } else {
          const currentPoint = connection.pathPoints[segmentIndex];
          const nextPoint = connection.pathPoints[segmentIndex + 1];
          currentPos = new THREE.Vector3(
            currentPoint.x + (nextPoint.x - currentPoint.x) * localProgress,
            currentPoint.y + (nextPoint.y - currentPoint.y) * localProgress,
            currentPoint.z + (nextPoint.z - currentPoint.z) * localProgress,
          );
        }

        if (connection.pulseSphere && connection.pulseSphere.material && connection.pulseSphere.scale) {
          connection.pulseSphere.position.copy(currentPos);
          const pulsePhase = Math.sin(currentTime * 0.015);
          const pulseIntensity = 1.0 + 0.5 * pulsePhase;
          connection.pulseSphere.material.emissiveIntensity = pulseIntensity;
          connection.pulseSphere.material.opacity = 0.9 + 0.1 * pulsePhase;
          const isInWeb = Math.abs(currentPos.y + 2.5) < 1.0;
          connection.pulseSphere.scale.setScalar(isInWeb ? 0.5 : 0.3);
          const glowIntensity = 1.2 + 0.3 * pulsePhase;
          if (connection.pulseSphere.material.emissive) {
            connection.pulseSphere.material.emissive.setScalar(glowIntensity);
          }
        }

        if (Math.abs(currentPos.y + 2.5) < 1.0) {
          _lightUpWebSegments(currentPos, connection.color, connection.intensity);
        }
      }

      if (connection.progress >= 1.0 || age > connection.lifetime) {
        if (connection.pulseSphere && connection.pulseSphere.parent) {
          connection.pulseSphere.parent.remove(connection.pulseSphere);
        }
        return false;
      }
      return true;
    } else {
      if (connection.pulseSphere && connection.pulseSphere.parent) {
        connection.pulseSphere.parent.remove(connection.pulseSphere);
      }
      return false;
    }
  });

  highways.segmentActivity.forEach((activity, segmentId) => {
    activity.intensity *= 0.95;
    if (activity.intensity < 0.05) {
      highways.segmentActivity.delete(segmentId);
      _resetWebSegmentColor(segmentId);
    }
  });
}

function _getCapabilityType(capabilityName) {
  if (capabilityName.includes('detection')) return 'detection';
  if (capabilityName.includes('data')) return 'data';
  if (capabilityName.includes('deployment')) return 'deployment';
  if (capabilityName.includes('strategy')) return 'strategy';
  if (capabilityName.includes('solar')) return 'solar';
  return 'default';
}

export function createDataPulse(sourceHub, destHub, color, pressure, capabilityName) {
  const highways = window._dataHighways;
  if (!highways.hubCenters[sourceHub] || !highways.hubCenters[destHub]) {
    console.log(`Missing hub centers for ${sourceHub} or ${destHub}`);
    return;
  }

  const sourceAgents = agentGroups?.filter(group =>
    group.userData && group.userData.agent && group.userData.agent.hub === sourceHub) || [];
  const destAgents = agentGroups?.filter(group =>
    group.userData && group.userData.agent && group.userData.agent.hub === destHub) || [];

  let sourcePos, destPos, sourceAgentName, destAgentName;

  if (sourceAgents.length > 0) {
    const sourceAgent = sourceAgents[Math.floor(Math.random() * sourceAgents.length)];
    sourcePos = sourceAgent.position;
    sourceAgentName = sourceAgent.userData.agent.name;
  } else {
    sourcePos = highways.hubCenters[sourceHub];
    sourceAgentName = `${sourceHub}-center`;
  }

  if (destAgents.length > 0) {
    const destAgent = destAgents[Math.floor(Math.random() * destAgents.length)];
    destPos = destAgent.position;
    destAgentName = destAgent.userData.agent.name;
  } else {
    destPos = highways.hubCenters[destHub];
    destAgentName = `${destHub}-center`;
  }

  const webPath = _calculateWebPath(sourceHub, destHub);
  const pathPoints = [];

  pathPoints.push(new THREE.Vector3(sourcePos.x, sourcePos.y, sourcePos.z));

  const sourceRadius = Math.sqrt(sourcePos.x * sourcePos.x + sourcePos.z * sourcePos.z);
  const sourceAngle = Math.atan2(sourcePos.z, sourcePos.x);
  pathPoints.push(new THREE.Vector3(
    Math.cos(sourceAngle) * Math.min(sourceRadius, 8), -2.5,
    Math.sin(sourceAngle) * Math.min(sourceRadius, 8),
  ));

  for (let i = 0; i <= 20; i++) {
    const webPosition = _getWebPathPosition(webPath, i / 20);
    if (webPosition) pathPoints.push(webPosition);
  }

  const destRadius = Math.sqrt(destPos.x * destPos.x + destPos.z * destPos.z);
  const destAngle = Math.atan2(destPos.z, destPos.x);
  pathPoints.push(new THREE.Vector3(
    Math.cos(destAngle) * Math.min(destRadius, 8), -2.5,
    Math.sin(destAngle) * Math.min(destRadius, 8),
  ));
  pathPoints.push(new THREE.Vector3(destPos.x, destPos.y, destPos.z));

  if (pathPoints.length < 2) {
    pathPoints.push(
      new THREE.Vector3(sourcePos.x, sourcePos.y, sourcePos.z),
      new THREE.Vector3(destPos.x, destPos.y, destPos.z),
    );
  }

  const pulseGeometry = new THREE.SphereGeometry(0.3, 8, 6);
  const pulseMaterial = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.95,
    emissive: new THREE.Color(color),
    emissiveIntensity: 0.8 * (window.mobileBrightnessBoost || 1.0),
  });

  const pulseSphere = new THREE.Mesh(pulseGeometry, pulseMaterial);
  getScene().add(pulseSphere);

  highways.connections.push({
    line: null,
    pulseSphere,
    webPath,
    pathPoints,
    progress: 0.0,
    speed: 0.003125 * (1 + pressure),
    color,
    intensity: pressure,
    capability: capabilityName,
    sourceHub, destHub, sourceAgent: sourceAgentName, destAgent: destAgentName,
    maxOpacity: 0.9,
    lifetime: 6000,
    startTime: performance.now(),
    phase: 'shooting_down',
  });
}

// Expose for scene.js setTimeout callback
window._createDataPulse = createDataPulse;

function _calculateWebPath(sourceHub, destHub) {
  const highways = window._dataHighways;
  const sourceZone = highways.hubZones[sourceHub];
  const destZone = highways.hubZones[destHub];
  if (!sourceZone || !destZone) { console.log(`Missing zone data for ${sourceHub} or ${destHub}`); return []; }

  const angleDiff = Math.abs(destZone.angle - sourceZone.angle);
  const normalizedDiff = Math.min(angleDiff, 2 * Math.PI - angleDiff);

  if (normalizedDiff < Math.PI / 2) {
    return [
      { ring: 0.5, angle: sourceZone.angle },
      { ring: 2.5, angle: sourceZone.angle },
      { ring: 2.5, angle: destZone.angle },
      { ring: 0.5, angle: destZone.angle },
    ];
  }

  const midAngle = (sourceZone.angle + destZone.angle) / 2;
  const spiralSteps = 6;
  const path = [];

  for (let i = 0; i <= spiralSteps; i++) {
    const progress = i / spiralSteps;
    const ring = 2.5 * (1 - progress);
    const angle = sourceZone.angle + progress * (midAngle - sourceZone.angle);
    path.push({ ring: Math.max(ring, 0.1), angle });
  }

  for (let i = 1; i <= spiralSteps; i++) {
    const progress = i / spiralSteps;
    const ring = 2.5 * progress;
    const angle = midAngle + progress * (destZone.angle - midAngle);
    path.push({ ring: Math.max(ring, 0.1), angle });
  }

  return path;
}

function _getWebPathPosition(path, progress) {
  if (!path || path.length < 2) return null;

  const segmentProgress = progress * (path.length - 1);
  const segmentIndex = Math.floor(segmentProgress);
  const localProgress = segmentProgress - segmentIndex;

  if (segmentIndex >= path.length - 1) {
    const lastPoint = path[path.length - 1];
    return new THREE.Vector3(
      Math.cos(lastPoint.angle) * lastPoint.ring * 3, -2.5,
      Math.sin(lastPoint.angle) * lastPoint.ring * 3,
    );
  }

  const currentPoint = path[segmentIndex];
  const nextPoint = path[segmentIndex + 1];
  const currentRadius = currentPoint.ring * 3;
  const nextRadius = nextPoint.ring * 3;
  const currentAngle = currentPoint.angle;
  let nextAngle = nextPoint.angle;

  const angleDiff = nextAngle - currentAngle;
  if (angleDiff > Math.PI) nextAngle -= 2 * Math.PI;
  else if (angleDiff < -Math.PI) nextAngle += 2 * Math.PI;

  const easedProgress = 0.5 - 0.5 * Math.cos(localProgress * Math.PI);
  const radius = currentRadius + (nextRadius - currentRadius) * easedProgress;
  const angle = currentAngle + (nextAngle - currentAngle) * easedProgress;
  const yOffset = Math.sin(progress * Math.PI * 4) * 0.5;

  return new THREE.Vector3(Math.cos(angle) * radius, -2.5 + yOffset, Math.sin(angle) * radius);
}

function _lightUpWebSegments(position, color, intensity) {
  if (!window._webRings) return;
  const highways = window._dataHighways;
  const radius = Math.sqrt(position.x * position.x + position.z * position.z);

  let closestRing = null, minDistance = Infinity;
  window._webRings.forEach((ring) => {
    const distance = Math.abs(radius - ring.userData.radius);
    if (distance < minDistance) { minDistance = distance; closestRing = ring; }
  });

  if (closestRing && minDistance < 2.0) {
    const segmentId = `ring_${closestRing.userData.ringIndex}`;
    highways.segmentActivity.set(segmentId, { intensity, color, ring: closestRing });
    const material = closestRing.material;
    if (material && material.color && material.emissive) {
      material.color.setHex(color);
      material.opacity = Math.min(0.8, 0.3 + intensity * 0.5);
      material.emissive.setHex(color);
      material.emissiveIntensity = intensity * 0.3 * (window.mobileBrightnessBoost || 1.0);
    }
  }
}

function _resetWebSegmentColor(segmentId) {
  const highways = window._dataHighways;
  const activity = highways.segmentActivity.get(segmentId);
  if (activity && activity.ring && activity.ring.material) {
    const material = activity.ring.material;
    if (material.color && material.emissive) {
      material.color.setHex(0x2a4a6a);
      material.opacity = 0.3;
      material.emissive.setHex(0x000000);
      material.emissiveIntensity = 0;
    }
  }
}
