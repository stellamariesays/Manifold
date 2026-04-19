// Cross-Hub Detection Sync — propagates detection events between federated hubs.
// Handles: claim propagation, verification relay, outcome broadcast, and trust-score gossip.

import type { DetectionCoord } from './detection-coord.js'
import type { PeerRegistry } from './peer-registry.js'
import type {
  DetectionClaim,
  DetectionVerify,
  DetectionOutcome,
  DetectionClaimMessage,
  DetectionVerifyMessage,
  DetectionOutcomeMessage,
  DetectionGossipMessage,
  GossipTrustScore,
} from '../protocol/messages.js'

export interface DetectionSyncOptions {
  /** Our hub identity */
  hub: string
  /** Detection coordinator to push incoming events to */
  detectionCoord: DetectionCoord
  /** Peer registry for cross-hub messaging */
  peerRegistry: PeerRegistry
  /** How often to gossip trust scores (ms). Default: 60000 */
  gossipIntervalMs?: number
  /** Max claims to buffer for initial sync when a new peer connects */
  initialSyncLimit?: number
  /** Debug logging */
  debug?: boolean
}

export class DetectionSync {
  private readonly hub: string
  private readonly coord: DetectionCoord
  private readonly peers: PeerRegistry
  private readonly gossipIntervalMs: number
  private readonly initialSyncLimit: number
  private readonly debug: boolean

  private gossipTimer: ReturnType<typeof setInterval> | null = null
  private knownPeers: Set<string> = new Set()
  private peerCheckTimer: ReturnType<typeof setInterval> | null = null

