/**
 * data.test.js — Unit tests for data.js mesh loading.
 *
 * Tests:
 *   - loadAgentsAndBuild calls buildSpiderWeb, buildAgentTopologies,
 *     buildCentralNexus, and animate with correct args
 *   - emits 'mesh-updated' on bridge after successful fetch
 *   - handles fetch failure gracefully (uses fallback agents, doesn't throw)
 *
 * Note: We use vi.resetModules() + dynamic import inside each test so that
 * the fetch stub is in place before the module is evaluated.
 */

import { vi, describe, test, expect, beforeEach, afterEach } from 'vitest';

// ── Helpers ────────────────────────────────────────────────────────────────

function makeFakeResponse(body) {
  return {
    json: async () => body,
    ok: true,
    status: 200,
  };
}

function makeMocks() {
  return {
    buildSpiderWeb:       vi.fn(),
    buildAgentTopologies: vi.fn(),
    buildCentralNexus:    vi.fn(),
    animate:              vi.fn(),
  };
}

// Reset modules before each test so fetch stubs apply cleanly
beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── Happy path ─────────────────────────────────────────────────────────────

describe('loadAgentsAndBuild — happy path', () => {
  test('calls buildSpiderWeb once', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeFakeResponse({
      agents: [
        { id: 'stella', hub: 'trillian', capabilities: ['guidance'] },
        { id: 'void-watcher', hub: 'thefog', capabilities: ['void-scan'] },
      ],
      darkCircles: [],
    })));

    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');
    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);
    expect(mocks.buildSpiderWeb).toHaveBeenCalledTimes(1);
  });

  test('calls buildAgentTopologies with agents array from fetch', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeFakeResponse({
      agents: [
        { id: 'stella', hub: 'trillian', capabilities: ['guidance'] },
        { id: 'void-watcher', hub: 'thefog', capabilities: ['void-scan'] },
      ],
      darkCircles: [],
    })));

    vi.resetModules();
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');
    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);

    expect(mocks.buildAgentTopologies).toHaveBeenCalledTimes(1);
    const calledWith = mocks.buildAgentTopologies.mock.calls[0][0];
    expect(Array.isArray(calledWith)).toBe(true);
    expect(calledWith.length).toBe(2);
    expect(calledWith[0].id).toBe('stella');
  });

  test('calls buildCentralNexus once', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeFakeResponse({
      agents: [{ id: 'x', hub: 'hog', capabilities: [] }],
    })));

    vi.resetModules();
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');
    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);
    expect(mocks.buildCentralNexus).toHaveBeenCalledTimes(1);
  });

  test('calls animate once', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeFakeResponse({
      agents: [{ id: 'x', hub: 'hog', capabilities: [] }],
    })));

    vi.resetModules();
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');
    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);
    expect(mocks.animate).toHaveBeenCalledTimes(1);
  });

  test('emits mesh-updated on bridge with agents array', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeFakeResponse({
      agents: [
        { id: 'stella', hub: 'trillian', capabilities: ['guidance'] },
        { id: 'void-watcher', hub: 'thefog', capabilities: ['void-scan'] },
      ],
      darkCircles: [],
    })));

    vi.resetModules();
    const { bridge } = await import('../../public/nexal/bridge.js');
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');

    let meshUpdatedPayload = null;
    bridge.on('mesh-updated', (p) => { meshUpdatedPayload = p; });

    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);

    expect(meshUpdatedPayload).not.toBeNull();
    expect(meshUpdatedPayload.agents).toHaveLength(2);
  });
});

// ── Fetch failure / fallback ───────────────────────────────────────────────

describe('loadAgentsAndBuild — fetch failure', () => {
  test('does not throw on fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')));
    vi.resetModules();
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');
    const mocks = makeMocks();
    await expect(loadAgentsAndBuild(mocks)).resolves.not.toThrow();
  });

  test('still calls buildSpiderWeb with fallback agents', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')));
    vi.resetModules();
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');
    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);
    expect(mocks.buildSpiderWeb).toHaveBeenCalledTimes(1);
  });

  test('buildAgentTopologies receives non-empty fallback agent array', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')));
    vi.resetModules();
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');
    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);
    expect(mocks.buildAgentTopologies).toHaveBeenCalledTimes(1);
    const agents = mocks.buildAgentTopologies.mock.calls[0][0];
    expect(agents.length).toBeGreaterThan(0);
  });

  test('animate still called even after fetch failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')));
    vi.resetModules();
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');
    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);
    expect(mocks.animate).toHaveBeenCalledTimes(1);
  });

  test('emits mesh-updated even on fetch failure (fallback path)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')));
    vi.resetModules();
    const { bridge } = await import('../../public/nexal/bridge.js');
    const { loadAgentsAndBuild } = await import('../../public/nexal/data.js');

    let payload = null;
    bridge.on('mesh-updated', (p) => { payload = p; });

    const mocks = makeMocks();
    await loadAgentsAndBuild(mocks);

    expect(payload).not.toBeNull();
    expect(payload.agents.length).toBeGreaterThan(0);
  });
});
