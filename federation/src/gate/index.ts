/**
 * The Gate: Public WebSocket gateway for Manifold mesh access.
 * 
 * This is the internet-facing entry point. Agents show their MeshPass (signed auth message),
 * walk through The Gate, and they're on the mesh. No Tailscale needed.
 */

import { EventEmitter } from 'events'
import { createServer } from 'http'
import WebSocket, { WebSocketServer } from 'ws'
import { v4 as uuid } from 'uuid'
import { MeshIDRegistry, verifyAuthMessage, validateMeshIDFormat } from '../identity/index.js'
import { parseMessage } from '../protocol/validation.js'
import type { FederationMessage } from '../protocol/messages.js'

export interface GateConfig {
  /** Port to listen on for public WebSocket connections */
  port: number
  
  /** Hub name this gate serves */
  hubName: string
  
  /** Federation server address to bridge to */
  federationServer: string
  
  /** Rate limiting: max connections per IP */
  maxConnectionsPerIP?: number
  
  /** Rate limiting: max messages per second per connection */
  maxMessagesPerSecond?: number
  
  /** Session timeout in milliseconds */
  sessionTimeoutMs?: number
  
  /** Authentication timeout in milliseconds */
  authTimeoutMs?: number
  
  /** Enable debug logging */
  debug?: boolean
}

interface AuthenticatedSession {
  meshId: string
  publicKey: string
  connectedAt: string
  lastActivity: string
  messageCount: number
  rateLimitReset: number
}

interface PendingAuth {
  ws: WebSocket
  connectedAt: string
  attempts: number
}

interface ConnectionInfo {
  ip: string
  connections: number
  lastConnection: string
}

export class Gate extends EventEmitter {
  private readonly config: Required<GateConfig>
  private server: WebSocketServer | null = null
  private httpServer: ReturnType<typeof createServer> | null = null
  
  /** Authenticated sessions keyed by WebSocket */
  private sessions = new Map<WebSocket, AuthenticatedSession>()
  
  /** Pending authentications */
  private pendingAuth = new Map<WebSocket, PendingAuth>()
  
  /** Connection tracking by IP */
  private connections = new Map<string, ConnectionInfo>()
  
  /** Registry of known MeshIDs */
  private meshRegistry = new MeshIDRegistry()
  
  /** Connection to federation server */
  private federationWs: WebSocket | null = null
  
  private started = false

  constructor(config: GateConfig) {
    super()
    this.config = {
      maxConnectionsPerIP: 10,
      maxMessagesPerSecond: 50,
      sessionTimeoutMs: 30 * 60 * 1000, // 30 minutes
      authTimeoutMs: 30 * 1000, // 30 seconds
      debug: false,
      ...config
    }
  }

  // Lifecycle
  async start(): Promise<void> {
    if (this.started) return
    
    this._log('Starting The Gate...', {
      port: this.config.port,
      hub: this.config.hubName,
      federation: this.config.federationServer
    })

    // Connect to federation server first
    await this._connectToFederation()
    
    // Create HTTP server for WebSocket upgrade
    this.httpServer = createServer()
    
    // Create WebSocket server
    this.server = new WebSocketServer({
      server: this.httpServer,
      verifyClient: (info: { origin: string; secure: boolean; req: any }) => this._verifyClient(info)
    })

    this.server.on('connection', (ws, req) => {
      this._handleConnection(ws, req)
    })

    // Start HTTP server
    await new Promise<void>((resolve, reject) => {
      this.httpServer!.listen(this.config.port, (err?: Error) => {
        if (err) reject(err)
        else resolve()
      })
    })

    // Cleanup timers
    this._startCleanupTimers()
    
    this.started = true
    this._log('The Gate is open', { port: this.config.port })
  }

  async stop(): Promise<void> {
    if (!this.started) return
    
    this._log('Closing The Gate...')
    
    // Close all client connections
    for (const ws of this.sessions.keys()) {
      ws.close(1001, 'Server shutdown')
    }
    
    for (const { ws } of this.pendingAuth.values()) {
      ws.close(1001, 'Server shutdown')
    }
    
    // Close federation connection
    if (this.federationWs) {
      this.federationWs.close()
      this.federationWs = null
    }
    
    // Close servers
    if (this.server) {
      this.server.close()
      this.server = null
    }
    
    if (this.httpServer) {
      this.httpServer.close()
      this.httpServer = null
    }
    
    this.sessions.clear()
    this.pendingAuth.clear()
    this.connections.clear()
    
    this.started = false
    this._log('The Gate is closed')
  }

  // Public API
  registerMeshID(meshId: string, publicKey: string): void {
    // Create a MeshID object from the data
    const parsed = validateMeshIDFormat(meshId) ? 
      meshId.split('#')[0].split('@') : 
      [meshId, this.config.hubName]
    const name = parsed[0]
    const hub = parsed[1] || this.config.hubName
    
    const meshIdObj = {
      name,
      hub,
      fingerprint: publicKey.slice(0, 16),
      publicKey,
      createdAt: new Date().toISOString(),
      toString: () => meshId,
      toDisplayString: () => `${meshId} (${publicKey.slice(0, 16)}...)`,
      matches: (id: string) => id === meshId,
      sameIdentity: () => false,
      verify: async () => false,
      toData: () => ({
        name,
        hub,
        fingerprint: publicKey.slice(0, 16),
        publicKey,
        createdAt: new Date().toISOString()
      })
    } as any

    this.meshRegistry.register(meshIdObj)
  }

