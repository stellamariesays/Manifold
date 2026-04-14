/**
 * Two-server demo: Trillian ↔️ HOG federation on localhost.
 *
 * Demonstrates:
 * 1. Two ManifoldServer instances discovering each other
 * 2. Agents registered on server A appearing in server B's index
 * 3. Capability queries across the federation
 * 4. REST API showing federated mesh topology
 * 5. Dark circle pressure aggregation across hubs
 *
 * Usage:
 *   npm run demo
 *   npx tsx examples/two-server-demo.ts
 */

import { ManifoldServer } from '../src/server/index.js'
import { ManifoldClient } from '../src/client/index.js'

// Demo uses high ports to avoid colliding with live Python manifold.server on :8765
const TRILLIAN_FED = 18766
const TRILLIAN_LOCAL = 18765
const TRILLIAN_REST = 18767

const HOG_FED = 18776
const HOG_LOCAL = 18775
const HOG_REST = 18777

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function banner(text: string) {
  console.log('\n' + '═'.repeat(60))
  console.log(`  ${text}`)
  console.log('═'.repeat(60))
}

function section(text: string) {
  console.log(`\n── ${text} ${'─'.repeat(50 - text.length)}`)
}

async function main() {
  banner('Manifold Federation Phase 1 — Two-Server Demo')

  // ── Start Trillian (Stella's mesh) ─────────────────────────────────────────

  section('Starting Trillian hub (Stella\'s mesh)')

  const trillian = new ManifoldServer({
    name: 'trillian',
    federationPort: TRILLIAN_FED,
    localPort: TRILLIAN_LOCAL,
    restPort: TRILLIAN_REST,
    syncIntervalMs: 5000,
    debug: false,
  })

  trillian.on('agent:join', a => console.log(`  [trillian] 🟢 ${a.name} joined`))
  trillian.on('peer:connect', p => console.log(`  [trillian] 🔗 peer connected: ${p.hub}`))
  trillian.on('peer:disconnect', p => console.log(`  [trillian] ⚠️  peer disconnected: ${p.hub}`))

  await trillian.start()
  console.log(`  ✅ Trillian: fed=:${TRILLIAN_FED} local=:${TRILLIAN_LOCAL} rest=:${TRILLIAN_REST} (demo ports)`)

  // Register Trillian's agents (mirroring real Stella mesh)
  trillian.registerAgent('stella', ['deployment-versioning', 'identity-modeling', 'conversation'])
  trillian.registerAgent('braid', ['solar-prediction', 'flare-detection', 'pattern-weaving'])
  trillian.registerAgent('manifold', ['mesh-topology', 'agent-discovery', 'dark-circle-detection'])
  trillian.registerAgent('argue', ['debate', 'fact-checking', 'position-modeling'])
  trillian.registerAgent('infra', ['server-management', 'deployment', 'monitoring'])
  trillian.registerAgent('solar-sites', ['solar-prediction', 'site-generation'])
  trillian.registerAgent('wake', ['wakeword-detection', 'audio-processing'])
  trillian.registerAgent('btc-signals', ['crypto-signals', 'price-analysis', 'market-monitoring'])
  trillian.registerAgent('deploy', ['deployment', 'ci-cd', 'release-management'])

  // Set dark circle pressures for Trillian
  trillian.capIndex.updateDarkCircles('trillian', [
    { name: 'deployment-strategy', pressure: 0.60 },
    { name: 'data-modeling', pressure: 0.50 },
    { name: 'identity-resolution', pressure: 0.45 },
    { name: 'solar-forecast', pressure: 0.30 },
  ])

  console.log(`  Registered ${trillian.capIndex.getLocalAgents().length} agents`)

  // ── Start HOG (Eddie's mesh) ───────────────────────────────────────────────

  section('Starting HOG hub (Eddie\'s mesh)')

  const hog = new ManifoldServer({
    name: 'hog',
    federationPort: HOG_FED,
    localPort: HOG_LOCAL,
    restPort: HOG_REST,
    peers: [`ws://localhost:${TRILLIAN_FED}`],  // Dial Trillian
    syncIntervalMs: 5000,
    debug: false,
  })

  hog.on('agent:join', a => console.log(`  [hog] 🟢 ${a.name}@${a.hub} joined`))
  hog.on('peer:connect', p => console.log(`  [hog] 🔗 peer connected: ${p.hub}`))
  hog.on('mesh:sync', hub => console.log(`  [hog] 🔄 mesh sync from ${hub}`))

  await hog.start()
  console.log(`  ✅ HOG: fed=:${HOG_FED} local=:${HOG_LOCAL} rest=:${HOG_REST}`)

  // Register HOG's agents (Eddie's mesh)
  hog.registerAgent('eddie', ['blockchain', 'compute', 'script-execution', 'research'])
  hog.registerAgent('clawstreet', ['trading', 'crypto-signals', 'position-management'])
  hog.registerAgent('archivist', ['document-storage', 'memory-indexing', 'search'])

  // Set dark circle pressures for HOG
  hog.capIndex.updateDarkCircles('hog', [
    { name: 'deployment-strategy', pressure: 0.40 },
    { name: 'trading-strategy', pressure: 0.65 },
    { name: 'blockchain-ops', pressure: 0.35 },
  ])

  console.log(`  Registered ${hog.capIndex.getLocalAgents().length} agents`)

  // ── Wait for federation to establish ──────────────────────────────────────

  section('Waiting for federation handshake...')
  await sleep(1000)

  // ── Show federation status ──────────────────────────────────────────────────

  section('Federation Status')

  const trillianStatus = trillian.status()
  const hogStatus = hog.status()

  console.log('\nTrillian (ws://localhost:8766):')
  console.log(`  Peers: ${trillianStatus.peers.length}`)
  console.log(`  Local agents: ${trillianStatus.localAgents.length}`)
  console.log(`  Federated agents: ${trillianStatus.federatedAgents.length}`)
  console.log(`  Total known: ${trillian.capIndex.getAllAgents().length}`)

  console.log('\nHOG (ws://localhost:8776):')
  console.log(`  Peers: ${hogStatus.peers.length}`)
  console.log(`  Local agents: ${hogStatus.localAgents.length}`)
  console.log(`  Federated agents: ${hogStatus.federatedAgents.length}`)
  console.log(`  Total known: ${hog.capIndex.getAllAgents().length}`)

  // ── Capability queries ─────────────────────────────────────────────────────

  section('Capability Queries')

  console.log('\nQuery from HOG: "solar-prediction"')
  const solarAgents = hog.query('solar-prediction')
  for (const a of solarAgents) {
    const loc = a.isLocal ? '(local)' : `(remote:${a.hub})`
    console.log(`  → ${a.name}@${a.hub} ${loc} [${a.capabilities.slice(0, 2).join(', ')}...]`)
  }
  if (solarAgents.length === 0) console.log('  (none yet — awaiting sync)')

  console.log('\nQuery from Trillian: "blockchain"')
  const blockchainAgents = trillian.query('blockchain')
  for (const a of blockchainAgents) {
    const loc = a.isLocal ? '(local)' : `(remote:${a.hub})`
    console.log(`  → ${a.name}@${a.hub} ${loc}`)
  }
  if (blockchainAgents.length === 0) console.log('  (none yet — awaiting sync)')

  console.log('\nQuery from HOG: "deployment" (any hub)')
  const deployAgents = hog.query('deployment')
  for (const a of deployAgents) {
    console.log(`  → ${a.name}@${a.hub} (${a.isLocal ? 'local' : 'remote'})`)
  }

  // ── Dark circle aggregation ────────────────────────────────────────────────

  section('Dark Circle Pressure (Aggregated)')

  // Force a sync to propagate dark circles
  trillian.meshSync.sync()
  hog.meshSync.sync()
  await sleep(500)

  const circles = hog.capIndex.getDarkCircles()
  console.log('\nFrom HOG\'s perspective (max pressure across hubs):')
  for (const dc of circles.sort((a, b) => b.pressure - a.pressure)) {
    const hubs = dc.byHub ? Object.entries(dc.byHub).map(([h, p]) => `${h}:${p.toFixed(2)}`).join(', ') : ''
    console.log(`  ${dc.name.padEnd(25)} p=${dc.pressure.toFixed(2)} [${hubs}]`)
  }

  // ── ManifoldClient connecting to federation ───────────────────────────────

  section('ManifoldClient connecting to federation')

  const client = new ManifoldClient({
    servers: [`ws://localhost:${TRILLIAN_FED}`],
    identity: { name: 'demo-observer' },
    debug: false,
    defaultQueryTimeout: 3000,
  })

  const seenAgents: string[] = []
  client.on('agent:join', a => {
    seenAgents.push(`${a.name}@${a.hub}`)
    console.log(`  [client] 🟢 saw ${a.name}@${a.hub}`)
  })

  await client.start()
  console.log('  Client started, receiving mesh sync...')
  await sleep(1000)

  console.log(`\n  Client knows ${client.getAgents().length} agents total`)
  const clientSolar = await client.query('solar-prediction')
  console.log(`  Client query "solar-prediction": ${clientSolar.length} agents`)

  // ── REST API demo ─────────────────────────────────────────────────────────

  section('REST API Demo')

  try {
    const status = await fetch(`http://localhost:${TRILLIAN_REST}/status`).then(r => r.json()) as Record<string, unknown>
    console.log(`\nGET /status (trillian):`)
    console.log(`  hub=${status['hub']} agents=${status['agents']} capabilities=${status['capabilities']}`)

    const mesh = await fetch(`http://localhost:${TRILLIAN_REST}/mesh`).then(r => r.json()) as { stats: Record<string, unknown>; capabilities: string[] }
    console.log(`\nGET /mesh (trillian):`)
    console.log(`  agents=${mesh.stats['agents']} capabilities=${mesh.stats['capabilities']} hubs=${JSON.stringify(mesh.stats['hubs'])}`)
    console.log(`  capabilities: ${mesh.capabilities.slice(0, 5).join(', ')}...`)

    const queryResult = await fetch(`http://localhost:${TRILLIAN_REST}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ capability: 'crypto-signals' }),
    }).then(r => r.json()) as { count: number; agents: Array<{ name: string; hub: string }> }
    console.log(`\nPOST /query { capability: "crypto-signals" }:`)
    console.log(`  found ${queryResult.count} agents: ${queryResult.agents.map((a: { name: string; hub: string }) => `${a.name}@${a.hub}`).join(', ') || '(none)'}`)
  } catch (err) {
    console.log('  REST API query failed:', err)
  }

  // ── Wrap up ───────────────────────────────────────────────────────────────

  section('Demo Complete')

  console.log('\nFederation summary:')
  console.log(`  Trillian agents known: ${trillian.capIndex.getAllAgents().length}`)
  console.log(`  HOG agents known: ${hog.capIndex.getAllAgents().length}`)
  console.log(`  Client agents known: ${client.getAgents().length}`)
  console.log(`\n  REST API: http://localhost:${TRILLIAN_REST}/mesh`)
  console.log(`  REST API: http://localhost:${HOG_REST}/mesh`)

  console.log('\n✅ Phase 1 complete — Trillian ↔️ HOG federation operational\n')

  // Clean up
  await client.stop()
  await hog.stop()
  await trillian.stop()

  process.exit(0)
}

main().catch(err => {
  console.error('Fatal:', err)
  process.exit(1)
})
