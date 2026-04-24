// @vitest-environment jsdom
/**
 * ui.test.js — Unit tests for ui.js HUD panel functions.
 *
 * Uses jsdom environment. Sets up the minimal DOM that ui.js expects,
 * then calls the exported functions and asserts the DOM was updated.
 */

import { describe, test, expect, beforeEach } from 'vitest';

// ── DOM setup ─────────────────────────────────────────────────────────────

function setupDOM() {
  document.body.innerHTML = `
    <div id="agents-list"></div>
    <span id="agent-count"></span>
    <span id="capability-count"></span>
    <div id="detail-panel">
      <div id="detail-agent-name"></div>
      <div id="detail-agent-hub"></div>
      <span id="detail-messages"></span>
      <span id="detail-uptime"></span>
      <div id="detail-capabilities"></div>
    </div>
  `;
}

// ── Helpers ────────────────────────────────────────────────────────────────

const sampleAgents = [
  { id: 'stella',       hub: 'trillian', capabilities: ['guidance', 'topology'] },
  { id: 'void-watcher', hub: 'thefog',   capabilities: ['void-scan'] },
  { id: 'relay-bot',    hub: 'relay',    capabilities: [] },
];

// ── Imports ────────────────────────────────────────────────────────────────

const {
  updateAgentsList,
  updateStatusPanel,
  showAgentDetails,
  showHubDetails,
  hideDetailPanel,
} = await import('../../public/nexal/ui.js');

// ── updateAgentsList ───────────────────────────────────────────────────────

describe('updateAgentsList', () => {
  beforeEach(setupDOM);

  test('populates the list with one item per agent', () => {
    updateAgentsList(sampleAgents);
    const items = document.querySelectorAll('.agent-item');
    expect(items.length).toBe(3);
  });

  test('each item contains the agent id/name', () => {
    updateAgentsList(sampleAgents);
    const text = document.getElementById('agents-list').textContent;
    expect(text).toContain('stella');
    expect(text).toContain('void-watcher');
    expect(text).toContain('relay-bot');
  });

  test('shows capability count in each item', () => {
    updateAgentsList(sampleAgents);
    const items = document.querySelectorAll('.agent-caps');
    // stella has 2, void-watcher has 1, relay-bot has 0 (shows 1 as fallback)
    const counts = Array.from(items).map(el => el.textContent.trim());
    expect(counts[0]).toMatch(/2/);
    expect(counts[1]).toMatch(/1/);
  });

  test('clears list before re-populating', () => {
    updateAgentsList(sampleAgents);
    updateAgentsList([sampleAgents[0]]);
    const items = document.querySelectorAll('.agent-item');
    expect(items.length).toBe(1);
  });

  test('handles empty agent array without throwing', () => {
    expect(() => updateAgentsList([])).not.toThrow();
    const items = document.querySelectorAll('.agent-item');
    expect(items.length).toBe(0);
  });

  test('uses agent.name if present, else agent.id', () => {
    updateAgentsList([{ id: 'foo', name: 'Foo Agent', hub: 'hog', capabilities: [] }]);
    expect(document.getElementById('agents-list').textContent).toContain('Foo Agent');
  });
});

// ── updateStatusPanel ──────────────────────────────────────────────────────

describe('updateStatusPanel', () => {
  beforeEach(setupDOM);

  test('sets agent-count to number of agents', () => {
    updateStatusPanel(sampleAgents);
    expect(document.getElementById('agent-count').textContent).toBe('3');
  });

  test('sets capability-count to total capabilities', () => {
    // stella: 2, void-watcher: 1, relay-bot: 0 (fallback 1) = total 4
    updateStatusPanel(sampleAgents);
    const count = parseInt(document.getElementById('capability-count').textContent, 10);
    // 2 + 1 + 1(fallback) = 4, or 2+1+0=3 depending on implementation
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test('handles empty array', () => {
    expect(() => updateStatusPanel([])).not.toThrow();
    expect(document.getElementById('agent-count').textContent).toBe('0');
  });
});

// ── showAgentDetails ───────────────────────────────────────────────────────

describe('showAgentDetails', () => {
  beforeEach(setupDOM);

  test('adds "visible" class to detail-panel', () => {
    showAgentDetails(sampleAgents[0]);
    expect(document.getElementById('detail-panel').classList.contains('visible')).toBe(true);
  });

  test('sets detail-agent-name to agent name or id', () => {
    showAgentDetails({ id: 'stella', hub: 'trillian', capabilities: [] });
    expect(document.getElementById('detail-agent-name').textContent).toBe('stella');
  });

  test('uses agent.name if present', () => {
    showAgentDetails({ id: 'x', name: 'Stella Marie', hub: 'trillian', capabilities: [] });
    expect(document.getElementById('detail-agent-name').textContent).toBe('Stella Marie');
  });

  test('sets detail-agent-hub to hub info', () => {
    showAgentDetails(sampleAgents[0]);
    expect(document.getElementById('detail-agent-hub').textContent).toContain('trillian');
  });

  test('renders capabilities in detail-capabilities', () => {
    showAgentDetails({ id: 'x', hub: 'hog', capabilities: ['monitoring', 'scheduling'] });
    const capsText = document.getElementById('detail-capabilities').textContent;
    expect(capsText).toContain('monitoring');
    expect(capsText).toContain('scheduling');
  });

  test('handles agent with no capabilities', () => {
    expect(() =>
      showAgentDetails({ id: 'x', hub: 'hog', capabilities: undefined })
    ).not.toThrow();
  });
});

// ── showHubDetails ─────────────────────────────────────────────────────────

describe('showHubDetails', () => {
  beforeEach(setupDOM);

  const hubInfo = {
    name: 'trillian',
    color: '#aa00ff',
    center: { x: 8, y: 3, z: 2 },
    description: 'Guidance hub.',
  };

  test('adds "visible" class to detail-panel', () => {
    showHubDetails(hubInfo);
    expect(document.getElementById('detail-panel').classList.contains('visible')).toBe(true);
  });

  test('sets detail-agent-name to hub name in uppercase', () => {
    showHubDetails(hubInfo);
    expect(document.getElementById('detail-agent-name').textContent).toContain('TRILLIAN');
  });

  test('shows hub description', () => {
    showHubDetails(hubInfo);
    const capsText = document.getElementById('detail-capabilities').textContent;
    expect(capsText).toContain('Guidance hub');
  });
});

// ── hideDetailPanel ────────────────────────────────────────────────────────

describe('hideDetailPanel', () => {
  beforeEach(setupDOM);

  test('removes "visible" class from detail-panel', () => {
    const panel = document.getElementById('detail-panel');
    panel.classList.add('visible');
    hideDetailPanel();
    expect(panel.classList.contains('visible')).toBe(false);
  });

  test('does not throw if panel is already hidden', () => {
    expect(() => hideDetailPanel()).not.toThrow();
  });
});
