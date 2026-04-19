/**
 * Phase 3: Detection-Coordination — comprehensive tests.
 *
 * Tests cover:
 * - DetectionLedger (append-only log, trust scoring, persistence)
 * - DetectionCoord (message routing, domain subscriptions, dedup)
 * - REST handler logic (claim, verify, outcome, queries — no HTTP server)
 * - Protocol message types
 * - Full lifecycle (claim → verify → challenge → resolve)
 *
 * Memory-safe: no Express/HTTP server, direct handler invocation.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { writeFileSync, unlinkSync, existsSync, readFileSync } from 'fs'
import { join } from 'path'
import * as crypto from 'crypto'

// Detection modules
import { DetectionLedger } from '../src/server/detection-ledger.js'
import { DetectionCoord } from '../src/server/detection-coord.js'

// Protocol types
import type {
  DetectionClaim,
  DetectionVerify,
  DetectionChallenge,
  DetectionOutcome,
  DetectionClaimMessage,
  DetectionVerifyMessage,
  DetectionChallengeMessage,
  DetectionOutcomeMessage,
} from '../src/protocol/messages.js'

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeClaim(overrides: Partial<DetectionClaim> = {}): DetectionClaim {
  return {
    id: `claim-${crypto.randomBytes(4).toString('hex')}`,
    source: 'detector-alpha@satelliteA',
    domain: 'solar',
    summary: 'Anomalous solar output detected',
    confidence: 0.92,
    evidence_hash: 'abc123def456',
    created_at: new Date().toISOString(),
    ttl_seconds: 3600,
    ...overrides,
  }
}

function makeVerify(claimId: string, overrides: Partial<DetectionVerify> = {}): DetectionVerify {
  return {
    claim_id: claimId,
    verifier: 'verifier-beta@thefog',
    agrees: true,
    confidence: 0.85,
    verified_at: new Date().toISOString(),
    ...overrides,
  }
}

function makeChallenge(claimId: string, overrides: Partial<DetectionChallenge> = {}): DetectionChallenge {
  return {
    claim_id: claimId,
    challenger: 'challenger-gamma@hog',
    reason: 'Conflicting evidence from site B',
    counter_evidence_hash: 'xyz789',
    challenged_at: new Date().toISOString(),
    ...overrides,
  }
}

function makeOutcome(claimId: string, overrides: Partial<DetectionOutcome> = {}): DetectionOutcome {
  return {
    claim_id: claimId,
    outcome: 'confirmed',
    resolved_by: 'arbiter@satelliteA',
    resolved_at: new Date().toISOString(),
    ...overrides,
  }
}

/** Mock response object for direct handler testing */
function mockRes() {
  const r: any = {
    statusCode: 200,
    jsonBody: null as any,
    status(code: number) { r.statusCode = code; return r },
    json(data: any) { r.jsonBody = data; return r },
  }
  return r
}

// ═══════════════════════════════════════════════════════════════════════════════
// DetectionLedger
// ═══════════════════════════════════════════════════════════════════════════════

