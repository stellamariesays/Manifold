/**
 * Anti-Sybil Registration — PoW-based agent registration to prevent spam.
 *
 * New agents must solve a SHA-256 hash challenge before registering.
 * Difficulty adapts based on recent registration rate. Challenge includes
 * mesh state hash to prevent pre-computation.
 */

import { createHash, randomBytes } from 'crypto'

// ── Types ───────────────────────────────────────────────────────────────────────

export interface PoWChallenge {
  /** Unique challenge ID */
  id: string
  /** Required number of leading zero bits in the hash */
  difficulty: number
  /** Challenge prefix (includes mesh state hash) */
  prefix: string
  /** Expiry timestamp (ISO) */
  expiresAt: string
  /** Timestamp when challenge was created */
  createdAt: string
}

export interface PoWSolution {
  /** Challenge ID being solved */
  challengeId: string
  /** Nonce that produces a valid hash */
  nonce: string
  /** The resulting hash (hex) — server will verify */
  hash: string
}

export interface AntiSybilConfig {
  /** Base difficulty (leading zero bits). Default 16 (≈65K hashes). */
  baseDifficulty?: number
  /** Max difficulty (leading zero bits). Default 24. */
  maxDifficulty?: number
  /** Challenge TTL in ms. Default 60000 (1 min). */
  challengeTtlMs?: number
  /** Registration rate window in ms for adaptive difficulty. Default 60000. */
  rateWindowMs?: number
  /** Registrations per window that triggers difficulty increase. Default 5. */
  rateThreshold?: number
  /** Max registrations per IP per window. Default 3. */
  maxPerIp?: number
}

// ── Implementation ──────────────────────────────────────────────────────────────

export class AntiSybilGuard {
  private readonly baseDifficulty: number
  private readonly maxDifficulty: number
  private readonly challengeTtlMs: number
  private readonly rateWindowMs: number
  private readonly rateThreshold: number
  private readonly maxPerIp: number

  /** Active challenges: id → PoWChallenge */
  private challenges: Map<string, PoWChallenge> = new Map()

  /** Recent registration timestamps for adaptive difficulty */
  private recentRegistrations: number[] = []

  /** IP → recent registration timestamps for rate limiting */
  private ipRegistrations: Map<string, number[]> = new Map()

  /** Used challenge IDs (prevent replay) */
  private usedChallenges: Set<string> = new Set()

  /** Current mesh state hash (updated externally) */
  private meshStateHash = ''

  constructor(config: AntiSybilConfig = {}) {
    this.baseDifficulty = config.baseDifficulty ?? 16
    this.maxDifficulty = config.maxDifficulty ?? 24
    this.challengeTtlMs = config.challengeTtlMs ?? 60_000
    this.rateWindowMs = config.rateWindowMs ?? 60_000
    this.rateThreshold = config.rateThreshold ?? 5
    this.maxPerIp = config.maxPerIp ?? 3
  }

  /**
   * Update the mesh state hash (call on mesh changes).
   */
  updateMeshState(stateData: string): void {
    this.meshStateHash = createHash('sha256').update(stateData).digest('hex')
  }

  /**
   * Issue a PoW challenge for registration.
   * Returns null if IP is rate-limited.
   */
  issueChallenge(ip?: string): PoWChallenge | null {
    // Check IP rate limit
    if (ip && this.isIpRateLimited(ip)) {
      return null
    }

    const difficulty = this.currentDifficulty()
    const id = randomBytes(16).toString('hex')
    const now = new Date()

    // Build prefix with mesh state hash to prevent pre-computation
    const prefix = createHash('sha256')
      .update(`${id}:${this.meshStateHash}:${now.toISOString()}`)
      .digest('hex')

    const challenge: PoWChallenge = {
      id,
      difficulty,
      prefix,
      expiresAt: new Date(now.getTime() + this.challengeTtlMs).toISOString(),
      createdAt: now.toISOString(),
    }

    this.challenges.set(id, challenge)
    return challenge
  }

