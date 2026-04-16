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

export class ManifestRegistry {
  private manifests = new Map<string, AgentManifest>() // key: "name@hub"
  private debug: boolean

  constructor(options?: { debug?: boolean }) {
    this.debug = options?.debug ?? false
  }

  private key(name: string, hub: string): string {
    return `${name}@${hub}`
  }

  /**
   * Register or update an agent manifest.
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

    this.manifests.set(k, entry)
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
    return this.manifests.delete(this.key(name, hub))
  }

  /**
   * Discover agents matching a natural language need.
   * Returns ranked results based on capability keyword matching.
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

    for (const manifest of this.getAll({ hub: options?.hub })) {
      const matched: CapabilityManifest[] = []
      let score = 0

      for (const cap of manifest.capabilities) {
        const text = `${cap.id} ${cap.description} ${(cap.examples ?? []).join(' ')}`.toLowerCase()
        const matchCount = terms.filter(t => text.includes(t)).length
        if (matchCount > 0) {
          matched.push(cap)
          score += matchCount
        }
      }

      // Also match on agent name and description
      const agentText = `${manifest.name} ${manifest.description ?? ''}`.toLowerCase()
      const agentMatch = terms.filter(t => agentText.includes(t)).length
      if (agentMatch > 0) {
        score += agentMatch * 0.5
      }

      if (matched.length > 0 || agentMatch > 0) {
        results.push({ manifest, matchedCapabilities: matched, score })
      }
    }

    results.sort((a, b) => b.score - a.score)
    return results.slice(0, options?.limit ?? 10)
  }

  /**
   * Stats about registered manifests.
   */
  stats(): { total: number; byHub: Record<string, number>; totalCapabilities: number } {
    const byHub: Record<string, number> = {}
    let totalCaps = 0

    for (const m of this.manifests.values()) {
      byHub[m.hub] = (byHub[m.hub] ?? 0) + 1
      totalCaps += m.capabilities.length
    }

    return { total: this.manifests.size, byHub, totalCapabilities: totalCaps }
  }

  private log(msg: string): void {
    if (this.debug) console.log(`[ManifestRegistry] ${msg}`)
  }
}
