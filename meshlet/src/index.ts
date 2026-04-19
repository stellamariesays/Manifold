#!/usr/bin/env node
/**
 * Meshlet - Lightweight Test Agent for Manifold
 * 
 * A simple Docker-ready agent that:
 * - Generates a MeshPass on first boot
 * - Connects to The Gate with MeshPass auth
 * - Responds to PING with PONG
 * - Handles capability challenges
 * - Optional LLM integration via Groq
 */

import { WebSocket } from 'ws'
import { v4 as uuid } from 'uuid'
import { loadConfig, logConfigSafely, type MeshletConfig } from './config.js'
import { MeshPass, createAuthMessage } from './meshpass.js'
import { MessageResponder, type MeshMessage, type ResponseContext } from './responder.js'

interface MeshletState {
  meshPass: MeshPass
  meshId: string
  connected: boolean
  authenticated: boolean
  lastActivity: string
  messageCount: number
  errors: number
}

class Meshlet {
  private config: MeshletConfig
  private state: MeshletState
  private ws: WebSocket | null = null
  private responder: MessageResponder
  private reconnectAttempts = 0
  private reconnectTimer: NodeJS.Timeout | null = null
  private healthInterval: NodeJS.Timeout | null = null

  constructor(config: MeshletConfig) {
    this.config = config
    
    // Initialize state placeholder - will be set in start()
    this.state = {} as MeshletState
    this.responder = {} as MessageResponder
  }

  async start(): Promise<void> {
    this.log('info', 'Meshlet starting...', logConfigSafely(this.config))

    try {
      // Generate MeshPass
      this.log('info', 'Generating MeshPass...')
      const meshPass = await MeshPass.generate()
      const fingerprint = meshPass.getFingerprint()
      const meshId = `${this.config.agentName}@${this.config.hubName}#${fingerprint}`

      this.state = {
        meshPass,
        meshId,
        connected: false,
        authenticated: false,
        lastActivity: new Date().toISOString(),
        messageCount: 0,
        errors: 0
      }

      const context: ResponseContext = {
        agentName: this.config.agentName,
        capabilities: this.config.capabilities,
        hubName: this.config.hubName,
        meshId
      }

      this.responder = new MessageResponder(this.config, context)

      this.log('info', 'MeshPass generated', {
        meshId,
        publicKey: meshPass.getPublicKeyHex().slice(0, 16) + '...',
        fingerprint
      })

      // Connect to The Gate
      await this.connect()

      // Setup health monitoring
      this.startHealthMonitoring()

      // Setup graceful shutdown
      this.setupGracefulShutdown()

      this.log('info', 'Meshlet ready', { meshId })

    } catch (error) {
      this.log('error', 'Failed to start Meshlet', { error: this.formatError(error) })
      process.exit(1)
    }
  }

  private async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.log('info', 'Connecting to The Gate...', { gateUrl: this.config.gateUrl })

      this.ws = new WebSocket(this.config.gateUrl)
      
      this.ws.on('open', () => {
        this.state.connected = true
        this.state.lastActivity = new Date().toISOString()
        this.reconnectAttempts = 0
        this.log('info', 'Connected to The Gate')
        resolve()
      })

      this.ws.on('message', (data) => {
        this.handleMessage(data)
      })

      this.ws.on('close', (code, reason) => {
        this.state.connected = false
        this.state.authenticated = false
        this.log('info', 'Disconnected from The Gate', { 
          code, 
          reason: reason?.toString() 
        })
        
        if (code !== 1000) { // Not a normal closure
          this.scheduleReconnect()
        }
      })

