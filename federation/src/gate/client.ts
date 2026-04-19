/**
 * Gate Client: Connect to The Gate (public WebSocket gateway) using MeshPass authentication.
 */

import { EventEmitter } from 'events'
import WebSocket from 'ws'
import { MeshPass, createAuthMessage } from '../identity/index.js'
import { parseMessage } from '../protocol/validation.js'
import type { FederationMessage } from '../protocol/messages.js'

export interface GateClientConfig {
  /** Gate server URL (e.g., 'wss://gate.manifold.org:8765') */
  gateUrl: string
  
  /** MeshPass for authentication */
  meshPass: MeshPass
  
  /** MeshID (name@hub) */
  meshId: string
  
  /** Reconnection settings */
  reconnectDelay?: number
  maxReconnectAttempts?: number
  
  /** Debug logging */
  debug?: boolean
}

export interface GateClientEvents {
  'connected': () => void
  'disconnected': () => void
  'authenticated': (session: { meshId: string; hub: string; sessionId: string }) => void
  'auth_error': (error: string) => void
  'message': (message: FederationMessage) => void
  'error': (error: Error) => void
}

type EventName = keyof GateClientEvents

export class GateClient extends EventEmitter {
  private readonly config: Required<GateClientConfig>
  private ws: WebSocket | null = null
  private authenticated = false
  private reconnectCount = 0
  private reconnectTimer: NodeJS.Timeout | null = null
  private sessionInfo: { meshId: string; hub: string; sessionId: string } | null = null

  constructor(config: GateClientConfig) {
    super()
    this.config = {
      reconnectDelay: 5000,
      maxReconnectAttempts: Infinity,
      debug: false,
      ...config
    }
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  async connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return // Already connected
    }

    this._log('Connecting to The Gate...', { url: this.config.gateUrl, meshId: this.config.meshId })

    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.config.gateUrl)
      
      ws.on('open', () => {
        this.ws = ws
        this.reconnectCount = 0
        this.authenticated = false
        this._log('Connected to The Gate')
        this.emit('connected')
        resolve()
      })
      
      ws.on('error', (error) => {
        this._log('Connection error', error)
        reject(error)
      })
      
      ws.on('close', (code, reason) => {
        this._log('Connection closed', { code, reason: reason?.toString() })
        this.ws = null
        this.authenticated = false
        this.sessionInfo = null
        this.emit('disconnected')
        
        // Auto-reconnect if not intentional
        if (code !== 1000 && this.reconnectCount < this.config.maxReconnectAttempts) {
          this._scheduleReconnect()
        }
      })
      
      ws.on('message', (data) => {
        this._handleMessage(data)
      })
    })
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect')
    }
  }

  // ── Authentication ──────────────────────────────────────────────────────────

  async authenticate(): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('Not connected to gate')
    }

    if (this.authenticated) {
      return // Already authenticated
    }

    this._log('Authenticating with MeshPass...', { meshId: this.config.meshId })

    // Create signed auth message
    const authMsg = await createAuthMessage(this.config.meshPass, this.config.meshId)
    
    const message = {
      type: 'mesh_auth',
      meshId: authMsg.meshId,
      nonce: authMsg.nonce,
      timestamp: authMsg.timestamp,
      signature: authMsg.signature
    }

    this.ws.send(JSON.stringify(message))
  }

  // ── Messaging ──────────────────────────────────────────────────────────────

  send(message: Partial<FederationMessage>): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this._log('Cannot send: not connected')
      return false
    }

    if (!this.authenticated) {
      this._log('Cannot send: not authenticated')
      return false
    }

    try {
      const enrichedMessage = {
        ...message,
        timestamp: message.timestamp ?? new Date().toISOString(),
        sender: this.config.meshId
      }
      
      this.ws.send(JSON.stringify(enrichedMessage))
      return true
    } catch (error) {
      this._log('Send error', error)
      return false
    }
  }

  // ── Status ──────────────────────────────────────────────────────────────────

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  isAuthenticated(): boolean {
    return this.authenticated
  }

  getSessionInfo() {
    return this.sessionInfo
  }

  // ── Event helpers ──────────────────────────────────────────────────────────

  emit<K extends EventName>(event: K, ...args: Parameters<GateClientEvents[K]>): boolean {
    return super.emit(event, ...args)
  }

  on<K extends EventName>(event: K, listener: GateClientEvents[K]): this {
    return super.on(event, listener)
  }

  // ── Private ────────────────────────────────────────────────────────────────

  private _handleMessage(data: any): void {
    try {
      const message = JSON.parse(data.toString())
      
      switch (message.type) {
        case 'gate_info':
          this._log('Gate info received', { hub: message.hub, message: message.message })
          // Auto-authenticate after receiving gate info
          setTimeout(() => this.authenticate(), 100)
          break
          
        case 'auth_success':
          this.authenticated = true
          this.sessionInfo = {
            meshId: message.meshId,
            hub: message.hub,
            sessionId: message.sessionId
          }
          this._log('Authentication successful', this.sessionInfo)
          this.emit('authenticated', this.sessionInfo)
          break
          
        case 'auth_error':
          this._log('Authentication failed', { error: message.error })
          this.emit('auth_error', message.error)
          break
          
        default:
          // Regular federation message
          const federationMessage = parseMessage(data.toString())
          if (federationMessage) {
            this.emit('message', federationMessage)
          }
          break
      }
    } catch (error) {
      this._log('Message parse error', error)
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
    }
    
    this.reconnectCount++
    const delay = this.config.reconnectDelay * Math.min(this.reconnectCount, 5) // Exponential backoff, max 5x
    
    this._log('Scheduling reconnect', { attempt: this.reconnectCount, delay })
    
    this.reconnectTimer = setTimeout(async () => {
      try {
        await this.connect()
      } catch (error) {
        this._log('Reconnect failed', error)
        // Will trigger another reconnect via the close handler
      }
    }, delay)
  }

  private _log(message: string, data?: any): void {
    if (this.config.debug) {
      const timestamp = new Date().toISOString()
      if (data) {
        console.log(`[${timestamp}] [GateClient:${this.config.meshId}] ${message}`, data)
      } else {
        console.log(`[${timestamp}] [GateClient:${this.config.meshId}] ${message}`)
      }
    }
  }
}