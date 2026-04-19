/**
 * AttestationEngine — manages the full attestation lifecycle.
 *
 * Agents claim capabilities → Engine issues challenges → Agents submit proofs →
 * Peers attest to proof quality → Engine tracks attestation scores.
 *
 * An agent's capability is "attested" when it accumulates enough peer attestations
 * above the configured threshold.
 */

import { createHash } from 'crypto'
import {
  generateChallenge,
  verifyIntegrity,
  isExpired,
  type Challenge,
  type ChallengeType,
} from './challenges.js'

// ── Types ───────────────────────────────────────────────────────────────────────

export interface Proof {
  /** Challenge ID this proof responds to */
  challengeId: string
  /** Agent submitting the proof (name@hub) */
  agentId: string
  /** Proof response data */
  response: Record<string, unknown>
  /** SHA-256 hash of the response for integrity */
  responseHash: string
  /** Submission timestamp */
  submittedAt: string
}

export interface PeerAttestation {
  /** Challenge ID being attested */
  challengeId: string
  /** Peer making the attestation (name@hub) */
  peerId: string
  /** Agent whose proof is being attested */
  agentId: string
  /** Capability being attested */
  capability: string
  /** Score 0.0–1.0 (0 = reject, 1 = perfect) */
  score: number
  /** Optional notes */
  notes?: string
  /** Timestamp */
  attestedAt: string
}

export interface AttestationRecord {
  /** Challenge issued */
  challenge: Challenge
  /** Proof submitted (null if not yet submitted) */
  proof: Proof | null
  /** Peer attestations received */
  attestations: PeerAttestation[]
  /** Status */
  status: 'pending' | 'proof_submitted' | 'attested' | 'expired' | 'failed'
}

export interface AttestationScore {
  /** Agent ID (name@hub) */
  agentId: string
  /** Capability name */
  capability: string
  /** Average attestation score from peers (0.0–1.0) */
  averageScore: number
  /** Number of peer attestations */
  attestationCount: number
  /** Whether this meets the attestation threshold */
  isAttested: boolean
  /** Most recent attestation timestamp */
  lastAttestedAt: string | null
}

export interface AttestationEngineConfig {
  /** Minimum number of peer attestations needed to consider a capability attested */
  minAttestations?: number
  /** Minimum average score needed (0.0–1.0) */
  minScore?: number
  /** Default challenge difficulty (0.0–1.0) */
  defaultDifficulty?: number
  /** Default challenge expiry in ms */
  defaultExpiryMs?: number
}

// ── Engine ──────────────────────────────────────────────────────────────────────

export class AttestationEngine {
  /** challengeId → AttestationRecord */
  private records: Map<string, AttestationRecord> = new Map()

  /** agentId:capability → AttestationScore (cached) */
  private scores: Map<string, AttestationScore> = new Map()

  private readonly minAttestations: number
  private readonly minScore: number
  private readonly defaultDifficulty: number
  private readonly defaultExpiryMs: number

  constructor(config: AttestationEngineConfig = {}) {
    this.minAttestations = config.minAttestations ?? 2
    this.minScore = config.minScore ?? 0.6
    this.defaultDifficulty = config.defaultDifficulty ?? 0.5
    this.defaultExpiryMs = config.defaultExpiryMs ?? 300_000
  }

  // ── Issue Challenge ─────────────────────────────────────────────────────────

  /**
   * Issue a challenge for an agent's capability claim.
   * Returns the challenge to send to the agent.
   */
  issueChallenge(
    capability: string,
    agentId: string,
    difficulty?: number,
    type?: ChallengeType,
  ): Challenge {
    const challenge = generateChallenge(
      capability,
      agentId,
      difficulty ?? this.defaultDifficulty,
      type,
      this.defaultExpiryMs,
    )

    this.records.set(challenge.id, {
      challenge,
      proof: null,
      attestations: [],
      status: 'pending',
    })

    return challenge
  }

  // ── Submit Proof ────────────────────────────────────────────────────────────

  /**
   * Submit proof for a challenge.
   * Returns { success, error? }
   */
  submitProof(
    challengeId: string,
    agentId: string,
    response: Record<string, unknown>,
  ): { success: boolean; error?: string } {
    const record = this.records.get(challengeId)
    if (!record) {
      return { success: false, error: 'Challenge not found' }
    }

    if (record.challenge.agentId !== agentId) {
      return { success: false, error: 'Agent mismatch — this challenge was not issued to you' }
    }

    if (!verifyIntegrity(record.challenge)) {
      return { success: false, error: 'Challenge integrity check failed' }
    }

    if (isExpired(record.challenge)) {
      record.status = 'expired'
      return { success: false, error: 'Challenge has expired' }
    }

    if (record.proof !== null) {
      return { success: false, error: 'Proof already submitted for this challenge' }
    }

    const responseHash = createHash('sha256')
      .update(JSON.stringify(response))
      .digest('hex')

    record.proof = {
      challengeId,
      agentId,
      response,
      responseHash,
      submittedAt: new Date().toISOString(),
    }
    record.status = 'proof_submitted'

    return { success: true }
  }

