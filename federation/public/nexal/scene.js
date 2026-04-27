/**
 * scene.js — Three.js scene initialization and topology building.
 * 3D LAYER ONLY. No imports from ui.js. No DOM touches except #scene canvas.
 *
 * Exports: init, buildSpiderWeb, buildAgentTopologies, buildCentralNexus,
 *          getScene, getCamera, getRenderer, getClickableObjects,
 *          CONSTRAINT_CONFIG, agentGroups
 *
 * Cross-layer communication goes through bridge.js (emitting events).
 * The 2D layer listens for 'agent-selected', 'hub-hovered' on bridge.
 */
import * as THREE from 'three';
import { OrbitControls } from 'https://unpkg.com/three@0.128.0/examples/jsm/controls/OrbitControls.js';
import { makeKleinBottleGeometry, makeMobiusStripGeometry } from './geometry.js';
import { bridge } from './bridge.js';

window.THREE = THREE;

// Module-level scene refs — accessed only through exported getters
let scene, camera, renderer;
export const agentGroups = [];
let clickableObjects = [];

// ──────── CONSTRAINT SYSTEM PARAMETERS ────────────────────────────────────
export const CONSTRAINT_CONFIG = {
  constraintRatio: 0.3,
  followMouse: true,
  whiteNodes: true,
  mouseRadius: 4.0,
  mouseForce: 2.5,

  shrinkOnProximity: true,
  shrinkRadius: 6.0,
  minShrinkScale: 0.3,

  particleEmissions: true,
  emissionInterval: 1000,
  particlesPerEmission: 2,
  particleSpeed: 0.012,
  particleSize: 0.05,

  meshStretch: true,
  stretchMagnitude: 1.8,
  stretchDuration: 2500,
  stretchRecovery: 0.08,

  thefogPreference: 0.6,
  thefogStretchBoost: 1.4,
  thefogDurationBoost: 1.6,
  thefogConcentration: 0.65,
  thefogParticipation: 0.75,

  stretchSpeed: 1.0,

  stretchLighting: true,
  maxLightening: 0.7,

  nodeCount: 200,
  connectionDistance: 1.2,
  springStrength: 0.05,
  damping: 0.98,
  nodeSize: 0.02,

  stableSpringStrength: 0.02,
  stableDamping: 0.95,

  reflectedGround: true,
  whiteTheme: false,
  nodeOpacity: 0.8,
  lineOpacity: 0.3,

  fxaa: false,
  motionBlur: false,
  bloom: false,
};

// ── Getters (replaces window._renderer / window._camera / window._scene) ──
export function getScene()            { return scene; }
export function getCamera()           { return camera; }
export function getRenderer()         { return renderer; }
export function getClickableObjects() { return clickableObjects; }

export function init() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x000000);

  // Only DOM touch allowed in the 3D layer: the canvas element
  const canvas = document.getElementById('scene');
  camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });

  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  camera.position.set(0, 8, 20);
  camera.lookAt(0, 0, 0);

  // Keep window.camera for animation.js mouse interaction (nexal.js also uses it)
  window.camera = camera;

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.minDistance = 5;
  controls.maxDistance = 50;
  controls.minPolarAngle = 0;
  controls.maxPolarAngle = Math.PI;
  controls.autoRotate = false;
  controls.enablePan = true;
  controls.enableZoom = true;
  controls.enableRotate = true;

  window.cameraControls = controls;

  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
                   || window.innerWidth <= 768;
  const mobileBrightnessBoost = isMobile ? 2.0 : 1.0;
  window.isMobile = isMobile;
  window.mobileBrightnessBoost = mobileBrightnessBoost;

  console.log(`Mobile device detected: ${isMobile}, brightness boost: ${mobileBrightnessBoost}x`);

  const ambientLight = new THREE.AmbientLight(0xffffff, 0.2 * mobileBrightnessBoost);
  scene.add(ambientLight);

  const directionalLight = new THREE.DirectionalLight(0xffffff, 1.2 * mobileBrightnessBoost);
  directionalLight.position.set(10, 10, 5);
  directionalLight.castShadow = true;
  directionalLight.shadow.mapSize.width = 2048;
  directionalLight.shadow.mapSize.height = 2048;
  scene.add(directionalLight);

  const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.6 * mobileBrightnessBoost);
  directionalLight2.position.set(-10, -10, -5);
  scene.add(directionalLight2);
}

