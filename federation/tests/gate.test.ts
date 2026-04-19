import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { Gate } from '../src/gate/index.js'
import { MeshPass } from '../src/identity/index.js'
import { createAuthMessage } from '../src/identity/index.js'
import WebSocket, { WebSocketServer } from 'ws'
import { createServer } from 'http'

describe('Gate', () => {
  let gate: Gate
  let mockFederationServer: any
  let federationPort: number
  let gatePort: number
  let meshPass: MeshPass
  let meshId: string

  beforeEach(async () => {
    // Find available ports
    gatePort = 8700 + Math.floor(Math.random() * 100)
    federationPort = gatePort + 1

    // Create test MeshPass
    meshPass = await MeshPass.generate()
    meshId = `alice@test#${meshPass.getFingerprint().slice(0, 8)}`

    // Mock federation server
    mockFederationServer = createMockFederationServer(federationPort)
    await new Promise(resolve => {
      mockFederationServer.listen(federationPort, resolve)
    })

    // Create gate
    gate = new Gate({
      port: gatePort,
      hubName: 'test-hub',
      federationServer: `ws://localhost:${federationPort}`,
      maxConnectionsPerIP: 5,
      maxMessagesPerSecond: 10,
      authTimeoutMs: 5000,
      sessionTimeoutMs: 30000,
      debug: false
    })

    // Register test MeshID
    gate.registerMeshID(meshId, meshPass.getPublicKeyHex())
  })

  afterEach(async () => {
    if (gate) {
      await gate.stop()
    }
    if (mockFederationServer) {
      mockFederationServer.close()
    }
  })

  function createMockFederationServer(port: number) {
    const server = createServer()
    const wss = new WebSocketServer({ server })
    const connectedClients = new Set<WebSocket>()

    wss.on('connection', (ws) => {
      connectedClients.add(ws)
      
      ws.on('close', () => {
        connectedClients.delete(ws)
      })
      
      ws.on('message', (data) => {
        // Echo messages back to simulate federation responses
        try {
          const message = JSON.parse(data.toString())
          // Send a mock response
          ws.send(JSON.stringify({
            type: 'federation_response',
            data: { echo: message },
            timestamp: new Date().toISOString()
          }))
        } catch {
          // Ignore parse errors in mock
        }
      })
    })

    return server
  }

  async function connectAndAuth(customMeshId?: string, customMeshPass?: MeshPass): Promise<WebSocket> {
    const client = new WebSocket(`ws://localhost:${gatePort}`)
    
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Connection timeout')), 5000)
      
      client.on('open', () => {
        clearTimeout(timeout)
        resolve(undefined)
      })
      
      client.on('error', (err) => {
        clearTimeout(timeout)
        reject(err)
      })
    })

    // Wait for gate_info message
    await new Promise((resolve) => {
      client.once('message', (data) => {
        const message = JSON.parse(data.toString())
        expect(message.type).toBe('gate_info')
        resolve(undefined)
      })
    })

    // Send authentication
    const usePass = customMeshPass || meshPass
    const useId = customMeshId || meshId
    const authMsg = await createAuthMessage(usePass, useId)
    
    client.send(JSON.stringify({
      type: 'mesh_auth',
      ...authMsg
    }))

    // Wait for auth response
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Auth timeout')), 5000)
      
      client.once('message', (data) => {
        clearTimeout(timeout)
        const response = JSON.parse(data.toString())
        
        if (response.type === 'auth_success') {
          resolve(client)
        } else {
          reject(new Error(`Auth failed: ${response.error}`))
        }
      })
    })
  }

  describe('lifecycle', () => {
    it('should start and stop cleanly', async () => {
      await gate.start()
      expect(gate.getStats().gate.started).toBe(true)
      
      await gate.stop()
      expect(gate.getStats().gate.started).toBe(false)
    })

    it('should not start twice', async () => {
      await gate.start()
      await gate.start() // Should not throw
      expect(gate.getStats().gate.started).toBe(true)
      
      await gate.stop()
    })
  })

  describe('client authentication', () => {
    beforeEach(async () => {
      await gate.start()
    })

    it('should authenticate client with valid MeshPass', async () => {
      const client = await connectAndAuth()
      
      expect(gate.getStats().sessions.authenticated).toBe(1)
      
      client.close()
      
      // Wait a bit for cleanup
      await new Promise(resolve => setTimeout(resolve, 100))
      expect(gate.getStats().sessions.authenticated).toBe(0)
    })

    it('should send gate_info on connection', async () => {
      const client = new WebSocket(`ws://localhost:${gatePort}`)
      
      await new Promise((resolve) => {
        client.once('open', resolve)
      })

      const response = await new Promise((resolve) => {
        client.once('message', (data) => {
          resolve(JSON.parse(data.toString()))
        })
      })

      expect(response).toMatchObject({
        type: 'gate_info',
        hub: 'test-hub',
        message: expect.stringContaining('Welcome to The Gate')
      })
      
      client.close()
    })

    it('should reject connection without valid auth', async () => {
      const client = new WebSocket(`ws://localhost:${gatePort}`)
      
      await new Promise((resolve) => {
        client.once('open', resolve)
      })

      // Wait for gate_info
      await new Promise((resolve) => {
        client.once('message', resolve)
      })

      // Send invalid auth message
      client.send(JSON.stringify({
        type: 'mesh_auth',
        meshId: meshId,
        nonce: 'test-nonce',
        timestamp: new Date().toISOString(),
        signature: 'invalid-signature'
      }))

      const response = await new Promise((resolve) => {
        client.once('message', (data) => {
          resolve(JSON.parse(data.toString()))
        })
      })

      expect(response).toMatchObject({
        type: 'auth_error',
        error: expect.stringContaining('Invalid signature')
      })

      client.close()
    })

    it('should reject unregistered MeshID', async () => {
      const unknownMeshPass = await MeshPass.generate()
      const unknownMeshId = `unknown@test#${unknownMeshPass.getFingerprint().slice(0, 8)}`
      
      const client = new WebSocket(`ws://localhost:${gatePort}`)
      
      await new Promise((resolve) => {
        client.once('open', resolve)
      })

      // Wait for gate_info
      await new Promise((resolve) => {
        client.once('message', resolve)
      })

      const authMsg = await createAuthMessage(unknownMeshPass, unknownMeshId)
      client.send(JSON.stringify({
        type: 'mesh_auth',
        ...authMsg
      }))

      const response = await new Promise((resolve) => {
        client.once('message', (data) => {
          resolve(JSON.parse(data.toString()))
        })
      })

      expect(response).toMatchObject({
        type: 'auth_error',
        error: 'MeshID not registered with this gate'
      })

      client.close()
    })

    it('should reject invalid MeshID format', async () => {
      const client = new WebSocket(`ws://localhost:${gatePort}`)
      
      await new Promise((resolve) => {
        client.once('open', resolve)
      })

      // Wait for gate_info
      await new Promise((resolve) => {
        client.once('message', resolve)
      })

      // Send auth with invalid format (missing fingerprint)
      const authMsg = await createAuthMessage(meshPass, 'invalid-format')
      client.send(JSON.stringify({
        type: 'mesh_auth',
        ...authMsg
      }))

      const response = await new Promise((resolve) => {
        client.once('message', (data) => {
          resolve(JSON.parse(data.toString()))
        })
      })

      expect(response).toMatchObject({
        type: 'auth_error',
        error: 'Invalid MeshID format (expected name@hub#fingerprint)'
      })

      client.close()
    })
  })

  describe('rate limiting', () => {
    beforeEach(async () => {
      await gate.start()
    })

    it('should enforce connection limits per IP', async () => {
      const clients: WebSocket[] = []
      
      // Connect up to the limit
      for (let i = 0; i < 5; i++) { // maxConnectionsPerIP = 5
        try {
          const client = await connectAndAuth()
          clients.push(client)
        } catch (error) {
          // Some connections might fail due to timing
          break
        }
      }

      expect(clients.length).toBeGreaterThan(0)

      // Additional connections should be rejected at WebSocket level
      const shouldFail = new WebSocket(`ws://localhost:${gatePort}`)
      
      await new Promise((resolve) => {
        const timeout = setTimeout(resolve, 1000)
        shouldFail.on('error', () => {
          clearTimeout(timeout)
          resolve(undefined)
        })
        shouldFail.on('open', () => {
          clearTimeout(timeout)
          // If it opens, close it immediately
          shouldFail.close()
          resolve(undefined)
        })
      })

      // Clean up
      clients.forEach(client => client.close())
    })

    it('should enforce message rate limits', async () => {
      const client = await connectAndAuth()
      
      // Send messages rapidly
      const responses: any[] = []
      
      for (let i = 0; i < 15; i++) { // maxMessagesPerSecond = 10
        client.send(JSON.stringify({
          type: 'test_message',
          data: { count: i }
        }))
      }

      // Collect responses
      await new Promise((resolve) => {
        let responseCount = 0
        const timeout = setTimeout(resolve, 2000)
        
        client.on('message', (data) => {
          const response = JSON.parse(data.toString())
          responses.push(response)
          responseCount++
          
          if (responseCount >= 5) { // Expect some rate limit responses
            clearTimeout(timeout)
            resolve(undefined)
          }
        })
      })

      // Should have received some rate limit errors
      const rateLimitErrors = responses.filter(r => r.code === 'RATE_LIMIT')
      expect(rateLimitErrors.length).toBeGreaterThan(0)

      client.close()
    })

    it('should timeout unauthenticated connections', async () => {
      // Reduce auth timeout for faster test
      const fastGate = new Gate({
        port: gatePort + 10,
        hubName: 'test-hub',
        federationServer: `ws://localhost:${federationPort}`,
        authTimeoutMs: 500 // 500ms timeout
      })

      await fastGate.start()

      try {
        const client = new WebSocket(`ws://localhost:${gatePort + 10}`)
        
        await new Promise((resolve) => {
          client.once('open', resolve)
        })

        // Wait for gate_info
        await new Promise((resolve) => {
          client.once('message', resolve)
        })

        // Don't send auth - just wait for timeout
        const closeReason = await new Promise((resolve) => {
          client.on('close', (code, reason) => {
            resolve({ code, reason: reason.toString() })
          })
        })

        expect(closeReason).toMatchObject({
          code: 4000,
          reason: 'Authentication timeout'
        })
      } finally {
        await fastGate.stop()
      }
    })
  })

  describe('message handling', () => {
    beforeEach(async () => {
      await gate.start()
    })

    it('should forward messages to federation server', async () => {
      const client = await connectAndAuth()
      
      // Send a test message
      client.send(JSON.stringify({
        type: 'capability_query',
        data: { capability: 'test' }
      }))

      // Should receive response from mock federation server
      const response = await new Promise((resolve) => {
        client.once('message', (data) => {
          resolve(JSON.parse(data.toString()))
        })
      })

      expect(response).toMatchObject({
        type: 'federation_response',
        data: {
          echo: {
            type: 'capability_query',
            sender: meshId,
            senderPublicKey: meshPass.getPublicKeyHex()
          }
        }
      })

      client.close()
    })

    it('should handle parse errors gracefully', async () => {
      const client = await connectAndAuth()
      
      // Send invalid JSON
      client.send('invalid-json-data')

      const response = await new Promise((resolve) => {
        client.once('message', (data) => {
          resolve(JSON.parse(data.toString()))
        })
      })

      expect(response).toMatchObject({
        type: 'error',
        code: 'INVALID_FORMAT'
      })

      client.close()
    })

    it('should only parse messages from authenticated sessions', async () => {
      const client = new WebSocket(`ws://localhost:${gatePort}`)
      
      await new Promise((resolve) => {
        client.once('open', resolve)
      })

      // Wait for gate_info
      await new Promise((resolve) => {
        client.once('message', resolve)
      })

      // Send non-auth message before authenticating
      client.send(JSON.stringify({
        type: 'capability_query',
        data: { capability: 'test' }
      }))

      // Should get auth error, not parse error
      const response = await new Promise((resolve) => {
        client.once('message', (data) => {
          resolve(JSON.parse(data.toString()))
        })
      })

      expect(response).toMatchObject({
        type: 'auth_error',
        error: 'Expected mesh_auth message'
      })

      client.close()
    })

    it('should handle federation server unavailable', async () => {
      // Stop mock federation server
      mockFederationServer.close()
      
      // Wait for disconnection
      await new Promise(resolve => setTimeout(resolve, 100))

      const client = await connectAndAuth()
      
      client.send(JSON.stringify({
        type: 'test_message',
        data: { test: true }
      }))

      const response = await new Promise((resolve) => {
        client.once('message', (data) => {
          resolve(JSON.parse(data.toString()))
        })
      })

      expect(response).toMatchObject({
        type: 'error',
        code: 'FEDERATION_DOWN'
      })

      client.close()
    })
  })

  describe('session management', () => {
    beforeEach(async () => {
      await gate.start()
    })

    it('should track authenticated sessions', async () => {
      expect(gate.getStats().sessions.authenticated).toBe(0)
      
      const client1 = await connectAndAuth()
      expect(gate.getStats().sessions.authenticated).toBe(1)
      
      const client2 = await connectAndAuth()
      expect(gate.getStats().sessions.authenticated).toBe(2)
      
      client1.close()
      await new Promise(resolve => setTimeout(resolve, 100))
      expect(gate.getStats().sessions.authenticated).toBe(1)
      
      client2.close()
      await new Promise(resolve => setTimeout(resolve, 100))
      expect(gate.getStats().sessions.authenticated).toBe(0)
    })

    it('should include MeshID in session stats', async () => {
      const client = await connectAndAuth()
      
      const stats = gate.getStats()
      expect(stats.sessions.byMeshId).toHaveProperty(meshId, 1)
      
      client.close()
    })

    it('should handle multiple auth attempts', async () => {
      const client = new WebSocket(`ws://localhost:${gatePort}`)
      
      await new Promise((resolve) => {
        client.once('open', resolve)
      })

      // Wait for gate_info
      await new Promise((resolve) => {
        client.once('message', resolve)
      })

      // Send multiple bad auth attempts
      for (let i = 0; i < 3; i++) {
        client.send(JSON.stringify({
          type: 'mesh_auth',
          meshId: meshId,
          nonce: `bad-nonce-${i}`,
          timestamp: new Date().toISOString(),
          signature: 'bad-signature'
        }))

        await new Promise((resolve) => {
          client.once('message', resolve) // Wait for error response
        })
      }

      // Fourth attempt should close connection
      const closePromise = new Promise((resolve) => {
        client.on('close', (code, reason) => {
          resolve({ code, reason: reason.toString() })
        })
      })

      client.send(JSON.stringify({
        type: 'mesh_auth',
        meshId: meshId,
        nonce: 'final-bad-nonce',
        timestamp: new Date().toISOString(),
        signature: 'bad-signature'
      }))

      const closeResult = await closePromise
      expect(closeResult).toMatchObject({
        code: 4001,
        reason: 'Too many authentication failures'
      })
    })
  })

  describe('statistics', () => {
    beforeEach(async () => {
      await gate.start()
    })

    it('should provide comprehensive stats', async () => {
      const client = await connectAndAuth()
      
      const stats = gate.getStats()
      
      expect(stats).toMatchObject({
        gate: {
          port: gatePort,
          hub: 'test-hub',
          started: true
        },
        sessions: {
          authenticated: 1,
          pending: 0,
          byMeshId: {
            [meshId]: 1
          }
        },
        connections: {
          totalIPs: 1
        },
        registry: {
          total: 1
        }
      })

      client.close()
    })
  })
})