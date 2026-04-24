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

export function updateStatusPanel(agents) {
  document.getElementById('agent-count').textContent = agents.length;

  const totalCaps = agents.reduce((sum, agent) =>
    sum + (agent.capabilities ? agent.capabilities.length : 1), 0);
  document.getElementById('capability-count').textContent = totalCaps;
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