      this.ws.on('error', (error) => {
        this.state.errors++
        this.log('error', 'WebSocket error', { error: this.formatError(error) })
        reject(error)
      })
    })
  }

  private async handleMessage(data: any): Promise<void> {
    try {
      this.state.lastActivity = new Date().toISOString()
      this.state.messageCount++

      const rawMessage = data.toString()
      let message: any

      try {
        message = JSON.parse(rawMessage)
      } catch {
        this.log('warn', 'Received invalid JSON message')
        return
      }

      this.log('debug', 'Received message', { type: message.type, requestId: message.requestId })

      // Handle gate-specific messages
      switch (message.type) {
        case 'gate_info':
          this.log('info', 'Gate info received', { 
            hub: message.hub, 
            message: message.message 
          })
          setTimeout(() => this.authenticate(), 100)
          break

        case 'auth_success':
          this.state.authenticated = true
          this.log('info', 'Authentication successful', {
            meshId: message.meshId,
            hub: message.hub,
            sessionId: message.sessionId
          })
          break

        case 'auth_error':
          this.log('error', 'Authentication failed', { error: message.error })
          this.state.errors++
          break

        default:
          // Handle mesh protocol messages
          await this.handleMeshMessage(message as MeshMessage)
      }

    } catch (error) {
      this.state.errors++
      this.log('error', 'Error handling message', { error: this.formatError(error) })
    }
  }

  private async handleMeshMessage(message: MeshMessage): Promise<void> {
    const response = await this.responder.handleMessage(message)
    
    if (response) {
      this.sendMessage(response)
      this.log('debug', 'Sent response', { 
        type: response.type, 
        requestId: response.requestId 
      })
    }
  }

  private async authenticate(): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.log('warn', 'Cannot authenticate: not connected')
      return
    }

    try {
      this.log('debug', 'Sending authentication...')
      
      const authMsg = await createAuthMessage(this.state.meshPass, this.state.meshId)
      
      const message = {
        type: 'mesh_auth',
        meshId: authMsg.meshId,
        nonce: authMsg.nonce,
        timestamp: authMsg.timestamp,
        signature: authMsg.signature
      }

      this.ws.send(JSON.stringify(message))
    } catch (error) {
      this.log('error', 'Authentication error', { error: this.formatError(error) })
    }
  }

  private sendMessage(message: MeshMessage): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.log('warn', 'Cannot send message: not connected')
      return false
    }

    if (!this.state.authenticated) {
      this.log('warn', 'Cannot send message: not authenticated')
      return false
    }

    try {
      const enrichedMessage = {
        ...message,
        timestamp: message.timestamp ?? new Date().toISOString(),
        sender: this.state.meshId
      }
      
      this.ws.send(JSON.stringify(enrichedMessage))
      return true
    } catch (error) {
      this.log('error', 'Error sending message', { error: this.formatError(error) })
      return false
    }
  }

  private scheduleReconnect(): void {
    if (this.config.maxReconnectAttempts > 0 && 
        this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      this.log('error', 'Max reconnect attempts reached, giving up')
      process.exit(1)
      return
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
    }

    this.reconnectAttempts++
    // Exponential backoff with jitter
    const baseDelay = this.config.reconnectDelayMs
    const backoffMultiplier = Math.min(Math.pow(2, this.reconnectAttempts - 1), 8)
    const jitter = Math.random() * 1000
    const delay = baseDelay * backoffMultiplier + jitter

    this.log('info', 'Scheduling reconnect', {
      attempt: this.reconnectAttempts,
      delay: Math.round(delay)
    })

    this.reconnectTimer = setTimeout(async () => {
      try {
        await this.connect()
      } catch (error) {
        this.log('error', 'Reconnect failed', { error: this.formatError(error) })
        // Will schedule another reconnect via close handler
      }
    }, delay)
  }

  private startHealthMonitoring(): void {
    this.healthInterval = setInterval(() => {
      const status = {
        meshId: this.state.meshId,
        connected: this.state.connected,
        authenticated: this.state.authenticated,
        uptime: process.uptime(),
        messageCount: this.state.messageCount,
        errors: this.state.errors,
        memoryUsage: process.memoryUsage(),
        lastActivity: this.state.lastActivity
      }

      this.log('debug', 'Health status', status)
    }, 60000) // Every minute
  }

  private setupGracefulShutdown(): void {
    const shutdown = (signal: string) => {
      this.log('info', `Received ${signal}, shutting down gracefully...`)
      
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer)
      }
      
      if (this.healthInterval) {
        clearInterval(this.healthInterval)
      }
      
      if (this.ws) {
        this.ws.close(1000, 'Meshlet shutdown')
      }
      
      this.log('info', 'Shutdown complete')
      process.exit(0)
    }

    process.on('SIGTERM', () => shutdown('SIGTERM'))
    process.on('SIGINT', () => shutdown('SIGINT'))
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, data?: any): void {
    const levels = { debug: 0, info: 1, warn: 2, error: 3 }
    const configLevel = levels[this.config.logLevel]
    const msgLevel = levels[level]

    if (msgLevel < configLevel) {
      return
    }

    const timestamp = new Date().toISOString()
    const logEntry = {
      timestamp,
      level,
      message,
      agent: this.config.agentName,
      ...data
    }

    console.log(JSON.stringify(logEntry))
  }

  private formatError(error: unknown): any {
    if (error instanceof Error) {
      return {
        name: error.name,
        message: error.message,
        stack: error.stack
      }
    }
    return error
  }
}

// Main execution
async function main(): Promise<void> {
  try {
    const config = loadConfig()
    const meshlet = new Meshlet(config)
    await meshlet.start()
  } catch (error) {
    console.error(JSON.stringify({
      timestamp: new Date().toISOString(),
      level: 'error',
      message: 'Failed to start Meshlet',
      error: error instanceof Error ? error.message : String(error)
    }))
    process.exit(1)
  }
}

// Handle unhandled rejections
process.on('unhandledRejection', (reason) => {
  console.error(JSON.stringify({
    timestamp: new Date().toISOString(),
    level: 'error',
    message: 'Unhandled promise rejection',
    reason: String(reason)
  }))
  process.exit(1)
})

if (import.meta.url === `file://${process.argv[1]}`) {
  main()
}