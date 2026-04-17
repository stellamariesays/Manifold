/**
 * Agent manifest registry.
 *
 * Agent runners POST manifests describing their agents' capabilities in detail:
 * - What tasks they accept (input schema)
 * - What they return (output schema)
 * - Current health, load, and metadata
 *
 * The registration `capabilities: string[]` stays lightweight for mesh sync.
 * Manifests are the richer layer on top — optional, backward compatible.
 */

import type { Request, Response } from 'express'

export interface CapabilityManifest {
  /** Capability ID — matches the string in AgentRegistration.capabilities */
  id: string
  /** Human-readable description */
  description: string
  /** Input schema (JSON Schema format) */
  input?: Record<string, unknown>
  /** Output schema (JSON Schema format) */
  output?: Record<string, unknown>
  /** Examples of task commands this capability handles */
  examples?: string[]
}

export interface AgentManifest {
  /** Agent name */
  name: string
  /** Hub name */
  hub: string
  /** Agent version */
  version?: string
  /** General description */
  description?: string
  /** Detailed capability manifests */
  capabilities: CapabilityManifest[]
  /** Supported task commands with descriptions */
  commands?: Record<string, string>
  /** Current health status */
  health?: {
    status: 'healthy' | 'degraded' | 'down'
    message?: string
    lastCheck?: string
  }
  /** Current load (0-1) */
  load?: number
  /** Arbitrary metadata */
  metadata?: Record<string, unknown>
  /** When this manifest was registered */
  registeredAt: string
  /** When this manifest was last updated */
  updatedAt: string
}

/**
 * Simple trie for fast prefix-based capability lookup.
 * Inserts capability IDs split on '-' tokens so "solar-flare-detection"
 * is findable by "solar", "flare", "detection", "solar-flare", etc.
 */
class CapabilityTrie {
  private root: Map<string, Set<string>> = new Map()

  /**
   * Insert a capability ID. All prefix tokens are indexed.
   * e.g. "solar-flare-detection" indexes:
   *   "solar", "solar-flare", "solar-flare-detection",
   *   "flare", "flare-detection", "detection"
   */
  insert(capId: string, agentKey: string): void {
    const tokens = capId.toLowerCase().split(/[-_]/)
    // Index all contiguous sub-spans of tokens
    for (let i = 0; i < tokens.length; i++) {
      for (let j = i + 1; j <= tokens.length; j++) {
        const prefix = tokens.slice(i, j).join('-')
        if (!this.root.has(prefix)) {
          this.root.set(prefix, new Set())
        }
        this.root.get(prefix)!.add(agentKey)
      }
    }
  }

  /**
   * Remove an agent key from all entries.
   */
  remove(agentKey: string): void {
    for (const set of this.root.values()) {
      set.delete(agentKey)
    }
  }

  /**
   * Find agent keys matching a query prefix.
   * Returns exact match or all keys matching any prefix of the query tokens.
   */
  search(query: string): Set<string> {
    const normalized = query.toLowerCase().replace(/[-_\s]+/g, '-')
    // Exact match
    if (this.root.has(normalized)) {
      return this.root.get(normalized)!
    }
    // Try individual tokens
    const tokens = normalized.split('-')
    const result = new Set<string>()
    for (const tok of tokens) {
      const found = this.root.get(tok)
      if (found) {
        for (const k of found) result.add(k)
      }
    }
    return result
  }

  /** Get number of indexed prefixes */
  get size(): number {
    return this.root.size
  }
}

export class ManifestRegistry {
  private manifests = new Map<string, AgentManifest>() // key: "name@hub"
  private trie = new CapabilityTrie()
  private debug: boolean

  constructor(options?: { debug?: boolean }) {
    this.debug = options?.debug ?? false
  }

  private key(name: string, hub: string): string {
    return `${name}@${hub}`
  }

  /**
   * Register or update an agent manifest.
   * Re-indexes the trie on update.
   */
  register(manifest: Omit<AgentManifest, 'registeredAt' | 'updatedAt'>): AgentManifest {
    const k = this.key(manifest.name, manifest.hub)
    const existing = this.manifests.get(k)
    const now = new Date().toISOString()

    const entry: AgentManifest = {
      ...manifest,
      registeredAt: existing?.registeredAt ?? now,
      updatedAt: now,
    }

    // Remove old trie entries if updating
    if (existing) {
      this.trie.remove(k)
    }

    this.manifests.set(k, entry)

    // Index capabilities in trie
    for (const cap of manifest.capabilities) {
      this.trie.insert(cap.id, k)
    }

    this.log(`Manifest registered: ${k} (${manifest.capabilities.length} capabilities)`)
    return entry
  }

  /**
   * Get manifest for a specific agent.
   */
  get(name: string, hub: string): AgentManifest | undefined {
    return this.manifests.get(this.key(name, hub))
  }