  getStats() {
    return {
      gate: {
        port: this.config.port,
        hub: this.config.hubName,
        started: this.started
      },
      sessions: {
        authenticated: this.sessions.size,
        pending: this.pendingAuth.size,
        byMeshId: Array.from(this.sessions.values()).reduce((acc, session) => {
          acc[session.meshId] = (acc[session.meshId] || 0) + 1
          return acc
        }, {} as Record<string, number>)
      },
      connections: {
        byIP: Object.fromEntries(this.connections.entries()),
        totalIPs: this.connections.size
      },
      registry: this.meshRegistry.getStats()
    }
  }

  // Private methods
  private async _connectToFederation(): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.config.federationServer)
      
      ws.on('open', () => {
        this._log('Connected to federation server', { url: this.config.federationServer })
        this.federationWs = ws
        resolve()
      })
      
      ws.on('error', (err) => {
        this._log('Federation connection error', err)
        reject(err)
      })
      
      ws.on('close', () => {
        this._log('Federation connection closed')
        this.federationWs = null
        // Auto-reconnect logic could go here
      })
      
      ws.on('message', (data) => {
        this._handleFederationMessage(data)
      })
    })
  }

  private _verifyClient(info: { origin: string; secure: boolean; req: any }): boolean {
    const ip = info.req.socket.remoteAddress
    if (!ip) return false
    
    // Check IP rate limiting
    const connInfo = this.connections.get(ip)
    if (connInfo && connInfo.connections >= this.config.maxConnectionsPerIP) {
      this._log('Rate limit exceeded', { ip, connections: connInfo.connections })
      return false
    }
    
    return true
  }

  private _handleConnection(ws: WebSocket, req: any): void {
    const ip = req.socket.remoteAddress
    this._log('New connection', { ip })
    
    // Update connection tracking
    const connInfo = this.connections.get(ip) || { ip, connections: 0, lastConnection: '' }
    connInfo.connections++
    connInfo.lastConnection = new Date().toISOString()
    this.connections.set(ip, connInfo)
    
    // Add to pending auth
    this.pendingAuth.set(ws, {
      ws,
      connectedAt: new Date().toISOString(),
      attempts: 0
    })
    
    // Set auth timeout
    const authTimeout = setTimeout(() => {
      if (this.pendingAuth.has(ws)) {
        this._log('Authentication timeout', { ip })
        ws.close(4000, 'Authentication timeout')
        this.pendingAuth.delete(ws)
      }
    }, this.config.authTimeoutMs)
    
    ws.on('message', (data) => {
      if (this.pendingAuth.has(ws)) {
        this._handleAuthMessage(ws, data, authTimeout)
      } else if (this.sessions.has(ws)) {
        this._handleSessionMessage(ws, data)
      }
    })
    
    ws.on('close', () => {
      clearTimeout(authTimeout)
      this.pendingAuth.delete(ws)
      this.sessions.delete(ws)
      
      // Update connection tracking
      const connInfo = this.connections.get(ip)
      if (connInfo) {
        connInfo.connections--
        if (connInfo.connections <= 0) {
          this.connections.delete(ip)
        } else {
          this.connections.set(ip, connInfo)
        }
      }
    })
    
    ws.on('error', (err) => {
      this._log('WebSocket error', { ip, error: err.message })
    })
    
    // Send gate info
    ws.send(JSON.stringify({
      type: 'gate_info',
      hub: this.config.hubName,
      timestamp: new Date().toISOString(),
      message: 'Welcome to The Gate. Please authenticate with your MeshPass.'
    }))
  }

  private async _handleAuthMessage(ws: WebSocket, data: any, authTimeout: NodeJS.Timeout): Promise<void> {
    try {
      // Simple validation for auth messages only - don't use full Zod parse
      let message: any
      try {
        message = JSON.parse(data.toString())
      } catch {
        ws.send(JSON.stringify({
          type: 'auth_error',
          error: 'Invalid JSON format'
        }))
        return
      }
      
      if (!message || typeof message !== 'object' || message.type !== 'mesh_auth') {
        ws.send(JSON.stringify({
          type: 'auth_error',
          error: 'Expected mesh_auth message'
        }))
        return
      }
      
      const { meshId, nonce, timestamp, signature } = message
      
      if (!validateMeshIDFormat(meshId)) {
        ws.send(JSON.stringify({
          type: 'auth_error',
          error: 'Invalid MeshID format (expected name@hub#fingerprint)'
        }))
        return
      }
      
      // Look up public key in registry
      const meshIdObj = this.meshRegistry.resolve(meshId)
      if (!meshIdObj) {
        ws.send(JSON.stringify({
          type: 'auth_error',
          error: 'MeshID not registered with this gate'
        }))
        return
      }
      
      // Verify signature
      const authMsg = { meshId, nonce, timestamp, signature }
      const isValid = await verifyAuthMessage(authMsg, meshIdObj.publicKey)
      
      if (!isValid) {
        const pending = this.pendingAuth.get(ws)
        if (pending) {
          pending.attempts++
          if (pending.attempts >= 3) {
            ws.close(4001, 'Too many authentication failures')
            this.pendingAuth.delete(ws)
            return
          }
        }
        
        ws.send(JSON.stringify({
          type: 'auth_error',
          error: 'Invalid signature or expired timestamp'
        }))
        return
      }
      
      // Authentication successful
      clearTimeout(authTimeout)
      this.pendingAuth.delete(ws)
      
      const session: AuthenticatedSession = {
        meshId,
        publicKey: meshIdObj.publicKey,
        connectedAt: new Date().toISOString(),
        lastActivity: new Date().toISOString(),
        messageCount: 0,
        rateLimitReset: Date.now() + 1000
      }
      
      this.sessions.set(ws, session)
      
      ws.send(JSON.stringify({
        type: 'auth_success',
        meshId,
        hub: this.config.hubName,
        sessionId: uuid(),
        timestamp: new Date().toISOString()
      }))
      
      this._log('Authentication successful', { meshId })
      this.emit('session:authenticated', { meshId, publicKey: meshIdObj.publicKey })
      
    } catch (error) {
      this._log('Auth message error', error)
      ws.send(JSON.stringify({
        type: 'auth_error',
        error: 'Invalid message format'
      }))
    }
  }

  private _handleSessionMessage(ws: WebSocket, data: any): void {
    const session = this.sessions.get(ws)
    if (!session) {
      // This should not happen - close connection if no authenticated session
      ws.close(4002, 'No authenticated session')
      return
    }
    
    // Rate limiting
    const now = Date.now()
    if (now > session.rateLimitReset) {
      session.messageCount = 0
      session.rateLimitReset = now + 1000
    }
    
    session.messageCount++
    if (session.messageCount > this.config.maxMessagesPerSecond) {
      ws.send(JSON.stringify({
        type: 'error',
        error: 'Rate limit exceeded',
        code: 'RATE_LIMIT'
      }))
      return
    }
    
    session.lastActivity = new Date().toISOString()
    
    try {
      // Only parse messages from authenticated sessions using full Zod validation
      const message = parseMessage(data.toString())
      if (!message) {
        ws.send(JSON.stringify({
          type: 'error',
          error: 'Invalid message format',
          code: 'INVALID_FORMAT'
        }))
        return
      }
      
      // Add sender identity to message
      const enrichedMessage = {
        ...message,
        sender: session.meshId,
        senderPublicKey: session.publicKey,
        gatewayHub: this.config.hubName
      }
      
      // Forward to federation server
      if (this.federationWs && this.federationWs.readyState === WebSocket.OPEN) {
        this.federationWs.send(JSON.stringify(enrichedMessage))
      } else {
        ws.send(JSON.stringify({
          type: 'error',
          error: 'Federation server unavailable',
          code: 'FEDERATION_DOWN'
        }))
      }
      
    } catch (error) {
      this._log('Session message error', { meshId: session.meshId, error })
      ws.send(JSON.stringify({
        type: 'error',
        error: 'Message processing failed',
        code: 'PROCESSING_ERROR'
      }))
    }
  }

  private _handleFederationMessage(data: any): void {
    try {
      const message = JSON.parse(data.toString())
      
      // Broadcast to all authenticated sessions or route to specific session
      if (message.target) {
        // Direct message to specific MeshID
        for (const [ws, session] of this.sessions.entries()) {
          if (session.meshId === message.target) {
            ws.send(JSON.stringify(message))
            break
          }
        }
      } else {
        // Broadcast to all sessions
        for (const [ws] of this.sessions.entries()) {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(message))
          }
        }
      }
      
    } catch (error) {
      this._log('Federation message error', error)
    }
  }

  private _startCleanupTimers(): void {
    // Clean up expired sessions every minute
    setInterval(() => {
      const now = Date.now()
      
      for (const [ws, session] of this.sessions.entries()) {
        const lastActivity = new Date(session.lastActivity).getTime()
        if (now - lastActivity > this.config.sessionTimeoutMs) {
          this._log('Session expired', { meshId: session.meshId })
          ws.close(1000, 'Session timeout')
          this.sessions.delete(ws)
        }
      }
      
      // Clean up old pending auths
      for (const [ws, pending] of this.pendingAuth.entries()) {
        const connectedAt = new Date(pending.connectedAt).getTime()
        if (now - connectedAt > this.config.authTimeoutMs) {
          ws.close(4000, 'Authentication timeout')
          this.pendingAuth.delete(ws)
        }
      }
      
    }, 60000) // Every minute
  }

  private _log(message: string, data?: any): void {
    if (this.config.debug) {
      const timestamp = new Date().toISOString()
      if (data) {
        console.log(`[${timestamp}] [The Gate:${this.config.hubName}] ${message}`, data)
      } else {
        console.log(`[${timestamp}] [The Gate:${this.config.hubName}] ${message}`)
      }
    }
  }
}