/**
 * nexal-mobile.js — Mobile entry point.
 *
 * Reuses the same scene.js / animation.js / data.js / bridge.js as desktop.
 * Overrides mobile-specific params BEFORE scene init:
 *   - Reduced particle count
 *   - Disabled mouse interaction (touch replaces it)
 *   - Lighter spring physics
 *   - No orbit controls pan / inertia tuned for touch
 *
 * Wires a mobile-native bottom-drawer UI instead of desktop panels.
 */
import { bridge } from '../bridge.js';
import {
  init, buildSpiderWeb, buildAgentTopologies, buildCentralNexus,
  getCamera, getRenderer, getScene, getClickableObjects,
  CONSTRAINT_CONFIG, agentGroups,
} from '../scene.js';
import { animate } from '../animation.js';
import { loadAgentsAndBuild } from '../data.js';
import * as THREE from 'three';

// ── Mobile overrides (before init) ────────────────────────────────────────
Object.assign(CONSTRAINT_CONFIG, {
  nodeCount:            80,    // desktop: 200
  particlesPerEmission: 1,     // desktop: 2
  emissionInterval:     1500,  // desktop: 1000
  particleSize:         0.07,  // slightly larger so visible on small screens
  connectionDistance:   1.4,
  followMouse:          false, // no mouse on touch
  shrinkOnProximity:    false, // saves GPU
  meshStretch:          true,
  stretchMagnitude:     1.4,   // toned down
});

// ── Scene bootstrap ────────────────────────────────────────────────────────
init();

// Tune orbit controls for touch
const controls = window.cameraControls;
if (controls) {
  controls.enablePan        = false;
  controls.dampingFactor    = 0.08;
  controls.minDistance      = 8;
  controls.maxDistance      = 35;
  controls.autoRotate       = true;
  controls.autoRotateSpeed  = 0.4;
  controls.touches = {
    ONE: THREE.TOUCH.ROTATE,
    TWO: THREE.TOUCH.DOLLY_ROTATE,
  };
}

// Forward touch events from the touch-capture div to the canvas so
// OrbitControls (attached to canvas) gets them, without the canvas
// itself sitting on top of and blocking the UI buttons.
const touchCapture = document.getElementById('touch-capture');
const canvas = document.getElementById('scene');
if (touchCapture && canvas) {
  ['touchstart', 'touchmove', 'touchend', 'touchcancel',
   'pointerdown', 'pointermove', 'pointerup',
   'wheel', 'contextmenu'].forEach(type => {
    touchCapture.addEventListener(type, e => {
      // Don't forward if a sheet/drawer is open (let backdrop handle it)
      if (document.getElementById('m-drawer')?.classList.contains('open')) return;
      if (document.getElementById('m-query-sheet')?.classList.contains('open')) return;
      const clone = new e.constructor(e.type, e);
      canvas.dispatchEvent(clone);
    }, { passive: false });
  });
}

// Camera closer for portrait screens
const cam = getCamera();
if (cam && window.innerWidth < window.innerHeight) {
  cam.position.set(0, 6, 26);
  cam.lookAt(0, 0, 0);
}

// ── Bridge: wire mobile UI ─────────────────────────────────────────────────
bridge.on('mesh-updated', ({ agents }) => {
  _updateMobileAgentCount(agents);
  _populateAgentDrawer(agents);
});

bridge.on('agent-selected', ({ agent }) => {
  _showAgentCard(agent);
});

bridge.on('hub-hovered', ({ hub }) => {
  _showHubCard(hub);
});

// ── Load data + start animation ────────────────────────────────────────────
loadAgentsAndBuild({ buildSpiderWeb, buildAgentTopologies, buildCentralNexus, animate });

