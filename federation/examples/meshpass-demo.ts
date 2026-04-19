/**
 * MeshPass Identity & Gate Demo
 * 
 * This example demonstrates the complete MeshPass identity system and The Gate public gateway.
 * Run this to see how agents can authenticate with cryptographic identities and connect
 * through The Gate instead of requiring Tailscale.
 */

import { Gate } from '../src/gate/index.js'
import { GateClient } from '../src/gate/client.js'
import { MeshPass, MeshID, createAuthMessage } from '../src/identity/index.js'
import { ManifoldServer } from '../src/server/index.js'

// Demo configuration
const DEMO_CONFIG = {
  // Federation server (internal, Tailscale-based)
  federationPort: 8766,
  
  // The Gate (public WebSocket gateway)
  gatePort: 8765,
  
  // Hub name
  hubName: 'demo-hub',
  
  // Debug logging
  debug: true
}

interface DemoAgent {
  name: string
  meshPass: MeshPass
  meshId: string
  capabilities: string[]
}

class MeshPassDemo {
  private federationServer: ManifoldServer | null = null
  private gate: Gate | null = null
  private agents: DemoAgent[] = []
  private clients: GateClient[] = []

  async start(): Promise<void> {
    console.log('🚀 Starting MeshPass Identity & Gate Demo')
    console.log('━'.repeat(60))
    
    // 1. Generate demo MeshPasses
    await this.setupDemoIdentities()
    
    // 2. Start federation server (internal)
    await this.startFederationServer()
    
    // 3. Start The Gate (public)
    await this.startGate()
    
    // 4. Connect agents through The Gate
    await this.connectAgents()
    
    // 5. Demonstrate mesh communication
    await this.demonstrateMeshCommunication()
    
    console.log('\n✅ Demo running! Press Ctrl+C to stop')
    console.log('\n📊 Try these:')
    console.log('  - Check gate stats: curl http://localhost:8767/stats')
    console.log('  - View mesh status: curl http://localhost:8767/mesh')
    console.log('  - Send capability query via gate')
  }

  async stop(): Promise<void> {
    console.log('\n🛑 Stopping demo...')
    
    // Disconnect clients
    for (const client of this.clients) {
      client.disconnect()
    }
    
    // Stop services
    if (this.gate) await this.gate.stop()
    if (this.federationServer) await this.federationServer.stop()
    
    console.log('✅ Demo stopped')
  }

  // ── Demo Setup ──────────────────────────────────────────────────────────────

  private async setupDemoIdentities(): Promise<void> {
    console.log('🔑 Generating demo MeshPass identities...')
    
    const agentConfigs = [
      { name: 'stella', capabilities: ['solar-monitoring', 'data-analysis'] },
      { name: 'eddie', capabilities: ['threat-detection', 'security-audit'] },
      { name: 'alice', capabilities: ['mesh-coordination', 'load-balancing'] }
    ]
    
    for (const config of agentConfigs) {
      const meshPass = await MeshPass.generate()
      const meshId = `${config.name}@${DEMO_CONFIG.hubName}`
      
      this.agents.push({
        name: config.name,
        meshPass,
        meshId,
        capabilities: config.capabilities
      })
      
      console.log(`  ✓ ${meshId} (${meshPass.getFingerprint()}...)`)
    }
    
    console.log(`\n🆔 Generated ${this.agents.length} MeshPass identities`)
  }

  private async startFederationServer(): Promise<void> {
    console.log('\n🔗 Starting federation server (internal)...')
    
    this.federationServer = new ManifoldServer({
      name: DEMO_CONFIG.hubName,
      federationPort: DEMO_CONFIG.federationPort,
      localPort: 8765,  // Not used in this demo
      restPort: 8767,
      debug: DEMO_CONFIG.debug
    })
    
    await this.federationServer.start()
    console.log(`  ✓ Federation server running on port ${DEMO_CONFIG.federationPort}`)
    console.log(`  ✓ REST API available on port 8767`)
  }

  private async startGate(): Promise<void> {
    console.log('\n🚪 Starting The Gate (public gateway)...')
    
    this.gate = new Gate({
      port: DEMO_CONFIG.gatePort,
      hubName: DEMO_CONFIG.hubName,
      federationServer: `ws://localhost:${DEMO_CONFIG.federationPort}`,
      maxConnectionsPerIP: 10,
      maxMessagesPerSecond: 50,
      debug: DEMO_CONFIG.debug
    })
    
    // Register demo MeshIDs
    for (const agent of this.agents) {
      this.gate!.registerMeshID(agent.meshId, agent.meshPass.getPublicKeyHex())
      console.log(`  ✓ Registered ${agent.meshId}`)
    }
    
    await this.gate.start()
    console.log(`\n✅ The Gate is open on port ${DEMO_CONFIG.gatePort}!`)
  }

  private async connectAgents(): Promise<void> {
    console.log('\n🤝 Connecting agents through The Gate...')
    
    for (const agent of this.agents) {
      const client = new GateClient({
        gateUrl: `ws://localhost:${DEMO_CONFIG.gatePort}`,
        meshPass: agent.meshPass,
        meshId: agent.meshId,
        debug: DEMO_CONFIG.debug
      })
      
      // Set up event handlers
      client.on('authenticated', (session) => {
        console.log(`  ✓ ${agent.meshId} authenticated (session: ${session.sessionId})`)
      })
      
      client.on('auth_error', (error) => {
        console.error(`  ✗ ${agent.meshId} auth failed: ${error}`)
      })
      
      client.on('message', (message) => {
        console.log(`  📨 ${agent.meshId} received: ${message.type}`)
      })
      
      // Connect and wait for authentication
      await client.connect()
      await this.waitForAuthentication(client)
      
      this.clients.push(client)
    }
    
    console.log(`\n✅ ${this.clients.length} agents connected and authenticated`)
  }

