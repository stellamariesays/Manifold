import type { MeshSyncMessage } from '../protocol/messages.js'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'

export interface MeshSyncOptions {
  hub: string
  /** Sync interval in milliseconds. Default 15000. */
  intervalMs?: number
  debug?: boolean
}

/**
 * Periodically broadcasts the local mesh state to all peers.
 * Also triggers immediate sync on significant events.
 */
export class MeshSync {
  private readonly hub: string
  private readonly intervalMs: number
  private readonly debug: boolean

  private timer: ReturnType<typeof setInterval> | null = null
  private capIndex!: CapabilityIndex
  private peerRegistry!: PeerRegistry

  constructor(options: MeshSyncOptions) {
    this.hub = options.hub
    this.intervalMs = options.intervalMs ?? 15_000
    this.debug = options.debug ?? false
  }

  start(capIndex: CapabilityIndex, peerRegistry: PeerRegistry): void {
    this.capIndex = capIndex
    this.peerRegistry = peerRegistry

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
   * Build and broadcast a mesh_sync message to all peers.
   */
  sync(): void {
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
    this.log(`Sync broadcast: ${localAgents.length} agents to ${this.peerRegistry.getPeers().length} peers`)
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[MeshSync:${this.hub}] ${msg}`)
  }
}
