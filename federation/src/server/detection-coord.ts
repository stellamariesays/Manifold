// Detection Coordination Handler — processes detection messages and manages the ledger.
// Sits on top of the federation server, listens for detection_claim/verify/challenge/outcome.

import type { DetectionLedger } from './detection-ledger.js'
import type { CapabilityIndex } from './capability-index.js'
import type { PeerRegistry } from './peer-registry.js'
import type {
  DetectionClaim,
  DetectionVerify,
  DetectionChallenge,
  DetectionOutcome,
  DetectionClaimMessage,
  DetectionVerifyMessage,
  DetectionChallengeMessage,
  DetectionOutcomeMessage,
} from '../protocol/messages.js'

export interface DetectionCoordOptions {
  hub: string
  ledger: DetectionLedger
  capIndex?: CapabilityIndex
  peerRegistry?: PeerRegistry
  /** Enable domain-based routing (only send to subscribers). Default true. */
  domainRoutingEnabled?: boolean
  debug?: boolean
}

type DetectionMessage = DetectionClaimMessage | DetectionVerifyMessage | DetectionChallengeMessage | DetectionOutcomeMessage

export class DetectionCoord {
  private readonly hub: string
  private readonly _ledger: DetectionLedger
  private readonly capIndex?: CapabilityIndex
  private readonly peerRegistry?: PeerRegistry
  private readonly domainRoutingEnabled: boolean
  private readonly debug: boolean
  private broadcastFn: ((msg: object) => void) | null = null

  // Subscribers — agents that want to hear about detection events in specific domains
  private domainSubscribers = new Map<string, Set<string>>() // domain → Set<agent@hub>

  // Track which hubs have agents subscribed to which domains
  private domainHubIndex = new Map<string, Set<string>>() // domain → Set<hub>

  constructor(options: DetectionCoordOptions) {
    this._ledger = options.ledger
    this.hub = options.hub
    this.capIndex = options.capIndex
    this.peerRegistry = options.peerRegistry
    this.domainRoutingEnabled = options.domainRoutingEnabled ?? true
    this.debug = options.debug ?? false
  }

  /** Public read-only access to ledger for REST API queries */
  get ledger(): DetectionLedger {
    return this._ledger
  }

  setBroadcast(fn: (msg: object) => void): void {
    this.broadcastFn = fn
  }

  // ── Message handling ────────────────────────────────────────────────────

  handleMessage(msg: DetectionMessage): void {
    switch (msg.type) {
      case 'detection_claim':
        this.handleClaim(msg.claim)
        break
      case 'detection_verify':
        this.handleVerify(msg.verification)
        break
      case 'detection_challenge':
        this.handleChallenge(msg.challenge)
        break
      case 'detection_outcome':
        this.handleOutcome(msg.outcome)
        break
    }
  }

  private handleClaim(claim: DetectionClaim): void {
    this.log(`Claim: [${claim.domain}] ${claim.summary} (confidence: ${claim.confidence}) from ${claim.source}`)

    // Store in ledger
    const entry = this._ledger.addClaim(claim)
    if (!entry) return

    // Domain-based routing: only send to hubs that have subscribers for this domain
    if (this.domainRoutingEnabled && this.domainHubIndex.has(claim.domain)) {
      this.routeToDomain(claim.domain, {
        type: 'detection_claim',
        claim,
      })
    } else {
      // Fallback: broadcast to all
      this.broadcast({
        type: 'detection_claim',
        claim,
      })
    }

    // Notify local subscribers
    this.notifySubscribers(claim.domain, claim)
  }

  private handleVerify(verification: DetectionVerify): void {
    this.log(`Verify: ${verification.verifier} ${verification.agrees ? 'confirms' : 'disputes'} claim ${verification.claim_id}`)

    const entry = this._ledger.addVerification(verification)
    if (!entry) {
      this.log(`  ⚠️ Claim ${verification.claim_id} not found`)
      return
    }

    this.broadcast({
      type: 'detection_verify',
      verification,
    })
  }

