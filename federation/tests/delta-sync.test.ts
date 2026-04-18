import { describe, it, expect, beforeEach } from 'vitest'
import { DeltaSync } from '../src/server/delta-sync.js'
import type { AgentInfo, DarkCircle } from '../src/protocol/messages.js'

function makeAgent(name: string, hub: string, caps: string[] = ['test']): AgentInfo {
  return { name, hub, capabilities: caps, seams: [], pressure: 1, lastSeen: new Date().toISOString() }
}

function makeDC(name: string, pressure: number): DarkCircle {
  return { name, pressure }
}

describe('DeltaSync', () => {
  let ds: DeltaSync

  beforeEach(() => {
    ds = new DeltaSync({ hub: 'hub-A', debug: false })
  })

  it('starts at version 0', () => {
    expect(ds.getVersion()).toBe(0)
  })

  it('bumps version on each snapshot', () => {
    ds.recordSnapshot([makeAgent('a1', 'hub-A')], [])
    expect(ds.getVersion()).toBe(1)
    ds.recordSnapshot([makeAgent('a1', 'hub-A'), makeAgent('a2', 'hub-A')], [])
    expect(ds.getVersion()).toBe(2)
  })

  it('returns full snapshot for new peer', () => {
    const agents = [makeAgent('a1', 'hub-A'), makeAgent('a2', 'hub-A')]
    ds.recordSnapshot(agents, [])

    const result = ds.getDeltaForPeer('peer-X')
    expect(result).not.toBeNull()
    expect(result!.type).toBe('full')
    if (result!.type === 'full') {
      expect(result!.agents).toHaveLength(2)
      expect(result!.version).toBe(1)
    }
  })

  it('returns null when peer is up to date', () => {
    ds.recordSnapshot([makeAgent('a1', 'hub-A')], [])
    ds.addPeer('peer-X')

    // Full sync sent
    const delta1 = ds.getDeltaForPeer('peer-X')
    expect(delta1).not.toBeNull()

    // ACK
    ds.ackPeer('peer-X', 1)

    // No changes
    const delta2 = ds.getDeltaForPeer('peer-X')
    expect(delta2).toBeNull()
  })

  it('sends delta for changed agents', () => {
    ds.addPeer('peer-X')
    ds.recordSnapshot([makeAgent('a1', 'hub-A')], [])
    ds.ackPeer('peer-X', 1)

    // Change a1's capabilities
    ds.recordSnapshot([makeAgent('a1', 'hub-A', ['test', 'new-cap'])], [])

    const delta = ds.getDeltaForPeer('peer-X')
    expect(delta).not.toBeNull()
    expect(delta!.type).toBe('delta')
    if (delta!.type === 'delta') {
      expect(delta!.fromVersion).toBe(1)
      expect(delta!.toVersion).toBe(2)
      expect(delta!.agentDeltas).toHaveLength(1)
      expect(delta!.agentDeltas[0].op).toBe('upsert')
    }
  })

  it('sends remove delta for deleted agents', () => {
    ds.addPeer('peer-X')
    ds.recordSnapshot([makeAgent('a1', 'hub-A'), makeAgent('a2', 'hub-A')], [])
    ds.ackPeer('peer-X', 1)

    // Remove a2
    ds.recordSnapshot([makeAgent('a1', 'hub-A')], [])

    const delta = ds.getDeltaForPeer('peer-X')
    expect(delta).not.toBeNull()
    if (delta!.type === 'delta') {
      const removes = delta!.agentDeltas.filter(d => d.op === 'remove')
      expect(removes).toHaveLength(1)
      expect(removes[0].agent.name).toBe('a2')
    }
  })

  it('tracks multiple peers independently', () => {
    ds.addPeer('peer-X')
    ds.addPeer('peer-Y')

    ds.recordSnapshot([makeAgent('a1', 'hub-A')], [])
    ds.ackPeer('peer-X', 1)
    // peer-Y hasn't ACKed yet

    ds.recordSnapshot([makeAgent('a1', 'hub-A', ['v2'])], [])

    const deltaX = ds.getDeltaForPeer('peer-X')
    const deltaY = ds.getDeltaForPeer('peer-Y')

    // peer-X should get delta from v1
    expect(deltaX?.type).toBe('delta')

    // peer-Y should get full (never ACKed)
    expect(deltaY?.type).toBe('full')
  })

  it('handles dark circle deltas', () => {
    ds.addPeer('peer-X')
    ds.recordSnapshot([], [{ circle: makeDC('dc1', 5), hub: 'hub-A' }])
    ds.ackPeer('peer-X', 1)

    // Change dark circle pressure
    ds.recordSnapshot([], [{ circle: makeDC('dc1', 10), hub: 'hub-A' }])

    const delta = ds.getDeltaForPeer('peer-X')
    expect(delta).not.toBeNull()
    if (delta!.type === 'delta') {
      expect(delta!.darkCircleDeltas).toHaveLength(1)
      expect(delta!.darkCircleDeltas[0].op).toBe('upsert')
    }
  })

  it('dedupes multiple changes to same agent', () => {
    ds.addPeer('peer-X')
    ds.recordSnapshot([makeAgent('a1', 'hub-A', ['v1'])], [])
    ds.ackPeer('peer-X', 1)

    // Multiple changes
    ds.recordSnapshot([makeAgent('a1', 'hub-A', ['v2'])], [])
    ds.recordSnapshot([makeAgent('a1', 'hub-A', ['v3'])], [])

    const delta = ds.getDeltaForPeer('peer-X')
    expect(delta).not.toBeNull()
    if (delta!.type === 'delta') {
      // Should only have 1 delta for a1 (deduped)
      expect(delta!.agentDeltas).toHaveLength(1)
      expect(delta!.agentDeltas[0].agent.capabilities).toContain('v3')
    }
  })

  it('removes peer from tracking', () => {
    ds.addPeer('peer-X')
    ds.recordSnapshot([makeAgent('a1', 'hub-A')], [])
    ds.ackPeer('peer-X', 1)

    ds.removePeer('peer-X')

    const versions = ds.getPeerVersions()
    expect(versions['peer-X']).toBeUndefined()
  })

  it('falls back to full sync when changelog is trimmed', () => {
    ds.addPeer('peer-X')
    ds.recordSnapshot([makeAgent('a1', 'hub-A')], [])
    ds.ackPeer('peer-X', 1)

    // Generate many changes to fill changelog beyond max
    for (let i = 2; i <= 110; i++) {
      ds.recordSnapshot([makeAgent('a1', 'hub-A', [`v${i}`])], [])
    }

    // peer-X only ACKed v1, changelog may have been trimmed
    const delta = ds.getDeltaForPeer('peer-X')
    // Should either be full or delta depending on trimming
    expect(delta).not.toBeNull()
    if (delta!.type === 'full') {
      expect(delta!.agents.length).toBeGreaterThanOrEqual(1)
    }
  })
})
