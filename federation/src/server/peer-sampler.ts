/**
 * Peer Sampler — Cyclon-style random peer sampling for GossipSub.
 *
 * Maintains a partial view of the network (K peers out of N total).
 * Periodically shuffles its view with a random neighbor to ensure
 * all nodes remain reachable through short paths.
 *
 * Based on: Voulgaris, Gavidia, Steen (2005) — "CYCLON: An Inexpensive
 * Protocol for Peer Sampling and Maintenance in Large-Scale Distributed Systems"
 *
 * Properties:
 * - Each node maintains K random peers (default 8)
 * - Shuffle interval: every 10s, pick random peer, exchange descriptors
 * - Guarantees O(log N) path length between any two nodes
 * - Self-healing: dead peers get evicted during shuffles
 */

import { EventEmitter } from 'events'
import type { PeerInfo } from '../shared/types.js'

// ── Types ────────────────────────────────────────────────────────────────────

export interface PeerDescriptor {
  /** Hub name (unique identifier) */
  hub: string
  /** WebSocket address, e.g. ws://host:port */
  address: string
  /** When we last heard from this peer */
  age: number          // incremented each shuffle cycle
  /** Public key (optional) */
  pubkey?: string
}

export interface ShuffleRequest {
  type: 'shuffle_request'
  sender: string       // our hub name
  samples: PeerDescriptor[]  // our outgoing samples
  requestId: string
}

export interface ShuffleResponse {
  type: 'shuffle_response'
  samples: PeerDescriptor[]  // their outgoing samples
  requestId: string
}

export type ShuffleMessage = ShuffleRequest | ShuffleResponse

export interface PeerSamplerOptions {
  /** Our hub name */
  selfHub: string
  /** Our address */
  selfAddress: string
  /** View size — max peers to track. Default 8 */
  viewSize?: number
  /** How many descriptors to exchange per shuffle. Default 3 */
  shuffleSize?: number
  /** Shuffle interval in ms. Default 10000 */
  shuffleIntervalMs?: number
  /** Max age before evicting a descriptor. Default 50 cycles */
  maxAge?: number
  /** Known seed addresses to bootstrap from */
  seeds?: string[]
  debug?: boolean
}

export class PeerSampler extends EventEmitter {
  private readonly selfHub: string
  private readonly selfAddress: string
  private readonly viewSize: number
  private readonly shuffleSize: number
  private readonly shuffleIntervalMs: number
  private readonly maxAge: number
  private readonly debug: boolean

  /** Partial view — our K random peers */
  private view: PeerDescriptor[] = []

  /** All known peer addresses for bootstrapping (beyond view) */
  private knownAddresses: Map<string, PeerDescriptor> = new Map()

  private shuffleTimer: ReturnType<typeof setInterval> | null = null
  private cycleCount = 0