  private handleChallenge(challenge: DetectionChallenge): void {
    this.log(`Challenge: ${challenge.challenger} challenges claim ${challenge.claim_id}: ${challenge.reason}`)

    const entry = this._ledger.addChallenge(challenge)
    if (!entry) {
      this.log(`  ⚠️ Claim ${challenge.claim_id} not found`)
      return
    }

    this.broadcast({
      type: 'detection_challenge',
      challenge,
    })
  }

  private handleOutcome(outcome: DetectionOutcome): void {
    this.log(`Outcome: Claim ${outcome.claim_id} → ${outcome.outcome} (by ${outcome.resolved_by})`)

    const entry = this._ledger.resolveOutcome(outcome)
    if (!entry) {
      this.log(`  ⚠️ Claim ${outcome.claim_id} not found`)
      return
    }

    this.broadcast({
      type: 'detection_outcome',
      outcome,
    })
  }

  // ── Subscription management ─────────────────────────────────────────────

  subscribe(domain: string, agent: string): void {
    if (!this.domainSubscribers.has(domain)) {
      this.domainSubscribers.set(domain, new Set())
    }
    this.domainSubscribers.get(domain)!.add(agent)
    this.log(`Subscribed ${agent} to domain: ${domain}`)

    // Update hub index
    if (!this.domainHubIndex.has(domain)) {
      this.domainHubIndex.set(domain, new Set())
    }
    // Extract hub from agent (format: "name@hub" or just "name")
    const hub = agent.includes('@') ? agent.split('@').pop()! : this.hub
    this.domainHubIndex.get(domain)!.add(hub)
  }

  unsubscribe(domain: string, agent: string): void {
    this.domainSubscribers.get(domain)?.delete(agent)
  }

  /** Get hubs subscribed to a domain */
  getHubsForDomain(domain: string): string[] {
    return Array.from(this.domainHubIndex.get(domain) ?? [])
  }

  /** Get stats about domain routing */
  getDomainRoutingStats(): { domains: number; totalSubscriptions: number; domainBreakdown: Record<string, number> } {
    let totalSubs = 0
    const breakdown: Record<string, number> = {}
    for (const [domain, subs] of this.domainSubscribers) {
      totalSubs += subs.size
      breakdown[domain] = subs.size
    }
    return { domains: this.domainSubscribers.size, totalSubscriptions: totalSubs, domainBreakdown: breakdown }
  }

  private notifySubscribers(domain: string, claim: DetectionClaim): void {
    // Subscribers are notified via broadcast — they filter locally
  }

  // ── REST API helpers ────────────────────────────────────────────────────

  getOpenClaims(domain?: string) {
    if (domain) return this._ledger.getClaimsByDomain(domain).filter(e => !e.outcome)
    return this._ledger.getOpenClaims()
  }

  getTrustScores() {
    return this._ledger.getTrustScores()
  }

  getStats() {
    return this._ledger.getStats()
  }

  getClaim(id: string) {
    return this._ledger.getClaim(id)
  }

  // ── Internals ───────────────────────────────────────────────────────────

  private broadcast(msg: object): void {
    if (this.broadcastFn) {
      this.broadcastFn(msg)
    }
  }

  /**
   * Route a message only to hubs that have agents subscribed to the given domain.
   */
  private routeToDomain(domain: string, msg: object): void {
    const targetHubs = this.domainHubIndex.get(domain)
    if (!targetHubs || targetHubs.size === 0) {
      // No subscribers — broadcast as fallback
      this.broadcast(msg)
      return
    }

    // Send to specific hubs via peer registry
    if (this.peerRegistry) {
      const msgStr = JSON.stringify(msg)
      let sent = false
      for (const hub of targetHubs) {
        if (hub === this.hub) continue // local subscribers handled separately
        if (this.peerRegistry.sendTo(hub, msgStr)) {
          sent = true
        }
      }
      // If we couldn't reach any specific hub, broadcast
      if (!sent && targetHubs.size > 1) {
        this.broadcast(msg)
      }
    } else {
      this.broadcast(msg)
    }
  }

  private log(msg: string): void {
    if (this.debug) {
      console.log(`[DetectionCoord:${this.hub}] ${msg}`)
    }
  }
}
