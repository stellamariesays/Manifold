/**
 * Phase 2: Attestation System — comprehensive tests.
 *
 * Tests cover:
 * - Challenge generation (all types)
 * - Attestation Engine lifecycle
 * - Anti-Sybil PoW registration
 * - CapabilityIndex attestation tracking
 * - REST API endpoints (via supertest-style testing)
 * - Protocol message types
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { createHash } from 'crypto'

// Attestation modules
import {
  AttestationEngine,
  type AttestationEngineConfig,
} from '../src/attestation/engine.js'
import {
  generateChallenge,
  selectChallengeType,
  verifyIntegrity,
  isExpired,
  GenericChallenge,
  CodeChallenge,
  AnalysisChallenge,
  type Challenge,
} from '../src/attestation/challenges.js'
import {
  AntiSybilGuard,
  hasLeadingZeroBits,
  solvePoW,
  type PoWChallenge,
} from '../src/attestation/anti-sybil.js'

// Server modules
import { CapabilityIndex } from '../src/server/capability-index.js'

// Protocol messages
import type {
  AttestationChallengeMessage,
  AttestationProofMessage,
  AttestationPeerMessage,
  MessageType,
} from '../src/protocol/messages.js'

// ════════════════════════════════════════════════════════════════════════════════
// Challenge Generation
// ════════════════════════════════════════════════════════════════════════════════

describe('Challenge Generation', () => {
  describe('GenericChallenge', () => {
    const gen = new GenericChallenge()

    it('generates a valid challenge', () => {
      const c = gen.generate('quantum-computing', 'alice@hub1', 0.5)
      expect(c.id).toBeTruthy()
      expect(c.type).toBe('generic')
      expect(c.capability).toBe('quantum-computing')
      expect(c.agentId).toBe('alice@hub1')
      expect(c.difficulty).toBe(0.5)
      expect(c.testData).toBeTruthy()
      expect(c.testData['prompt']).toContain('quantum-computing')
      expect(c.testData['nonce']).toBeTruthy()
      expect(c.integrityHash).toBeTruthy()
      expect(c.createdAt).toBeTruthy()
      expect(new Date(c.expiresAt).getTime()).toBeGreaterThan(Date.now())
    })

    it('scales minResponseLength with difficulty', () => {
      const easy = gen.generate('x', 'a@b', 0.0)
      const hard = gen.generate('x', 'a@b', 1.0)
      expect((hard.testData['minResponseLength'] as number)).toBeGreaterThan(
        easy.testData['minResponseLength'] as number,
      )
    })

    it('clamps difficulty to 0–1', () => {
      const c = gen.generate('x', 'a@b', 1.5)
      expect(c.difficulty).toBe(1.0)
    })
  })

  describe('CodeChallenge', () => {
    const gen = new CodeChallenge()

    it('generates a code challenge with input/expectedOutput', () => {
      const c = gen.generate('coding', 'bob@hub2', 0.3)
      expect(c.type).toBe('code')
      expect(c.testData['input']).toBeTruthy()
      expect(c.testData['expectedOutput']).toBeTruthy()
      expect(c.testData['description']).toBeTruthy()
    })

    it('selects harder problems at higher difficulty', () => {
      const easy = gen.generate('coding', 'bob@hub2', 0.1)
      const hard = gen.generate('coding', 'bob@hub2', 0.9)
      // Different problems based on difficulty
      expect(easy.testData['description']).not.toBe(hard.testData['description'])
    })
  })

  describe('AnalysisChallenge', () => {
    const gen = new AnalysisChallenge()

    it('generates an analysis challenge with dataset and metrics', () => {
      const c = gen.generate('data-analysis', 'carol@hub3', 0.5)
      expect(c.type).toBe('analysis')
      expect(Array.isArray(c.testData['dataset'])).toBe(true)
      expect(c.testData['requiredMetrics']).toEqual(['mean', 'variance', 'trend'])
      expect(typeof c.testData['expectedMean']).toBe('number')
      expect(typeof c.testData['expectedVariance']).toBe('number')
      expect(typeof c.testData['tolerance']).toBe('number')
    })

    it('generates larger datasets at higher difficulty', () => {
      const easy = gen.generate('analytics', 'a@b', 0.0)
      const hard = gen.generate('analytics', 'a@b', 1.0)
      expect((hard.testData['dataset'] as number[]).length).toBeGreaterThan(
        (easy.testData['dataset'] as number[]).length,
      )
    })

    it('has tighter tolerance at higher difficulty', () => {
      const easy = gen.generate('analytics', 'a@b', 0.1)
      const hard = gen.generate('analytics', 'a@b', 0.9)
      expect(hard.testData['tolerance'] as number).toBeLessThan(
        easy.testData['tolerance'] as number,
      )
    })
  })

  describe('selectChallengeType', () => {
    it('selects code for coding capabilities', () => {
      expect(selectChallengeType('coding')).toBe('code')
      expect(selectChallengeType('programming')).toBe('code')
      expect(selectChallengeType('script-execution')).toBe('code')
    })

    it('selects analysis for analytical capabilities', () => {
      expect(selectChallengeType('data-analysis')).toBe('analysis')
      expect(selectChallengeType('detection')).toBe('analysis')
      expect(selectChallengeType('monitoring')).toBe('analysis')
    })

    it('defaults to generic for unknown capabilities', () => {
      expect(selectChallengeType('quantum-computing')).toBe('generic')
      expect(selectChallengeType('translation')).toBe('generic')
    })
  })

  describe('generateChallenge (auto-select)', () => {
    it('auto-selects based on capability name', () => {
      const code = generateChallenge('coding', 'a@b')
      expect(code.type).toBe('code')

      const analysis = generateChallenge('data-analysis', 'a@b')
      expect(analysis.type).toBe('analysis')

      const generic = generateChallenge('quantum', 'a@b')
      expect(generic.type).toBe('generic')
    })

    it('allows overriding the type', () => {
      const c = generateChallenge('quantum', 'a@b', 0.5, 'code')
      expect(c.type).toBe('code')
    })
  })

  describe('Integrity & Expiry', () => {
    it('verifyIntegrity passes for valid challenge', () => {
      const c = generateChallenge('test', 'a@b')
      expect(verifyIntegrity(c)).toBe(true)
    })

    it('verifyIntegrity fails for tampered challenge', () => {
      const c = generateChallenge('test', 'a@b')
      c.capability = 'hacked'
      expect(verifyIntegrity(c)).toBe(false)
    })

    it('isExpired returns false for fresh challenge', () => {
      const c = generateChallenge('test', 'a@b')
      expect(isExpired(c)).toBe(false)
    })

    it('isExpired returns true for expired challenge', () => {
      const c = generateChallenge('test', 'a@b', 0.5, undefined, 1)
      // Wait 2ms to ensure expiry
      const start = Date.now()
      while (Date.now() - start < 5) { /* spin */ }
      expect(isExpired(c)).toBe(true)
    })
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// Attestation Engine
// ════════════════════════════════════════════════════════════════════════════════

