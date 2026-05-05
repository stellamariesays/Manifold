/**
 * ui.js — HUD panel update functions.
 * Exports: updateAgentsList, updateStatusPanel, showAgentDetails, showHubDetails, hideDetailPanel
 */

export function updateAgentsList(agents) {
  const agentsList = document.getElementById('agents-list');
  agentsList.innerHTML = '';

  const hubColors = {
    'hog': '#00ff88',
    'trillian': '#aa00ff',
    'thefog': '#8800ff',
    'relay': '#00e5ff',
    'bobiverse': '#ff6600',
  };

  agents.forEach(agent => {
    const item = document.createElement('div');
    item.className = 'agent-item';

    const hubColor = hubColors[agent.hub] || '#666666';

    item.innerHTML = `
      <div class="agent-dot" style="background: ${hubColor}"></div>
      <span class="agent-name">${agent.name || agent.id}</span>
      <span class="agent-caps">${agent.capabilities ? agent.capabilities.length : 1} caps</span>
    `;

    agentsList.appendChild(item);
  });
}

// ── Animated counter helpers ────────────────────────────────
const _animatedValues = {};

function animateValue(el, key, target) {
  if (!_animatedValues[key]) _animatedValues[key] = { current: 0, el };
  const entry = _animatedValues[key];
  entry.target = target;
  if (!entry.raf) {
    const tick = () => {
      const diff = entry.target - entry.current;
      if (Math.abs(diff) < 0.5) {
        entry.current = entry.target;
        entry.el.textContent = Math.round(entry.current);
        entry.raf = null;
        return;
      }
      entry.current += diff * 0.2;
      entry.el.textContent = Math.round(entry.current);
      entry.raf = requestAnimationFrame(tick);
    };
    entry.raf = requestAnimationFrame(tick);
  }
}

// ── Last-updated ticker ─────────────────────────────────────
let _lastUpdatedInterval = null;

function startLastUpdatedTicker() {
  if (_lastUpdatedInterval) return;
  _lastUpdatedInterval = setInterval(() => {
    const el = document.getElementById('last-updated');
    if (!el) return;
    const lastPoll = (typeof window !== 'undefined' && window._meshLastPoll) || 0;
    if (!lastPoll) { el.textContent = '—'; return; }
    const ago = Math.round((Date.now() - lastPoll) / 1000);
    el.textContent = ago < 60 ? `${ago}s ago` : `${Math.floor(ago / 60)}m ${ago % 60}s ago`;
  }, 1000);
}

// ── Pressure bar graph ──────────────────────────────────────
function renderPressureBars(darkCircles) {
  const container = document.getElementById('pressure-bars');
  if (!container) return;
  if (!darkCircles || !darkCircles.length) { container.innerHTML = '<div style="font-size:9px;color:rgba(255,255,255,0.3)">No dark circle data</div>'; return; }

  // Sort by strength descending, take top 5
  const top5 = [...darkCircles]
    .sort((a, b) => (b.strength || b.pressure || 0) - (a.strength || a.pressure || 0))
    .slice(0, 5);

  const maxStr = Math.max(1, ...top5.map(c => c.strength || c.pressure || 0));

  container.innerHTML = top5.map(c => {
    const val = c.strength || c.pressure || 0;
    const pct = Math.round((val / maxStr) * 100);
    const name = (c.name || c.id || 'unknown').substring(0, 12);
    return `<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">
      <span style="font-size:9px;color:rgba(255,255,255,0.5);width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${name}</span>
      <div style="flex:1;height:8px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden">
        <div style="width:${pct}%;height:100%;background:linear-gradient(90deg,#aa00ff,#ff0077);border-radius:2px;transition:width 0.6s ease"></div>
      </div>
      <span style="font-size:8px;color:rgba(255,255,255,0.4);width:24px;text-align:right">${val.toFixed(1)}</span>
    </div>`;
  }).join('');
}

