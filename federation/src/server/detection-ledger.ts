// Detection Ledger — append-only log of detection claims, verifications, and outcomes.
// Lives at the federation layer so all hubs share the same view.

import type { DetectionClaim, DetectionVerify, DetectionChallenge, DetectionOutcome } from '../protocol/messages.js'
import { createHash } from 'crypto'

export interface LedgerEntry {
  claim: DetectionClaim
  verifications: DetectionVerify[]
  challenges: DetectionChallenge[]
  outcome?: DetectionOutcome
}

export class DetectionLedger {
  private entries = new Map<string, LedgerEntry>()
  private logPath: string | null
  private trustScores = new Map<string, { verified: number; false_positive: number; total: number }>()

  constructor(logPath?: string) {
    this.logPath = logPath ?? null
  }

  // ── Write operations ────────────────────────────────────────────────────

  addClaim(claim: DetectionClaim): LedgerEntry {
    const entry: LedgerEntry = {
      claim,
      verifications: [],
      challenges: [],
    }
    this.entries.set(claim.id, entry)
    this.appendLog('claim', claim)
    return entry
  }

  addVerification(verification: DetectionVerify): LedgerEntry | null {
    const entry = this.entries.get(verification.claim_id)
    if (!entry) return null
    entry.verifications.push(verification)
    this.appendLog('verify', verification)

    // Update trust score for the claim's source
    this.updateTrustScore(entry.claim.source, verification.agrees)
    return entry
  }

  addChallenge(challenge: DetectionChallenge): LedgerEntry | null {
    const entry = this.entries.get(challenge.claim_id)
    if (!entry) return null
    entry.challenges.push(challenge)
    this.appendLog('challenge', challenge)
    return entry
  }

  resolveOutcome(outcome: DetectionOutcome): LedgerEntry | null {
    const entry = this.entries.get(outcome.claim_id)
    if (!entry) return null
    entry.outcome = outcome
    this.appendLog('outcome', outcome)

    // Final trust update
    if (entry.claim.source) {
      this.updateTrustFromOutcome(entry.claim.source, outcome.outcome)
    }
    return entry
  }

  // ── Read operations ─────────────────────────────────────────────────────

  getClaim(id: string): LedgerEntry | undefined {
    return this.entries.get(id)
  }

  getClaimsByDomain(domain: string): LedgerEntry[] {
    return [...this.entries.values()].filter(e => e.claim.domain === domain)
  }

  getClaimsBySource(source: string): LedgerEntry[] {
    return [...this.entries.values()].filter(e => e.claim.source === source)
  }

  getOpenClaims(): LedgerEntry[] {
    return [...this.entries.values()].filter(e => !e.outcome)
  }

  getRecentClaims(limit = 20): LedgerEntry[] {
    const sorted = [...this.entries.values()]
      .sort((a, b) => b.claim.created_at.localeCompare(a.claim.created_at))
    return sorted.slice(0, limit)
  }

  getAllEntries(): LedgerEntry[] {
    return [...this.entries.values()]
  }

  getStats(): { total: number; open: number; confirmed: number; false_positive: number; domains: string[] } {
    const entries = [...this.entries.values()]
    return {
      total: entries.length,
      open: entries.filter(e => !e.outcome).length,
      confirmed: entries.filter(e => e.outcome?.outcome === 'confirmed').length,
      false_positive: entries.filter(e => e.outcome?.outcome === 'false_positive').length,
      domains: [...new Set(entries.map(e => e.claim.domain))],
    }
  }

  // ── Trust scoring ───────────────────────────────────────────────────────

  getTrustScore(source: string): number {
    const scores = this.trustScores.get(source)
    if (!scores || scores.total === 0) return 0.5 // Unknown = neutral
    return scores.verified / scores.total
  }

  getTrustScores(): Record<string, { score: number; verified: number; false_positive: number; total: number }> {
    const result: Record<string, { score: number; verified: number; false_positive: number; total: number }> = {}
    for (const [source, scores] of this.trustScores) {
      result[source] = {
        score: scores.total > 0 ? scores.verified / scores.total : 0.5,
        ...scores,
      }
    }
    return result
  }

  private updateTrustScore(source: string, agrees: boolean): void {
    const current = this.trustScores.get(source) ?? { verified: 0, false_positive: 0, total: 0 }
    current.total++
    if (agrees) current.verified++
    else current.false_positive++
    this.trustScores.set(source, current)
  }

  private updateTrustFromOutcome(source: string, outcome: string): void {
    // Outcomes are the strongest signal — weighted more heavily
    const current = this.trustScores.get(source) ?? { verified: 0, false_positive: 0, total: 0 }
    current.total += 3 // Weight outcomes 3x
    if (outcome === 'confirmed') current.verified += 3
    else if (outcome === 'false_positive') current.false_positive += 3
    this.trustScores.set(source, current)
  }

  // ── Persistence ─────────────────────────────────────────────────────────

  private appendLog(type: string, data: unknown): void {
    if (!this.logPath) return
    const entry = JSON.stringify({ type, data, logged_at: new Date().toISOString() }) + '\n'
    // Fire-and-forget append — don't block the event loop
    import('fs').then(fs => fs.appendFile(this.logPath!, entry, () => {}))
  }

  loadFromLog(logPath: string): number {
    // Load existing ledger from JSONL file
    try {
      const fs = require('fs')
      if (!fs.existsSync(logPath)) return 0
      const lines = fs.readFileSync(logPath, 'utf-8').split('\n').filter(Boolean)
      let loaded = 0
      for (const line of lines) {
        try {
          const { type, data } = JSON.parse(line)
          if (type === 'claim') this.addClaim(data as DetectionClaim)
          else if (type === 'verify') this.addVerification(data as DetectionVerify)
          else if (type === 'challenge') this.addChallenge(data as DetectionChallenge)
          else if (type === 'outcome') this.resolveOutcome(data as DetectionOutcome)
          loaded++
        } catch { /* skip malformed lines */ }
      }
      return loaded
    } catch {
      return 0
    }
  }
}