  /**
   * Verify a PoW solution.
   * Returns { valid, error? }
   */
  verifySolution(
    solution: PoWSolution,
    ip?: string,
  ): { valid: boolean; error?: string } {
    const challenge = this.challenges.get(solution.challengeId)
    if (!challenge) {
      return { valid: false, error: 'Challenge not found or already used' }
    }

    // Check expiry
    if (new Date(challenge.expiresAt).getTime() < Date.now()) {
      this.challenges.delete(solution.challengeId)
      return { valid: false, error: 'Challenge has expired' }
    }

    // Check replay
    if (this.usedChallenges.has(solution.challengeId)) {
      return { valid: false, error: 'Challenge already used' }
    }

    // Verify hash: SHA-256(prefix + nonce) must have `difficulty` leading zero bits
    const computedHash = createHash('sha256')
      .update(challenge.prefix + solution.nonce)
      .digest('hex')

    if (computedHash !== solution.hash) {
      return { valid: false, error: 'Hash mismatch' }
    }

    if (!hasLeadingZeroBits(computedHash, challenge.difficulty)) {
      return { valid: false, error: `Hash does not meet difficulty requirement (${challenge.difficulty} leading zero bits)` }
    }

    // Mark challenge as used
    this.usedChallenges.add(solution.challengeId)
    this.challenges.delete(solution.challengeId)

    // Record registration for rate tracking
    const now = Date.now()
    this.recentRegistrations.push(now)
    if (ip) {
      const ipRegs = this.ipRegistrations.get(ip) ?? []
      ipRegs.push(now)
      this.ipRegistrations.set(ip, ipRegs)
    }

    return { valid: true }
  }

  /**
   * Get current adaptive difficulty.
   */
  currentDifficulty(): number {
    this.pruneRateWindow()
    const recentCount = this.recentRegistrations.length

    if (recentCount >= this.rateThreshold) {
      // Scale difficulty up based on how much we exceed the threshold
      const excess = recentCount / this.rateThreshold
      const extraBits = Math.floor(Math.log2(excess) * 4)
      return Math.min(this.baseDifficulty + extraBits, this.maxDifficulty)
    }

    return this.baseDifficulty
  }

  /**
   * Check if an IP is rate-limited.
   */
  isIpRateLimited(ip: string): boolean {
    this.pruneIpWindow(ip)
    const regs = this.ipRegistrations.get(ip) ?? []
    return regs.length >= this.maxPerIp
  }

  /**
   * Clean up expired challenges and old rate data.
   */
  prune(): number {
    let pruned = 0
    const now = Date.now()

    for (const [id, challenge] of this.challenges) {
      if (new Date(challenge.expiresAt).getTime() < now) {
        this.challenges.delete(id)
        pruned++
      }
    }

    this.pruneRateWindow()

    // Clean up old used challenges (keep last 1000)
    if (this.usedChallenges.size > 1000) {
      const arr = Array.from(this.usedChallenges)
      this.usedChallenges = new Set(arr.slice(-500))
    }

    return pruned
  }

  /**
   * Get stats.
   */
  stats(): {
    activeChallenges: number
    recentRegistrations: number
    currentDifficulty: number
    usedChallenges: number
  } {
    this.pruneRateWindow()
    return {
      activeChallenges: this.challenges.size,
      recentRegistrations: this.recentRegistrations.length,
      currentDifficulty: this.currentDifficulty(),
      usedChallenges: this.usedChallenges.size,
    }
  }

  // ── Private ───────────────────────────────────────────────────────────────

  private pruneRateWindow(): void {
    const cutoff = Date.now() - this.rateWindowMs
    this.recentRegistrations = this.recentRegistrations.filter(t => t > cutoff)
  }

  private pruneIpWindow(ip: string): void {
    const cutoff = Date.now() - this.rateWindowMs
    const regs = this.ipRegistrations.get(ip)
    if (regs) {
      const filtered = regs.filter(t => t > cutoff)
      if (filtered.length === 0) {
        this.ipRegistrations.delete(ip)
      } else {
        this.ipRegistrations.set(ip, filtered)
      }
    }
  }
}

// ── PoW Helpers ─────────────────────────────────────────────────────────────────

/**
 * Check if a hex hash has at least `bits` leading zero bits.
 */
export function hasLeadingZeroBits(hexHash: string, bits: number): boolean {
  const fullBytes = Math.floor(bits / 8)
  const remainingBits = bits % 8

  for (let i = 0; i < fullBytes; i++) {
    const byte = parseInt(hexHash.substring(i * 2, i * 2 + 2), 16)
    if (byte !== 0) return false
  }

  if (remainingBits > 0) {
    const byte = parseInt(hexHash.substring(fullBytes * 2, fullBytes * 2 + 2), 16)
    const mask = 0xFF << (8 - remainingBits)
    if ((byte & mask) !== 0) return false
  }

  return true
}

/**
 * Solve a PoW challenge (for testing / client use).
 * Finds a nonce such that SHA-256(prefix + nonce) has the required leading zeros.
 */
export function solvePoW(prefix: string, difficulty: number): PoWSolution & { attempts: number } {
  let nonce = 0
  while (true) {
    const nonceStr = nonce.toString(16)
    const hash = createHash('sha256')
      .update(prefix + nonceStr)
      .digest('hex')

    if (hasLeadingZeroBits(hash, difficulty)) {
      return {
        challengeId: '', // caller fills in
        nonce: nonceStr,
        hash,
        attempts: nonce + 1,
      }
    }
    nonce++
  }
}