  // ── Peer Attestation ───────────────────────────────────────────────────────

  /**
   * Record a peer attestation for a submitted proof.
   * Returns { success, error? }
   */
  addAttestation(
    challengeId: string,
    peerId: string,
    score: number,
    notes?: string,
  ): { success: boolean; error?: string } {
    const record = this.records.get(challengeId)
    if (!record) {
      return { success: false, error: 'Challenge not found' }
    }

    if (!record.proof) {
      return { success: false, error: 'No proof submitted yet' }
    }

    if (record.proof.agentId === peerId) {
      return { success: false, error: 'Cannot attest your own proof' }
    }

    // Check for duplicate attestation from same peer
    if (record.attestations.some(a => a.peerId === peerId)) {
      return { success: false, error: 'Already attested by this peer' }
    }

    const attestation: PeerAttestation = {
      challengeId,
      peerId,
      agentId: record.proof.agentId,
      capability: record.challenge.capability,
      score: Math.max(0, Math.min(1, score)),
      notes,
      attestedAt: new Date().toISOString(),
    }

    record.attestations.push(attestation)

    // Check if we've reached threshold
    if (record.attestations.length >= this.minAttestations) {
      const avgScore = record.attestations.reduce((s, a) => s + a.score, 0) / record.attestations.length
      if (avgScore >= this.minScore) {
        record.status = 'attested'
      }
    }

    // Invalidate cached score
    this.scores.delete(`${record.proof.agentId}:${record.challenge.capability}`)

    return { success: true }
  }

  // ── Query ──────────────────────────────────────────────────────────────────

  /**
   * Check if a specific capability is fully attested for an agent.
   */
  isAttested(agentId: string, capability: string): boolean {
    const score = this.getScore(agentId, capability)
    return score.isAttested
  }

  /**
   * Get attestation score for an agent + capability.
   * Aggregates across all relevant challenges.
   */
  getScore(agentId: string, capability: string): AttestationScore {
    const cacheKey = `${agentId}:${capability}`
    const cached = this.scores.get(cacheKey)
    if (cached) return cached

    // Gather all attestations for this agent+capability
    const allAttestations: PeerAttestation[] = []
    let lastAttestedAt: string | null = null

    for (const record of this.records.values()) {
      if (
        record.challenge.agentId === agentId &&
        record.challenge.capability === capability &&
        record.attestations.length > 0
      ) {
        allAttestations.push(...record.attestations)
        for (const a of record.attestations) {
          if (!lastAttestedAt || a.attestedAt > lastAttestedAt) {
            lastAttestedAt = a.attestedAt
          }
        }
      }
    }

    const averageScore = allAttestations.length > 0
      ? allAttestations.reduce((s, a) => s + a.score, 0) / allAttestations.length
      : 0

    const score: AttestationScore = {
      agentId,
      capability,
      averageScore: Math.round(averageScore * 1000) / 1000,
      attestationCount: allAttestations.length,
      isAttested: allAttestations.length >= this.minAttestations && averageScore >= this.minScore,
      lastAttestedAt,
    }

    this.scores.set(cacheKey, score)
    return score
  }

  /**
   * Get all attestation scores for an agent.
   */
  getAgentScores(agentId: string): AttestationScore[] {
    const capabilities = new Set<string>()
    for (const record of this.records.values()) {
      if (record.challenge.agentId === agentId) {
        capabilities.add(record.challenge.capability)
      }
    }
    return Array.from(capabilities).map(cap => this.getScore(agentId, cap))
  }

  /**
   * Get an attestation record by challenge ID.
   */
  getRecord(challengeId: string): AttestationRecord | undefined {
    return this.records.get(challengeId)
  }

  /**
   * Get all challenge IDs for an agent.
   */
  getChallengesForAgent(agentId: string): string[] {
    const ids: string[] = []
    for (const [id, record] of this.records) {
      if (record.challenge.agentId === agentId) ids.push(id)
    }
    return ids
  }

  /**
   * Clean up expired challenges.
   */
  pruneExpired(): number {
    let pruned = 0
    for (const [id, record] of this.records) {
      if (isExpired(record.challenge) && record.status === 'pending') {
        record.status = 'expired'
        pruned++
      }
    }
    return pruned
  }

  /**
   * Get engine stats.
   */
  stats(): {
    totalChallenges: number
    pending: number
    proofSubmitted: number
    attested: number
    expired: number
    failed: number
  } {
    let pending = 0, proofSubmitted = 0, attested = 0, expired = 0, failed = 0
    for (const record of this.records.values()) {
      switch (record.status) {
        case 'pending': pending++; break
        case 'proof_submitted': proofSubmitted++; break
        case 'attested': attested++; break
        case 'expired': expired++; break
        case 'failed': failed++; break
      }
    }
    return {
      totalChallenges: this.records.size,
      pending,
      proofSubmitted,
      attested,
      expired,
      failed,
    }
  }
}
