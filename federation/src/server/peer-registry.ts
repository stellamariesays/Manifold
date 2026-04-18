import { EventEmitter } from 'events'
import WebSocket from 'ws'
import { v4 as uuid } from 'uuid'
import { parseMessage } from '../protocol/validation.js'
import { PeerSampler } from './peer-sampler.js'
import type { FederationMessage, PeerAnnounceMessage } from '../protocol/messages.js'
import type { PeerInfo } from '../shared/types.js'
import type { ShuffleRequest, ShuffleResponse } from './peer-sampler.js'

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
  /** Enable GossipSub peer sampling. Default true. */
  gossipEnabled?: boolean
  /** Max peers to maintain connections to (GossipSub view size). Default 8 */
  gossipViewSize?: number
  /** Gossip shuffle interval in ms. Default 10000 */
  gossipShuffleIntervalMs?: number
  /** Seed addresses for bootstrapping */
  gossipSeeds?: string[]
  debug?: boolean
}

export class PeerRegistry extends EventEmitter {
  private readonly selfHub: string
  private readonly selfAddress: string
  private readonly selfPubkey: string | undefined
  private readonly reconnectDelay: number
  private readonly gossipEnabled: boolean
  private readonly debug: boolean

  /** Outbound peers (we dial these) — keyed by address */
  private outbound: Map<string, PeerEntry> = new Map()

  /** Inbound peers (they dialed us) — keyed by address or hub name */
  private inbound: Map<string, PeerEntry> = new Map()

  /** O(1) hub-name index — Maps hub name → PeerEntry */
  private byHub: Map<string, PeerEntry> = new Map()

  /** GossipSub peer sampler */
  readonly sampler: PeerSampler

