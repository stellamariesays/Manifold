import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { CapabilityIndex } from '../src/server/capability-index.js'
import { MeshSync } from '../src/server/mesh-sync.js'
import type { AgentInfo } from '../src/protocol/messages.js'

// ── CapabilityIndex unit tests ─────────────────────────────────────────────────

describe('CapabilityIndex', () => {
  let idx: CapabilityIndex

  beforeEach(() => {
    idx = new CapabilityIndex()
  })

  it('starts empty', () => {
    expect(idx.getAllAgents()).toHaveLength(0)
    expect(idx.getAllCapabilities()).toHaveLength(0)
  })

  it('inserts an agent', () => {
    idx.upsertAgent({ name: 'braid', hub: 'trillian', capabilities: ['solar-prediction'] }, true)
    expect(idx.getAllAgents()).toHaveLength(1)
  })

  it('finds agent by key', () => {
    idx.upsertAgent({ name: 'stella', hub: 'trillian', capabilities: ['deployment-versioning'] }, true)
    const a = idx.getAgent('stella', 'trillian')
    expect(a).toBeDefined()
    expect(a!.name).toBe('stella')
  })

  it('finds agents by capability', () => {
    idx.upsertAgent({ name: 'braid', hub: 'trillian', capabilities: ['solar-prediction', 'flare-detection'] }, true)
    idx.upsertAgent({ name: 'stella', hub: 'trillian', capabilities: ['deployment-versioning'] }, false)

    const solar = idx.findByCapability('solar-prediction')
    expect(solar).toHaveLength(1)
    expect(solar[0].name).toBe('braid')
  })

  it('filters by minPressure', () => {
    idx.upsertAgent({ name: 'a', hub: 'h', capabilities: ['foo'], pressure: 0.8 }, true)
    idx.upsertAgent({ name: 'b', hub: 'h', capabilities: ['foo'], pressure: 0.2 }, true)

    const results = idx.findByCapability('foo', 0.5)
    expect(results).toHaveLength(1)
    expect(results[0].name).toBe('a')
  })

  it('returns empty when capability not found', () => {
    expect(idx.findByCapability('nonexistent')).toHaveLength(0)
  })

  it('marks local agents correctly', () => {
    idx.upsertAgent({ name: 'local', hub: 'h', capabilities: ['foo'] }, true)
    idx.upsertAgent({ name: 'remote', hub: 'other', capabilities: ['foo'] }, false)

    expect(idx.getLocalAgents()).toHaveLength(1)
    expect(idx.getLocalAgents()[0].name).toBe('local')
  })

  it('removes agent', () => {
    idx.upsertAgent({ name: 'a', hub: 'h', capabilities: ['foo'] }, true)
    const removed = idx.removeAgent('a', 'h')
    expect(removed).toBe(true)
    expect(idx.getAllAgents()).toHaveLength(0)
    expect(idx.findByCapability('foo')).toHaveLength(0)
  })

  it('returns false when removing non-existent agent', () => {
    expect(idx.removeAgent('ghost', 'h')).toBe(false)
  })

  it('removes all agents from a hub', () => {
    idx.upsertAgent({ name: 'a', hub: 'hog', capabilities: ['foo'] }, false)
    idx.upsertAgent({ name: 'b', hub: 'hog', capabilities: ['bar'] }, false)
    idx.upsertAgent({ name: 'c', hub: 'trillian', capabilities: ['foo'] }, true)

    const removed = idx.removeHub('hog')
    expect(removed).toHaveLength(2)
    expect(idx.getAllAgents()).toHaveLength(1)
    expect(idx.getAllAgents()[0].hub).toBe('trillian')
  })

  it('updates capability index on upsert', () => {
    const agent: AgentInfo = { name: 'x', hub: 'h', capabilities: ['a', 'b'] }
    idx.upsertAgent(agent, true)

    const caps = idx.getAllCapabilities()
    expect(caps).toContain('a')
    expect(caps).toContain('b')
  })

  it('detects capability changes on upsert', () => {
    idx.upsertAgent({ name: 'x', hub: 'h', capabilities: ['a', 'b'] }, true)
    const { capChanges } = idx.upsertAgent({ name: 'x', hub: 'h', capabilities: ['b', 'c'] }, true)

    expect(capChanges.added).toContain('c')
    expect(capChanges.removed).toContain('a')
  })

  it('updates dark circles', () => {
    idx.updateDarkCircles('trillian', [
      { name: 'deployment-strategy', pressure: 0.70 },
      { name: 'data-modeling', pressure: 0.50 },
    ])

    const circles = idx.getDarkCircles()
    expect(circles).toHaveLength(2)

    const dc = idx.getDarkCircle('deployment-strategy')
    expect(dc).toBeDefined()
    expect(dc!.pressure).toBe(0.70)
  })

  it('aggregates dark circle pressure across hubs (max)', () => {
    idx.updateDarkCircles('trillian', [{ name: 'void', pressure: 0.60 }])
    idx.updateDarkCircles('hog', [{ name: 'void', pressure: 0.80 }])

    const dc = idx.getDarkCircle('void')!
    expect(dc.pressure).toBe(0.80)
    expect(dc.byHub?.trillian).toBe(0.60)
    expect(dc.byHub?.hog).toBe(0.80)
  })

  it('stats returns correct counts', () => {
    idx.upsertAgent({ name: 'a', hub: 'h1', capabilities: ['foo', 'bar'] }, true)
    idx.upsertAgent({ name: 'b', hub: 'h2', capabilities: ['foo'] }, false)
    idx.updateDarkCircles('h1', [{ name: 'dc1', pressure: 0.5 }])

    const stats = idx.stats()
    expect(stats.agents).toBe(2)
    expect(stats.capabilities).toBe(2)
    expect(stats.darkCircles).toBe(1)
    expect(stats.hubs.size).toBe(2)
  })
})

// ── MeshSync unit tests ────────────────────────────────────────────────────────

describe('MeshSync', () => {
  it('instantiates with correct hub', () => {
    const sync = new MeshSync({ hub: 'test-hub', intervalMs: 999 })
    expect(sync).toBeDefined()
  })

  it('sync builds correct message shape', () => {
    const idx = new CapabilityIndex()
    idx.upsertAgent({ name: 'stella', hub: 'trillian', capabilities: ['deployment-versioning'] }, true)
    idx.updateDarkCircles('trillian', [{ name: 'deployment-strategy', pressure: 0.7 }])

    // Mock peer registry
    const broadcasts: string[] = []
    const mockRegistry = {
      broadcast: (data: string) => broadcasts.push(data),
      getPeers: () => [],
    }

    const sync = new MeshSync({ hub: 'trillian', intervalMs: 60_000, deltaSyncEnabled: false })
    // @ts-expect-error — testing internals
    sync.capIndex = idx
    // @ts-expect-error — testing internals
    sync.peerRegistry = mockRegistry

    sync.sync()

    expect(broadcasts).toHaveLength(1)
    const msg = JSON.parse(broadcasts[0])
    expect(msg.type).toBe('mesh_sync')
    expect(msg.hub).toBe('trillian')
    expect(msg.agents).toHaveLength(1)
    expect(msg.agents[0].name).toBe('stella')
    expect(msg.darkCircles).toHaveLength(1)
    expect(msg.darkCircles[0].name).toBe('deployment-strategy')
  })
})
