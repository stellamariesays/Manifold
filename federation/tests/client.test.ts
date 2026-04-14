import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ManifoldClient } from '../src/client/index.js'
import type { AgentResult } from '../src/shared/types.js'

// ── Unit tests for ManifoldClient (no real network) ───────────────────────────

describe('ManifoldClient', () => {
  let client: ManifoldClient

  beforeEach(() => {
    client = new ManifoldClient({
      servers: [], // No servers — tests isolated behaviour
      identity: { name: 'test-agent' },
      defaultQueryTimeout: 500,
      debug: false,
    })
  })

  afterEach(async () => {
    await client.stop()
  })

  it('creates with correct identity', () => {
    expect(client).toBeDefined()
  })

  it('returns empty agent list initially', () => {
    const agents = client.getAgents()
    expect(agents).toEqual([])
  })

  it('starts and stops without error', async () => {
    await client.start()
    await client.stop()
  })

  it('returns empty connected servers when no servers configured', async () => {
    await client.start()
    expect(client.getConnectedServers()).toEqual([])
  })

  it('query returns empty array when no servers and no cached agents', async () => {
    await client.start()
    const results = await client.query('solar-prediction')
    expect(results).toEqual([])
  })

  it('emits agent:join when mesh_sync arrives with new agent', async () => {
    await client.start()

    const joins: AgentResult[] = []
    client.on('agent:join', (agent) => joins.push(agent))

    // Simulate internal mesh_sync handling by calling private method via cast
    const msg = {
      type: 'mesh_sync' as const,
      hub: 'trillian',
      agents: [
        {
          name: 'braid',
          hub: 'trillian',
          capabilities: ['solar-prediction', 'flare-detection'],
          seams: ['prediction'],
          pressure: 0.6,
        },
      ],
      darkCircles: [],
      timestamp: new Date().toISOString(),
    }

    ;(client as unknown as { _handleMeshSync: (m: typeof msg) => void })._handleMeshSync(msg)

    expect(joins).toHaveLength(1)
    expect(joins[0].name).toBe('braid')
    expect(joins[0].hub).toBe('trillian')
    expect(joins[0].capabilities).toContain('solar-prediction')
  })

  it('emits capability:change when agent updates capabilities', async () => {
    await client.start()

    const changes: Array<{ agent: string; added: string[]; removed: string[] }> = []
    client.on('capability:change', (e) => changes.push(e))

    const msg1 = {
      type: 'mesh_sync' as const,
      hub: 'trillian',
      agents: [{ name: 'stella', hub: 'trillian', capabilities: ['deployment-versioning'] }],
      darkCircles: [],
      timestamp: new Date().toISOString(),
    }

    const msg2 = {
      type: 'mesh_sync' as const,
      hub: 'trillian',
      agents: [
        {
          name: 'stella',
          hub: 'trillian',
          capabilities: ['deployment-versioning', 'identity-modeling'],
        },
      ],
      darkCircles: [],
      timestamp: new Date().toISOString(),
    }

    const handleSync = (client as unknown as { _handleMeshSync: (m: typeof msg1) => void })._handleMeshSync.bind(client)
    handleSync(msg1)
    handleSync(msg2)

    expect(changes).toHaveLength(1)
    expect(changes[0].added).toContain('identity-modeling')
    expect(changes[0].removed).toHaveLength(0)
  })

  it('emits agent:leave when agent disappears from mesh_sync', async () => {
    await client.start()

    const leaves: Array<{ name: string; hub: string }> = []
    client.on('agent:leave', (a) => leaves.push(a))

    const handleSync = (client as unknown as { _handleMeshSync: (m: unknown) => void })._handleMeshSync.bind(client)

    handleSync({
      type: 'mesh_sync',
      hub: 'trillian',
      agents: [{ name: 'wake', hub: 'trillian', capabilities: ['wakeword'] }],
      darkCircles: [],
      timestamp: new Date().toISOString(),
    })

    // Next sync from same hub, wake is gone
    handleSync({
      type: 'mesh_sync',
      hub: 'trillian',
      agents: [],
      darkCircles: [],
      timestamp: new Date().toISOString(),
    })

    expect(leaves).toHaveLength(1)
    expect(leaves[0].name).toBe('wake')
  })

  it('emits pressure:update on dark circle data', async () => {
    await client.start()

    const updates: Array<{ circle: string; pressure: number; hub: string }> = []
    client.on('pressure:update', (u) => updates.push(u))

    const handleSync = (client as unknown as { _handleMeshSync: (m: unknown) => void })._handleMeshSync.bind(client)
    handleSync({
      type: 'mesh_sync',
      hub: 'trillian',
      agents: [],
      darkCircles: [{ name: 'deployment-strategy', pressure: 0.70, hub: 'trillian' }],
      timestamp: new Date().toISOString(),
    })

    expect(updates).toHaveLength(1)
    expect(updates[0].circle).toBe('deployment-strategy')
    expect(updates[0].pressure).toBe(0.70)
  })

  it('query returns cached agents matching capability', async () => {
    await client.start()

    const handleSync = (client as unknown as { _handleMeshSync: (m: unknown) => void })._handleMeshSync.bind(client)
    handleSync({
      type: 'mesh_sync',
      hub: 'trillian',
      agents: [
        { name: 'braid', hub: 'trillian', capabilities: ['solar-prediction'], pressure: 0.6 },
        { name: 'stella', hub: 'trillian', capabilities: ['deployment-versioning'], pressure: 0.3 },
      ],
      darkCircles: [],
      timestamp: new Date().toISOString(),
    })

    const results = await client.query('solar-prediction', { local: true })
    expect(results).toHaveLength(1)
    expect(results[0].name).toBe('braid')
  })

  it('query filters by minPressure', async () => {
    await client.start()

    const handleSync = (client as unknown as { _handleMeshSync: (m: unknown) => void })._handleMeshSync.bind(client)
    handleSync({
      type: 'mesh_sync',
      hub: 'trillian',
      agents: [
        { name: 'braid', hub: 'trillian', capabilities: ['solar-prediction'], pressure: 0.6 },
        { name: 'other', hub: 'trillian', capabilities: ['solar-prediction'], pressure: 0.1 },
      ],
      darkCircles: [],
      timestamp: new Date().toISOString(),
    })

    const results = await client.query('solar-prediction', { local: true, minPressure: 0.5 })
    expect(results).toHaveLength(1)
    expect(results[0].name).toBe('braid')
  })

  it('routeWork rejects when no servers connected', async () => {
    await client.start()
    await expect(
      client.routeWork('deploy@trillian', { task: 'test', type: 'deployment' }),
    ).rejects.toThrow('No connected servers')
  })
})