  /**
   * Get all manifests, optionally filtered.
   */
  getAll(options?: { hub?: string; capability?: string }): AgentManifest[] {
    let results = Array.from(this.manifests.values())

    if (options?.hub) {
      results = results.filter(m => m.hub === options.hub)
    }

    if (options?.capability) {
      results = results.filter(m =>
        m.capabilities.some(c => c.id === options.capability)
      )
    }

    return results
  }

  /**
   * Remove a manifest (agent left).
   */
  remove(name: string, hub: string): boolean {
    const k = this.key(name, hub)
    const removed = this.manifests.delete(k)
    if (removed) {
      this.trie.remove(k)
    }
    return removed
  }

  /**
   * Discover agents matching a natural language need.
   *
   * Uses the trie for fast prefix-based capability lookup first,
   * then falls back to full-text search on descriptions and examples.
   * Returns ranked results.
   */
  discover(query: string, options?: { hub?: string; limit?: number }): Array<{
    manifest: AgentManifest
    matchedCapabilities: CapabilityManifest[]
    score: number
  }> {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
    const results: Array<{
      manifest: AgentManifest
      matchedCapabilities: CapabilityManifest[]
      score: number
    }> = []

    // Phase 1: Trie lookup for each term — fast prefix matching
    const trieCandidates = new Map<string, number>() // agentKey → trieScore
    for (const term of terms) {
      const matched = this.trie.search(term)
      for (const agentKey of matched) {
        trieCandidates.set(agentKey, (trieCandidates.get(agentKey) ?? 0) + 1)
      }
    }

    // Phase 2: Full-text scan on descriptions/examples for agents not found via trie
    const candidates = new Set<string>()
    for (const k of trieCandidates.keys()) candidates.add(k)

    for (const manifest of this.getAll({ hub: options?.hub })) {
      const k = this.key(manifest.name, manifest.hub)
      if (candidates.has(k)) continue // already scored by trie

      const agentText = `${manifest.name} ${manifest.description ?? ''}`.toLowerCase()
      const agentMatch = terms.filter(t => agentText.includes(t)).length
      if (agentMatch > 0) {
        candidates.add(k)
        // These will be scored in the loop below via full-text
      }
    }

    // Score all candidates
    for (const agentKey of candidates) {
      const manifest = this.manifests.get(agentKey)
      if (!manifest) continue
      if (options?.hub && manifest.hub !== options.hub) continue

      const matched: CapabilityManifest[] = []
      let score = 0

      // Trie bonus: matches from prefix lookup are stronger signals
      const trieScore = trieCandidates.get(agentKey) ?? 0
      score += trieScore * 2

      // Full-text match on capabilities
      for (const cap of manifest.capabilities) {
        const text = `${cap.id} ${cap.description} ${(cap.examples ?? []).join(' ')}`.toLowerCase()
        const matchCount = terms.filter(t => text.includes(t)).length
        if (matchCount > 0) {
          matched.push(cap)
          score += matchCount
        }
      }

      // Agent name/description match
      const agentText = `${manifest.name} ${manifest.description ?? ''}`.toLowerCase()
      const agentMatch = terms.filter(t => agentText.includes(t)).length
      if (agentMatch > 0) {
        score += agentMatch * 0.5
      }

      if (matched.length > 0 || score > 0) {
        results.push({ manifest, matchedCapabilities: matched, score })
      }
    }

    results.sort((a, b) => b.score - a.score)
    return results.slice(0, options?.limit ?? 10)
  }

  /**
   * Stats about registered manifests.
   */
  stats(): {
    total: number
    byHub: Record<string, number>
    totalCapabilities: number
    avgCapabilitiesPerAgent: number
    medianCapabilitiesPerAgent: number
    maxCapabilities: number
    minCapabilities: number
    trieSize: number
    healthSummary: Record<string, number>
  } {
    const byHub: Record<string, number> = {}
    let totalCaps = 0
    const capCounts: number[] = []
    const healthCounts: Record<string, number> = {}

    for (const m of this.manifests.values()) {
      byHub[m.hub] = (byHub[m.hub] ?? 0) + 1
      capCounts.push(m.capabilities.length)
      totalCaps += m.capabilities.length
      const status = m.health?.status ?? 'unknown'
      healthCounts[status] = (healthCounts[status] ?? 0) + 1
    }

    capCounts.sort((a, b) => a - b)
    const total = this.manifests.size

    return {
      total,
      byHub,
      totalCapabilities: totalCaps,
      avgCapabilitiesPerAgent: total > 0 ? Math.round((totalCaps / total) * 100) / 100 : 0,
      medianCapabilitiesPerAgent: capCounts.length > 0 ? capCounts[Math.floor(capCounts.length / 2)] : 0,
      maxCapabilities: capCounts.length > 0 ? capCounts[capCounts.length - 1] : 0,
      minCapabilities: capCounts.length > 0 ? capCounts[0] : 0,
      trieSize: this.trie.size,
      healthSummary: healthCounts,
    }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[ManifestRegistry] ${msg}`)
  }
}