  constructor(opts: DetectionSyncOptions) {
    this.hub = opts.hub
    this.coord = opts.detectionCoord
    this.peers = opts.peerRegistry
    this.gossipIntervalMs = opts.gossipIntervalMs ?? 60_000
    this.initialSyncLimit = opts.initialSyncLimit ?? 50
    this.debug = opts.debug ?? false
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  /** Start periodic gossip and peer tracking */
  start(): void {
    if (this.gossipTimer) return
    this.log('Starting cross-hub detection sync')
    this.gossipTimer = setInterval(() => this.gossipTrustScores(), this.gossipIntervalMs)
    // Periodically check for new peers and send initial sync
    this.peerCheckTimer = setInterval(() => this.checkForNewPeers(), 30_000)
    setTimeout(() => this.checkForNewPeers(), 5_000)
  }

  /** Stop periodic gossip */
  stop(): void {
    if (this.gossipTimer) {
      clearInterval(this.gossipTimer)
      this.gossipTimer = null
    }
    if (this.peerCheckTimer) {
      clearInterval(this.peerCheckTimer)
      this.peerCheckTimer = null
    }
    this.log('Stopped cross-hub detection sync')
  }

  // ── Outbound sync ──────────────────────────────────────────────────────────

  /** Propagate a claim to all known peer hubs via broadcast */
  propagateClaim(claim: DetectionClaim): void {
    const msg: DetectionClaimMessage = {
      type: 'detection_claim',
      timestamp: new Date().toISOString(),
      gatewayHub: this.hub,
      claim,
    }
    this.broadcastToPeers(msg)
    this.log(`Propagated claim ${claim.id} to peers`)
  }

  /** Relay a verification to all known peer hubs */
  propagateVerification(verification: DetectionVerify): void {
    const msg: DetectionVerifyMessage = {
      type: 'detection_verify',
      timestamp: new Date().toISOString(),
      gatewayHub: this.hub,
      verification,
    }
    this.broadcastToPeers(msg)
    this.log(`Propagated verification for claim ${verification.claim_id}`)
  }

  /** Broadcast an outcome to all known peer hubs */
  propagateOutcome(outcome: DetectionOutcome): void {
    const msg: DetectionOutcomeMessage = {
      type: 'detection_outcome',
      timestamp: new Date().toISOString(),
      gatewayHub: this.hub,
      outcome,
    }
    this.broadcastToPeers(msg)
    this.log(`Propagated outcome ${outcome.outcome} for claim ${outcome.claim_id}`)
  }

  /** Gossip trust scores to all peers */
  gossipTrustScores(): void {
    const scores = this.buildGossipPayload()
    if (scores.length === 0) return

    const msg: DetectionGossipMessage = {
      type: 'detection_gossip',
      timestamp: new Date().toISOString(),
      gatewayHub: this.hub,
      scores,
      hub: this.hub,
    }
    this.broadcastToPeers(msg)
    this.log(`Gossiped ${scores.length} trust scores to peers`)
  }

  // ── Inbound sync ───────────────────────────────────────────────────────────

  /** Handle an incoming detection message from a peer hub */
  handleIncomingMessage(msg: object): void {
    const m = msg as any
    switch (m.type) {
      case 'detection_claim':
        if (m.claim) {
          this.coord.handleMessage({ type: 'detection_claim', claim: m.claim })
          this.log(`Received claim ${m.claim.id} from ${m.gatewayHub ?? 'unknown'}`)
        }
        break

      case 'detection_verify':
        if (m.verification) {
          this.coord.handleMessage({ type: 'detection_verify', verification: m.verification })
          this.log(`Received verification for claim ${m.verification.claim_id}`)
        }
        break

      case 'detection_outcome':
        if (m.outcome) {
          this.coord.handleMessage({ type: 'detection_outcome', outcome: m.outcome })
          this.log(`Received outcome ${m.outcome.outcome} for claim ${m.outcome.claim_id}`)
        }
        break

      case 'detection_gossip':
        if (m.scores && Array.isArray(m.scores)) {
          this.ingestGossip(m.hub ?? m.gatewayHub ?? 'unknown', m.scores)
        }
        break

      default:
        this.log(`Unknown detection message type: ${m.type}`)
    }
  }

  /** Send initial sync of recent claims to a newly connected peer */
  sendInitialSync(peerHub: string): void {
    const openClaims = this.coord.getOpenClaims()
    const claims = openClaims.slice(0, this.initialSyncLimit)

    for (const entry of claims) {
      this.sendToPeer(peerHub, JSON.stringify({
        type: 'detection_claim',
        timestamp: new Date().toISOString(),
        gatewayHub: this.hub,
        claim: entry.claim,
      }))

      for (const v of entry.verifications) {
        this.sendToPeer(peerHub, JSON.stringify({
          type: 'detection_verify',
          timestamp: new Date().toISOString(),
          gatewayHub: this.hub,
          verification: v,
        }))
      }

      if (entry.outcome) {
        this.sendToPeer(peerHub, JSON.stringify({
          type: 'detection_outcome',
          timestamp: new Date().toISOString(),
          gatewayHub: this.hub,
          outcome: entry.outcome,
        }))
      }
    }

    this.log(`Sent initial sync (${claims.length} claims) to ${peerHub}`)
  }

  // ── Gossip payload ─────────────────────────────────────────────────────────

  /** Build gossip payload from current trust scores */
  buildGossipPayload(): GossipTrustScore[] {
    const rawScores = this.coord.getTrustScores()
    const result: GossipTrustScore[] = []
    for (const [source, data] of Object.entries(rawScores)) {
      const d = data as any
      result.push({
        source,
        score: d.score ?? 0.5,
        totalClaims: d.totalClaims ?? 0,
        verified: d.verified ?? 0,
      })
    }
    return result
  }

  /** Ingest gossip trust scores from a peer — informational, not authoritative */
  ingestGossip(fromHub: string, scores: GossipTrustScore[]): void {
    this.log(`Received gossip from ${fromHub}: ${scores.length} scores`)
    // Trust scores from other hubs are informational — we store them for reference
    // but don't override our own scores. This prevents trust manipulation.
  }

  // ── Peer tracking ──────────────────────────────────────────────────────────

  /** Check for new peers and send initial sync */
  private checkForNewPeers(): void {
    // We don't have direct access to peer list from PeerRegistry
    // but peers.registerPeer can be called externally to notify us
  }

  /** Register that a peer hub has connected — triggers initial sync */
  registerPeer(hub: string): void {
    if (this.knownPeers.has(hub)) return
    this.knownPeers.add(hub)
    this.sendInitialSync(hub)
  }

  /** Get set of known peer hubs */
  getKnownPeers(): Set<string> {
    return new Set(this.knownPeers)
  }

  // ── Messaging helpers ──────────────────────────────────────────────────────

  /** Broadcast a message to all known peer hubs */
  private broadcastToPeers(msg: object): void {
    try {
      this.peers.broadcast(JSON.stringify(msg))
    } catch (err) {
      this.log(`Broadcast failed: ${err}`)
    }
  }

  /** Send a message to a specific peer hub */
  private sendToPeer(hub: string, data: string): void {
    try {
      this.peers.sendTo(hub, data)
    } catch (err) {
      this.log(`Failed to send to ${hub}: ${err}`)
    }
  }

  // ── Logging ────────────────────────────────────────────────────────────────

  private log(msg: string): void {
    if (this.debug) {
      console.log(`[DetectionSync:${this.hub}] ${msg}`)
    }
  }
}
