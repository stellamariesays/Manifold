/**
 * Managed WebSocket connection with automatic reconnection.
 * Works in Node.js (ws library) and in the browser (native WebSocket).
 */

import { EventEmitter } from 'events'

type WS = import('ws').WebSocket

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'closed'

export interface ManagedSocketOptions {
  url: string
  reconnectDelay?: number
  maxReconnectAttempts?: number
  debug?: boolean
}

export class ManagedSocket extends EventEmitter {
  private readonly url: string
  private readonly reconnectDelay: number
  private readonly maxReconnectAttempts: number
  private readonly debug: boolean

  private ws: WS | WebSocket | null = null
  private state: ConnectionState = 'disconnected'
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private closed = false

  constructor(options: ManagedSocketOptions) {
    super()
    this.url = options.url
    this.reconnectDelay = options.reconnectDelay ?? 5000
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? Infinity
    this.debug = options.debug ?? false
  }

  get connectionState(): ConnectionState {
    return this.state
  }

  get isConnected(): boolean {
    return this.state === 'connected'
  }

  connect(): void {
    if (this.closed) return
    if (this.state === 'connecting' || this.state === 'connected') return
    this._connect()
  }

  private _connect(): void {
    this.state = 'connecting'
    this.log(`Connecting to ${this.url}`)

    try {
      // Use native WebSocket if available (browser), otherwise ws module
      if (typeof WebSocket !== 'undefined') {
        this.ws = new WebSocket(this.url)
      } else {
        // Node.js — dynamic import handled by caller injecting the class
        // We support being passed a WebSocket constructor via _wsClass
        const WsClass = (this as unknown as { _wsClass?: new (url: string) => WebSocket })._wsClass
        if (!WsClass) throw new Error('No WebSocket implementation available')
        this.ws = new WsClass(this.url) as unknown as WS
      }
    } catch (err) {
      this.log(`Failed to create WebSocket: ${err}`)
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.state = 'connected'
      this.reconnectAttempts = 0
      this.log('Connected')
      this.emit('open')
    }

    this.ws.onmessage = (event: { data: unknown }) => {
      this.emit('message', event.data)
    }

    this.ws.onclose = (event: { code: number; reason: string | Buffer }) => {
      const reason = Buffer.isBuffer(event.reason) ? event.reason.toString() : event.reason
      this.log(`Closed: ${event.code} ${reason}`)
      this.ws = null

      if (!this.closed) {
        this.state = 'disconnected'
        this.emit('close', event.code, reason)
        this._scheduleReconnect()
      }
    }

    this.ws.onerror = (event: unknown) => {
      this.log(`Error: ${event}`)
      this.emit('error', new Error(String(event)))
    }
  }

  private _scheduleReconnect(): void {
    if (this.closed) return
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.log('Max reconnect attempts reached')
      this.state = 'closed'
      this.emit('exhausted')
      return
    }

    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.min(this.reconnectAttempts, 5)
    this.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`)

    this.reconnectTimer = setTimeout(() => {
      if (!this.closed) this._connect()
    }, delay)
  }

  send(data: string): boolean {
    if (!this.ws || this.state !== 'connected') return false
    try {
      this.ws.send(data)
      return true
    } catch {
      return false
    }
  }

  close(): void {
    this.closed = true
    this.state = 'closed'
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      try {
        this.ws.close()
      } catch {
        // ignore
      }
      this.ws = null
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[ManagedSocket:${this.url}] ${msg}`)
  }
}

/**
 * Create a ManagedSocket wired to the ws Node.js library.
 */
export async function createNodeSocket(
  url: string,
  options?: Omit<ManagedSocketOptions, 'url'>,
): Promise<ManagedSocket> {
  const { WebSocket: WsClass } = await import('ws')
  const sock = new ManagedSocket({ url, ...options })
  ;(sock as unknown as { _wsClass: new (url: string) => WebSocket })._wsClass =
    WsClass as unknown as new (url: string) => WebSocket
  return sock
}
