import type { AgentInfo, DarkCircle } from '../protocol/messages.js'
import type { CapabilityIndex } from './capability-index.js'

// ── Types ──────────────────────────────────────────────────────────────────────

/** Tracks the per-hub version that each peer has acknowledged. */
export interface PeerVersionMap {
  /** peer address → last version they've seen from us */
  [address: string]: number
}

/** A single agent change in a delta. */
export interface AgentDelta {
  op: 'upsert' | 'remove'
  agent: AgentInfo
}

/** Change to a dark circle entry. */
export interface DarkCircleDelta {
  op: 'upsert' | 'remove'
  circle: DarkCircle
  /** Hub that owns this dark circle */
  hub: string
}

// ── DeltaSync ──────────────────────────────────────────────────────────────────

/**
 * Maintains versioned snapshots of local agent state and computes
 * deltas for each peer based on what version they've seen.
 *
 * Design:
 * - Monotonically increasing version counter per hub
 * - On any local agent change, bump version and record the delta
 * - When syncing to a peer, send only changes since their last seen version
 * - Peers ACK with the version they processed → we update PeerVersionMap
 * - Fallback: if peer version is 0 or gap is too large, send full snapshot
 */
export class DeltaSync {
  private hub: string
  private debug: boolean

  /** Current version counter — bumps on every local state change */
  private version = 0

  /** Ordered log of (version → set of changes). Trimmed after all peers ACK. */
  private changelog: Array<{
    version: number
    timestamp: string
    agentDeltas: AgentDelta[]
    darkCircleDeltas: DarkCircleDelta[]
  }> = []

  /** Per-peer tracking: what version each peer has seen */
  private peerVersions: PeerVersionMap = {}

  /** Full snapshot cache — rebuilt on every change */
  private lastSnapshot: {
    agents: AgentInfo[]
    darkCircles: Array<{ circle: DarkCircle; hub: string }>
  } = { agents: [], darkCircles: [] }

  /** Max changelog entries before forcing full sync */
  private readonly maxChangelogSize = 100

  constructor(opts: { hub: string; debug?: boolean }) {
    this.hub = opts.hub
    this.debug = opts.debug ?? false
  }

  // ── Called by MeshSync on local changes ────────────────────────────────────

  /**
   * Record that the full local state has changed.
   * Call this AFTER CapabilityIndex has been updated.
   */
  recordSnapshot(agents: AgentInfo[], darkCircles: Array<{ circle: DarkCircle; hub: string }>): void {
    this.version++
    const now = new Date().toISOString()

    // Compute deltas by diffing against last snapshot
    const agentDeltas = this._diffAgents(this.lastSnapshot.agents, agents)
    const dcDeltas = this._diffDarkCircles(this.lastSnapshot.darkCircles, darkCircles)

    this.changelog.push({
      version: this.version,
      timestamp: now,
      agentDeltas,
      darkCircleDeltas: dcDeltas,
    })

    this.lastSnapshot = { agents: [...agents], darkCircles: [...darkCircles] }
    this._trimChangelog()
    this.log(`Snapshot v${this.version}: ${agentDeltas.length} agent deltas, ${dcDeltas.length} DC deltas`)
  }

  /**
   * Get a delta (or full snapshot) for a specific peer.
   * Returns null if nothing to send (peer is up to date).
   */
  getDeltaForPeer(
    peerAddress: string,
  ):
    | { type: 'full'; version: number; agents: AgentInfo[]; darkCircles: Array<{ circle: DarkCircle; hub: string }> }
    | { type: 'delta'; fromVersion: number; toVersion: number; agentDeltas: AgentDelta[]; darkCircleDeltas: DarkCircleDelta[] }
    | null {
    const peerVersion = this.peerVersions[peerAddress] ?? 0

    // Peer is up to date
    if (peerVersion >= this.version) return null

    // No changelog entries for the gap, or gap too large — send full
    const oldestInLog = this.changelog.length > 0 ? this.changelog[0].version : this.version + 1
    if (peerVersion === 0 || peerVersion < oldestInLog - 1 || this.changelog.length === 0) {
      return {
        type: 'full',
        version: this.version,
        agents: this.lastSnapshot.agents,
        darkCircles: this.lastSnapshot.darkCircles,
      }
    }

    // Accumulate deltas from peerVersion+1 → current
    const agentDeltas: AgentDelta[] = []
    const darkCircleDeltas: DarkCircleDelta[] = []

    for (const entry of this.changelog) {
      if (entry.version > peerVersion) {
        agentDeltas.push(...entry.agentDeltas)
        darkCircleDeltas.push(...entry.darkCircleDeltas)
      }
    }

    // Dedupe: later ops for same agent override earlier ones
    const dedupedAgents = this._dedupeAgentDeltas(agentDeltas)
    const dedupedDCs = this._dedupeDarkCircleDeltas(darkCircleDeltas)

    if (dedupedAgents.length === 0 && dedupedDCs.length === 0) return null

    return {
      type: 'delta',
      fromVersion: peerVersion,
      toVersion: this.version,
      agentDeltas: dedupedAgents,
      darkCircleDeltas: dedupedDCs,
    }
  }

