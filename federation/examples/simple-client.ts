/**
 * Simple ManifoldClient example.
 *
 * Connects to a federation server, registers capabilities, and queries for agents.
 *
 * Usage:
 *   npx tsx examples/simple-client.ts [server-url]
 *
 * Example:
 *   npx tsx examples/simple-client.ts ws://trillian:8766
 */

import { ManifoldClient } from '../src/client/index.js'

const serverUrl = process.argv[2] ?? 'ws://localhost:8766'

console.log(`Connecting to federation server: ${serverUrl}`)

const client = new ManifoldClient({
  servers: [serverUrl],
  identity: {
    name: 'demo-agent',
  },
  debug: true,
  defaultQueryTimeout: 5000,
})

// Wire up event listeners
client.on('connected', () => {
  console.log('✅ Connected to federation server')
})

client.on('disconnected', () => {
  console.log('❌ Disconnected from federation server')
})

client.on('agent:join', (agent) => {
  console.log(`🟢 Agent joined: ${agent.name}@${agent.hub} [${agent.capabilities.join(', ')}]`)
})

client.on('agent:leave', (agent) => {
  console.log(`🔴 Agent left: ${agent.name}@${agent.hub}`)
})

client.on('capability:change', ({ agent, added, removed }) => {
  console.log(`🔄 ${agent} capabilities changed — added: [${added.join(', ')}] removed: [${removed.join(', ')}]`)
})

client.on('pressure:update', ({ circle, pressure, hub }) => {
  console.log(`⚡ Dark circle "${circle}" pressure: ${pressure} (from ${hub})`)
})

async function main() {
  await client.start()

  // Register demo capabilities
  console.log('\n📡 Registering capabilities...')
  await client.register(['demo-skill', 'example-task'])

  // Wait a moment for mesh sync
  await sleep(2000)

  // Query for all known agents
  console.log('\n🔍 Known agents:')
  const agents = client.getAgents()
  if (agents.length === 0) {
    console.log('  (none yet — server may be empty or not connected)')
  } else {
    for (const agent of agents) {
      console.log(`  - ${agent.name}@${agent.hub}: [${agent.capabilities.join(', ')}]`)
    }
  }

  // Query for a specific capability
  console.log('\n🔍 Querying for solar-prediction...')
  const solarAgents = await client.query('solar-prediction')
  if (solarAgents.length === 0) {
    console.log('  No agents found with solar-prediction capability')
  } else {
    for (const agent of solarAgents) {
      console.log(`  - ${agent.name}@${agent.hub} (pressure: ${agent.pressure ?? 'n/a'})`)
    }
  }

  // Keep running for 10 seconds then exit
  console.log('\n⏳ Listening for 10 seconds...')
  await sleep(10_000)

  console.log('\n👋 Stopping client...')
  await client.stop()
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

main().catch(err => {
  console.error('Fatal error:', err)
  process.exit(1)
})