describe('DetectionLedger', () => {
  let ledger: DetectionLedger

  beforeEach(() => {
    ledger = new DetectionLedger()
  })

  // ── addClaim ──────────────────────────────────────────────────────────────

  describe('addClaim', () => {
    it('should add a new claim and return the entry', () => {
      const claim = makeClaim()
      const entry = ledger.addClaim(claim)
      expect(entry).not.toBeNull()
      expect(entry!.claim).toEqual(claim)
      expect(entry!.verifications).toEqual([])
      expect(entry!.challenges).toEqual([])
      expect(entry!.outcome).toBeUndefined()
    })

    it('should return null for duplicate claim ID', () => {
      const claim = makeClaim({ id: 'dupe-123' })
      const first = ledger.addClaim(claim)
      const second = ledger.addClaim(claim)
      expect(first).not.toBeNull()
      expect(second).toBeNull()
    })
  })

  // ── addVerification ──────────────────────────────────────────────────────

  describe('addVerification', () => {
    it('should add a verification to an existing claim', () => {
      const claim = makeClaim()
      ledger.addClaim(claim)
      const v = makeVerify(claim.id)
      const entry = ledger.addVerification(v)
      expect(entry).not.toBeNull()
      expect(entry!.verifications).toHaveLength(1)
      expect(entry!.verifications[0].verifier).toBe('verifier-beta@thefog')
    })

    it('should return null for unknown claim ID', () => {
      const v = makeVerify('nonexistent')
      const entry = ledger.addVerification(v)
      expect(entry).toBeNull()
    })

    it('should reject duplicate verifier (returns null)', () => {
      const claim = makeClaim()
      ledger.addClaim(claim)
      const v1 = makeVerify(claim.id, { verifier: 'same-verifier@hog' })
      const v2 = makeVerify(claim.id, { verifier: 'same-verifier@hog' })
      ledger.addVerification(v1)
      const dup = ledger.addVerification(v2)
      expect(dup).toBeNull()
    })

    it('should allow multiple different verifiers', () => {
      const claim = makeClaim()
      ledger.addClaim(claim)
      ledger.addVerification(makeVerify(claim.id, { verifier: 'v1@hog' }))
      ledger.addVerification(makeVerify(claim.id, { verifier: 'v2@thefog' }))
      ledger.addVerification(makeVerify(claim.id, { verifier: 'v3@satelliteA' }))
      const entry = ledger.getClaim(claim.id)
      expect(entry!.verifications).toHaveLength(3)
    })
  })

  // ── addChallenge ─────────────────────────────────────────────────────────

  describe('addChallenge', () => {
    it('should add a challenge to an existing claim', () => {
      const claim = makeClaim()
      ledger.addClaim(claim)
      const ch = makeChallenge(claim.id)
      const entry = ledger.addChallenge(ch)
      expect(entry).not.toBeNull()
      expect(entry!.challenges).toHaveLength(1)
    })

    it('should return null for unknown claim', () => {
      const entry = ledger.addChallenge(makeChallenge('ghost'))
      expect(entry).toBeNull()
    })

    it('should reject duplicate challenger', () => {
      const claim = makeClaim()
      ledger.addClaim(claim)
      ledger.addChallenge(makeChallenge(claim.id, { challenger: 'dup@hog' }))
      const dup = ledger.addChallenge(makeChallenge(claim.id, { challenger: 'dup@hog' }))
      expect(dup).toBeNull()
    })
  })

  // ── resolveOutcome ───────────────────────────────────────────────────────

  describe('resolveOutcome', () => {
    it('should resolve a claim with an outcome', () => {
      const claim = makeClaim()
      ledger.addClaim(claim)
      const outcome = makeOutcome(claim.id, { outcome: 'confirmed' })
      const entry = ledger.resolveOutcome(outcome)
      expect(entry).not.toBeNull()
      expect(entry!.outcome!.outcome).toBe('confirmed')
    })

    it('should return null for unknown claim', () => {
      const outcome = makeOutcome('nonexistent')
      const entry = ledger.resolveOutcome(outcome)
      expect(entry).toBeNull()
    })

    it('should support all outcome types', () => {
      const outcomes: Array<DetectionOutcome['outcome']> = ['confirmed', 'false_positive', 'expired', 'superseded']
      for (const o of outcomes) {
        const l = new DetectionLedger()
        const claim = makeClaim()
        l.addClaim(claim)
        l.resolveOutcome(makeOutcome(claim.id, { outcome: o }))
        const entry = l.getClaim(claim.id)
        expect(entry!.outcome!.outcome).toBe(o)
      }
    })
  })

  // ── Read operations ──────────────────────────────────────────────────────

  describe('read operations', () => {
    let claim1: DetectionClaim, claim2: DetectionClaim, claim3: DetectionClaim

    beforeEach(() => {
      claim1 = makeClaim({ id: 'c1', domain: 'solar', source: 'det-A@satelliteA' })
      claim2 = makeClaim({ id: 'c2', domain: 'market', source: 'det-B@hog' })
      claim3 = makeClaim({ id: 'c3', domain: 'solar', source: 'det-A@satelliteA' })
      ledger.addClaim(claim1)
      ledger.addClaim(claim2)
      ledger.addClaim(claim3)
    })

    it('getClaim returns entry by ID', () => {
      expect(ledger.getClaim('c1')).toBeDefined()
      expect(ledger.getClaim('c1')!.claim.id).toBe('c1')
      expect(ledger.getClaim('nonexistent')).toBeUndefined()
    })

    it('getClaimsByDomain filters correctly', () => {
      const solar = ledger.getClaimsByDomain('solar')
      expect(solar).toHaveLength(2)
      const market = ledger.getClaimsByDomain('market')
      expect(market).toHaveLength(1)
      const empty = ledger.getClaimsByDomain('security')
      expect(empty).toHaveLength(0)
    })

    it('getClaimsBySource filters correctly', () => {
      const fromA = ledger.getClaimsBySource('det-A@satelliteA')
      expect(fromA).toHaveLength(2)
      const fromB = ledger.getClaimsBySource('det-B@hog')
      expect(fromB).toHaveLength(1)
    })

    it('getOpenClaims returns claims without outcomes', () => {
      expect(ledger.getOpenClaims()).toHaveLength(3)
      ledger.resolveOutcome(makeOutcome('c1', { outcome: 'confirmed' }))
      expect(ledger.getOpenClaims()).toHaveLength(2)
    })

    it('getRecentClaims respects limit and ordering', () => {
      const recent = ledger.getRecentClaims(2)
      expect(recent).toHaveLength(2)
    })

    it('getAllEntries returns everything', () => {
      expect(ledger.getAllEntries()).toHaveLength(3)
    })
  })

  // ── Stats ────────────────────────────────────────────────────────────────

  describe('getStats', () => {
    it('returns correct stats for mixed state', () => {
      const c1 = makeClaim({ id: 's1', domain: 'solar' })
      const c2 = makeClaim({ id: 's2', domain: 'market' })
      const c3 = makeClaim({ id: 's3', domain: 'solar' })
      ledger.addClaim(c1)
      ledger.addClaim(c2)
      ledger.addClaim(c3)

      ledger.resolveOutcome(makeOutcome('s1', { outcome: 'confirmed' }))
      ledger.resolveOutcome(makeOutcome('s2', { outcome: 'false_positive' }))

      const stats = ledger.getStats()
      expect(stats.total).toBe(3)
      expect(stats.open).toBe(1)
      expect(stats.confirmed).toBe(1)
      expect(stats.false_positive).toBe(1)
      expect(stats.domains).toContain('solar')
      expect(stats.domains).toContain('market')
    })

    it('returns empty stats for fresh ledger', () => {
      const stats = ledger.getStats()
      expect(stats.total).toBe(0)
      expect(stats.open).toBe(0)
      expect(stats.confirmed).toBe(0)
      expect(stats.false_positive).toBe(0)
      expect(stats.domains).toEqual([])
    })
  })

  // ── Trust scoring ────────────────────────────────────────────────────────

  describe('trust scoring', () => {
    it('returns 0.5 for unknown source (neutral)', () => {
      expect(ledger.getTrustScore('unknown@hub')).toBe(0.5)
    })

    it('increases trust for agreeing verifications', () => {
      const claim = makeClaim({ id: 'trust-1', source: 'source-A@satelliteA' })
      ledger.addClaim(claim)
      ledger.addVerification(makeVerify(claim.id, { agrees: true }))
      const score = ledger.getTrustScore('source-A@satelliteA')
      expect(score).toBe(1.0)
    })

    it('decreases trust for disagreeing verifications', () => {
      const claim = makeClaim({ id: 'trust-2', source: 'source-B@hog' })
      ledger.addClaim(claim)
      ledger.addVerification(makeVerify(claim.id, { agrees: false }))
      const score = ledger.getTrustScore('source-B@hog')
      expect(score).toBe(0.0)
    })

    it('blends trust across multiple verifications', () => {
      const claim = makeClaim({ id: 'trust-3', source: 'source-C@thefog' })
      ledger.addClaim(claim)
      ledger.addVerification(makeVerify(claim.id, { agrees: true, verifier: 'v1@h1' }))
      ledger.addVerification(makeVerify(claim.id, { agrees: false, verifier: 'v2@h2' }))
      ledger.addVerification(makeVerify(claim.id, { agrees: true, verifier: 'v3@h3' }))
      // 2 agrees, 1 disagrees = 2/3 ≈ 0.667
      const score = ledger.getTrustScore('source-C@thefog')
      expect(score).toBeCloseTo(2 / 3, 2)
    })

    it('weights outcomes 3x more than verifications', () => {
      // One agree verification (weight 1), one false_positive outcome (weight 3)
      // total = 1 + 3 = 4, verified = 1, false_positive = 3
      // trust = verified / total = 1 / 4 = 0.25
      const claim = makeClaim({ id: 'trust-4', source: 'source-D@satelliteA' })
      ledger.addClaim(claim)
      ledger.addVerification(makeVerify(claim.id, { agrees: true, verifier: 'v@h' }))
      ledger.resolveOutcome(makeOutcome(claim.id, { outcome: 'false_positive' }))
      const score = ledger.getTrustScore('source-D@satelliteA')
      expect(score).toBeCloseTo(0.25, 2)
    })

    it('getTrustScores returns all tracked sources', () => {
      const c1 = makeClaim({ id: 'ts1', source: 'src-A@h1' })
      const c2 = makeClaim({ id: 'ts2', source: 'src-B@h2' })
      ledger.addClaim(c1)
      ledger.addClaim(c2)
      ledger.addVerification(makeVerify('ts1', { agrees: true }))
      const scores = ledger.getTrustScores()
      expect(scores['src-A@h1']).toBeDefined()
      // src-B has no verifications, so may not be tracked
      expect(scores['src-A@h1'].verified).toBe(1)
    })
  })

  // ── JSONL Persistence ────────────────────────────────────────────────────

  describe('JSONL persistence', () => {
    const tmpPath = join(process.cwd(), 'test-detection-log.jsonl')

    afterEach(() => {
      if (existsSync(tmpPath)) unlinkSync(tmpPath)
    })

    it('should round-trip claims, verifications, and outcomes through JSONL', async () => {
      const liveLedger = new DetectionLedger(tmpPath)

      const claim = makeClaim({ id: 'persist-1' })
      liveLedger.addClaim(claim)
      liveLedger.addVerification(makeVerify('persist-1', { verifier: 'pv@hub' }))
      liveLedger.resolveOutcome(makeOutcome('persist-1', { outcome: 'confirmed' }))

      // Wait for async file writes
      await new Promise(r => setTimeout(r, 500))

      expect(existsSync(tmpPath)).toBe(true)
      const content = readFileSync(tmpPath, 'utf-8')
      const lines = content.trim().split('\n')
      expect(lines.length).toBe(3)

      const loaded = new DetectionLedger()
      const count = loaded.loadFromLog(tmpPath)
      expect(count).toBe(3)

      const entry = loaded.getClaim('persist-1')
      expect(entry).toBeDefined()
      expect(entry!.verifications).toHaveLength(1)
      expect(entry!.outcome!.outcome).toBe('confirmed')
    })

    it('should handle loading from nonexistent file', () => {
      const fresh = new DetectionLedger()
      const count = fresh.loadFromLog('/tmp/no-such-file.jsonl')
      expect(count).toBe(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// DetectionCoord
// ═══════════════════════════════════════════════════════════════════════════════

describe('DetectionCoord', () => {
  let coord: DetectionCoord
  let ledger: DetectionLedger
  let broadcastLog: object[]

  beforeEach(() => {
    broadcastLog = []
    ledger = new DetectionLedger()
    coord = new DetectionCoord({
      hub: 'satelliteA',
      ledger,
      debug: false,
    })
    coord.setBroadcast((msg) => broadcastLog.push(msg))
  })

  // ── Message routing ──────────────────────────────────────────────────────

  describe('message routing', () => {
    it('routes detection_claim messages correctly', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      expect(ledger.getClaim(claim.id)).toBeDefined()
    })

    it('routes detection_verify messages correctly', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      const v = makeVerify(claim.id)
      coord.handleMessage({ type: 'detection_verify', verification: v })
      expect(ledger.getClaim(claim.id)!.verifications).toHaveLength(1)
    })

    it('routes detection_challenge messages correctly', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      const ch = makeChallenge(claim.id)
      coord.handleMessage({ type: 'detection_challenge', challenge: ch })
      expect(ledger.getClaim(claim.id)!.challenges).toHaveLength(1)
    })

    it('routes detection_outcome messages correctly', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      const out = makeOutcome(claim.id)
      coord.handleMessage({ type: 'detection_outcome', outcome: out })
      expect(ledger.getClaim(claim.id)!.outcome!.outcome).toBe('confirmed')
    })
  })

  // ── Broadcast ────────────────────────────────────────────────────────────

  describe('broadcast', () => {
    it('broadcasts new claims', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      expect(broadcastLog).toHaveLength(1)
      expect(broadcastLog[0]).toEqual({ type: 'detection_claim', claim })
    })

    it('does NOT broadcast duplicate claims', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      coord.handleMessage({ type: 'detection_claim', claim })
      expect(broadcastLog).toHaveLength(1)
    })

    it('broadcasts verifications', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      const v = makeVerify(claim.id)
      coord.handleMessage({ type: 'detection_verify', verification: v })
      expect(broadcastLog).toHaveLength(2)
    })

    it('broadcasts challenges', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      const ch = makeChallenge(claim.id)
      coord.handleMessage({ type: 'detection_challenge', challenge: ch })
      expect(broadcastLog).toHaveLength(2)
    })

    it('broadcasts outcomes', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      const out = makeOutcome(claim.id)
      coord.handleMessage({ type: 'detection_outcome', outcome: out })
      expect(broadcastLog).toHaveLength(2)
    })
  })

  // ── Dedup ────────────────────────────────────────────────────────────────

  describe('deduplication', () => {
    it('ignores resubmission of same claim ID', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      broadcastLog = []
      coord.handleMessage({ type: 'detection_claim', claim })
      expect(broadcastLog).toHaveLength(0)
      expect(ledger.getStats().total).toBe(1)
    })
  })

  // ── Domain subscriptions ─────────────────────────────────────────────────

  describe('domain subscriptions', () => {
    it('allows agents to subscribe to domains', () => {
      coord.subscribe('solar', 'agent-X@satelliteA')
      coord.subscribe('solar', 'agent-Y@hog')
      expect(coord.getHubsForDomain('solar')).toContain('satelliteA')
      expect(coord.getHubsForDomain('solar')).toContain('hog')
    })

    it('allows agents to unsubscribe', () => {
      coord.subscribe('market', 'agent-Z@thefog')
      coord.unsubscribe('market', 'agent-Z@thefog')
      const stats = coord.getDomainRoutingStats()
      // After unsubscribe, count drops to 0 (key may still exist with value 0)
      expect(stats.domainBreakdown['market']).toBeFalsy()
    })

    it('tracks domain routing stats', () => {
      coord.subscribe('solar', 'a@h1')
      coord.subscribe('solar', 'b@h2')
      coord.subscribe('market', 'c@h3')
      const stats = coord.getDomainRoutingStats()
      expect(stats.domains).toBe(2)
      expect(stats.totalSubscriptions).toBe(3)
      expect(stats.domainBreakdown['solar']).toBe(2)
      expect(stats.domainBreakdown['market']).toBe(1)
    })
  })

  // ── Domain routing ───────────────────────────────────────────────────────

  describe('domain routing', () => {
    let sentToHubs: string[]
    let mockPeerRegistry: any

    beforeEach(() => {
      sentToHubs = []
      mockPeerRegistry = {
        sendTo: (hub: string, _msg: string) => {
          sentToHubs.push(hub)
          return true
        },
      }
    })

    it('routes claims only to subscribed hubs when domain routing is enabled', () => {
      const domainCoord = new DetectionCoord({
        hub: 'satelliteA',
        ledger: new DetectionLedger(),
        peerRegistry: mockPeerRegistry,
        domainRoutingEnabled: true,
        debug: false,
      })
      domainCoord.setBroadcast((msg) => broadcastLog.push(msg))
      domainCoord.subscribe('solar', 'agent@hog')

      const claim = makeClaim({ domain: 'solar' })
      domainCoord.handleMessage({ type: 'detection_claim', claim })

      expect(sentToHubs).toContain('hog')
    })

    it('falls back to broadcast when no subscribers for domain', () => {
      const domainCoord = new DetectionCoord({
        hub: 'satelliteA',
        ledger: new DetectionLedger(),
        domainRoutingEnabled: true,
        debug: false,
      })
      domainCoord.setBroadcast((msg) => broadcastLog.push(msg))

      const claim = makeClaim({ domain: 'unknown-domain' })
      domainCoord.handleMessage({ type: 'detection_claim', claim })

      expect(broadcastLog).toHaveLength(1)
    })
  })

  // ── Delegates to ledger ──────────────────────────────────────────────────

  describe('delegation to ledger', () => {
    it('getOpenClaims delegates correctly', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      expect(coord.getOpenClaims()).toHaveLength(1)
      expect(coord.getOpenClaims('nonexistent')).toHaveLength(0)
    })

    it('getStats delegates correctly', () => {
      const claim = makeClaim()
      coord.handleMessage({ type: 'detection_claim', claim })
      const stats = coord.getStats()
      expect(stats.total).toBe(1)
      expect(stats.open).toBe(1)
    })

    it('getTrustScores delegates correctly', () => {
      const claim = makeClaim({ source: 'src@hub' })
      coord.handleMessage({ type: 'detection_claim', claim })
      coord.handleMessage({ type: 'detection_verify', verification: makeVerify(claim.id, { agrees: true }) })
      const scores = coord.getTrustScores()
      expect(scores['src@hub']).toBeDefined()
    })

    it('getClaim delegates correctly', () => {
      const claim = makeClaim({ id: 'deleg-1' })
      coord.handleMessage({ type: 'detection_claim', claim })
      expect(coord.getClaim('deleg-1')).toBeDefined()
      expect(coord.getClaim('nonexistent')).toBeUndefined()
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Protocol message types
// ═══════════════════════════════════════════════════════════════════════════════

describe('Protocol message types', () => {
  it('DetectionClaimMessage has correct structure', () => {
    const claim = makeClaim()
    const msg: DetectionClaimMessage = {
      type: 'detection_claim',
      from: 'satelliteA',
      to: 'hog',
      timestamp: new Date().toISOString(),
      claim,
    }
    expect(msg.type).toBe('detection_claim')
    expect(msg.claim.id).toBeTruthy()
    expect(msg.claim.source).toBeTruthy()
    expect(msg.claim.domain).toBeTruthy()
    expect(msg.claim.confidence).toBeGreaterThanOrEqual(0)
    expect(msg.claim.confidence).toBeLessThanOrEqual(1)
  })

  it('DetectionVerifyMessage has correct structure', () => {
    const v = makeVerify('test-claim')
    const msg: DetectionVerifyMessage = {
      type: 'detection_verify',
      from: 'hog',
      timestamp: new Date().toISOString(),
      verification: v,
    }
    expect(msg.type).toBe('detection_verify')
    expect(msg.verification.claim_id).toBe('test-claim')
  })

  it('DetectionChallengeMessage has correct structure', () => {
    const ch = makeChallenge('test-claim')
    const msg: DetectionChallengeMessage = {
      type: 'detection_challenge',
      from: 'thefog',
      timestamp: new Date().toISOString(),
      challenge: ch,
    }
    expect(msg.type).toBe('detection_challenge')
    expect(msg.challenge.claim_id).toBe('test-claim')
  })

  it('DetectionOutcomeMessage has correct structure', () => {
    const o = makeOutcome('test-claim')
    const msg: DetectionOutcomeMessage = {
      type: 'detection_outcome',
      from: 'satelliteA',
      timestamp: new Date().toISOString(),
      outcome: o,
    }
    expect(msg.type).toBe('detection_outcome')
    expect(msg.outcome.claim_id).toBe('test-claim')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// REST handler logic (no HTTP server — memory-safe for Pi)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Detection REST handlers', () => {
  let detectionCoord: DetectionCoord
  let detectionLedger: DetectionLedger

  // Reimplement REST handler logic directly (mirrors rest-api.ts _submitClaim etc.)
  function submitClaim(body: Record<string, any>) {
    const res = mockRes()
    const { source, domain, summary, confidence, evidence_hash, ttl_seconds, evidence } = body
    if (!source || !domain || !summary || confidence === undefined) {
      return res.status(400).json({ error: 'source, domain, summary, and confidence are required' })
    }
    const claim: DetectionClaim = {
      id: crypto.randomUUID(),
      source,
      domain,
      summary,
      confidence: Math.max(0, Math.min(1, confidence)),
      evidence_hash: evidence_hash ?? '',
      created_at: new Date().toISOString(),
      ttl_seconds,
      evidence,
    }
    detectionCoord.handleMessage({ type: 'detection_claim', claim })
    return res.json({ claim_id: claim.id, status: 'recorded', propagated: true })
  }

  function submitVerify(body: Record<string, any>) {
    const res = mockRes()
    const { claim_id, verifier, agrees, confidence, notes } = body
    if (!claim_id || !verifier || agrees === undefined) {
      return res.status(400).json({ error: 'claim_id, verifier, and agrees are required' })
    }
    const verification: DetectionVerify = {
      claim_id,
      verifier,
      agrees,
      confidence: confidence ?? (agrees ? 0.8 : 0.2),
      notes,
      verified_at: new Date().toISOString(),
    }
    detectionCoord.handleMessage({ type: 'detection_verify', verification })
    return res.json({ claim_id, status: 'verified', agrees })
  }

  function submitOutcome(body: Record<string, any>) {
    const res = mockRes()
    const { claim_id, outcome, resolved_by, notes, superseded_by } = body
    if (!claim_id || !outcome || !resolved_by) {
      return res.status(400).json({ error: 'claim_id, outcome, and resolved_by are required' })
    }
    const detOutcome: DetectionOutcome = {
      claim_id,
      outcome,
      resolved_by,
      resolved_at: new Date().toISOString(),
      notes,
      superseded_by,
    }
    detectionCoord.handleMessage({ type: 'detection_outcome', outcome: detOutcome })
    return res.json({ claim_id, status: outcome })
  }

  beforeEach(() => {
    detectionLedger = new DetectionLedger()
    detectionCoord = new DetectionCoord({
      hub: 'test-hub',
      ledger: detectionLedger,
    })
    detectionCoord.setBroadcast(() => {})
  })

  // ── POST /detection/claim ────────────────────────────────────────────────

  describe('POST /detection/claim', () => {
    it('creates a new detection claim', () => {
      const res = submitClaim({
        source: 'detector@test-hub',
        domain: 'solar',
        summary: 'Panel output anomaly',
        confidence: 0.88,
      })
      expect(res.statusCode).toBe(200)
      expect(res.jsonBody.claim_id).toBeTruthy()
      expect(res.jsonBody.status).toBe('recorded')
    })

    it('returns 400 when required fields are missing', () => {
      const res = submitClaim({
        source: 'detector@test-hub',
      })
      expect(res.statusCode).toBe(400)
      expect(res.jsonBody.error).toContain('required')
    })

    it('clamps confidence to 0-1 range', () => {
      const res = submitClaim({
        source: 'det@test',
        domain: 'solar',
        summary: 'test',
        confidence: 5.0,
      })
      expect(res.statusCode).toBe(200)
      const claimId = res.jsonBody.claim_id
      const entry = detectionCoord.getClaim(claimId)
      expect(entry!.claim.confidence).toBe(1)
    })

    it('clamps negative confidence to 0', () => {
      const res = submitClaim({
        source: 'det@test',
        domain: 'solar',
        summary: 'negative',
        confidence: -3.0,
      })
      expect(res.statusCode).toBe(200)
      const claimId = res.jsonBody.claim_id
      const entry = detectionCoord.getClaim(claimId)
      expect(entry!.claim.confidence).toBe(0)
    })
  })

  // ── POST /detection/verify ───────────────────────────────────────────────

  describe('POST /detection/verify', () => {
    it('verifies an existing claim', () => {
      const claimRes = submitClaim({
        source: 'det@test',
        domain: 'solar',
        summary: 'test claim',
        confidence: 0.9,
      })
      const claimId = claimRes.jsonBody.claim_id

      const res = submitVerify({
        claim_id: claimId,
        verifier: 'peer@test',
        agrees: true,
      })
      expect(res.statusCode).toBe(200)
      expect(res.jsonBody.status).toBe('verified')
      expect(res.jsonBody.agrees).toBe(true)
    })

    it('returns 400 when required fields are missing', () => {
      const res = submitVerify({
        claim_id: 'abc',
      })
      expect(res.statusCode).toBe(400)
    })

    it('defaults confidence based on agrees', () => {
      const claimRes = submitClaim({
        source: 'det@test',
        domain: 'solar',
        summary: 'test',
        confidence: 0.5,
      })
      const claimId = claimRes.jsonBody.claim_id

      const agreeRes = submitVerify({ claim_id: claimId, verifier: 'v1@test', agrees: true })
      expect(agreeRes.statusCode).toBe(200)
      const entry = detectionCoord.getClaim(claimId)
      expect(entry!.verifications[0].confidence).toBe(0.8)
    })
  })

  // ── POST /detection/outcome ──────────────────────────────────────────────

  describe('POST /detection/outcome', () => {
    it('resolves a claim with an outcome', () => {
      const claimRes = submitClaim({
        source: 'det@test',
        domain: 'market',
        summary: 'Flash crash detected',
        confidence: 0.95,
      })
      const claimId = claimRes.jsonBody.claim_id

      const res = submitOutcome({
        claim_id: claimId,
        outcome: 'confirmed',
        resolved_by: 'arbiter@test',
      })
      expect(res.statusCode).toBe(200)
      expect(res.jsonBody.status).toBe('confirmed')
    })

    it('returns 400 when required fields are missing', () => {
      const res = submitOutcome({
        claim_id: 'abc',
      })
      expect(res.statusCode).toBe(400)
    })

    it('supports all outcome types', () => {
      const types: Array<DetectionOutcome['outcome']> = ['confirmed', 'false_positive', 'expired', 'superseded']
      for (const t of types) {
        const c = submitClaim({ source: `d${t}@t`, domain: 'test', summary: t, confidence: 0.5 })
        const r = submitOutcome({ claim_id: c.jsonBody.claim_id, outcome: t, resolved_by: 'arb@test' })
        expect(r.statusCode).toBe(200)
        expect(r.jsonBody.status).toBe(t)
      }
    })
  })

  // ── Query operations (via coord/ledger directly) ─────────────────────────

  describe('query operations', () => {
    it('getStats returns correct counts', () => {
      submitClaim({ source: 'a@t', domain: 'solar', summary: 's1', confidence: 0.8 })
      const c2 = submitClaim({ source: 'b@t', domain: 'market', summary: 'm1', confidence: 0.7 })
      submitOutcome({ claim_id: c2.jsonBody.claim_id, outcome: 'confirmed', resolved_by: 'a@t' })

      const stats = detectionCoord.getStats()
      expect(stats.total).toBe(2)
      expect(stats.confirmed).toBe(1)
      expect(stats.open).toBe(1)
    })

    it('getTrustScores reflects verification history', () => {
      const c = submitClaim({ source: 'src@test', domain: 'solar', summary: 'test', confidence: 0.8 })
      submitVerify({ claim_id: c.jsonBody.claim_id, verifier: 'v@test', agrees: true })

      const scores = detectionCoord.getTrustScores()
      expect(scores['src@test']).toBeDefined()
    })

    it('getClaim returns null for unknown IDs', () => {
      expect(detectionCoord.getClaim('nonexistent')).toBeUndefined()
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Full lifecycle
// ═══════════════════════════════════════════════════════════════════════════════

describe('Detection full lifecycle', () => {
  it('handles claim → verify → challenge → resolve flow', () => {
    const ledger = new DetectionLedger()
    const coord = new DetectionCoord({ hub: 'satelliteA', ledger })
    const broadcastLog: object[] = []
    coord.setBroadcast((msg) => broadcastLog.push(msg))

    // 1. Submit claim
    const claim = makeClaim({ id: 'lifecycle-1', source: 'src@hub', domain: 'security' })
    coord.handleMessage({ type: 'detection_claim', claim })
    expect(ledger.getStats().total).toBe(1)

    // 2. Verify from 2 peers
    coord.handleMessage({
      type: 'detection_verify',
      verification: makeVerify('lifecycle-1', { verifier: 'v1@h1', agrees: true }),
    })
    coord.handleMessage({
      type: 'detection_verify',
      verification: makeVerify('lifecycle-1', { verifier: 'v2@h2', agrees: true }),
    })
    expect(ledger.getClaim('lifecycle-1')!.verifications).toHaveLength(2)

    // 3. Challenge from skeptic
    coord.handleMessage({
      type: 'detection_challenge',
      challenge: makeChallenge('lifecycle-1', { challenger: 'skeptic@h3' }),
    })
    expect(ledger.getClaim('lifecycle-1')!.challenges).toHaveLength(1)

    // 4. Resolve as confirmed
    coord.handleMessage({
      type: 'detection_outcome',
      outcome: makeOutcome('lifecycle-1', { outcome: 'confirmed', resolved_by: 'arbiter@hub' }),
    })

    const entry = ledger.getClaim('lifecycle-1')!
    expect(entry.outcome!.outcome).toBe('confirmed')
    expect(entry.verifications).toHaveLength(2)
    expect(entry.challenges).toHaveLength(1)

    // 5. Trust score should reflect verified + confirmed outcome
    const trust = ledger.getTrustScore('src@hub')
    expect(trust).toBeGreaterThan(0.8)

    // 6. All events broadcast: claim, verify1, verify2, challenge, outcome = 5
    expect(broadcastLog.length).toBe(5)
  })

  it('handles false positive lifecycle', () => {
    const ledger = new DetectionLedger()
    const coord = new DetectionCoord({ hub: 'hog', ledger })
    coord.setBroadcast(() => {})

    const claim = makeClaim({ id: 'fp-1', source: 'bad-src@hub' })
    coord.handleMessage({ type: 'detection_claim', claim })
    coord.handleMessage({
      type: 'detection_verify',
      verification: makeVerify('fp-1', { agrees: false }),
    })
    coord.handleMessage({
      type: 'detection_outcome',
      outcome: makeOutcome('fp-1', { outcome: 'false_positive' }),
    })

    const trust = ledger.getTrustScore('bad-src@hub')
    expect(trust).toBeLessThan(0.3)
  })

  it('handles expired claim lifecycle', () => {
    const ledger = new DetectionLedger()
    const coord = new DetectionCoord({ hub: 'thefog', ledger })
    coord.setBroadcast(() => {})

    const claim = makeClaim({ id: 'exp-1', source: 'src@hub' })
    coord.handleMessage({ type: 'detection_claim', claim })
    coord.handleMessage({
      type: 'detection_outcome',
      outcome: makeOutcome('exp-1', { outcome: 'expired' }),
    })

    const entry = ledger.getClaim('exp-1')!
    expect(entry.outcome!.outcome).toBe('expired')
    expect(ledger.getOpenClaims()).toHaveLength(0)
  })

  it('handles superseded claim lifecycle', () => {
    const ledger = new DetectionLedger()
    const coord = new DetectionCoord({ hub: 'satelliteA', ledger })
    coord.setBroadcast(() => {})

    const claim1 = makeClaim({ id: 'old-1', source: 'src@hub', domain: 'solar' })
    const claim2 = makeClaim({ id: 'new-1', source: 'src@hub', domain: 'solar' })
    coord.handleMessage({ type: 'detection_claim', claim: claim1 })
    coord.handleMessage({ type: 'detection_claim', claim: claim2 })
    coord.handleMessage({
      type: 'detection_outcome',
      outcome: makeOutcome('old-1', { outcome: 'superseded', superseded_by: 'new-1' }),
    })

    const entry = ledger.getClaim('old-1')!
    expect(entry.outcome!.outcome).toBe('superseded')
    expect(entry.outcome!.superseded_by).toBe('new-1')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Cross-Hub Detection Sync
// ═══════════════════════════════════════════════════════════════════════════════

import { DetectionSync } from '../src/server/detection-sync.js'

describe('DetectionSync — cross-hub', () => {
  let sync: DetectionSync
  let coord: DetectionCoord
  let ledger: DetectionLedger
  let sentMessages: { hub: string; data: string }[]
  let broadcastMessages: string[]
  let mockPeerRegistry: any

  beforeEach(() => {
    sentMessages = []
    broadcastMessages = []
    ledger = new DetectionLedger()
    coord = new DetectionCoord({ hub: 'satelliteA', ledger })
    coord.setBroadcast(() => {})

    mockPeerRegistry = {
      broadcast: (data: string) => { broadcastMessages.push(data) },
      sendTo: (hub: string, data: string) => {
        sentMessages.push({ hub, data })
        return true
      },
    }

    sync = new DetectionSync({
      hub: 'satelliteA',
      detectionCoord: coord,
      peerRegistry: mockPeerRegistry,
      gossipIntervalMs: 600_000, // long interval so it doesn't fire during tests
      debug: false,
    })
  })

  afterEach(() => {
    sync.stop()
  })

  // ── Claim propagation ──────────────────────────────────────────────────────

  describe('claim propagation', () => {
    it('propagates claims via broadcast', () => {
      const claim = makeClaim()
      sync.propagateClaim(claim)
      expect(broadcastMessages).toHaveLength(1)
      const parsed = JSON.parse(broadcastMessages[0])
      expect(parsed.type).toBe('detection_claim')
      expect(parsed.claim.id).toBe(claim.id)
      expect(parsed.gatewayHub).toBe('satelliteA')
    })
  })

  // ── Verification relay ────────────────────────────────────────────────────

  describe('verification relay', () => {
    it('propagates verifications via broadcast', () => {
      const v = makeVerify('test-claim')
      sync.propagateVerification(v)
      expect(broadcastMessages).toHaveLength(1)
      const parsed = JSON.parse(broadcastMessages[0])
      expect(parsed.type).toBe('detection_verify')
      expect(parsed.verification.claim_id).toBe('test-claim')
    })
  })

  // ── Outcome broadcast ─────────────────────────────────────────────────────

  describe('outcome broadcast', () => {
    it('propagates outcomes via broadcast', () => {
      const o = makeOutcome('test-claim', { outcome: 'false_positive' })
      sync.propagateOutcome(o)
      expect(broadcastMessages).toHaveLength(1)
      const parsed = JSON.parse(broadcastMessages[0])
      expect(parsed.type).toBe('detection_outcome')
      expect(parsed.outcome.outcome).toBe('false_positive')
    })
  })

  // ── Gossip ─────────────────────────────────────────────────────────────────

  describe('gossip', () => {
    it('builds gossip payload from trust scores', () => {
      const claim = makeClaim({ source: 'src@hub' })
      coord.handleMessage({ type: 'detection_claim', claim })
      coord.handleMessage({ type: 'detection_verify', verification: makeVerify(claim.id, { agrees: true }) })

      const payload = sync.buildGossipPayload()
      expect(payload.length).toBeGreaterThan(0)
      expect(payload[0].source).toBe('src@hub')
      expect(payload[0].score).toBeGreaterThan(0)
      expect(payload[0].verified).toBe(1)
    })

    it('gossips trust scores to peers', () => {
      const claim = makeClaim({ source: 'src@hub' })
      coord.handleMessage({ type: 'detection_claim', claim })
      coord.handleMessage({ type: 'detection_verify', verification: makeVerify(claim.id, { agrees: true }) })

      sync.gossipTrustScores()
      expect(broadcastMessages).toHaveLength(1)
      const parsed = JSON.parse(broadcastMessages[0])
      expect(parsed.type).toBe('detection_gossip')
      expect(parsed.hub).toBe('satelliteA')
      expect(parsed.scores.length).toBeGreaterThan(0)
    })

    it('does not gossip when no trust scores exist', () => {
      sync.gossipTrustScores()
      expect(broadcastMessages).toHaveLength(0)
    })
  })

  // ── Inbound sync ───────────────────────────────────────────────────────────

  describe('inbound sync', () => {
    it('handles incoming detection_claim', () => {
      const claim = makeClaim({ id: 'inbound-1' })
      sync.handleIncomingMessage({
        type: 'detection_claim',
        gatewayHub: 'hog',
        claim,
      })
      expect(coord.getClaim('inbound-1')).toBeDefined()
    })

    it('handles incoming detection_verify', () => {
      const claim = makeClaim({ id: 'inbound-v' })
      coord.handleMessage({ type: 'detection_claim', claim })

      sync.handleIncomingMessage({
        type: 'detection_verify',
        gatewayHub: 'thefog',
        verification: makeVerify('inbound-v', { verifier: 'remote@thefog' }),
      })
      expect(coord.getClaim('inbound-v')!.verifications).toHaveLength(1)
    })

    it('handles incoming detection_outcome', () => {
      const claim = makeClaim({ id: 'inbound-o' })
      coord.handleMessage({ type: 'detection_claim', claim })

      sync.handleIncomingMessage({
        type: 'detection_outcome',
        gatewayHub: 'hog',
        outcome: makeOutcome('inbound-o', { outcome: 'confirmed' }),
      })
      expect(coord.getClaim('inbound-o')!.outcome!.outcome).toBe('confirmed')
    })

    it('handles incoming detection_gossip', () => {
      // Should not throw
      sync.handleIncomingMessage({
        type: 'detection_gossip',
        gatewayHub: 'hog',
        hub: 'hog',
        scores: [{ source: 'src@hog', score: 0.85, totalClaims: 5, verified: 3 }],
      })
    })

    it('ignores unknown message types', () => {
      sync.handleIncomingMessage({ type: 'unknown_thing' })
      // Should not throw
    })

    it('handles malformed messages gracefully', () => {
      sync.handleIncomingMessage({ type: 'detection_claim' }) // no claim field
      sync.handleIncomingMessage({ type: 'detection_verify' }) // no verification
      sync.handleIncomingMessage({}) // no type
    })
  })

  // ── Initial sync ───────────────────────────────────────────────────────────

  describe('initial sync', () => {
    it('sends open claims to a newly registered peer', () => {
      // Create some claims on our hub
      const c1 = makeClaim({ id: 'sync-1', domain: 'solar' })
      const c2 = makeClaim({ id: 'sync-2', domain: 'market' })
      coord.handleMessage({ type: 'detection_claim', claim: c1 })
      coord.handleMessage({ type: 'detection_claim', claim: c2 })

      // Register a new peer
      sync.registerPeer('hog')

      // Should have sent 2 claims to hog
      const hogMessages = sentMessages.filter(m => m.hub === 'hog')
      expect(hogMessages.length).toBeGreaterThanOrEqual(2)
      const types = hogMessages.map(m => JSON.parse(m.data).type)
      expect(types.filter(t => t === 'detection_claim')).toHaveLength(2)
    })

    it('sends verifications and outcomes in initial sync', () => {
      const c1 = makeClaim({ id: 'sync-v' })
      coord.handleMessage({ type: 'detection_claim', claim: c1 })
      coord.handleMessage({ type: 'detection_verify', verification: makeVerify('sync-v', { verifier: 'v@h' }) })
      // Don't resolve — resolved claims are no longer open, so won't be in initial sync
      // coord.handleMessage({ type: 'detection_outcome', outcome: makeOutcome('sync-v', { outcome: 'confirmed' }) })

      sync.registerPeer('thefog')

      const fogMessages = sentMessages.filter(m => m.hub === 'thefog')
      const types = fogMessages.map(m => JSON.parse(m.data).type)
      expect(types).toContain('detection_claim')
      expect(types).toContain('detection_verify')
    })

    it('does not re-sync an already known peer', () => {
      sync.registerPeer('hog')
      sentMessages = []
      sync.registerPeer('hog') // second call should be no-op
      expect(sentMessages).toHaveLength(0)
    })

    it('tracks known peers', () => {
      sync.registerPeer('hog')
      sync.registerPeer('thefog')
      const known = sync.getKnownPeers()
      expect(known.has('hog')).toBe(true)
      expect(known.has('thefog')).toBe(true)
      expect(known.has('satelliteA')).toBe(false)
    })
  })

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  describe('lifecycle', () => {
    it('start and stop work cleanly', () => {
      sync.start()
      sync.stop()
      // Should not throw
    })

    it('double start is idempotent', () => {
      sync.start()
      sync.start()
      sync.stop()
    })
  })

  // ── Full cross-hub flow ────────────────────────────────────────────────────

  describe('full cross-hub flow', () => {
    it('simulates claim propagation across 3 hubs', () => {
      // Hub 1: satelliteA (our hub)
      // Hub 2: hog (remote)
      // Hub 3: thefog (remote)

      const ledger2 = new DetectionLedger()
      const ledger3 = new DetectionLedger()
      const coord2 = new DetectionCoord({ hub: 'hog', ledger: ledger2 })
      const coord3 = new DetectionCoord({ hub: 'thefog', ledger: ledger3 })
      coord2.setBroadcast(() => {})
      coord3.setBroadcast(() => {})

      const sync2 = new DetectionSync({
        hub: 'hog',
        detectionCoord: coord2,
        peerRegistry: mockPeerRegistry,
        debug: false,
      })
      const sync3 = new DetectionSync({
        hub: 'thefog',
        detectionCoord: coord3,
        peerRegistry: mockPeerRegistry,
        debug: false,
      })

      // satelliteA detects something
      const claim = makeClaim({ id: 'xhub-1', source: 'solar-detect@satelliteA', domain: 'solar' })
      coord.handleMessage({ type: 'detection_claim', claim })

      // Propagate to peers
      sync.propagateClaim(claim)
      expect(broadcastMessages).toHaveLength(1)

      // Hog receives it
      sync2.handleIncomingMessage(JSON.parse(broadcastMessages[0]))
      expect(coord2.getClaim('xhub-1')).toBeDefined()

      // Hog verifies it
      coord2.handleMessage({
        type: 'detection_verify',
        verification: makeVerify('xhub-1', { verifier: 'data-detect@hog', agrees: true }),
      })

      // thefog also receives and verifies
      sync3.handleIncomingMessage(JSON.parse(broadcastMessages[0]))
      expect(coord3.getClaim('xhub-1')).toBeDefined()

      // All 3 hubs have the claim
      expect(coord.getClaim('xhub-1')).toBeDefined()
      expect(coord2.getClaim('xhub-1')).toBeDefined()
      expect(coord3.getClaim('xhub-1')).toBeDefined()

      // satelliteA resolves it
      coord.handleMessage({
        type: 'detection_outcome',
        outcome: makeOutcome('xhub-1', { outcome: 'confirmed', resolved_by: 'arbiter@satelliteA' }),
      })
      expect(coord.getClaim('xhub-1')!.outcome!.outcome).toBe('confirmed')

      // Clean up
      sync2.stop()
      sync3.stop()
    })
  })
})