  /**
   * Peer ACKed a version. Update tracking.
   */
  ackPeer(peerAddress: string, version: number): void {
    this.peerVersions[peerAddress] = version
    this._trimChangelog()
    this.log(`Peer ${peerAddress} ACKed v${version}`)
  }

  /**
   * Register a new peer (starts at version 0 → will get full sync).
   */
  addPeer(address: string): void {
    if (!(address in this.peerVersions)) {
      this.peerVersions[address] = 0
    }
  }

  /**
   * Remove a peer from tracking.
   */
  removePeer(address: string): void {
    delete this.peerVersions[address]
  }

  /** Get the current full snapshot (for local clients, new peers, etc.) */
  getFullSnapshot(): { agents: AgentInfo[]; darkCircles: Array<{ circle: DarkCircle; hub: string }> } {
    return {
      agents: [...this.lastSnapshot.agents],
      darkCircles: [...this.lastSnapshot.darkCircles],
    }
  }

  /** Current version */
  getVersion(): number {
    return this.version
  }

  /** Get all tracked peers and their versions */
  getPeerVersions(): PeerVersionMap {
    return { ...this.peerVersions }
  }

  // ── Internals ───────────────────────────────────────────────────────────────

  private _diffAgents(old: AgentInfo[], current: AgentInfo[]): AgentDelta[] {
    const oldMap = new Map(old.map(a => [`${a.name}@${a.hub}`, a]))
    const curMap = new Map(current.map(a => [`${a.name}@${a.hub}`, a]))
    const deltas: AgentDelta[] = []

    // Upserts: new or changed
    for (const agent of current) {
      const key = `${agent.name}@${agent.hub}`
      const oldAgent = oldMap.get(key)
      if (!oldAgent || !this._agentEqual(oldAgent, agent)) {
        deltas.push({ op: 'upsert', agent })
      }
    }

    // Removes
    for (const agent of old) {
      const key = `${agent.name}@${agent.hub}`
      if (!curMap.has(key)) {
        deltas.push({ op: 'remove', agent })
      }
    }

    return deltas
  }

  private _diffDarkCircles(
    old: Array<{ circle: DarkCircle; hub: string }>,
    current: Array<{ circle: DarkCircle; hub: string }>,
  ): DarkCircleDelta[] {
    const oldMap = new Map(old.map(dc => [`${dc.circle.name}@${dc.hub}`, dc]))
    const curMap = new Map(current.map(dc => [`${dc.circle.name}@${dc.hub}`, dc]))
    const deltas: DarkCircleDelta[] = []

    for (const { circle, hub } of current) {
      const key = `${circle.name}@${hub}`
      const oldEntry = oldMap.get(key)
      if (!oldEntry || oldEntry.circle.pressure !== circle.pressure) {
        deltas.push({ op: 'upsert', circle, hub })
      }
    }

    for (const { circle, hub } of old) {
      const key = `${circle.name}@${hub}`
      if (!curMap.has(key)) {
        deltas.push({ op: 'remove', circle, hub })
      }
    }

    return deltas
  }

  private _dedupeAgentDeltas(deltas: AgentDelta[]): AgentDelta[] {
    // Later operations for the same agent key win
    const map = new Map<string, AgentDelta>()
    for (const d of deltas) {
      map.set(`${d.agent.name}@${d.agent.hub}`, d)
    }
    return [...map.values()]
  }

  private _dedupeDarkCircleDeltas(deltas: DarkCircleDelta[]): DarkCircleDelta[] {
    const map = new Map<string, DarkCircleDelta>()
    for (const d of deltas) {
      map.set(`${d.circle.name}@${d.hub}`, d)
    }
    return [...map.values()]
  }

  private _agentEqual(a: AgentInfo, b: AgentInfo): boolean {
    return (
      a.name === b.name &&
      a.hub === b.hub &&
      a.pressure === b.pressure &&
      JSON.stringify(a.capabilities) === JSON.stringify(b.capabilities) &&
      JSON.stringify(a.seams) === JSON.stringify(b.seams)
    )
  }

  /** Trim changelog entries that ALL peers have ACKed */
  private _trimChangelog(): void {
    if (this.changelog.length === 0) return

    const minPeerVersion = Object.values(this.peerVersions).length > 0
      ? Math.min(...Object.values(this.peerVersions))
      : 0

    // Keep entries that at least one peer hasn't seen yet
    const cutoff = minPeerVersion
    while (this.changelog.length > this.maxChangelogSize) {
      this.changelog.shift()
    }
    // Also trim entries all peers have seen
    while (this.changelog.length > 0 && this.changelog[0].version <= cutoff) {
      this.changelog.shift()
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[DeltaSync:${this.hub}] ${msg}`)
  }
}