  constructor(options: PeerSamplerOptions) {
    super()
    this.selfHub = options.selfHub
    this.selfAddress = options.selfAddress
    this.viewSize = options.viewSize ?? 8
    this.shuffleSize = options.shuffleSize ?? 3
    this.shuffleIntervalMs = options.shuffleIntervalMs ?? 10_000
    this.maxAge = options.maxAge ?? 50
    this.debug = options.debug ?? false

    // Bootstrap with seeds
    if (options.seeds) {
      for (const addr of options.seeds) {
        this.addSeed(addr)
      }
    }
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  start(): void {
    if (this.shuffleTimer) return

    this.shuffleTimer = setInterval(() => {
      this._doShuffle()
    }, this.shuffleIntervalMs)

    this.log(`Started: viewSize=${this.viewSize}, shuffleInterval=${this.shuffleIntervalMs}ms`)
  }

  stop(): void {
    if (this.shuffleTimer) {
      clearInterval(this.shuffleTimer)
      this.shuffleTimer = null
    }
  }

  // ── View Management ────────────────────────────────────────────────────────

  /**
   * Add a seed address for bootstrapping.
   */
  addSeed(address: string): void {
    // Don't add ourselves
    if (address === this.selfAddress) return
    const descriptor: PeerDescriptor = {
      hub: address,  // placeholder until announced
      address,
      age: 0,
    }
    this.knownAddresses.set(address, descriptor)
    this._tryInsertToView(descriptor)
  }

  /**
   * Add a peer descriptor (e.g., from peer_announce or shuffle).
   * Returns true if the view changed.
   */
  addDescriptor(desc: PeerDescriptor): boolean {
    // Don't add ourselves (check both hub name and address)
    if (desc.hub === this.selfHub || desc.address === this.selfAddress) return false

    this.knownAddresses.set(desc.address, desc)
    return this._tryInsertToView(desc)
  }

  /**
   * Remove a peer from view and known set.
   */
  removePeer(hub: string): void {
    this.view = this.view.filter(d => d.hub !== hub)
    for (const [addr, d] of this.knownAddresses) {
      if (d.hub === hub) this.knownAddresses.delete(addr)
    }
    this.emit('peer:evicted', hub)
  }

  /**
   * Get current view — the peers we should maintain connections to.
   */
  getView(): PeerDescriptor[] {
    return [...this.view]
  }

  /**
   * Get addresses of peers in our view that we should connect to.
   */
  getViewAddresses(): string[] {
    return this.view.map(d => d.address)
  }

  /**
   * Get all known peer descriptors (view + cache).
   */
  getAllKnown(): PeerDescriptor[] {
    return Array.from(this.knownAddresses.values())
  }

  /**
   * Get count of known peers (not just view).
   */
  get knownCount(): number {
    return this.knownAddresses.size
  }

  /**
   * Get count of peers in active view.
   */
  get viewCount(): number {
    return this.view.length
  }

  // ── Shuffle Protocol ───────────────────────────────────────────────────────

  /**
   * Handle an incoming shuffle request from a peer.
   * Exchange our samples for theirs.
   */
  handleShuffleRequest(msg: ShuffleRequest): ShuffleResponse {
    // Pick random samples from our view (excluding the sender)
    const candidates = this.view.filter(d => d.hub !== msg.sender)
    const samples = this._pickRandom(candidates, this.shuffleSize)

    // Add their samples to our view
    for (const desc of msg.samples) {
      this.addDescriptor(desc)
    }

    this.log(`Shuffle from ${msg.sender}: received ${msg.samples.length}, sent ${samples.length}`)

    return {
      type: 'shuffle_response',
      samples,
      requestId: msg.requestId,
    }
  }

  /**
   * Handle a shuffle response (result of our outgoing shuffle).
   */
  handleShuffleResponse(msg: ShuffleResponse): void {
    for (const desc of msg.samples) {
      this.addDescriptor(desc)
    }
    this.log(`Shuffle response: received ${msg.samples.length} descriptors`)
  }

  // ── Internal ───────────────────────────────────────────────────────────────

  /**
   * Try to insert a descriptor into the view.
   * If view is full, replace the oldest entry.
   */
  private _tryInsertToView(desc: PeerDescriptor): boolean {
    // Already in view?
    if (this.view.some(d => d.hub === desc.hub)) {
      // Update age if newer
      const existing = this.view.find(d => d.hub === desc.hub)!
      if (desc.age < existing.age) existing.age = desc.age
      return false
    }

    if (this.view.length < this.viewSize) {
      this.view.push({ ...desc })
      this.emit('view:added', desc)
      return true
    }

    // View full — replace oldest entry
    const oldest = this.view.reduce((a, b) => a.age > b.age ? a : b)
    if (desc.age < oldest.age) {
      const idx = this.view.indexOf(oldest)
      const evicted = this.view[idx]
      this.view[idx] = { ...desc }
      this.emit('view:evicted', evicted)
      this.emit('view:added', desc)
      return true
    }

    return false
  }

  /**
   * Perform one shuffle cycle.
   * Pick random peer from view, send shuffle request.
   */
  private _doShuffle(): void {
    this.cycleCount++

    // Increment age of all view entries
    for (const desc of this.view) {
      desc.age++
    }

    // Pick oldest peer to shuffle with (Cyclon strategy — increases randomness)
    if (this.view.length === 0) return

    const target = this.view.reduce((a, b) => a.age > b.age ? a : b)

    // Pick random samples to send (excluding target)
    const candidates = this.view.filter(d => d.hub !== target.hub)
    const samples = this._pickRandom(candidates, this.shuffleSize)

    // Add our own descriptor
    const selfDesc: PeerDescriptor = {
      hub: this.selfHub,
      address: this.selfAddress,
      age: 0,
    }

    const request: ShuffleRequest = {
      type: 'shuffle_request',
      sender: this.selfHub,
      samples: [selfDesc, ...samples],
      requestId: `shuffle-${this.selfHub}-${this.cycleCount}`,
    }

    this.emit('shuffle:send', target, request)
    this.log(`Shuffle #${this.cycleCount}: sending ${request.samples.length} descriptors to ${target.hub}`)

    // Age out very old entries
    this.view = this.view.filter(d => d.age <= this.maxAge)

    // Fill empty slots from known cache
    while (this.view.length < this.viewSize) {
      const candidates = Array.from(this.knownAddresses.values())
        .filter(d => d.hub !== this.selfHub && !this.view.some(v => v.hub === d.hub))
      if (candidates.length === 0) break
      const pick = candidates[Math.floor(Math.random() * candidates.length)]
      this.view.push({ ...pick, age: 0 })
    }
  }

  /**
   * Pick N random items from an array.
   */
  private _pickRandom<T>(arr: T[], n: number): T[] {
    const shuffled = [...arr].sort(() => Math.random() - 0.5)
    return shuffled.slice(0, n)
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[PeerSampler:${this.selfHub}] ${msg}`)
  }
}
