/**
 * Attestation Challenge Types — domain-specific challenge generators.
 *
 * Each challenge proves an agent can actually perform a claimed capability.
 * Challenges have difficulty, expiry, test data, and an integrity hash so
 * they can't be tampered with after issuance.
 */

import { createHash, randomBytes } from 'crypto'

// ── Types ───────────────────────────────────────────────────────────────────────

export type ChallengeType = 'generic' | 'code' | 'analysis'

export interface Challenge {
  /** Unique challenge ID */
  id: string
  /** Type of challenge */
  type: ChallengeType
  /** Capability being challenged */
  capability: string
  /** Agent being challenged (name@hub) */
  agentId: string
  /** Difficulty 0.0–1.0 */
  difficulty: number
  /** Expiry timestamp (ISO) */
  expiresAt: string
  /** Challenge-specific test data */
  testData: Record<string, unknown>
  /** SHA-256 integrity hash of (id + type + capability + agentId + testData) */
  integrityHash: string
  /** Timestamp when challenge was created */
  createdAt: string
}

export interface ChallengeGenerator {
  type: ChallengeType
  generate(capability: string, agentId: string, difficulty: number, expiryMs?: number): Challenge
}

// ── Helpers ─────────────────────────────────────────────────────────────────────

function makeId(): string {
  return randomBytes(16).toString('hex')
}

function computeIntegrityHash(
  id: string,
  type: string,
  capability: string,
  agentId: string,
  testData: Record<string, unknown>,
): string {
  const payload = JSON.stringify({ id, type, capability, agentId, testData })
  return createHash('sha256').update(payload).digest('hex')
}

function makeChallenge(
  type: ChallengeType,
  capability: string,
  agentId: string,
  difficulty: number,
  testData: Record<string, unknown>,
  expiryMs: number,
): Challenge {
  const id = makeId()
  const now = new Date()
  const expiresAt = new Date(now.getTime() + expiryMs).toISOString()

  return {
    id,
    type,
    capability,
    agentId,
    difficulty: Math.max(0, Math.min(1, difficulty)),
    expiresAt,
    testData,
    integrityHash: computeIntegrityHash(id, type, capability, agentId, testData),
    createdAt: now.toISOString(),
  }
}

/** Verify a challenge's integrity hash hasn't been tampered with */
export function verifyIntegrity(challenge: Challenge): boolean {
  const expected = computeIntegrityHash(
    challenge.id,
    challenge.type,
    challenge.capability,
    challenge.agentId,
    challenge.testData,
  )
  return expected === challenge.integrityHash
}

/** Check if a challenge has expired */
export function isExpired(challenge: Challenge): boolean {
  return new Date(challenge.expiresAt).getTime() < Date.now()
}

// ── Generic Challenge ───────────────────────────────────────────────────────────

/**
 * GenericChallenge: For unknown/custom capabilities.
 * Peers design ad-hoc challenges with arbitrary test data.
 * The challenge provides a prompt and expects a freeform response
 * that peers then evaluate.
 */
export class GenericChallenge implements ChallengeGenerator {
  readonly type: ChallengeType = 'generic'

  generate(
    capability: string,
    agentId: string,
    difficulty: number,
    expiryMs = 300_000, // 5 minutes default
  ): Challenge {
    const nonce = randomBytes(8).toString('hex')
    const testData: Record<string, unknown> = {
      prompt: `Demonstrate capability "${capability}" by responding to this challenge.`,
      nonce,
      requiredFields: ['response', 'evidence'],
      minResponseLength: Math.floor(50 + difficulty * 450), // 50–500 chars
    }
    return makeChallenge('generic', capability, agentId, difficulty, testData, expiryMs)
  }
}

// ── Code Challenge ──────────────────────────────────────────────────────────────