export function buildSpiderWeb() {
  const webGroup = new THREE.Group();
  webGroup.position.set(0, -3, 0);

  const spokes = 8;
  const rings = 4;
  const outerR = 12;
  const webRings = [];

  for (let r = 1; r <= rings; r++) {
    const radius = (r / rings) * outerR;
    const segmentCount = 64;
    const positions = new Float32Array((segmentCount + 1) * 3);
    const originalPositions = new Float32Array((segmentCount + 1) * 3);

    for (let i = 0; i <= segmentCount; i++) {
      const angle = (i / segmentCount) * Math.PI * 2;
      const x = Math.cos(angle) * radius;
      const y = 0;
      const z = Math.sin(angle) * radius;

      const i3 = i * 3;
      positions[i3] = x; positions[i3 + 1] = y; positions[i3 + 2] = z;
      originalPositions[i3] = x; originalPositions[i3 + 1] = y; originalPositions[i3 + 2] = z;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.MeshBasicMaterial({
      color: 0x2a4a6a, transparent: true, opacity: 0.3,
      emissive: 0x000000, emissiveIntensity: 0,
    });

    const line = new THREE.Line(geometry, material);
    line.userData = { originalPositions, radius, segmentCount, ringIndex: r };

    webRings.push(line);
    webGroup.add(line);
  }

  for (let s = 0; s < spokes; s++) {
    const angle = (s / spokes) * Math.PI * 2;
    const points = [
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(Math.cos(angle) * outerR, 0, Math.sin(angle) * outerR),
    ];
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.MeshBasicMaterial({ color: 0x1a3a5a, transparent: true, opacity: 0.4 });
    webGroup.add(new THREE.Line(geometry, material));
  }

  scene.add(webGroup);

  window._webGroup = webGroup;
  window._webRings = webRings;

  window._dataHighways = {
    connections: [],
    segmentActivity: new Map(),
    lastPulseTime: 0,
    capabilityColors: {
      'detection': 0xff3366,
      'data': 0x00e5ff,
      'deployment': 0x00ff88,
      'strategy': 0xaa00ff,
      'solar': 0xffaa00,
      'default': 0xffffff,
    },
    hubCenters: {
      'hog': { x: -8, y: 2, z: -6 },
      'trillian': { x: 8, y: 3, z: 2 },
      'thefog': { x: -2, y: 5, z: 8 },
      'relay': { x: 6, y: 1, z: -8 },
      'bobiverse': { x: 0, y: 6, z: -10 },
    },
    hubZones: {
      'hog': { angle: 0 },
      'trillian': { angle: Math.PI / 2 },
      'thefog': { angle: Math.PI },
      'relay': { angle: 3 * Math.PI / 2 },
      'bobiverse': { angle: Math.PI / 4 },
    },
  };

  // TEST: Create a visible test connection after animation loop starts
  setTimeout(() => {
    console.log('Creating test neural connection...');
    if (window._createDataPulse) {
      window._createDataPulse('hog', 'trillian', 0xff0000, 1.0, 'TEST-CONNECTION');
      window._createDataPulse('thefog', 'relay', 0x00ff00, 1.0, 'TEST-CONNECTION-2');
    }
  }, 2000);
}

export function buildAgentTopologies(agents) {
  const hubColors = {
    'relay': 0x00e5ff,
    'hog': 0x00ff88,
    'trillian': 0xaa00ff,
    'thefog': 0x8800ff,
    'bobiverse': 0xff6600,
  };

  const hubCenters = {
    'hog': { x: -8, y: 2, z: -6 },
    'trillian': { x: 8, y: 3, z: 2 },
    'thefog': { x: -2, y: 5, z: 8 },
    'relay': { x: 6, y: 1, z: -8 },
    'bobiverse': { x: 0, y: 6, z: -10 },
  };

  window.hubCenters = hubCenters;

  const agentsByHub = {};
  agents.forEach(agent => {
    if (!agentsByHub[agent.hub]) agentsByHub[agent.hub] = [];
    agentsByHub[agent.hub].push(agent);
  });

  agents.forEach((agent, idx) => {
    const group = new THREE.Group();
    const hubColor = hubColors[agent.hub] || 0x666666;
    const scale = 0.8 + Math.random() * 0.4;

    let formGeo;
    if (idx % 2 === 0) {
      formGeo = makeKleinBottleGeometry(scale, 20);
      agent.topologyType = 'kleinBottle';
    } else {
      formGeo = makeMobiusStripGeometry(scale * 1.2, scale * 0.5, 40);
      agent.topologyType = 'mobiusStrip';
    }

    const formMat = new THREE.MeshPhongMaterial({
      color: 0xcccccc,
      emissive: new THREE.Color(hubColor).multiplyScalar(0.15 * window.mobileBrightnessBoost),
      transparent: true, opacity: 0.8, side: THREE.DoubleSide,
    });
    const formMesh = new THREE.Mesh(formGeo, formMat);
    formMesh.castShadow = true;
    formMesh.userData = { type: 'agent', agent, idx };
    clickableObjects.push(formMesh);
    group.add(formMesh);

    const wfMat = new THREE.MeshBasicMaterial({
      color: hubColor, wireframe: true, transparent: true, opacity: 0.9,
    });
    group.add(new THREE.Mesh(formGeo, wfMat));

    const coreGeo = new THREE.SphereGeometry(0.12, 8, 8);
    const coreMat = new THREE.MeshPhongMaterial({
      color: hubColor, emissive: hubColor,
      emissiveIntensity: 0.6 * window.mobileBrightnessBoost,
    });
    group.add(new THREE.Mesh(coreGeo, coreMat));

    const hubCenter = hubCenters[agent.hub] || { x: 0, y: 0, z: 0 };
    const hubAgents = agentsByHub[agent.hub];
    const agentIndexInHub = hubAgents.indexOf(agent);
    const agentsInHub = hubAgents.length;

    let orbitRadius;
    if (agent.hub === 'thefog') {
      orbitRadius = 0.8 + (agentIndexInHub % 3) * 0.3;
    } else {
      orbitRadius = 1.5 + (agentIndexInHub % 3) * 0.8;
    }
    const orbitAngle = (agentIndexInHub / agentsInHub) * Math.PI * 2;
    const orbitHeight = Math.sin(agentIndexInHub * 0.7) * 0.5;

    const orbitalX = hubCenter.x + Math.cos(orbitAngle) * orbitRadius;
    const orbitalY = hubCenter.y + orbitHeight;
    const orbitalZ = hubCenter.z + Math.sin(orbitAngle) * orbitRadius;

    group.position.set(orbitalX, orbitalY, orbitalZ);

    let orbitSpeed;
    if (agent.hub === 'thefog') {
      orbitSpeed = 0.03 + Math.random() * 0.05;
    } else {
      orbitSpeed = 0.2 + Math.random() * 0.3;
    }
    const orbitDirection = Math.random() > 0.5 ? 1 : -1;

    group.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, Math.random() * Math.PI);

    group.userData = {
      agent, idx, hubCenter, orbitRadius,
      baseOrbitAngle: orbitAngle, orbitHeight,
      orbitSpeed, orbitDirection, agentIndexInHub,
    };

    scene.add(group);
    agentGroups.push(group);
  });

  // Hub center markers — clicking them emits 'agent-selected' or 'hub-hovered' via bridge
  Object.entries(hubCenters).forEach(([hubName, center], idx) => {
    const hubMarkerGeo = new THREE.SphereGeometry(0.3, 16, 16);
    const hubColor = hubColors[hubName] || 0x666666;
    const hubMarkerMat = new THREE.MeshPhongMaterial({
      color: hubColor, emissive: hubColor,
      emissiveIntensity: 0.8 * window.mobileBrightnessBoost,
      transparent: true, opacity: 0.9,
    });

    const hubMarker = new THREE.Mesh(hubMarkerGeo, hubMarkerMat);

    const baseOrbitRadius = Math.sqrt(center.x * center.x + center.z * center.z);
    const baseOrbitAngle = Math.atan2(center.z, center.x);
    const baseOrbitHeight = center.y;
    const orbitSpeed = 0.05 + (idx % 3) * 0.01;

    hubMarker.position.set(center.x, center.y, center.z);
    hubMarker.userData = {
      type: 'hub', hubName, isHubCenter: true, isOrbitingHub: true,
      orbitRadius: baseOrbitRadius, orbitAngle: baseOrbitAngle,
      orbitHeight: baseOrbitHeight, orbitSpeed,
      baseCenter: { x: center.x, y: center.y, z: center.z },
      hubInfo: {
        name: hubName,
        color: `#${hubColor.toString(16).padStart(6, '0')}`,
        center,
        description: _getHubDescription(hubName),
      },
    };

    clickableObjects.push(hubMarker);
    scene.add(hubMarker);
    agentGroups.push(hubMarker);

    // Pulsing ring indicator around hub
    const ringGeo = new THREE.RingGeometry(1.0, 1.1, 32);
    const ringMat = new THREE.MeshBasicMaterial({
      color: hubColor, transparent: true, opacity: 0.4, side: THREE.DoubleSide,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(center.x, center.y, center.z);
    ring.lookAt(camera.position);
    ring.userData = { type: 'hub-ring', pulsePhase: idx * 1.2 };
    scene.add(ring);
  });
}

function _getHubDescription(hubName) {
  const descriptions = {
    'hog': 'Development & Monitoring Hub - System health, data detection, solar monitoring, and deployment management.',
    'trillian': 'Guidance & Strategy Hub - Leadership, decision-making, manifold topology, and strategic coordination.',
    'thefog': 'Mystical Computation Hub - Void scanning, deep analysis, and advanced computational research within Sophia\'s realm.',
    'relay': 'Network Coordination Hub - Federation relay, communications, and inter-hub connectivity management.',
  };
  return descriptions[hubName] || 'Unknown hub configuration.';
}

export function buildCentralNexus() {
  const constraintGroup = new THREE.Group();
  constraintGroup.position.set(0, 1, 0);

  const nodes = [];
  const constraints = [];

  for (let i = 0; i < CONSTRAINT_CONFIG.nodeCount; i++) {
    const node = {
      x: (Math.random() - 0.5) * 4, y: (Math.random() - 0.5) * 3, z: (Math.random() - 0.5) * 4,
      vx: 0, vy: 0, vz: 0,
      ox: 0, oy: 0, oz: 0,
      mass: 1, fixed: false, id: i,
    };
    node.ox = node.x; node.oy = node.y; node.oz = node.z;
    nodes.push(node);
  }

  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const nodeA = nodes[i], nodeB = nodes[j];
      const dx = nodeA.x - nodeB.x, dy = nodeA.y - nodeB.y, dz = nodeA.z - nodeB.z;
      const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (distance < CONSTRAINT_CONFIG.connectionDistance) {
        constraints.push({ nodeA: i, nodeB: j, restLength: distance });
      }
    }
  }

  const nodeGeometry = new THREE.SphereGeometry(CONSTRAINT_CONFIG.nodeSize, 8, 8);
  const nodeMaterial = new THREE.MeshPhongMaterial({
    color: CONSTRAINT_CONFIG.whiteNodes ? 0xffffff : 0x4400aa,
    emissive: CONSTRAINT_CONFIG.whiteNodes ? 0x222222 : 0x220044,
    emissiveIntensity: (CONSTRAINT_CONFIG.whiteNodes ? 0.1 : 0.1) * (window.mobileBrightnessBoost || 1.0),
    transparent: true, opacity: CONSTRAINT_CONFIG.nodeOpacity,
  });

  const nodeInstances = [];
  nodes.forEach((node) => {
    const individualMaterial = nodeMaterial.clone();
    const nodeMesh = new THREE.Mesh(nodeGeometry, individualMaterial);
    nodeMesh.position.set(node.x, node.y, node.z);
    nodeInstances.push(nodeMesh);
    constraintGroup.add(nodeMesh);
  });

  const lineGeometry = new THREE.BufferGeometry();
  const linePositions = new Float32Array(constraints.length * 6);

  const lineMaterial = new THREE.LineBasicMaterial({
    color: 0x333333, transparent: true, opacity: CONSTRAINT_CONFIG.lineOpacity,
  });

  constraints.forEach((constraint, i) => {
    const nodeA = nodes[constraint.nodeA], nodeB = nodes[constraint.nodeB];
    const i6 = i * 6;
    linePositions[i6] = nodeA.x; linePositions[i6 + 1] = nodeA.y; linePositions[i6 + 2] = nodeA.z;
    linePositions[i6 + 3] = nodeB.x; linePositions[i6 + 4] = nodeB.y; linePositions[i6 + 5] = nodeB.z;
  });

  lineGeometry.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));
  const constraintLines = new THREE.LineSegments(lineGeometry, lineMaterial);
  constraintGroup.add(constraintLines);

  if (CONSTRAINT_CONFIG.reflectedGround) {
    const groundGeometry = new THREE.PlaneGeometry(20, 20);
    const groundMaterial = new THREE.MeshPhongMaterial({
      color: 0x001122, transparent: true, opacity: 0.1, side: THREE.DoubleSide,
    });
    const ground = new THREE.Mesh(groundGeometry, groundMaterial);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -2;
    constraintGroup.add(ground);
  }

  const initialScale = 25.0;
  constraintGroup.scale.setScalar(initialScale);
  console.log('Constraint group initialized with scale:', initialScale);

  scene.add(constraintGroup);

  const hubCenters = {
    'hog': { x: -8, y: 2, z: -6 },
    'trillian': { x: 8, y: 3, z: 2 },
    'thefog': { x: -2, y: 5, z: 8 },
    'relay': { x: 6, y: 1, z: -8 },
    'bobiverse': { x: 0, y: 6, z: -10 },
  };

  const hubNames = Object.keys(hubCenters);
  const hubPositions = hubNames.map(name => ({
    name,
    position: new THREE.Vector3(hubCenters[name].x, hubCenters[name].y, hubCenters[name].z),
    isThefog: name === 'thefog',
  }));

  window._constraintSystem = {
    group: constraintGroup,
    nodes,
    constraints,
    nodeInstances,
    constraintLines,
    mousePosition: new THREE.Vector3(),
    raycaster: new THREE.Raycaster(),
    mouse: new THREE.Vector2(),

    startTime: null,
    introAnimation: true,
    initialScale,
    targetScale: 1.0,
    introDuration: 2000,
    mouseInteractionEnabled: false,
    mouseEnableTime: 2200,
    frameCount: 0,

    currentScale: 1.0,
    targetProximityScale: 1.0,

    particles: [],
    lastEmissionTime: 0,
    hubPositions,
    particleGroup: new THREE.Group(),

    originalNodePositions: nodes.map(node => ({ x: node.x, y: node.y, z: node.z })),
    activeStretchEffects: [],
    stretchTargets: [],
  };

  scene.add(window._constraintSystem.particleGroup);
}