  private async demonstrateMeshCommunication(): Promise<void> {
    console.log('\n💬 Demonstrating mesh communication...')
    
    if (this.clients.length < 2) {
      console.log('  ⚠️  Need at least 2 clients for communication demo')
      return
    }
    
    const [stellaClient, eddieClient] = this.clients
    
    // Stella sends a capability query
    console.log('  📤 stella sends capability query for "threat-detection"')
    stellaClient.send({
      type: 'capability_query',
      capability: 'threat-detection',
      requestId: 'demo-query-1',
      timestamp: new Date().toISOString()
    })
    
    // Eddie sends an agent request
    setTimeout(() => {
      console.log('  📤 eddie sends agent request to stella')
      eddieClient.send({
        type: 'agent_request',
        target: 'stella@demo-hub',
        task: {
          type: 'solar-status',
          query: 'current-output'
        },
        requestId: 'demo-request-1',
        timestamp: new Date().toISOString()
      })
    }, 1000)
    
    // Demonstrate signed message
    setTimeout(async () => {
      console.log('  📤 alice sends signed mesh sync message')
      const authMsg = await createAuthMessage(
        this.agents[2].meshPass, 
        this.agents[2].meshId
      )
      
      this.clients[2].send({
        type: 'mesh_sync',
        hub: DEMO_CONFIG.hubName,
        agents: [{
          name: 'alice',
          hub: DEMO_CONFIG.hubName,
          capabilities: ['mesh-coordination'],
          pressure: 0.7,
          lastSeen: new Date().toISOString()
        }],
        darkCircles: [],
        timestamp: new Date().toISOString()
      })
    }, 2000)
    
    console.log('  ⏳ Messages sent, check logs for responses...')
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  private async waitForAuthentication(client: GateClient): Promise<void> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Authentication timeout'))
      }, 10000)
      
      client.on('authenticated', () => {
        clearTimeout(timeout)
        resolve()
      })
      
      client.on('auth_error', (error) => {
        clearTimeout(timeout)
        reject(new Error(`Auth failed: ${error}`))
      })
    })
  }
}

// ── CLI Runner ──────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const demo = new MeshPassDemo()
  
  // Handle graceful shutdown
  process.on('SIGINT', async () => {
    await demo.stop()
    process.exit(0)
  })
  
  process.on('SIGTERM', async () => {
    await demo.stop()
    process.exit(0)
  })
  
  try {
    await demo.start()
    
    // Keep running until interrupted
    await new Promise(() => {})
  } catch (error) {
    console.error('Demo failed:', error)
    await demo.stop()
    process.exit(1)
  }
}

// ── Interactive Demo Functions ──────────────────────────────────────────────────

/**
 * Show how to manually create and use MeshPass credentials.
 */
export async function demonstrateMeshPassUsage(): Promise<void> {
  console.log('🔑 MeshPass Usage Demo')
  console.log('━'.repeat(30))
  
  // Generate a MeshPass
  console.log('1. Generating MeshPass...')
  const meshPass = await MeshPass.generate()
  console.log(`   Public key: ${meshPass.getPublicKeyHex()}`)
  console.log(`   Fingerprint: ${meshPass.getFingerprint()}`)
  
  // Create a MeshID
  console.log('\n2. Creating MeshID...')
  const meshId = MeshID.fromMeshPass(meshPass, 'demo-user', 'demo-hub')
  console.log(`   MeshID: ${meshId.toString()}`)
  console.log(`   Display: ${meshId.toDisplayString()}`)
  
  // Sign a message
  console.log('\n3. Signing message...')
  const message = 'Hello from the Manifold mesh!'
  const signature = await meshPass.sign(message)
  console.log(`   Message: "${message}"`)
  console.log(`   Signature: ${signature.slice(0, 32)}...`)
  
  // Verify signature
  console.log('\n4. Verifying signature...')
  const isValid = await meshPass.verify(message, signature)
  console.log(`   Valid: ${isValid ? '✅' : '❌'}`)
  
  // Create auth message
  console.log('\n5. Creating auth message...')
  const authMsg = await createAuthMessage(meshPass, meshId.toString())
  console.log(`   MeshID: ${authMsg.meshId}`)
  console.log(`   Nonce: ${authMsg.nonce}`)
  console.log(`   Signature: ${authMsg.signature.slice(0, 32)}...`)
  
  console.log('\n✅ MeshPass demo complete!')
}

/**
 * Show gate statistics and monitoring.
 */
export function demonstrateGateMonitoring(): void {
  console.log('📊 Gate Monitoring Demo')
  console.log('━'.repeat(30))
  console.log('\nThe Gate provides real-time statistics:')
  console.log('\n• Active sessions by MeshID')
  console.log('• Connection counts by IP address')
  console.log('• Authentication success/failure rates')
  console.log('• Message throughput and rate limiting')
  console.log('• MeshID registry status')
  console.log('\nAccess via:')
  console.log('  curl http://localhost:8767/stats')
  console.log('  curl http://localhost:8767/mesh')
}

// Run if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  const command = process.argv[2]
  
  switch (command) {
    case 'meshpass':
      demonstrateMeshPassUsage().catch(console.error)
      break
    case 'monitoring':
      demonstrateGateMonitoring()
      break
    default:
      main().catch(console.error)
      break
  }
}

export { MeshPassDemo }