/** Pre-defined code problems by difficulty tier */
const CODE_PROBLEMS = [
  // Easy (difficulty 0.0–0.3)
  {
    input: 'reverse("hello")',
    expectedOutput: 'olleh',
    description: 'Reverse a string',
  },
  {
    input: 'fibonacci(10)',
    expectedOutput: '55',
    description: 'Compute the 10th Fibonacci number',
  },
  // Medium (difficulty 0.3–0.7)
  {
    input: 'isPalindrome("racecar")',
    expectedOutput: 'true',
    description: 'Check if a string is a palindrome',
  },
  {
    input: 'primeFactors(84)',
    expectedOutput: '[2, 2, 3, 7]',
    description: 'Find prime factors of a number',
  },
  // Hard (difficulty 0.7–1.0)
  {
    input: 'longestCommonSubsequence("ABCBDAB", "BDCAB")',
    expectedOutput: 'BCAB',
    description: 'Find the longest common subsequence of two strings',
  },
  {
    input: 'balancedParens("((()))()")',
    expectedOutput: 'true',
    description: 'Check if parentheses are balanced',
  },
]

/**
 * CodeChallenge: For coding capabilities.
 * Given code input, agent must produce correct output.
 */
export class CodeChallenge implements ChallengeGenerator {
  readonly type: ChallengeType = 'code'

  generate(
    capability: string,
    agentId: string,
    difficulty: number,
    expiryMs = 600_000, // 10 minutes default
  ): Challenge {
    // Select problem based on difficulty
    const tier = Math.min(Math.floor(difficulty * CODE_PROBLEMS.length), CODE_PROBLEMS.length - 1)
    const problem = CODE_PROBLEMS[tier]!

    const testData: Record<string, unknown> = {
      description: problem.description,
      input: problem.input,
      expectedOutput: problem.expectedOutput,
      nonce: randomBytes(8).toString('hex'),
    }

    return makeChallenge('code', capability, agentId, difficulty, testData, expiryMs)
  }
}

// ── Analysis Challenge ──────────────────────────────────────────────────────────

/**
 * AnalysisChallenge: For analytical capabilities.
 * Given data, agent must produce analysis with verifiable metrics.
 */
export class AnalysisChallenge implements ChallengeGenerator {
  readonly type: ChallengeType = 'analysis'

  generate(
    capability: string,
    agentId: string,
    difficulty: number,
    expiryMs = 600_000, // 10 minutes
  ): Challenge {
    // Generate synthetic dataset for analysis
    const dataPoints = Math.floor(5 + difficulty * 45) // 5–50 points
    const dataset: number[] = []
    for (let i = 0; i < dataPoints; i++) {
      dataset.push(Math.round((Math.sin(i * 0.5) * 100 + Math.random() * 20) * 100) / 100)
    }

    const mean = dataset.reduce((a, b) => a + b, 0) / dataset.length
    const variance = dataset.reduce((a, b) => a + (b - mean) ** 2, 0) / dataset.length

    const testData: Record<string, unknown> = {
      dataset,
      requiredMetrics: ['mean', 'variance', 'trend'],
      expectedMean: Math.round(mean * 100) / 100,
      expectedVariance: Math.round(variance * 100) / 100,
      tolerance: Math.max(0.01, 0.1 - difficulty * 0.09), // tighter tolerance at higher difficulty
      nonce: randomBytes(8).toString('hex'),
    }

    return makeChallenge('analysis', capability, agentId, difficulty, testData, expiryMs)
  }
}

// ── Registry ────────────────────────────────────────────────────────────────────

/** Map capability patterns to challenge types */
const CAPABILITY_PATTERNS: Array<{ pattern: RegExp; type: ChallengeType }> = [
  { pattern: /cod(?:e|ing)|program|develop|script|compile/i, type: 'code' },
  { pattern: /analy|data|detect|monitor|stat|metric/i, type: 'analysis' },
]

const GENERATORS: Record<ChallengeType, ChallengeGenerator> = {
  generic: new GenericChallenge(),
  code: new CodeChallenge(),
  analysis: new AnalysisChallenge(),
}

/** Auto-select the best challenge type for a capability */
export function selectChallengeType(capability: string): ChallengeType {
  for (const { pattern, type } of CAPABILITY_PATTERNS) {
    if (pattern.test(capability)) return type
  }
  return 'generic'
}

/** Generate a challenge for a capability */
export function generateChallenge(
  capability: string,
  agentId: string,
  difficulty = 0.5,
  type?: ChallengeType,
  expiryMs?: number,
): Challenge {
  const challengeType = type ?? selectChallengeType(capability)
  return GENERATORS[challengeType].generate(capability, agentId, difficulty, expiryMs)
}