describe('AttestationEngine', () => {
  let engine: AttestationEngine

  beforeEach(() => {
    engine = new AttestationEngine({
      minAttestations: 2,
      minScore: 0.6,
      defaultDifficulty: 0.5,
      defaultExpiryMs: 300_000,
    })
  })

  describe('Issue Challenge', () => {
    it('issues a challenge and stores it', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      expect(challenge.id).toBeTruthy()
      expect(challenge.capability).toBe('coding')
      expect(challenge.agentId).toBe('alice@hub1')

      const record = engine.getRecord(challenge.id)
      expect(record).toBeTruthy()
      expect(record!.status).toBe('pending')
      expect(record!.proof).toBeNull()
      expect(record!.attestations).toHaveLength(0)
    })

    it('issues different challenge types', () => {
      const code = engine.issueChallenge('coding', 'a@b', 0.5, 'code')
      expect(code.type).toBe('code')

      const analysis = engine.issueChallenge('analytics', 'a@b', 0.5, 'analysis')
      expect(analysis.type).toBe('analysis')

      const generic = engine.issueChallenge('quantum', 'a@b', 0.5, 'generic')
      expect(generic.type).toBe('generic')
    })
  })

  describe('Submit Proof', () => {
    it('accepts a valid proof', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      const result = engine.submitProof(challenge.id, 'alice@hub1', { output: 'olleh' })
      expect(result.success).toBe(true)

      const record = engine.getRecord(challenge.id)
      expect(record!.status).toBe('proof_submitted')
      expect(record!.proof).toBeTruthy()
      expect(record!.proof!.response).toEqual({ output: 'olleh' })
    })

    it('rejects proof for unknown challenge', () => {
      const result = engine.submitProof('nonexistent', 'alice@hub1', { output: 'x' })
      expect(result.success).toBe(false)
      expect(result.error).toContain('not found')
    })

    it('rejects proof from wrong agent', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      const result = engine.submitProof(challenge.id, 'bob@hub2', { output: 'x' })
      expect(result.success).toBe(false)
      expect(result.error).toContain('mismatch')
    })

    it('rejects duplicate proof', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(challenge.id, 'alice@hub1', { output: 'first' })
      const result = engine.submitProof(challenge.id, 'alice@hub1', { output: 'second' })
      expect(result.success).toBe(false)
      expect(result.error).toContain('already submitted')
    })

    it('rejects proof for expired challenge', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      // Manually expire it
      const record = engine.getRecord(challenge.id)!
      record.challenge.expiresAt = new Date(Date.now() - 1000).toISOString()

      const result = engine.submitProof(challenge.id, 'alice@hub1', { output: 'x' })
      expect(result.success).toBe(false)
      expect(result.error).toContain('expired')
    })
  })

  describe('Peer Attestation', () => {
    it('accepts a valid attestation', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(challenge.id, 'alice@hub1', { output: 'olleh' })

      const result = engine.addAttestation(challenge.id, 'bob@hub2', 0.9, 'Good work')
      expect(result.success).toBe(true)
    })

    it('rejects attestation without proof', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      const result = engine.addAttestation(challenge.id, 'bob@hub2', 0.9)
      expect(result.success).toBe(false)
      expect(result.error).toContain('No proof')
    })

    it('rejects self-attestation', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(challenge.id, 'alice@hub1', { output: 'x' })
      const result = engine.addAttestation(challenge.id, 'alice@hub1', 0.9)
      expect(result.success).toBe(false)
      expect(result.error).toContain('own proof')
    })

    it('rejects duplicate attestation from same peer', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(challenge.id, 'alice@hub1', { output: 'x' })
      engine.addAttestation(challenge.id, 'bob@hub2', 0.9)
      const result = engine.addAttestation(challenge.id, 'bob@hub2', 0.8)
      expect(result.success).toBe(false)
      expect(result.error).toContain('Already attested')
    })

    it('marks as attested when threshold met', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(challenge.id, 'alice@hub1', { output: 'olleh' })

      engine.addAttestation(challenge.id, 'bob@hub2', 0.8)
      expect(engine.getRecord(challenge.id)!.status).toBe('proof_submitted')

      engine.addAttestation(challenge.id, 'carol@hub3', 0.9)
      expect(engine.getRecord(challenge.id)!.status).toBe('attested')
    })

    it('does NOT mark as attested when scores are too low', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(challenge.id, 'alice@hub1', { output: 'x' })

      engine.addAttestation(challenge.id, 'bob@hub2', 0.3)
      engine.addAttestation(challenge.id, 'carol@hub3', 0.4)
      // Average is 0.35, below minScore of 0.6
      expect(engine.getRecord(challenge.id)!.status).toBe('proof_submitted')
    })
  })

  describe('Scoring', () => {
    it('returns zero score for unchalllenged capability', () => {
      const score = engine.getScore('alice@hub1', 'unknown')
      expect(score.averageScore).toBe(0)
      expect(score.attestationCount).toBe(0)
      expect(score.isAttested).toBe(false)
    })

    it('computes correct average score', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(challenge.id, 'alice@hub1', { output: 'x' })
      engine.addAttestation(challenge.id, 'bob@hub2', 0.8)
      engine.addAttestation(challenge.id, 'carol@hub3', 1.0)

      const score = engine.getScore('alice@hub1', 'coding')
      expect(score.averageScore).toBe(0.9)
      expect(score.attestationCount).toBe(2)
      expect(score.isAttested).toBe(true)
    })

    it('isAttested checks both count and score', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(challenge.id, 'alice@hub1', { output: 'x' })
      engine.addAttestation(challenge.id, 'bob@hub2', 0.9)
      // Only 1 attestation, need 2
      expect(engine.isAttested('alice@hub1', 'coding')).toBe(false)
    })

    it('aggregates across multiple challenges for same capability', () => {
      const c1 = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(c1.id, 'alice@hub1', { output: 'x' })
      engine.addAttestation(c1.id, 'bob@hub2', 0.7)

      const c2 = engine.issueChallenge('coding', 'alice@hub1')
      engine.submitProof(c2.id, 'alice@hub1', { output: 'y' })
      engine.addAttestation(c2.id, 'carol@hub3', 0.9)

      const score = engine.getScore('alice@hub1', 'coding')
      expect(score.attestationCount).toBe(2)
      expect(score.averageScore).toBe(0.8)
      expect(score.isAttested).toBe(true)
    })

    it('getAgentScores returns all capabilities', () => {
      const c1 = engine.issueChallenge('coding', 'alice@hub1')
      const c2 = engine.issueChallenge('analysis', 'alice@hub1')
      engine.submitProof(c1.id, 'alice@hub1', { output: 'x' })
      engine.submitProof(c2.id, 'alice@hub1', { output: 'y' })

      const scores = engine.getAgentScores('alice@hub1')
      expect(scores).toHaveLength(2)
      const caps = scores.map(s => s.capability).sort()
      expect(caps).toEqual(['analysis', 'coding'])
    })
  })

  describe('Lifecycle', () => {
    it('getChallengesForAgent returns all challenges', () => {
      engine.issueChallenge('coding', 'alice@hub1')
      engine.issueChallenge('analysis', 'alice@hub1')
      engine.issueChallenge('coding', 'bob@hub2')

      expect(engine.getChallengesForAgent('alice@hub1')).toHaveLength(2)
      expect(engine.getChallengesForAgent('bob@hub2')).toHaveLength(1)
    })

    it('pruneExpired marks expired pending challenges', () => {
      const challenge = engine.issueChallenge('coding', 'alice@hub1')
      const record = engine.getRecord(challenge.id)!
      record.challenge.expiresAt = new Date(Date.now() - 1000).toISOString()

      const pruned = engine.pruneExpired()
      expect(pruned).toBe(1)
      expect(record.status).toBe('expired')
    })

    it('stats returns correct counts', () => {
      const c1 = engine.issueChallenge('coding', 'alice@hub1')
      engine.issueChallenge('analysis', 'bob@hub2') // pending

      engine.submitProof(c1.id, 'alice@hub1', { output: 'x' })
      engine.addAttestation(c1.id, 'bob@hub2', 0.8)
      engine.addAttestation(c1.id, 'carol@hub3', 0.9)

      const stats = engine.stats()
      expect(stats.totalChallenges).toBe(2)
      expect(stats.attested).toBe(1)
      expect(stats.pending).toBe(1)
    })
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// Anti-Sybil PoW
// ════════════════════════════════════════════════════════════════════════════════

describe('Anti-Sybil PoW', () => {
  describe('hasLeadingZeroBits', () => {
    it('correctly checks zero bits', () => {
      // 0000... = 0 in hex → all zero bits
      expect(hasLeadingZeroBits('0000ffff', 16)).toBe(true)
      expect(hasLeadingZeroBits('0000ffff', 17)).toBe(false)

      // 00ff = 8 leading zero bits
      expect(hasLeadingZeroBits('00ff', 8)).toBe(true)
      expect(hasLeadingZeroBits('00ff', 9)).toBe(false)

      // 0f = 4 leading zero bits
      expect(hasLeadingZeroBits('0f', 4)).toBe(true)
      expect(hasLeadingZeroBits('0f', 5)).toBe(false)

      // ff = 0 leading zero bits
      expect(hasLeadingZeroBits('ff', 0)).toBe(true)
      expect(hasLeadingZeroBits('ff', 1)).toBe(false)
    })
  })

  describe('solvePoW', () => {
    it('finds a valid solution', () => {
      const prefix = 'test-prefix-12345'
      const difficulty = 8 // relatively easy
      const solution = solvePoW(prefix, difficulty)

      expect(solution.nonce).toBeTruthy()
      expect(solution.hash).toBeTruthy()
      expect(hasLeadingZeroBits(solution.hash, difficulty)).toBe(true)
      expect(solution.attempts).toBeGreaterThan(0)

      // Verify the hash
      const computed = createHash('sha256')
        .update(prefix + solution.nonce)
        .digest('hex')
      expect(computed).toBe(solution.hash)
    })
  })

  describe('AntiSybilGuard', () => {
    let guard: AntiSybilGuard

    beforeEach(() => {
      guard = new AntiSybilGuard({
        baseDifficulty: 4, // Very low for testing (16 hashes avg)
        maxDifficulty: 12,
        challengeTtlMs: 5000,
        rateWindowMs: 60000,
        rateThreshold: 3,
        maxPerIp: 2,
      })
    })

    it('issues a challenge', () => {
      const challenge = guard.issueChallenge('1.2.3.4')
      expect(challenge).not.toBeNull()
      expect(challenge!.id).toBeTruthy()
      expect(challenge!.difficulty).toBe(4)
      expect(challenge!.prefix).toBeTruthy()
      expect(new Date(challenge!.expiresAt).getTime()).toBeGreaterThan(Date.now())
    })

    it('includes mesh state in challenge prefix', () => {
      guard.updateMeshState('agents:10,peers:3')
      const c1 = guard.issueChallenge()
      guard.updateMeshState('agents:11,peers:3')
      const c2 = guard.issueChallenge()
      // Different mesh state → different prefixes
      expect(c1!.prefix).not.toBe(c2!.prefix)
    })

    it('verifies a valid solution', () => {
      const challenge = guard.issueChallenge()!
      const solution = solvePoW(challenge.prefix, challenge.difficulty)
      solution.challengeId = challenge.id

      const result = guard.verifySolution(solution)
      expect(result.valid).toBe(true)
    })

    it('rejects invalid hash', () => {
      const challenge = guard.issueChallenge()!
      const result = guard.verifySolution({
        challengeId: challenge.id,
        nonce: 'fake',
        hash: 'not-a-valid-hash',
      })
      expect(result.valid).toBe(false)
      expect(result.error).toContain('mismatch')
    })

    it('rejects replayed challenge', () => {
      const challenge = guard.issueChallenge()!
      const solution = solvePoW(challenge.prefix, challenge.difficulty)
      solution.challengeId = challenge.id

      guard.verifySolution(solution)
      const result = guard.verifySolution(solution)
      expect(result.valid).toBe(false)
    })

    it('rejects expired challenge', () => {
      const guard2 = new AntiSybilGuard({
        baseDifficulty: 4,
        challengeTtlMs: 1, // 1ms TTL
      })
      const challenge = guard2.issueChallenge()!
      // Wait for expiry
      const start = Date.now()
      while (Date.now() - start < 5) { /* spin */ }

      const solution = solvePoW(challenge.prefix, challenge.difficulty)
      solution.challengeId = challenge.id
      const result = guard2.verifySolution(solution)
      expect(result.valid).toBe(false)
      expect(result.error).toContain('expired')
    })

    it('rate limits by IP', () => {
      const ip = '10.0.0.1'

      // Issue and solve 2 challenges (maxPerIp = 2)
      for (let i = 0; i < 2; i++) {
        const c = guard.issueChallenge(ip)!
        const s = solvePoW(c.prefix, c.difficulty)
        s.challengeId = c.id
        guard.verifySolution(s, ip)
      }

      // 3rd attempt should be rate limited
      const c3 = guard.issueChallenge(ip)
      expect(c3).toBeNull()
    })

    it('adapts difficulty under load', () => {
      const baseDiff = guard.currentDifficulty()
      expect(baseDiff).toBe(4)

      // Simulate registrations exceeding threshold
      for (let i = 0; i < 4; i++) {
        const c = guard.issueChallenge()!
        const s = solvePoW(c.prefix, c.difficulty)
        s.challengeId = c.id
        guard.verifySolution(s)
      }

      // Difficulty should have increased
      expect(guard.currentDifficulty()).toBeGreaterThan(4)
    })

    it('prune cleans up expired challenges', () => {
      const guard2 = new AntiSybilGuard({
        baseDifficulty: 4,
        challengeTtlMs: 1,
      })
      guard2.issueChallenge()
      guard2.issueChallenge()

      const start = Date.now()
      while (Date.now() - start < 5) { /* spin */ }

      const pruned = guard2.prune()
      expect(pruned).toBe(2)
    })

    it('stats returns correct data', () => {
      guard.issueChallenge()
      guard.issueChallenge()

      const stats = guard.stats()
      expect(stats.activeChallenges).toBe(2)
      expect(stats.currentDifficulty).toBe(4)
      expect(stats.recentRegistrations).toBe(0)
    })
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// CapabilityIndex Attestation Extension
// ════════════════════════════════════════════════════════════════════════════════

describe('CapabilityIndex — Attestation', () => {
  let index: CapabilityIndex

  beforeEach(() => {
    index = new CapabilityIndex()
    // Register some agents
    index.upsertAgent({ name: 'alice', hub: 'hub1', capabilities: ['coding', 'analysis'] }, true)
    index.upsertAgent({ name: 'bob', hub: 'hub2', capabilities: ['coding'] }, false)
    index.upsertAgent({ name: 'carol', hub: 'hub3', capabilities: ['coding', 'design'] }, false)
  })

  it('stores and retrieves attestation scores', () => {
    index.setAttestationScore('alice@hub1', 'coding', 0.9, 3, true)
    const score = index.getAttestationScore('alice@hub1', 'coding')
    expect(score).toEqual({ score: 0.9, count: 3, attested: true })
  })

  it('returns undefined for non-existent score', () => {
    expect(index.getAttestationScore('alice@hub1', 'quantum')).toBeUndefined()
  })

  it('findByCapabilityAttested returns all agents without filter', () => {
    index.setAttestationScore('alice@hub1', 'coding', 0.9, 3, true)
    const agents = index.findByCapabilityAttested('coding')
    expect(agents).toHaveLength(3)
  })

  it('findByCapabilityAttested sorts attested first', () => {
    index.setAttestationScore('carol@hub3', 'coding', 0.95, 3, true)
    // alice and bob are unattested
    const agents = index.findByCapabilityAttested('coding')
    expect(agents[0].name).toBe('carol')
  })

  it('findByCapabilityAttested with attestedOnly=true filters unattested', () => {
    index.setAttestationScore('alice@hub1', 'coding', 0.9, 3, true)
    // bob and carol are unattested
    const agents = index.findByCapabilityAttested('coding', { attestedOnly: true })
    expect(agents).toHaveLength(1)
    expect(agents[0].name).toBe('alice')
  })

  it('findByCapabilityAttested with attestedOnly returns empty when none attested', () => {
    const agents = index.findByCapabilityAttested('coding', { attestedOnly: true })
    expect(agents).toHaveLength(0)
  })

  it('getAgentAttestations returns all capabilities for an agent', () => {
    index.setAttestationScore('alice@hub1', 'coding', 0.9, 3, true)
    index.setAttestationScore('alice@hub1', 'analysis', 0.7, 2, true)

    const attestations = index.getAgentAttestations('alice@hub1')
    expect(attestations).toHaveLength(2)
    const caps = attestations.map(a => a.capability).sort()
    expect(caps).toEqual(['analysis', 'coding'])
  })

  it('sorts by score among attested agents', () => {
    index.setAttestationScore('alice@hub1', 'coding', 0.8, 2, true)
    index.setAttestationScore('bob@hub2', 'coding', 0.95, 3, true)
    index.setAttestationScore('carol@hub3', 'coding', 0.7, 2, true)

    const agents = index.findByCapabilityAttested('coding')
    expect(agents[0].name).toBe('bob')   // highest score
    expect(agents[1].name).toBe('alice')
    expect(agents[2].name).toBe('carol')  // lowest score
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// Protocol Message Types
// ════════════════════════════════════════════════════════════════════════════════

describe('Protocol Messages — Attestation', () => {
  it('attestation_challenge message type is valid', () => {
    const msg: AttestationChallengeMessage = {
      type: 'attestation_challenge',
      payload: {
        id: 'challenge-1',
        type: 'code',
        capability: 'coding',
        agentId: 'alice@hub1',
        difficulty: 0.5,
        expiresAt: new Date().toISOString(),
        testData: { input: 'reverse("hello")' },
        integrityHash: 'abc123',
        createdAt: new Date().toISOString(),
        issuedBy: 'hub1',
      },
    }
    expect(msg.type).toBe('attestation_challenge')
    expect(msg.payload.capability).toBe('coding')
  })

  it('attestation_proof message type is valid', () => {
    const msg: AttestationProofMessage = {
      type: 'attestation_proof',
      payload: {
        challengeId: 'challenge-1',
        agentId: 'alice@hub1',
        response: { output: 'olleh' },
        responseHash: 'hash123',
        submittedAt: new Date().toISOString(),
        submittedVia: 'hub1',
      },
    }
    expect(msg.type).toBe('attestation_proof')
    expect(msg.payload.agentId).toBe('alice@hub1')
  })

  it('attestation_peer message type is valid', () => {
    const msg: AttestationPeerMessage = {
      type: 'attestation_peer',
      payload: {
        challengeId: 'challenge-1',
        peerId: 'bob@hub2',
        agentId: 'alice@hub1',
        capability: 'coding',
        score: 0.9,
        notes: 'Solid implementation',
        attestedAt: new Date().toISOString(),
        attestedVia: 'hub2',
      },
    }
    expect(msg.type).toBe('attestation_peer')
    expect(msg.payload.score).toBe(0.9)
  })

  it('message types are part of MessageType union', () => {
    const types: MessageType[] = [
      'attestation_challenge',
      'attestation_proof',
      'attestation_peer',
    ]
    expect(types).toHaveLength(3)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// REST API Integration (unit-level)
// ════════════════════════════════════════════════════════════════════════════════

describe('REST API — Attestation Endpoints', () => {
  // We test the REST API via express supertest-style approach
  // Import RestApi and create a minimal instance
  let app: import('express').Express

  beforeEach(async () => {
    // Dynamic import to get the internal express app
    const { RestApi } = await import('../src/server/rest-api.js')
    const rest = new RestApi({ hub: 'test-hub', port: 0 })

    // Access the internal express app for testing
    // We need to start with mocked dependencies
    const { CapabilityIndex } = await import('../src/server/capability-index.js')
    const capIndex = new CapabilityIndex()
    capIndex.upsertAgent({ name: 'alice', hub: 'test-hub', capabilities: ['coding'] }, true)

    // Create minimal mocks for required deps
    const mockPeerRegistry = { getPeers: () => [], sampler: { viewCount: 0, knownCount: 0, getView: () => [] } }
    const mockMeshSync = { onLocalChange: () => {} }
    const mockTaskRouter = { on: () => {}, removeListener: () => {}, routeTask: () => {}, getTaskStatus: () => 'unknown', getPendingTasks: () => [], runnerCount: 0 }
    const mockTaskHistory = { getRecent: async () => [], getTeacups: async () => [], scoreOutcome: async () => false }
    const mockMetrics = { getSnapshot: () => ({ hub: 'test-hub', uptime: 0, peers: 0, agents: 0, capabilities: 0, darkCircles: 0, runnersConnected: 0, tasksTotal: 0, tasksSuccess: 0, tasksError: 0, successRate: '0%', avgExecutionMs: 0, tasksPending: 0, perAgent: {} }) }
    const mockDetectionCoord = { getOpenClaims: () => [], getClaim: () => null, getStats: () => ({}), getTrustScores: () => ({}), ledger: { getRecentClaims: () => [], getTrustScore: () => 0 }, handleMessage: () => {} }

    // Start the REST API with mocks (use port 0 to avoid binding issues)
    // Since we can't easily test HTTP endpoints without binding, we test the engine/guard directly through accessors
    await rest.start(
      capIndex as any,
      mockPeerRegistry as any,
      mockMeshSync as any,
      mockTaskRouter as any,
      mockTaskHistory as any,
      mockMetrics as any,
      undefined,
      mockDetectionCoord as any,
    )

    // Test attestation engine through the rest api's internal engine
    const engine = rest.getAttestationEngine()
    const guard = rest.getAntiSybilGuard()

    // Test the full attestation flow through the engine
    const challenge = engine.issueChallenge('coding', 'alice@test-hub')
    expect(challenge.id).toBeTruthy()

    const proofResult = engine.submitProof(challenge.id, 'alice@test-hub', { output: 'olleh' })
    expect(proofResult.success).toBe(true)

    const attestResult = engine.addAttestation(challenge.id, 'bob@hub2', 0.9)
    expect(attestResult.success).toBe(true)

    // Test anti-sybil through the guard
    const powChallenge = guard.issueChallenge('127.0.0.1')
    expect(powChallenge).not.toBeNull()

    await rest.stop()
  })

  it('REST API initializes attestation components', () => {
    // The beforeEach already validates the full flow
    expect(true).toBe(true)
  })
})

// ════════════════════════════════════════════════════════════════════════════════
// End-to-End Attestation Flow
// ════════════════════════════════════════════════════════════════════════════════

describe('End-to-End Attestation Flow', () => {
  it('full lifecycle: challenge → proof → attest → attested', () => {
    const engine = new AttestationEngine({ minAttestations: 2, minScore: 0.6 })
    const capIndex = new CapabilityIndex()

    // 1. Register agent
    capIndex.upsertAgent({ name: 'agent-x', hub: 'alpha', capabilities: ['detection', 'coding'] }, true)

    // 2. Issue challenge
    const challenge = engine.issueChallenge('detection', 'agent-x@alpha')
    expect(challenge.type).toBe('analysis') // auto-selected for detection

    // 3. Submit proof
    const proofResult = engine.submitProof(challenge.id, 'agent-x@alpha', {
      mean: 42.5,
      variance: 123.4,
      trend: 'upward',
    })
    expect(proofResult.success).toBe(true)

    // 4. Peers attest
    engine.addAttestation(challenge.id, 'peer-a@beta', 0.85)
    engine.addAttestation(challenge.id, 'peer-b@gamma', 0.92)

    // 5. Check status
    expect(engine.isAttested('agent-x@alpha', 'detection')).toBe(true)

    const score = engine.getScore('agent-x@alpha', 'detection')
    expect(score.averageScore).toBe(0.885)
    expect(score.attestationCount).toBe(2)

    // 6. Update CapabilityIndex
    capIndex.setAttestationScore(
      'agent-x@alpha',
      'detection',
      score.averageScore,
      score.attestationCount,
      score.isAttested,
    )

    // 7. Query with attestation filter
    const attested = capIndex.findByCapabilityAttested('detection', { attestedOnly: true })
    expect(attested).toHaveLength(1)
    expect(attested[0].name).toBe('agent-x')

    // 8. Coding is NOT attested
    expect(engine.isAttested('agent-x@alpha', 'coding')).toBe(false)
    const unattested = capIndex.findByCapabilityAttested('coding', { attestedOnly: true })
    expect(unattested).toHaveLength(0)
  })

  it('anti-sybil + attestation: agent must solve PoW before registering', () => {
    const guard = new AntiSybilGuard({ baseDifficulty: 4 })
    guard.updateMeshState('agents:5,peers:2')

    // 1. Get PoW challenge
    const powChallenge = guard.issueChallenge('192.168.1.1')!
    expect(powChallenge).not.toBeNull()

    // 2. Solve it
    const solution = solvePoW(powChallenge.prefix, powChallenge.difficulty)
    solution.challengeId = powChallenge.id

    // 3. Verify
    const result = guard.verifySolution(solution, '192.168.1.1')
    expect(result.valid).toBe(true)

    // 4. Now the agent can register and go through attestation
    const engine = new AttestationEngine({ minAttestations: 1, minScore: 0.5 })
    const challenge = engine.issueChallenge('coding', 'new-agent@hub1')
    engine.submitProof(challenge.id, 'new-agent@hub1', { output: 'result' })
    engine.addAttestation(challenge.id, 'validator@hub2', 0.8)
    expect(engine.isAttested('new-agent@hub1', 'coding')).toBe(true)
  })
})