// ── Window resize ──────────────────────────────────────────────────────────
window.addEventListener('resize', () => {
  const camera   = getCamera();
  const renderer = getRenderer();
  if (!camera || !renderer) return;
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ── Touch tap → agent/hub selection (on touch-capture zone only) ──────────
let _tapStart = null;
const _tapTarget = document.getElementById('touch-capture') ?? window;
_tapTarget.addEventListener('touchstart', e => { _tapStart = e.touches[0]; }, { passive: true });
_tapTarget.addEventListener('touchend', e => {
  if (!_tapStart) return;
  const t = e.changedTouches[0];
  const dx = t.clientX - _tapStart.clientX;
  const dy = t.clientY - _tapStart.clientY;
  if (Math.sqrt(dx * dx + dy * dy) > 10) return; // was a drag, not a tap

  const camera = getCamera();
  if (!camera) return;

  const mouse = new THREE.Vector2(
    (t.clientX / window.innerWidth)  *  2 - 1,
    (t.clientY / window.innerHeight) * -2 + 1,
  );

  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(mouse, camera);
  const hits = raycaster.intersectObjects(getClickableObjects());

  if (hits.length > 0) {
    const obj = hits[0].object;
    if (obj.userData?.agent) {
      bridge.emit('agent-selected', { agent: obj.userData.agent });
    } else if (obj.userData?.type === 'hub') {
      bridge.emit('hub-hovered', { hub: obj.userData.hubInfo });
    }
  } else {
    _hideCard();
  }
});

// ── Mobile UI helpers ──────────────────────────────────────────────────────

function _updateMobileAgentCount(agents) {
  const el = document.getElementById('m-agent-count');
  if (el) el.textContent = agents.length;
}

function _populateAgentDrawer(agents) {
  const list = document.getElementById('m-drawer-list');
  if (!list) return;

  const hubColors = {
    hog:      '#00ff88',
    trillian: '#aa00ff',
    thefog:   '#8800ff',
    relay:    '#00e5ff',
    bobiverse:'#ff6600',
  };

  list.innerHTML = '';
  agents.forEach(agent => {
    const row = document.createElement('div');
    row.className = 'drawer-row';
    row.innerHTML = `
      <div class="drawer-dot" style="background:${hubColors[agent.hub] ?? '#666'}"></div>
      <div class="drawer-name">${agent.name ?? agent.id}</div>
      <div class="drawer-hub">${agent.hub}</div>
    `;
    row.addEventListener('click', () => {
      bridge.emit('agent-selected', { agent });
      _closeDrawer();
    });
    list.appendChild(row);
  });
}

function _showAgentCard(agent) {
  const card = document.getElementById('m-card');
  if (!card) return;
  document.getElementById('m-card-title').textContent = agent.name ?? agent.id;
  document.getElementById('m-card-sub').textContent   = `Hub: ${agent.hub}`;
  document.getElementById('m-card-body').textContent  =
    agent.capabilities?.join(' · ') ?? 'No capabilities listed';
  card.classList.add('visible');
}

function _showHubCard(hub) {
  const card = document.getElementById('m-card');
  if (!card) return;
  document.getElementById('m-card-title').textContent = `${hub.name?.toUpperCase()} HUB`;
  document.getElementById('m-card-sub').textContent   = 'Federation Hub';
  document.getElementById('m-card-body').textContent  = hub.description ?? '';
  card.classList.add('visible');
}

function _hideCard() {
  document.getElementById('m-card')?.classList.remove('visible');
}

function _closeDrawer() {
  document.getElementById('m-drawer')?.classList.remove('open');
}

// Expose for inline HTML handlers
window._mHideCard   = _hideCard;
window._mToggleDrawer = () => {
  document.getElementById('m-drawer')?.classList.toggle('open');
};
window._mOpenQuery = () => {
  document.getElementById('m-query-sheet')?.classList.add('open');
};
window._mCloseQuery = () => {
  document.getElementById('m-query-sheet')?.classList.remove('open');
};

// ── Query submit ───────────────────────────────────────────────────────────
const PRESET_PROMPT =
  `Look into current sentiment around Bitcoin, Iran, fed funds, and the gold narrative. ` +
  `Consider using the Stingray tool for live indicator data. ` +
  `Then write a 5-week trading plan for Bitcoin — can use up to 5× leverage long or short.`;

window._mLoadPreset = () => {
  const ta = document.getElementById('m-query-input');
  if (ta) ta.value = PRESET_PROMPT;
};

window._mSubmitQuery = async () => {
  const ta  = document.getElementById('m-query-input');
  const btn = document.getElementById('m-query-btn');
  const out = document.getElementById('m-query-out');
  if (!ta || !btn) return;

  const prompt = ta.value.trim();
  if (!prompt) return;

  btn.disabled = true;
  btn.textContent = 'Routing…';
  out.textContent = '';
  out.style.display = 'none';

  try {
    const res = await fetch('/tasks', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('nexal_token') ?? ''}`,
      },
      body: JSON.stringify({
        target: 'stella@trillian',
        command: 'prompt',
        args: { message: prompt },
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const taskId = data.taskId ?? data.id;
    if (taskId) {
      out.style.display = 'block';
      out.textContent = `Task queued (${taskId.slice(0,8)}…) — polling…`;
      await _pollTask(taskId, out);
    } else {
      out.style.display = 'block';
      out.textContent = JSON.stringify(data, null, 2);
    }
  } catch (err) {
    out.style.display = 'block';
    out.textContent = `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Send';
  }
};

async function _pollTask(taskId, out) {
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 3000));
    try {
      const r = await fetch(`/tasks/${taskId}`);
      if (!r.ok) continue;
      const d = await r.json();
      if (d.status === 'complete' || d.status === 'done') {
        out.textContent = typeof d.result === 'string' ? d.result : JSON.stringify(d.result ?? d, null, 2);
        return;
      }
      if (d.status === 'error' || d.status === 'failed') {
        out.textContent = `Failed: ${d.error ?? 'unknown'}`;
        return;
      }
      out.textContent = `Status: ${d.status} (${i + 1}/60)…`;
    } catch {}
  }
  out.textContent = 'Timeout — no result after 3 minutes.';
}