export function updateStatusPanel(agents, rtt) {
  // Agent count — animated
  const agentEl = document.getElementById('agent-count');
  if (agentEl) animateValue(agentEl, 'agents', agents.length);

  // Capability count — animated
  const totalCaps = agents.reduce((sum, a) => sum + (a.capabilities ? a.capabilities.length : 1), 0);
  const capEl = document.getElementById('capability-count');
  if (capEl) animateValue(capEl, 'caps', totalCaps);

  // Latency — from RTT measurement
  const latEl = document.getElementById('mesh-latency');
  if (latEl) {
    const ms = rtt != null ? rtt : (typeof window !== 'undefined' && window._meshRTT) || '—';
    latEl.textContent = typeof ms === 'number' ? `${ms}ms` : ms;
  }

  // Peer count — unique hubs
  const hubs = [...new Set(agents.map(a => a.hub).filter(Boolean))];
  const peerEl = document.getElementById('peer-count');
  if (peerEl) animateValue(peerEl, 'peers', hubs.length);

  // Hub names
  const hubEl = document.getElementById('hub-names');
  if (hubEl) hubEl.textContent = hubs.join(', ') || '—';

  // Pressure bar graph
  const meshData = (typeof window !== 'undefined' && window._meshData) || {};
  renderPressureBars(meshData.darkCircles);

  // Start the last-updated ticker
  startLastUpdatedTicker();
}

export function showAgentDetails(agent) {
  const panel = document.getElementById('detail-panel');
  panel.classList.add('visible');

  document.getElementById('detail-agent-name').textContent = agent.name || agent.id;
  document.getElementById('detail-agent-hub').textContent = `Hub: ${agent.hub}`;
  document.getElementById('detail-messages').textContent = Math.floor(Math.random() * 999);
  document.getElementById('detail-uptime').textContent = '99%';

  const capsDiv = document.getElementById('detail-capabilities');
  capsDiv.innerHTML = agent.capabilities
    ? agent.capabilities.map(cap => `<span style="color: #00e5ff; font-size: 10px;">${cap}</span>`).join(', ')
    : '<span style="color: #666;">No capabilities listed</span>';
}

export function showHubDetails(hubInfo) {
  const panel = document.getElementById('detail-panel');
  panel.classList.add('visible');

  document.getElementById('detail-agent-name').textContent = `${hubInfo.name.toUpperCase()} HUB`;
  document.getElementById('detail-agent-hub').textContent = `Type: Federation Hub`;

  const pos = hubInfo.center;
  document.getElementById('detail-messages').textContent = `${pos.x}, ${pos.y}, ${pos.z}`;
  document.getElementById('detail-uptime').textContent = 'ACTIVE';

  const capsDiv = document.getElementById('detail-capabilities');
  capsDiv.innerHTML = `<span style="color: ${hubInfo.color}; font-size: 11px; line-height: 1.4;">${hubInfo.description}</span>`;
}

export function hideDetailPanel() {
  document.getElementById('detail-panel').classList.remove('visible');
}

// ── Query Panel Logic ──────────────────────────────────────────

const queryHistory = []
const MAX_HISTORY = 5
let currentAbortController = null
let typingInterval = null

