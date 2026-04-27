import type { MeshSyncMessage, MeshDeltaMessage, MeshDeltaAckMessage } from '../protocol/messages.js'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'
import { DeltaSync } from './delta-sync.js'

export interface MeshSyncOptions {
  hub: string
  /** Sync interval in milliseconds. Default 15000. */
  intervalMs?: number
  /** Enable delta sync (versioned). Default true. */
  deltaSyncEnabled?: boolean
  /** Callback to broadcast to local clients (non-federation WebSocket connections) */
  localBroadcast?: (data: string) => void
  debug?: boolean
}

/**
 * Periodically synchronizes local mesh state to all peers.
 *
 * When deltaSyncEnabled:
 * - Tracks a monotonic version counter
 * - Sends only changed agents/darkCircles since each peer's last ACK
 * - Falls back to full snapshot for new peers or large gaps
 * - Peers ACK with mesh_delta_ack to update their version tracking
 *
 * Otherwise, broadcasts full mesh_sync every interval (legacy mode).
 */
export class MeshSync {
  private readonly hub: string
  private readonly intervalMs: number
  private readonly deltaSyncEnabled: boolean
  private readonly debug: boolean
  private readonly localBroadcast?: (data: string) => void

  private timer: ReturnType<typeof setInterval> | null = null
  private capIndex!: CapabilityIndex
  private peerRegistry!: PeerRegistry
  private deltaSync!: DeltaSync

  constructor(options: MeshSyncOptions) {
    this.hub = options.hub
    this.intervalMs = options.intervalMs ?? 15_000
    this.deltaSyncEnabled = options.deltaSyncEnabled ?? true
    this.debug = options.debug ?? false
    this.localBroadcast = options.localBroadcast
  }

  start(capIndex: CapabilityIndex, peerRegistry: PeerRegistry): void {
    this.capIndex = capIndex
    this.peerRegistry = peerRegistry

    if (this.deltaSyncEnabled) {
      this.deltaSync = new DeltaSync({ hub: this.hub, debug: this.debug })
      this._recordSnapshot()
    }

    // Immediate first sync
    this.sync()

    this.timer = setInterval(() => {
      this.sync()
    }, this.intervalMs)
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
  }

  /**
   * Called when local agents change (register/unregister/update).
   * Bumps version and records the delta.
   */
  onLocalChange(): void {
    if (!this.deltaSyncEnabled) return
    this._recordSnapshot()
  }

  /**
   * Called when a new peer connects — registers them for delta tracking.
   * Uses hub name as the identifier.
   */
  onPeerConnect(hub: string): void {
    if (!this.deltaSyncEnabled) return
    this.deltaSync.addPeer(hub)
  }

  /**
   * Called when a peer disconnects — removes from delta tracking.
   */
  onPeerDisconnect(hub: string): void {
    if (!this.deltaSyncEnabled) return
    this.deltaSync.removePeer(hub)
  }

  /**
   * Handle a mesh_delta_ack from a peer — updates version tracking.
   */
  handleDeltaAck(msg: MeshDeltaAckMessage): void {
    if (!this.deltaSyncEnabled) return
    // Find peer by hub name — ACK comes from the remote hub about our version
    const peers = this.peerRegistry.getPeers()
    const peer = peers.find(p => p.hub === msg.hub)
    if (peer) {
      this.deltaSync.ackPeer(peer.address, msg.version)
    }
  }

  /**
   * Build and send sync messages to all peers.
   * In delta mode: sends per-peer deltas (or full if needed).
   * In legacy mode: broadcasts full mesh_sync.
   */
  sync(): void {
    if (this.deltaSyncEnabled) {
      this._syncDelta()
    } else {
      this._syncFull()
    }
  }

  // ── Delta sync ─────────────────────────────────────────────────────────────

  private _syncDelta(): void {
    const peers = this.peerRegistry.getPeers()
    if (peers.length === 0 && !this.localBroadcast) return

    let fullCount = 0
    let deltaCount = 0
    let skippedCount = 0

    // Always send full snapshot to local clients (they don't track versions)
    if (this.localBroadcast) {
      const snapshot = this.deltaSync.getFullSnapshot()
      const fullMsg: MeshSyncMessage = {
        type: 'mesh_sync',
        hub: this.hub,
        version: this.deltaSync.getVersion(),
        agents: snapshot.agents,
        darkCircles: snapshot.darkCircles.map(dc => dc.circle),
        timestamp: new Date().toISOString(),
      }
      this.localBroadcast(JSON.stringify(fullMsg))
    }

    if (peers.length === 0) return

    for (const peer of peers) {
      // Use hub name as the peer identifier for delta tracking
      const delta = this.deltaSync.getDeltaForPeer(peer.hub)

      if (delta === null) {
        skippedCount++
        continue
      }

      if (delta.type === 'full') {
        // Send full snapshot with version
        const msg: MeshSyncMessage = {
          type: 'mesh_sync',
          hub: this.hub,
          version: delta.version,
          agents: delta.agents,
          darkCircles: delta.darkCircles.map(dc => dc.circle),
          timestamp: new Date().toISOString(),
        }
        this.peerRegistry.sendToPeer(peer.hub, JSON.stringify(msg))
        fullCount++
      } else {
        // Send delta only
        const msg: MeshDeltaMessage = {
          type: 'mesh_delta',
          hub: this.hub,
          fromVersion: delta.fromVersion,
          toVersion: delta.toVersion,
          agentDeltas: delta.agentDeltas,
          darkCircleDeltas: delta.darkCircleDeltas,
          timestamp: new Date().toISOString(),
        }
        this.peerRegistry.sendToPeer(peer.hub, JSON.stringify(msg))
        deltaCount++
      }
    }

    this.log(`Delta sync: ${fullCount} full, ${deltaCount} delta, ${skippedCount} skipped to ${peers.length} peers`)
  }

  // ── Legacy full sync ───────────────────────────────────────────────────────

  private _syncFull(): void {
    const localAgents = this.capIndex.getLocalAgents()
    const darkCircles = this.capIndex.getDarkCircles()

    const msg: MeshSyncMessage = {
      type: 'mesh_sync',
      hub: this.hub,
      agents: localAgents.map(a => ({
        name: a.name,
        hub: a.hub,
        capabilities: a.capabilities,
        seams: a.seams,
        pressure: a.pressure,
        lastSeen: a.lastSeen,
      })),
      darkCircles: darkCircles.map(dc => ({
        name: dc.name,
        pressure: dc.pressure,
        hub: this.hub,
      })),
      timestamp: new Date().toISOString(),
    }

    const data = JSON.stringify(msg)
    this.peerRegistry.broadcast(data)
    this.log(`Full sync broadcast: ${localAgents.length} agents to ${this.peerRegistry.getPeers().length} peers`)
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  private _recordSnapshot(): void {
    const agents = this.capIndex.getLocalAgents().map(a => ({
      name: a.name,
      hub: a.hub,
      capabilities: a.capabilities,
      seams: a.seams,
      pressure: a.pressure,
      lastSeen: a.lastSeen,
    }))

    const darkCircles = this.capIndex.getDarkCircles().map(dc => ({
      circle: { name: dc.name, pressure: dc.pressure, hub: this.hub } as any,
      hub: this.hub,
    }))

    this.deltaSync.recordSnapshot(agents, darkCircles)
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[MeshSync:${this.hub}] ${msg}`)
  }
}
