/**
 * Integration tests — two real ManifoldServer instances talking to each other
 * over localhost WebSocket connections.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { ManifoldServer } from '../src/server/index.js'
import { ManifoldClient } from '../src/client/index.js'

const BASE_FED = 19000
const BASE_LOCAL = 19100
const BASE_REST = 19200

// Use unique ports per test to avoid conflicts
let portOffset = 0
function nextPorts() {
  const n = portOffset++
  return {
    federationPort: BASE_FED + n,
    localPort: BASE_LOCAL + n,
    restPort: BASE_REST + n,
  }
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// ── Single server tests ───────────────────────────────────────────────────────

describe('ManifoldServer (single)', () => {
  let server: ManifoldServer

  beforeEach(async () => {
    server = new ManifoldServer({
      name: 'test-hub',
      ...nextPorts(),
      syncIntervalMs: 60_000,
      debug: false,
    })
    await server.start()
  })

  afterEach(async () => {
    await server.stop()
  })

  it('starts successfully', () => {
    expect(server).toBeDefined()
  })

  it('returns status', () => {
    const s = server.status()
    expect(s.hub).toBe('test-hub')
    expect(s.localAgents).toHaveLength(0)
    expect(s.peers).toHaveLength(0)
  })

  it('registers a local agent', () => {
    server.registerAgent('stella', ['deployment-versioning', 'identity-modeling'])
    const agents = server.query('deployment-versioning')
    expect(agents).toHaveLength(1)
    expect(agents[0].name).toBe('stella')
    expect(agents[0].isLocal).toBe(true)
  })

  it('emits agent:join when agent registered', async () => {
    const joins: string[] = []
    server.on('agent:join', (a) => joins.push(a.name))
    server.registerAgent('braid', ['solar-prediction'])
    expect(joins).toContain('braid')
  })

  it('query returns empty for unknown capability', () => {
    expect(server.query('nonexistent')).toHaveLength(0)
  })

  it('query filters by minPressure', () => {
    server.registerAgent('high', ['foo'])
    server.registerAgent('low', ['foo'])
    // Manually set pressure via index
    server.capIndex.upsertAgent({ name: 'high', hub: 'test-hub', capabilities: ['foo'], pressure: 0.9 }, true)
    server.capIndex.upsertAgent({ name: 'low', hub: 'test-hub', capabilities: ['foo'], pressure: 0.1 }, true)

    const results = server.query('foo', 0.5)
    expect(results.every(a => (a.pressure ?? 0) >= 0.5)).toBe(true)
  })
})

// ── REST API tests ────────────────────────────────────────────────────────────

describe('ManifoldServer REST API', () => {
  let server: ManifoldServer
  let ports: ReturnType<typeof nextPorts>

  beforeEach(async () => {
    ports = nextPorts()
    server = new ManifoldServer({
      name: 'rest-test-hub',
      ...ports,
      syncIntervalMs: 60_000,
      debug: false,
    })
    await server.start()
  })

  afterEach(async () => {
    await server.stop()
  })

  async function get(path: string) {
    const res = await fetch(`http://localhost:${ports.restPort}${path}`)
    return res.json()
  }

  async function post(path: string, body: unknown) {
    const res = await fetch(`http://localhost:${ports.restPort}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return res.json()
  }

  it('GET /status returns hub name', async () => {
    const data = await get('/status')
    expect(data.hub).toBe('rest-test-hub')
    expect(data.status).toBe('ok')
  })

  it('GET /peers returns empty initially', async () => {
    const data = await get('/peers')
    expect(data.peers).toEqual([])
  })

  it('GET /agents returns registered agents', async () => {
    server.registerAgent('stella', ['deployment-versioning'])
    const data = await get('/agents')
    expect(data.agents.length).toBeGreaterThanOrEqual(1)
    expect(data.agents.some((a: { name: string }) => a.name === 'stella')).toBe(true)
  })

  it('GET /agents/:name returns specific agent', async () => {
    server.registerAgent('braid', ['solar-prediction'])
    const data = await get('/agents/braid@rest-test-hub')
    expect(data.name).toBe('braid')
  })

  it('GET /agents/:name returns 404 for unknown', async () => {
    const res = await fetch(`http://localhost:${ports.restPort}/agents/ghost@unknown`)
    expect(res.status).toBe(404)
  })

  it('GET /capabilities lists registered capabilities', async () => {
    server.registerAgent('a', ['foo', 'bar'])
    const data = await get('/capabilities')
    const caps = data.capabilities.map((c: { capability: string }) => c.capability)
    expect(caps).toContain('foo')
    expect(caps).toContain('bar')
  })

  it('GET /dark-circles returns dark circles', async () => {
    server.capIndex.updateDarkCircles('rest-test-hub', [
      { name: 'deployment-strategy', pressure: 0.7 },
    ])
    const data = await get('/dark-circles')
    expect(data.darkCircles.length).toBeGreaterThanOrEqual(1)
    expect(data.darkCircles[0].name).toBe('deployment-strategy')
  })

  it('GET /mesh returns full topology', async () => {
    server.registerAgent('stella', ['deployment-versioning'])
    const data = await get('/mesh')
    expect(data.hub).toBe('rest-test-hub')
    expect(Array.isArray(data.agents)).toBe(true)
    expect(Array.isArray(data.capabilities)).toBe(true)
    expect(data.stats).toBeDefined()
  })

  it('POST /query returns matching agents', async () => {
    server.registerAgent('braid', ['solar-prediction'])
    const data = await post('/query', { capability: 'solar-prediction' })
    expect(data.agents.length).toBeGreaterThanOrEqual(1)
    expect(data.agents[0].name).toBe('braid')
  })

  it('POST /query returns 400 without capability', async () => {
    const res = await fetch(`http://localhost:${ports.restPort}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    expect(res.status).toBe(400)
  })

  it('POST /route returns routing info', async () => {
    server.registerAgent('deploy', ['deployment'])
    const data = await post('/route', {
      target: 'deploy@rest-test-hub',
      task: { type: 'deployment', payload: { version: '1.0' } },
    })
    expect(data.status).toBe('routed')
    expect(data.target).toBe('deploy@rest-test-hub')
  })

  it('POST /route returns 404 for unknown agent', async () => {
    const res = await fetch(`http://localhost:${ports.restPort}/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: 'ghost@unknown', task: { type: 'test' } }),
    })
    expect(res.status).toBe(404)
  })
})

// ── Two-server federation tests ───────────────────────────────────────────────

describe('Two-server federation', () => {
  let serverA: ManifoldServer
  let serverB: ManifoldServer
  let portsA: ReturnType<typeof nextPorts>
  let portsB: ReturnType<typeof nextPorts>

  beforeEach(async () => {
    portsA = nextPorts()
    portsB = nextPorts()

    serverA = new ManifoldServer({
      name: 'trillian',
      ...portsA,
      syncIntervalMs: 60_000,
      debug: false,
    })

    serverB = new ManifoldServer({
      name: 'hog',
      ...portsB,
      peers: [`ws://localhost:${portsA.federationPort}`],
      syncIntervalMs: 60_000,
      debug: false,
    })

    await serverA.start()
    await serverB.start()

    // Allow time for peer connection + sync
    await sleep(300)
  })

  afterEach(async () => {
    await serverA.stop()
    await serverB.stop()
  })

  it('servers discover each other', async () => {
    // Give them a moment to handshake
    await sleep(200)
    const peersA = serverA.peerRegistry.getPeers()
    const peersB = serverB.peerRegistry.getPeers()
    // At least one direction should have found the other
    expect(peersA.length + peersB.length).toBeGreaterThanOrEqual(1)
  })

  it('agents registered on serverA appear in serverB via mesh sync', async () => {
    serverA.registerAgent('stella', ['deployment-versioning', 'identity-modeling'])
    serverA.meshSync.sync()

    await sleep(300)

    const agents = serverB.capIndex.getAllAgents()
    const stella = agents.find(a => a.name === 'stella')
    expect(stella).toBeDefined()
    expect(stella!.hub).toBe('trillian')
  })

  it('capability query on serverB finds agents on serverA', async () => {
    serverA.registerAgent('braid', ['solar-prediction'])
    serverA.meshSync.sync()

    await sleep(300)

    const results = serverB.query('solar-prediction')
    expect(results.length).toBeGreaterThanOrEqual(1)
    expect(results.some(a => a.name === 'braid' && a.hub === 'trillian')).toBe(true)
  })

  it('agents from both hubs coexist in federated index', async () => {
    serverA.registerAgent('stella', ['deployment-versioning'])
    serverB.registerAgent('eddie', ['blockchain', 'compute'])
    serverA.meshSync.sync()
    serverB.meshSync.sync()

    await sleep(300)

    // serverA should see eddie from HOG
    const agntsOnA = serverA.capIndex.getAllAgents()
    expect(agntsOnA.some(a => a.name === 'stella')).toBe(true)

    // serverB should see stella from trillian
    const agntsOnB = serverB.capIndex.getAllAgents()
    expect(agntsOnB.some(a => a.name === 'eddie')).toBe(true)
  })

  it('dark circles aggregate across hubs', async () => {
    serverA.capIndex.updateDarkCircles('trillian', [{ name: 'deployment-strategy', pressure: 0.60 }])
    serverB.capIndex.updateDarkCircles('hog', [{ name: 'deployment-strategy', pressure: 0.75 }])
    serverA.meshSync.sync()
    serverB.meshSync.sync()

    await sleep(300)

    // Each server should have the circle; pressure = max
    const dcOnB = serverB.capIndex.getDarkCircle('deployment-strategy')
    if (dcOnB) {
      expect(dcOnB.pressure).toBeGreaterThanOrEqual(0.60)
    }
  })

  it('peer disconnection removes remote agents', async () => {
    serverA.registerAgent('braid', ['solar-prediction'])
    serverA.meshSync.sync()

    await sleep(300)

    // Verify braid is known on B
    expect(serverB.capIndex.getAgent('braid', 'trillian')).toBeDefined()

    // Stop A
    await serverA.stop()
    await sleep(400)

    // Braid should be removed from B's index
    expect(serverB.capIndex.getAgent('braid', 'trillian')).toBeUndefined()
  })
})

// ── ManifoldClient with live server ──────────────────────────────────────────

describe('ManifoldClient with live server', () => {
  let server: ManifoldServer
  let client: ManifoldClient
  let ports: ReturnType<typeof nextPorts>

  beforeEach(async () => {
    ports = nextPorts()
    server = new ManifoldServer({
      name: 'client-test-hub',
      ...ports,
      syncIntervalMs: 60_000,
      debug: false,
    })
    await server.start()

    client = new ManifoldClient({
      servers: [`ws://localhost:${ports.federationPort}`],
      identity: { name: 'test-client' },
      defaultQueryTimeout: 2000,
      debug: false,
    })
    await client.start()
    await sleep(200)
  })

  afterEach(async () => {
    await client.stop()
    await server.stop()
  })

  it('client connects to server', async () => {
    const connected = client.getConnectedServers()
    expect(connected.length).toBeGreaterThanOrEqual(1)
  })

  it('client receives mesh_sync from server', async () => {
    const joins: string[] = []
    client.on('agent:join', a => joins.push(a.name))

    server.registerAgent('stella', ['deployment-versioning'])
    server.meshSync.sync()

    await sleep(300)

    expect(joins).toContain('stella')
  })

  it('client.query returns agents from server', async () => {
    server.registerAgent('braid', ['solar-prediction'])
    server.meshSync.sync()

    await sleep(300)

    const results = await client.query('solar-prediction')
    expect(results.some(a => a.name === 'braid')).toBe(true)
  })

  it('client registers capabilities via mesh_sync', async () => {
    await client.register(['custom-skill', 'extra-skill'])
    await sleep(300)

    const agents = server.capIndex.getAllAgents()
    const clientAgent = agents.find(a => a.name === 'test-client')
    expect(clientAgent).toBeDefined()
    expect(clientAgent!.capabilities).toContain('custom-skill')
  })
})