  constructor(options: PeerRegistryOptions) {
    super()
    this.selfHub = options.selfHub
    this.selfAddress = options.selfAddress
    this.selfPubkey = options.selfPubkey
    this.reconnectDelay = options.reconnectDelay ?? 10000
    this.gossipEnabled = options.gossipEnabled ?? true
    this.debug = options.debug ?? false

    this.sampler = new PeerSampler({
      selfHub: this.selfHub,
      selfAddress: this.selfAddress,
      viewSize: options.gossipViewSize ?? 8,
      shuffleIntervalMs: options.gossipShuffleIntervalMs ?? 10_000,
      seeds: options.gossipSeeds,
      debug: this.debug,
    })

    // Wire sampler events
    this.sampler.on('shuffle:send', (target, request: ShuffleRequest) => {
      this._sendShuffleRequest(target, request)
    })

    this.sampler.on('view:added', (desc) => {
      // Connect to new view member if not already connected
      this._ensureConnection(desc)
    })

    this.sampler.on('view:evicted', (desc) => {
      this.log(`View evicted: ${desc.hub}`)
      // Don't disconnect immediately — they might be in inbound map
      // Only disconnect if purely outbound and not needed
    })
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────────

  /**
   * Start the peer registry and gossip sampler.
   */
  start(): void {
    if (this.gossipEnabled) {
      this.sampler.start()
    }
  }

  // ── Peer management ─────────────────────────────────────────────────────────

  /**
   * Add a static peer (outbound connection we maintain).
   * In gossip mode, this adds to the sampler as a seed.
   * In non-gossip mode, dials immediately.
   */
  addPeer(address: string): void {
    if (this.gossipEnabled) {
      this.sampler.addSeed(address)
      // Trigger immediate connection to seed
      const desc = { hub: address, address, age: 0 }
      this._ensureConnection(desc)
    } else {
      this._addAndDialPeer(address)
    }
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

    this.inbound.set(remoteAddress, entry)

    ws.on('message', (data) => {
      const raw = typeof data === 'string' ? data : data.toString()
      // Check for shuffle messages first
      if (this._tryHandleShuffle(raw, entry)) return

      const msg = parseMessage(raw)
      if (!msg) return

      if (msg.type === 'peer_announce') {
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
   * In gossip mode, sends to view peers only (bounded fanout).
   */
  broadcast(data: string): void {
    for (const entry of this._allConnected()) {
      this._safeSend(entry.ws!, data)
    }
  }

  /**
   * Send a message to a specific peer by hub name. O(1).
   */
  sendTo(hubName: string, data: string): boolean {
    const entry = this.byHub.get(hubName)
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
    const entry = this.byHub.get(hub)
    if (entry) entry.agentCount = count
  }

  stop(): void {
    this.sampler.stop()
    for (const entry of this.outbound.values()) {
      if (entry.reconnectTimer) clearTimeout(entry.reconnectTimer)
      entry.ws?.close()
    }
    for (const entry of this.inbound.values()) {
      entry.ws?.close()
    }
    this.outbound.clear()
    this.inbound.clear()
    this.byHub.clear()
  }

  // ── Gossip: Shuffle Message Handling ────────────────────────────────────────

  /**
   * Try to parse and handle a gossip shuffle message.
   * Returns true if handled (not a federation protocol message).
   */
  private _tryHandleShuffle(raw: string, entry: PeerEntry): boolean {
    try {
      const obj = JSON.parse(raw)
      if (obj.type === 'shuffle_request') {
        const request = obj as ShuffleRequest
        const response = this.sampler.handleShuffleRequest(request)
        if (entry.ws && entry.ws.readyState === WebSocket.OPEN) {
          entry.ws.send(JSON.stringify(response))
        }
        // Also add sender to known descriptors
        for (const desc of request.samples) {
          this.sampler.addDescriptor(desc)
        }
        return true
      }
      if (obj.type === 'shuffle_response') {
        const response = obj as ShuffleResponse
        this.sampler.handleShuffleResponse(response)
        return true
      }
    } catch {
      // Not JSON or not a shuffle message — fall through to normal handling
    }
    return false
  }

  /**
   * Send a shuffle request to a target peer via WebSocket.
   */
  private _sendShuffleRequest(target: { hub: string; address: string }, request: ShuffleRequest): void {
    // Find the connection for this target
    const entry = this.byHub.get(target.hub)
    if (entry?.ws && entry.ws.readyState === WebSocket.OPEN) {
      entry.ws.send(JSON.stringify(request))
    } else {
      // Not connected to this view member — will be resolved on next cycle
      this.log(`Cannot shuffle with ${target.hub}: not connected`)
    }
  }

  // ── Connection Management ───────────────────────────────────────────────────

  /**
   * Ensure we have an outbound connection to a peer descriptor.
   */
  private _ensureConnection(desc: { hub: string; address: string }): void {
    // Already connected?
    if (this.byHub.has(desc.hub)) {
      const existing = this.byHub.get(desc.hub)!
      if (existing.ws && existing.ws.readyState === WebSocket.OPEN) return
    }

    // Already have outbound to this address?
    if (this.outbound.has(desc.address)) return

    this._addAndDialPeer(desc.address)
  }

  // ── Private: Original Peer Logic ────────────────────────────────────────────

  private _addAndDialPeer(address: string): void {
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

      // Check for shuffle messages
      if (this._tryHandleShuffle(raw, entry)) return

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
      this.byHub.delete(entry.hub)
      this.emit('peer:disconnect', { hub: entry.hub })

      // Only reconnect if this peer is still in our gossip view
      if (this.gossipEnabled) {
        const inView = this.sampler.getView().some(d => d.hub === entry.hub || d.address === entry.address)
        if (inView) this._scheduleOutboundReconnect(entry)
        else this.outbound.delete(entry.address)
      } else {
        this._scheduleOutboundReconnect(entry)
      }
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

    // Update hub-name index
    if (oldHub !== msg.hub) this.byHub.delete(oldHub)
    this.byHub.set(msg.hub, entry)

    // Add to gossip sampler
    if (this.gossipEnabled) {
      this.sampler.addDescriptor({
        hub: msg.hub,
        address: msg.address || entry.address,
        age: 0,
        pubkey: msg.pubkey,
      })
    }

    this.log(`Peer identified as hub: ${msg.hub}`)
  }

  private _handleInboundClose(entry: PeerEntry): void {
    this.inbound.delete(entry.hub)
    this.inbound.delete(entry.address)
    this.byHub.delete(entry.hub)
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
