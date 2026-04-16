import { EventEmitter } from 'events'
import WebSocket from 'ws'
import { v4 as uuid } from 'uuid'
import { parseMessage } from '../protocol/validation.js'
import type { FederationMessage, PeerAnnounceMessage } from '../protocol/messages.js'
import type { PeerInfo } from '../shared/types.js'

export interface PeerEntry extends PeerInfo {
  ws: WebSocket | null
  reconnectTimer: ReturnType<typeof setTimeout> | null
  reconnectAttempts: number
}

export interface PeerRegistryOptions {
  selfHub: string
  selfAddress: string
  selfPubkey?: string
  reconnectDelay?: number
  debug?: boolean
}

export class PeerRegistry extends EventEmitter {
  private readonly selfHub: string
  private readonly selfAddress: string
  private readonly selfPubkey: string | undefined
  private readonly reconnectDelay: number
  private readonly debug: boolean

  /** Outbound peers (we dial these) */
  private outbound: Map<string, PeerEntry> = new Map()

  /** Inbound peers (they dialed us) keyed by hub name */
  private inbound: Map<string, PeerEntry> = new Map()

  constructor(options: PeerRegistryOptions) {
    super()
    this.selfHub = options.selfHub
    this.selfAddress = options.selfAddress
    this.selfPubkey = options.selfPubkey
    this.reconnectDelay = options.reconnectDelay ?? 10000
    this.debug = options.debug ?? false
  }

  // ── Peer management ─────────────────────────────────────────────────────────

  /**
   * Add a static peer (outbound connection we maintain).
   */
  addPeer(address: string): void {
    if (this.outbound.has(address)) return
    const entry: PeerEntry = {
      hub: address, // placeholder until peer announces itself
      address,
      connectedAt: '',
      lastSeen: new Date().toISOString(),
      agentCount: 0,
      ws: null,
      reconnectTimer: null,
      reconnectAttempts: 0,
    }
    this.outbound.set(address, entry)
    this._dialPeer(entry)
  }

  /**
   * Register an inbound peer (they connected to us).
   */
  registerInbound(ws: WebSocket, remoteAddress: string): void {
    const entry: PeerEntry = {
      hub: remoteAddress,
      address: remoteAddress,
      connectedAt: new Date().toISOString(),
      lastSeen: new Date().toISOString(),
      agentCount: 0,
      ws,
      reconnectTimer: null,
      reconnectAttempts: 0,
    }

    // Use remoteAddress as temporary key until they announce their hub name
    this.inbound.set(remoteAddress, entry)

    ws.on('message', (data) => {
      const raw = typeof data === 'string' ? data : data.toString()
      const msg = parseMessage(raw)
      if (!msg) return

      if (msg.type === 'peer_announce') {
        // Promote to named entry
        this._handlePeerAnnounce(entry, msg)
      }

      this.emit('message', msg, entry)
    })

    ws.on('close', () => {
      this._handleInboundClose(entry)
    })

    ws.on('error', (err) => {
      this.log(`Inbound peer error (${entry.hub}): ${err.message}`)
    })

    // Send our announcement
    this._sendAnnounce(ws)
    this.emit('peer:connect', this._toPeerInfo(entry))
  }

  /**
   * Send a message to all connected peers.
   */
  broadcast(data: string): void {
    for (const entry of this._allConnected()) {
      this._safeSend(entry.ws!, data)
    }
  }

  /**
   * Send a message to a specific peer by hub name.
   */
  sendTo(hubName: string, data: string): boolean {
    const entry = this._findByHub(hubName)
    if (!entry?.ws) return false
    return this._safeSend(entry.ws, data)
  }

  /**
   * Get all connected peer infos.
   */
  getPeers(): PeerInfo[] {
    return Array.from(this._allConnected()).map(e => this._toPeerInfo(e))
  }

  /**
   * Update agent count for a peer.
   */
  updateAgentCount(hub: string, count: number): void {
    const entry = this._findByHub(hub)
    if (entry) entry.agentCount = count
  }

  stop(): void {
    for (const entry of this.outbound.values()) {
      if (entry.reconnectTimer) clearTimeout(entry.reconnectTimer)
      entry.ws?.close()
    }
    for (const entry of this.inbound.values()) {
      entry.ws?.close()
    }
    this.outbound.clear()
    this.inbound.clear()
  }

  // ── Private ─────────────────────────────────────────────────────────────────

