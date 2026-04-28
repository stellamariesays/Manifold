/**
 * scene.js — Clean 3D federation mesh visualization.
 * Hub spheres with orbiting agent dots. Connections between hubs.
 * No topology shapes, no spider webs, no particles.
 */

import * as THREE from 'three';
import { OrbitControls } from 'https://unpkg.com/three@0.128.0/examples/jsm/controls/OrbitControls.js';
import { bridge } from './bridge.js';

let scene, camera, renderer;
export const agentGroups = [];
let clickableObjects = [];

export function getScene()            { return scene; }
export function getCamera()           { return camera; }
export function getRenderer()         { return renderer; }
export function getClickableObjects() { return clickableObjects; }

export function init() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000510);

  const canvas = document.getElementById('scene');
  camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 500);
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  camera.position.set(0, 12, 25);
  camera.lookAt(0, 0, 0);

  window.camera = camera;

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.minDistance = 8;
  controls.maxDistance = 60;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.3;
  window.cameraControls = controls;

  // Lighting
  scene.add(new THREE.AmbientLight(0xffffff, 0.4));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(10, 15, 10);
  scene.add(dirLight);

  // Subtle grid floor
  const grid = new THREE.GridHelper(40, 40, 0x0a1a2a, 0x0a1a2a);
  grid.position.y = -5;
  scene.add(grid);
}

export function buildSpiderWeb() {
  // No-op — spider web removed
}

export function buildAgentTopologies(agents) {
  // Clear previous
  agentGroups.length = 0;
  clickableObjects.length = 0;

  const hubColors = {
    'relay': 0x00e5ff,
    'hog': 0x00ff88,
    'trillian': 0xaa00ff,
    'thefog': 0x8800ff,
    'bobiverse': 0xff6600,
  };

  const hubCenters = {
    'hog':        { x: -8, y: 1, z: -5 },
    'trillian':   { x: 7,  y: 2, z: 3 },
    'thefog':     { x: -3, y: 4, z: 7 },
    'relay':      { x: 5,  y: 0, z: -7 },
    'bobiverse':  { x: 0,  y: 5, z: -9 },
  };

  window.hubCenters = hubCenters;

  const agentsByHub = {};
  agents.forEach(a => {
    if (!agentsByHub[a.hub]) agentsByHub[a.hub] = [];
    agentsByHub[a.hub].push(a);
  });

  // Draw hub spheres + labels
  Object.entries(hubCenters).forEach(([hub, center]) => {
    const color = hubColors[hub] || 0x666666;
    const agentCount = (agentsByHub[hub] || []).length;

    // Hub sphere — glow
    const glowGeo = new THREE.SphereGeometry(0.8, 32, 32);
    const glowMat = new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: 0.15,
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    glow.position.set(center.x, center.y, center.z);
    scene.add(glow);

    // Hub sphere — core
    const coreGeo = new THREE.SphereGeometry(0.4, 24, 24);
    const coreMat = new THREE.MeshPhongMaterial({
      color, emissive: color, emissiveIntensity: 0.5,
      transparent: true, opacity: 0.9,
    });
    const core = new THREE.Mesh(coreGeo, coreMat);
    core.position.set(center.x, center.y, center.z);
    core.userData = { type: 'hub', hubInfo: { name: hub, agentCount } };
    clickableObjects.push(core);
    scene.add(core);

    // Orbiting ring
    const ringGeo = new THREE.RingGeometry(1.2, 1.25, 64);
    const ringMat = new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: 0.2, side: THREE.DoubleSide,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(center.x, center.y, center.z);
    ring.userData = { type: 'hub-ring', pulsePhase: Math.random() * Math.PI * 2 };
    scene.add(ring);
  });

  // Draw connections between hubs
  const hubNames = Object.keys(hubCenters);
  for (let i = 0; i < hubNames.length; i++) {
    for (let j = i + 1; j < hubNames.length; j++) {
      const a = hubCenters[hubNames[i]];
      const b = hubCenters[hubNames[j]];
      const points = [new THREE.Vector3(a.x, a.y, a.z), new THREE.Vector3(b.x, b.y, b.z)];
      const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
      const lineMat = new THREE.LineBasicMaterial({ color: 0x1a3050, transparent: true, opacity: 0.15 });
      scene.add(new THREE.Line(lineGeo, lineMat));
    }
  }

  // Draw agents as small spheres orbiting their hub
  agents.forEach((agent, idx) => {
    const group = new THREE.Group();
    const hubColor = hubColors[agent.hub] || 0x666666;
    const hubCenter = hubCenters[agent.hub] || { x: 0, y: 0, z: 0 };
    const hubAgents = agentsByHub[agent.hub];
    const agentIndexInHub = hubAgents.indexOf(agent);
    const agentsInHub = hubAgents.length;

    const orbitRadius = 1.8 + (agentIndexInHub % 3) * 0.6;
    const orbitAngle = (agentIndexInHub / agentsInHub) * Math.PI * 2;
    const orbitHeight = Math.sin(agentIndexInHub * 0.7) * 0.3;

    const x = hubCenter.x + Math.cos(orbitAngle) * orbitRadius;
    const y = hubCenter.y + orbitHeight;
    const z = hubCenter.z + Math.sin(orbitAngle) * orbitRadius;
    group.position.set(x, y, z);

    // Agent dot
    const dotGeo = new THREE.SphereGeometry(0.18, 12, 12);
    const dotMat = new THREE.MeshPhongMaterial({
      color: hubColor, emissive: hubColor, emissiveIntensity: 0.3,
    });
    const dot = new THREE.Mesh(dotGeo, dotMat);
    dot.userData = { type: 'agent', agent };
    clickableObjects.push(dot);
    group.add(dot);

    // Thin line from agent to hub center
    const linePoints = [
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(
        hubCenter.x - x,
        hubCenter.y - y,
        hubCenter.z - z
      ),
    ];
    const lineGeo = new THREE.BufferGeometry().setFromPoints(linePoints);
    const lineMat = new THREE.LineBasicMaterial({
      color: hubColor, transparent: true, opacity: 0.12,
    });
    group.add(new THREE.Line(lineGeo, lineMat));

    group.userData = {
      agent, idx, hubCenter, orbitRadius,
      baseOrbitAngle: orbitAngle, orbitHeight,
      orbitSpeed: 0.15 + Math.random() * 0.2,
      orbitDirection: Math.random() > 0.5 ? 1 : -1,
    };

    agentGroups.push(group);
    scene.add(group);
  });
}

export function buildCentralNexus() {
  // Small central reference point
  const geo = new THREE.OctahedronGeometry(0.3, 0);
  const mat = new THREE.MeshPhongMaterial({
    color: 0x00e5ff, emissive: 0x00e5ff, emissiveIntensity: 0.2,
    transparent: true, opacity: 0.4, wireframe: true,
  });
  scene.add(new THREE.Mesh(geo, mat));
}