export function initQueryPanel(agents) {
  // IDs match the HTML in index.html
  const input = document.getElementById('query-input')
  const sendBtn = document.getElementById('query-send')
  const agentSelect = document.getElementById('agent-route')
  const responseDiv = document.getElementById('query-response')
  const responseText = document.getElementById('response-text')
  const responseTag = document.getElementById('response-tag')
  const copyBtn = document.getElementById('copy-btn')
  const histToggle = document.getElementById('history-toggle')
  const historyDiv = document.getElementById('query-history')

  if (!input || !sendBtn) return // panel not in DOM

  // Build agent lookup: name → name@hub
  const agentMap = {}
  agents.forEach(a => {
    const key = a.name || a.id
    agentMap[key] = `${key}@${a.hub}`
  })

  // Populate agent dropdown with live agents
  const currentVal = agentSelect ? agentSelect.value : ''
  if (agentSelect) {
    agentSelect.innerHTML = '<option value="auto">⟐ Auto-route</option>'
    agents.forEach(a => {
      const name = a.name || a.id
      const opt = document.createElement('option')
      opt.value = name
      opt.textContent = `${name} · ${a.hub}`
      agentSelect.appendChild(opt)
    })
    agentSelect.value = currentVal || 'auto'
  }

  // Copy button
  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const text = (responseText || responseDiv).textContent.replace('📋 Copy', '').trim()
      navigator.clipboard.writeText(text).catch(() => {})
      copyBtn.textContent = '✓ Copied'
      setTimeout(() => { copyBtn.textContent = '📋 Copy' }, 1500)
    })
  }

  // History toggle
  if (histToggle && historyDiv) {
    histToggle.addEventListener('click', () => {
      histToggle.classList.toggle('open')
      historyDiv.classList.toggle('open')
    })
  }

  // Send query
  function sendQuery() {
    const command = input.value.trim()
    if (!command) return
    const selectedAgent = agentSelect ? agentSelect.value : 'auto'
    const target = selectedAgent !== 'auto' ? (agentMap[selectedAgent] || selectedAgent) : null
    input.value = ''
    sendBtn.disabled = true

    // Show response area
    if (responseDiv) responseDiv.style.display = 'block'
    if (responseTag) responseTag.textContent = target ? `→ ${target}` : '→ auto'
    if (responseText) responseText.textContent = '…'

    // Add to history
    queryHistory.unshift({ command, agent: target })
    if (queryHistory.length > MAX_HISTORY) queryHistory.pop()
    renderHistory()

    // Cancel any in-flight
    cancelQuery()
    currentAbortController = new AbortController()

    const body = target
      ? { command, target, timeout_ms: 20000 }
      : { command, capability: 'task-execution', timeout_ms: 20000 }

    fetch('/api/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: currentAbortController.signal
    })
    .then(r => r.json())
    .then(data => {
      // Update tag with actual responder
      if (data.executed_by && responseTag) responseTag.textContent = `→ ${data.executed_by}`
      const text = data.output || data.error || data.status || 'No response'
      if (responseText) {
        responseText.textContent = ''
        typewriterEffect(responseText, text, null, null)
      }
    })
    .catch(err => {
      if (err.name === 'AbortError') return
      if (responseText) responseText.textContent = `Mesh unreachable: ${err.message}`
      if (responseTag) responseTag.textContent = '× offline'
    })
    .finally(() => {
      sendBtn.disabled = false
      currentAbortController = null
    })
  }

  sendBtn.addEventListener('click', sendQuery)
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') sendQuery()
  })

  function renderHistory() {
    if (!historyDiv) return
    historyDiv.innerHTML = ''
    queryHistory.forEach(item => {
      const div = document.createElement('div')
      div.className = 'history-item'
      div.innerHTML = `<div class="history-q">${item.agent ? item.agent + ': ' : ''}${item.command}</div>`
      div.addEventListener('click', () => {
        input.value = item.command
        if (agentSelect && item.agent) {
          const name = item.agent.split('@')[0]
          agentSelect.value = name
        }
      })
      historyDiv.appendChild(div)
    })
  }
}

function typewriterEffect(container, text, copyEl, cursorEl) {
  let i = 0
  const span = document.createElement('span')
  span.className = 'typewriter-text'
  container.insertBefore(span, copyEl)
  if (typingInterval) clearInterval(typingInterval)
  typingInterval = setInterval(() => {
    if (i < text.length) {
      span.textContent += text[i]
      i++
    } else {
      clearInterval(typingInterval)
      typingInterval = null
      if (cursorEl) cursorEl.remove()
    }
  }, 20)
}

function cancelQuery() {
  if (typingInterval) { clearInterval(typingInterval); typingInterval = null }
  if (currentAbortController) { currentAbortController.abort(); currentAbortController = null }
  const responseDiv = document.getElementById('query-response')
  const cursor = responseDiv.querySelector('.typing-cursor')
  if (cursor) cursor.remove()
}

// Global hotkeys
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', e => {
    // Q focuses query input (only when not already typing)
    if (e.key === 'q' || e.key === 'Q') {
      const active = document.activeElement
      if (active && (active.tagName === 'INPUT' || active.tagName === 'SELECT' || active.tagName === 'TEXTAREA')) return
      const input = document.getElementById('query-input')
      if (input) { e.preventDefault(); input.focus() }
    }
    // Escape cancels in-flight query
    if (e.key === 'Escape') {
      cancelQuery()
      const input = document.getElementById('query-input')
      if (input) { input.value = ''; input.blur() }
    }
  })
}