  private _dialPeer(entry: PeerEntry): void {
    this.log(`Dialing ${entry.address}`)

    let ws: WebSocket
    try {
      ws = new WebSocket(entry.address)
    } catch (err) {
      this.log(`Failed to create WS for ${entry.address}: ${err}`)
      this._scheduleOutboundReconnect(entry)
      return
    }

    entry.ws = ws

    ws.on('open', () => {
      this.log(`Connected to peer ${entry.address}`)
      entry.connectedAt = new Date().toISOString()
      entry.lastSeen = new Date().toISOString()
      entry.reconnectAttempts = 0
      this._sendAnnounce(ws)
      this.emit('peer:connect', this._toPeerInfo(entry))
    })

    ws.on('message', (data) => {
      entry.lastSeen = new Date().toISOString()
      const raw = typeof data === 'string' ? data : data.toString()
      const msg = parseMessage(raw)
      if (!msg) return

      if (msg.type === 'peer_announce') {
        this._handlePeerAnnounce(entry, msg)
      }

      this.emit('message', msg, entry)
    })

    ws.on('close', () => {
      this.log(`Peer disconnected: ${entry.hub}`)
      entry.ws = null
      this.emit('peer:disconnect', { hub: entry.hub })
      this._scheduleOutboundReconnect(entry)
    })

    ws.on('error', (err) => {
      this.log(`Peer error (${entry.address}): ${err.message}`)
    })
  }

  private _scheduleOutboundReconnect(entry: PeerEntry): void {
    entry.reconnectAttempts++
    const delay = this.reconnectDelay * Math.min(entry.reconnectAttempts, 6)
    this.log(`Reconnecting to ${entry.address} in ${delay}ms`)
    entry.reconnectTimer = setTimeout(() => {
      entry.reconnectTimer = null
      this._dialPeer(entry)
    }, delay)
  }

  private _handlePeerAnnounce(entry: PeerEntry, msg: PeerAnnounceMessage): void {
    const oldHub = entry.hub

    // Update entry with announced hub name
    entry.hub = msg.hub
    entry.pubkey = msg.pubkey
    entry.lastSeen = new Date().toISOString()

    // Re-key inbound map if needed
    if (this.inbound.has(oldHub) && oldHub !== msg.hub) {
      this.inbound.delete(oldHub)
      this.inbound.set(msg.hub, entry)
    }

    // Dedup: if we already have an outbound connection to this hub, close the inbound duplicate
    for (const [addr, outbound] of this.outbound.entries()) {
      if (outbound.hub === msg.hub && outbound.ws && outbound.ws !== entry.ws) {
        this.log(`Duplicate inbound for ${msg.hub}, closing (outbound at ${addr} preferred)`)
        // Close inbound, keep outbound
        entry.ws?.close()
        this.inbound.delete(msg.hub)
        return
      }
    }

    this.log(`Peer identified as hub: ${msg.hub}`)
  }

  private _handleInboundClose(entry: PeerEntry): void {
    this.inbound.delete(entry.hub)
    this.inbound.delete(entry.address)
    entry.ws = null
    this.emit('peer:disconnect', { hub: entry.hub })
  }

  private _sendAnnounce(ws: WebSocket): void {
    const msg: PeerAnnounceMessage = {
      type: 'peer_announce',
      hub: this.selfHub,
      address: this.selfAddress,
      pubkey: this.selfPubkey,
      timestamp: new Date().toISOString(),
      requestId: uuid(),
    }
    this._safeSend(ws, JSON.stringify(msg))
  }

  private _safeSend(ws: WebSocket, data: string): boolean {
    if (ws.readyState !== WebSocket.OPEN) return false
    try {
      ws.send(data)
      return true
    } catch {
      return false
    }
  }

  private _findByHub(hub: string): PeerEntry | undefined {
    for (const entry of [...this.outbound.values(), ...this.inbound.values()]) {
      if (entry.hub === hub) return entry
    }
    return undefined
  }

  private *_allConnected(): IterableIterator<PeerEntry> {
    for (const entry of [...this.outbound.values(), ...this.inbound.values()]) {
      if (entry.ws && entry.ws.readyState === WebSocket.OPEN) yield entry
    }
  }

  private _toPeerInfo(entry: PeerEntry): PeerInfo {
    return {
      hub: entry.hub,
      address: entry.address,
      pubkey: entry.pubkey,
      connectedAt: entry.connectedAt,
      lastSeen: entry.lastSeen,
      agentCount: entry.agentCount,
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[PeerRegistry:${this.selfHub}] ${msg}`)
  }
}
